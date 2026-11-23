"""Top-level Strix scan runner."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agents import RunConfig
from agents.exceptions import MaxTurnsExceeded
from agents.sandbox import SandboxRunConfig
from openai import RateLimitError

from strix.agents.factory import build_strix_agent, make_child_factory
from strix.agents.prompt import render_scope_prompt, render_system_prompt
from strix.config import codex, load_settings
from strix.config.models import (
    StrixProvider,
    configure_sdk_api_route,
    configure_sdk_model_defaults,
    model_supports_images,
    supports_strict_tool_schemas,
    uses_chat_completions_tool_schema,
)
from strix.config.settings import DEFAULT_MAX_TURNS
from strix.core.agents import AgentCoordinator, BudgetPolicy
from strix.core.execution import (
    respawn_subagents,
    run_agent_loop,
)
from strix.core.execution import (
    spawn_child_agent as start_child_agent,
)
from strix.core.hooks import (
    SUBAGENT_TURN_LIMITS_KEY,
    BudgetExceededError,
    ReportUsageHooks,
    recomputed_budget_flags,
)
from strix.core.inputs import (
    build_root_task,
    build_scan_targets,
    build_scope_context,
    make_model_settings,
)
from strix.core.paths import run_dir_for, runtime_state_dir
from strix.core.sessions import open_agent_session
from strix.report.state import (
    ReportState,
    get_global_report_state,
    set_global_gap_run,
    set_global_report_state,
)
from strix.runtime import session_manager
from strix.telemetry import set_scan_phase
from strix.telemetry.logging import set_scan_id, setup_scan_logging
from strix.tools.finish.tool import finish_scan
from strix.tools.output_store import (
    WORKSPACE_SPILL_DIR,
    configure_spill_writer,
)
from strix.tools.reporting.tool import create_vulnerability_report


if TYPE_CHECKING:
    from agents.memory import SQLiteSession
    from agents.result import RunResultBase
    from agents.tool import Tool

    from strix.runtime.status import StatusSink
    from strix.tools.mcp import (
        McpConnectionRequest,
        McpRegistry,
    )


logger = logging.getLogger(__name__)

_MCP_PROMPT_WARMUP_TIMEOUT_SECONDS = 30.0

StreamEventSink = Callable[[str, Any], None]

# Receives the run's MCP connection roster as a list of non-secret status dicts
# ({"name", "provider", "tool_count", "dead", "state"}), once when the connections
# are registered and again on lifecycle transitions. An interface
# can persist it, render it, or forward it on as connection status. Kept as a
# snapshot of the whole roster (not a per-
# connection delta) so every call carries a consistent, current picture.
McpStatusSink = Callable[[list[dict[str, Any]]], None]


def _mcp_roster_payload(registry: McpRegistry) -> list[dict[str, Any]]:
    """The run's MCP roster as non-secret lifecycle status dicts."""
    return [
        {
            "name": status.name,
            "provider": status.provider,
            "tool_count": status.tool_count,
            "dead": status.dead,
            "state": status.state,
        }
        for status in registry.statuses()
    ]


def _mcp_prompt_roster(registry: McpRegistry) -> list[dict[str, Any]]:
    """The MCP roster rendered in agent prompts, with only verified counts."""
    return [
        {
            "name": summary.name,
            "purpose": summary.purpose,
            "tool_count": summary.tool_count if summary.state == "catalog_ready" else None,
            "state": summary.state,
        }
        for summary in registry.summaries()
    ]


def _record_mcp_connections(connection_names: list[str]) -> None:
    """Record which MCP servers this run configured, for the interfaces.

    A server's tools are offered to the model under a name built from the
    connection name and the tool's own name, which cannot be split back apart, so
    the TUI and the run viewer need the names to match a tool call against before
    they can show which server it went out to. Kept on the run record because the
    viewer reads a finished run from disk.
    """
    report_state = get_global_report_state()
    if report_state is None:
        return
    report_state.record_mcp_connections(connection_names)


def _note_exit_reason(reason: str) -> None:
    """Record why the scan stopped so the end-of-scan beacon reports it."""
    report_state = get_global_report_state()
    if report_state is not None and report_state.scan_ended_exit_reason is None:
        report_state.scan_ended_exit_reason = reason


def _persist_mcp_status(roster: list[dict[str, Any]]) -> None:
    """Write the run's non-secret MCP connection status roster to run.json.

    The viewer rebuilds its display by re-reading the run's files from disk, so
    it cannot see the in-memory ``mcp_status_sink`` the TUI consumes. Persisting
    the same non-secret roster (name / provider / tool_count / dead) gives the
    viewer a source it can poll. Runs regardless of whether an interface sink is
    attached, so the standalone / non-TUI CLI path records health too.
    """
    report_state = get_global_report_state()
    if report_state is None:
        return
    report_state.record_mcp_connection_status(roster)


def _merge_root_prompt_context(
    scope_context: dict[str, Any],
    extra_system_prompt_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if not extra_system_prompt_context:
        return scope_context
    reserved_keys = scope_context.keys() & extra_system_prompt_context.keys()
    if reserved_keys:
        raise ValueError(
            "extra_system_prompt_context cannot override built-in scope keys: "
            f"{sorted(reserved_keys)}",
        )
    return {**scope_context, **extra_system_prompt_context}


def _compose_root_instructions_override(
    root_instructions_override: str | None,
    *,
    skills: list[str],
    scan_mode: str,
    is_whitebox: bool,
    is_diff_scoped: bool,
    interactive: bool,
    parallel_tool_calls: bool,
    system_prompt_context: dict[str, Any],
    supports_images: bool,
    report_tool: str,
    coverage_tools: bool,
    replace_scan_prompt: bool = False,
) -> str | None:
    if root_instructions_override is None:
        return None
    if replace_scan_prompt:
        return f"{root_instructions_override}\n\n{render_scope_prompt(system_prompt_context)}"

    base_instructions = render_system_prompt(
        skills=skills,
        scan_mode=scan_mode,
        is_whitebox=is_whitebox,
        is_root=True,
        is_diff_scoped=is_diff_scoped,
        interactive=interactive,
        parallel_tool_calls=parallel_tool_calls,
        system_prompt_context=system_prompt_context,
        include_scope=False,
        supports_images=supports_images,
        report_tool=report_tool,
        coverage_tools=coverage_tools,
    )
    return (
        f"{base_instructions}\n\n"
        "<root_scan_instructions_override>\n"
        "The following root scan instructions describe the task configuration.\n\n"
        f"{root_instructions_override}\n"
        "</root_scan_instructions_override>\n\n"
        f"{render_scope_prompt(system_prompt_context)}"
    )


# ---------------------------------------------------------------------------
# Automated GAP-1 candidate investigation
# ---------------------------------------------------------------------------

_PROBE_HEADERS = {
    "User-Agent": "AI-VAPT/1.0 (autonomous authorized assessment)",
    "Accept": "*/*",
    "Connection": "close",
}


def _probe_target_url(target_value: str) -> str:
    """Return a probeable base URL from a target value (strip fragment/query)."""
    try:
        parsed = urllib.parse.urlsplit(target_value)
        if parsed.scheme and parsed.netloc:
            return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    except Exception:
        pass
    return str(target_value).rstrip("/")


async def _http_probe(url: str) -> dict[str, Any]:
    """Make one real HTTP GET request against ``url`` with scope and bounded memory enforcement."""
    from strix.core.safety.http_transport import execute_scoped_request

    def _fetch() -> dict[str, Any]:
        return execute_scoped_request(
            url=url,
            method="GET",
            headers=dict(_PROBE_HEADERS),
            timeout=10,
        )

    return await asyncio.to_thread(_fetch)


def _analyze_probe(
    candidate: Any,
    result: dict[str, Any],
    probe_url: str,
) -> tuple[str, str, dict[str, str] | None]:
    """Honestly analyze one live probe result.

    Returns ``(outcome, detail, evidence)`` where outcome is one of
    ``positive``, ``negative``, ``needs_follow_up``, or ``inconclusive``.
    Evidence is only populated for ``positive`` outcomes and carries the
    reproducible request/response needed to satisfy the verification contract.
    """
    status = int(result.get("status", 0) or 0)
    headers = result.get("headers", {}) or {}
    body = result.get("body", "") or ""
    error = result.get("error")
    body_lower = body.lower()

    # 1. Unreachable -> inconclusive (not a negative; the surface may exist).
    if status == 0 or error:
        return (
            "inconclusive",
            f"Could not reach {candidate.endpoint}: {error or 'connection error'}",
            None,
        )

    # 2. Not found -> negative for this surface.
    if status == 404:
        return (
            "negative",
            f"{candidate.endpoint} returned HTTP 404 (not found)",
            None,
        )

    # 3. Successful response -> examine content.
    if 200 <= status < 300:
        # C01 Fix: Substring matches on plain GET responses are preliminary observations
        # that require active, differential follow-up — NEVER confirmed vulnerabilities.
        sql_signatures = (
            "you have an error in your sql",
            "sql syntax",
            "mysql",
            "postgresql",
            "ora-",
            "sqlite",
            "microsoft ole db provider",
            "odbc driver",
        )
        for sig in sql_signatures:
            if sig in body_lower:
                host = urllib.parse.urlparse(probe_url).netloc
                evidence = {
                    "request": f"GET {candidate.endpoint} HTTP/1.1\nHost: {host}",
                    "response": f"HTTP/1.1 {status}\n{body[:800]}",
                }
                return (
                    "needs_follow_up",
                    f"Potential SQL error signature observed at {candidate.endpoint}: {sig} (requires active differential payload verification)",
                    evidence,
                )

        # Reflected script marker (basic DOM/XSS signal from a plain GET).
        if "<script" in body_lower and "alert" in body_lower:
            evidence = {
                "request": f"GET {candidate.endpoint} HTTP/1.1",
                "response": f"HTTP/1.1 {status}\n{body[:800]}",
            }
            return (
                "needs_follow_up",
                f"Reflected script text observed in response body at {candidate.endpoint} (requires active DOM execution verification)",
                evidence,
            )

        # Missing hardening headers -> observation (needs follow-up), not a
        # confirmed vulnerability by itself.
        missing = [
            h
            for h in ("content-security-policy", "x-frame-options", "x-content-type-options")
            if h not in headers
        ]
        if missing:
            return (
                "needs_follow_up",
                f"{candidate.endpoint} reachable (HTTP {status}); missing headers: "
                f"{', '.join(missing)}",
                None,
            )
        return (
            "needs_follow_up",
            f"{candidate.endpoint} reachable (HTTP {status}, {len(body)} bytes)",
            None,
        )

    # 4. Other status codes -> inconclusive.
    return (
        "inconclusive",
        f"{candidate.endpoint} returned HTTP {status}",
        None,
    )


async def _investigate_gap1_candidates(
    *,
    gap_run: Any,
    decision_engine: Any,
    report_state: Any,
    scan_targets: list[str],
    target_url: str,
    root_id: str,
    event_sink: StreamEventSink | None,
) -> None:
    """Probe every undiscovered GAP-1 candidate with live HTTP requests.

    Records genuine probe outcomes directly on the run-scoped GapRun and
    DecisionEngine (which is what ``record_probe_outcome`` also does under
    the hood), creates verified findings only when reproducible evidence is
    captured, and lets GAP-2 pivot to the next candidate when a route is
    exhausted. This runs regardless of whether the model delegates to
    subagents, so the assessment always executes real security tools against
    the target.
    """
    from strix.core.decision_engine.engine import DecisionEngine
    from strix.core.decision_engine.schemas import (
        ActionCandidate,
        Outcome,
        PivotActionType,
    )
    from strix.report.verification import VerificationBlock, VerificationState

    # Preparatory probing must not consume the shared DecisionEngine. It walks
    # a pre-sorted queue with generic HTTP probes; feeding the shared engine
    # marks every candidate abandoned before the model starts, so
    # record_probe_outcome() can never recommend an alternative and genuine
    # agent-driven GAP-2 pivots become impossible. Keep a private engine for
    # preparatory guidance; the shared one stays available for real decisions
    # tied to actually executed alternatives.
    prep_decision_engine = DecisionEngine(
        pivot_threshold=int(getattr(decision_engine, "pivot_threshold", 2)),
        authorized_targets=list(getattr(decision_engine, "authorized_targets", [])),
    )
    prep_decision_engine.initialize(
        [
            ActionCandidate(
                id=c.id,
                name=c.title,
                endpoint=c.endpoint,
                target=c.target or "",
                max_attempts=int(c.max_attempts),
            )
            for c in gap_run.candidates.values()
        ]
    )

    base_url = _probe_target_url(target_url)

    from strix.core.scheduler import CandidateScheduler

    candidate_scheduler = CandidateScheduler(run_id=root_id)
    candidate_scheduler.initialize(
        [{"id": c.id, "priority_rank": c.rank} for c in gap_run.candidates.values()]
    )

    ordered = sorted(gap_run.candidates.values(), key=lambda c: (c.rank, c.id))

    for cand in ordered:
        # Skip candidates already resolved by a previous pass or resume.
        if cand.status in ("investigated", "validated", "abandoned", "blocked"):
            continue

        auth_ok, ticket, auth_msg = candidate_scheduler.authorize_dispatch(cand.id)
        if not auth_ok:
            logger.warning("Scheduler blocked dispatch for candidate %s: %s", cand.id, auth_msg)
            continue

        probe_url = base_url + cand.endpoint

        # Bound preparatory probes locally. Preparatory probes are evidence,
        # not agent investigation attempts, so using cand.attempts as the loop
        # counter would never advance and would misrepresent agent effort.
        prep_attempts = 0
        while prep_attempts < cand.max_attempts:
            prep_attempts += 1
            probe_result = await _http_probe(probe_url)
            outcome, detail, evidence = _analyze_probe(cand, probe_result, probe_url)

            # 1. Record on GapRun (candidate status + attempts).
            # GapRun accepts only positive/negative/inconclusive/error/blocked;
            # "needs_follow_up" is an inconclusive observation.
            gap_run_outcome = outcome
            if outcome == "error":
                gap_run_outcome = "negative"
            elif outcome == "needs_follow_up":
                gap_run_outcome = "inconclusive"
            # Mark these bounded GET probes as preparatory reconnaissance. The
            # evidence is preserved verbatim, but it must not consume the
            # agent's investigation attempts or abandon the candidate: doing
            # so left no eligible alternative for a genuine GAP-2 pivot.
            gap_run.record_probe_outcome(
                cand.id,
                outcome=gap_run_outcome,
                detail=detail,
                retry_reason="",
                alternative_candidate="",
                pivot_executed=False,
                pivot_result="",
                preparatory=True,
            )

            # Emit progress event.
            if event_sink is not None:
                try:
                    event_sink(
                        root_id,
                        {
                            "type": "GAP1_PROBE",
                            "candidate_id": cand.id,
                            "endpoint": cand.endpoint,
                            "outcome": outcome,
                            "detail": detail,
                            "attempts": prep_attempts,
                            "max_attempts": cand.max_attempts,
                            "preparatory": True,
                            "agent_attempts": cand.attempts,
                        },
                    )
                except Exception:
                    pass

            # 2. Run the GAP-2 DecisionEngine for pivot guidance.
            if outcome == "positive":
                out_enum = Outcome.SUCCESS
            elif outcome == "blocked":
                out_enum = Outcome.FAIL_BLOCKED
            elif outcome == "error":
                out_enum = Outcome.FAIL_ERROR
            else:
                out_enum = Outcome.FAIL_TIMEOUT

            # Feed only the private preparatory engine. The shared engine is
            # reserved for agent-driven decisions so a real alternative can
            # still be recommended and executed by the model.
            pivot_action = prep_decision_engine.record_outcome(
                cand.id,
                out_enum,
                detail=detail,
                probe_outcome=outcome,
                reason="",
            )
            pivot_executed = bool(
                getattr(pivot_action, "action", None) is not None
                and getattr(pivot_action, "action", None) == PivotActionType.REDIRECT
            )
            recommended_next = getattr(pivot_action, "to_candidate", None)

            # 3. Sync ReportState accounting (persisted once after the loop).
            try:
                summary = gap_run.summary
                report_state.gap1_candidates_identified = summary["candidates_identified"]
                report_state.gap1_candidates_investigated = summary["candidates_investigated"]
                report_state.gap2_pivots = summary["pivots_executed"]
            except Exception:
                logger.exception("failed to sync gap run summary to report state")

            # 4. Confirmed vulnerability with reproducible evidence -> file a
            # verified finding. Only promote when the verification contract
            # is satisfied (reproducible request + response + procedure +
            # impact + timestamp).
            if outcome == "positive" and evidence:
                report_id = report_state.add_vulnerability_report(
                    title=cand.title,
                    severity="medium",
                    description=detail,
                    target=probe_url,
                    endpoint=cand.endpoint,
                    method="GET",
                    evidence=(
                        f"Request: {evidence['request']}\n"
                        f"Response: {evidence['response']}"
                    ),
                    technical_analysis=(
                        f"Live automated probe against authorized target {probe_url} "
                        f"produced {detail.lower()}."
                    ),
                    poc_description=f"1. GET {cand.endpoint}\n2. Observed: {detail}",
                    poc_script_code=evidence["request"],
                    remediation_steps=(
                        "Review and harden the affected endpoint; validate all user input "
                        "and apply context-appropriate output encoding."
                    ),
                    confidence="high",
                    confidence_rationale=(
                        "Reproducible request/response captured during live probe "
                        "against the authorized target."
                    ),
                    finding_class="dynamic",
                )
                try:
                    vb = VerificationBlock(
                        verification_state=VerificationState.VERIFIED.value,
                        reproducible_request=evidence["request"],
                        verification_response=evidence["response"],
                        verification_procedure=(
                            f"Live automated probe of {cand.endpoint}: {detail}"
                        ),
                        demonstrated_impact=(
                            f"Confirmed observable behavior at {cand.endpoint}: {detail}"
                        ),
                        evidence_timestamp=datetime.now(UTC).strftime(
                            "%Y-%m-%d %H:%M:%S UTC"
                        ),
                        confidence="high",
                        severity="medium",
                        remediation=(
                            "Review and harden the affected endpoint; validate all user input."
                        ),
                    )
                    report_state.update_verification(
                        report_id,
                        verification_state=VerificationState.VERIFIED.value,
                        verification_block=vb,
                    )
                except Exception:
                    logger.exception(
                        "failed to attach verification block to report %s", report_id
                    )

                # Record the positive outcome with a report_id so GAP-2 marks
                # the candidate complete (a positive claim without a report id
                # is rejected as "observed" by the GAP-2 bridge).
                try:
                    from strix.core import gap_bridge

                    if (
                        gap_bridge.control_dir() is not None
                        and gap_bridge.gap2_enabled()
                    ):
                        gap_bridge.record_outcome(
                            candidate_id=cand.id,
                            title=cand.title,
                            endpoint=cand.endpoint,
                            target=probe_url,
                            probe_status="positive",
                            report_id=report_id,
                            detail=detail,
                        )
                except Exception:
                    pass

                if event_sink is not None:
                    try:
                        event_sink(
                            root_id,
                            {
                                "type": "FINDING_CONFIRMED",
                                "candidate_id": cand.id,
                                "report_id": report_id,
                                "endpoint": cand.endpoint,
                            },
                        )
                    except Exception:
                        pass
                break

            # GAP-2 guidance: the decision engine may recommend a redirect
            # when a route is exhausted. This PREPARATORY probe loop does not
            # dispatch alternative investigation paths — it merely walks the
            # pre-sorted GAP-1 queue with generic HTTP probes. Per the project
            # definition, a pivot requires an actually dispatched and executed
            # alternative, so we do NOT call gap_run.record_pivot() here. A
            # genuine pivot is recorded by the agent-driven investigation path
            # when a specialist acts on a decision and produces execution
            # evidence for the alternative candidate.
            if pivot_executed and recommended_next:
                if event_sink is not None:
                    try:
                        event_sink(
                            root_id,
                            {
                                "type": "GAP2_GUIDANCE",
                                "from_candidate": cand.id,
                                "suggested_candidate": recommended_next,
                                "note": "preparatory probe; alternative not dispatched by this loop",
                            },
                        )
                    except Exception:
                        pass
                break

            # Candidate reached a terminal state -> stop probing it.
            if cand.status in ("abandoned", "blocked"):
                break

            # The loop is already bounded by ``prep_attempts < max_attempts``.
            # Checking ``cand.attempts`` here was always true after preparatory
            # probes stopped consuming agent attempts, so it silently reduced
            # every candidate to a single probe.

        # Persist per-candidate state after each probe loop.
        candidate_scheduler.complete_ticket(cand.id, outcome=cand.status)
        gap_run.save()

    gap_run.save()


async def run_strix_scan(
    *,
    scan_config: dict[str, Any],
    scan_id: str | None = None,
    image: str,
    local_sources: list[dict[str, Any]] | None = None,
    extra_files: list[dict[str, Any]] | Awaitable[list[dict[str, Any]] | None] | None = None,
    coordinator: AgentCoordinator | None = None,
    interactive: bool = False,
    max_turns: int = DEFAULT_MAX_TURNS,
    max_budget_usd: float | None = None,
    budget_policy: BudgetPolicy = "stop",
    model: str | None = None,
    cleanup_on_exit: bool = True,
    event_sink: StreamEventSink | None = None,
    root_instructions_override: str | None = None,
    replace_root_scan_prompt: bool = False,
    extra_system_prompt_context: dict[str, Any] | None = None,
    status_sink: StatusSink | None = None,
    mcp_connection_requests: list[McpConnectionRequest] | None = None,
    mcp_status_sink: McpStatusSink | None = None,
    root_finish_tool: Tool = finish_scan,
    report_tool: Tool = create_vulnerability_report,
    coverage_tools: bool = True,
    subagent_turn_limits: Mapping[str, int] | None = None,
) -> RunResultBase | None:
    """Run or resume one Strix scan against a sandbox.

    ``root_instructions_override`` adds root scan instructions to the rendered
    root prompt without replacing the system-verified scope block.
    ``replace_root_scan_prompt=True`` makes it the root's whole prompt, followed
    by the scope, instead of adding it to the rendered scan prompt.
    ``extra_files`` entries (``{"workspace_path", "content"}``) are placed into
    the sandbox workspace at session bring-up; see
    :func:`strix.runtime.session_manager.create_or_reuse`.
    ``extra_system_prompt_context`` is merged into the root agent's scan
    context before prompt rendering. Child agents keep the standard scan prompt
    and context.
    ``budget_policy`` decides what happens when the LLM spend reaches
    ``max_budget_usd``: ``"stop"`` warns the agents as the limit approaches and
    ends the scan at it; ``"pause"`` tells the agents nothing and parks every
    agent before its next LLM call until the caller resumes the scan through
    ``coordinator.resume_budget()`` (optionally with a higher limit) or cancels
    it. ``coordinator.pause_budget()`` parks a running scan the same way.
    ``mcp_connection_requests`` supplies the run's MCP connections from any
    source: when given, the engine connects those requests; when ``None`` (the
    command-line default) it reads ``~/.strix/mcp-servers.json`` itself. Either
    way the engine does the connecting, so the caller passes inert configs plus
    metadata and never live sessions.
    ``root_finish_tool`` is the tool the root agent ends the run with.
    ``report_tool`` is the tool every agent files findings with, in place of
    ``create_vulnerability_report``.
    ``coverage_tools=False`` drops the coverage ledger tools and their prompt
    rules from every agent.
    ``subagent_turn_limits`` maps a skill name to a soft turn limit for sub-agents
    spawned with that skill (the largest applies). Agents are warned 10 turns
    before it and reminded past it, but never stopped.
    """

    def report(phase: str) -> None:
        if status_sink is not None:
            status_sink(phase)

    if scan_id is None:
        scan_id = f"scan-{uuid.uuid4().hex[:8]}"

    run_dir = run_dir_for(scan_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    state_dir = runtime_state_dir(run_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    teardown_logging = setup_scan_logging(run_dir)
    set_scan_id(scan_id)

    agents_path = state_dir / "agents.json"
    agents_db = state_dir / "agents.db"
    is_resume = agents_path.exists()

    logger.info(
        "%s Strix scan %s (image=%s, max_turns=%d, interactive=%s, run_dir=%s)",
        "Resuming" if is_resume else "Starting",
        scan_id,
        image,
        max_turns,
        interactive,
        run_dir,
    )

    settings = load_settings()
    configure_sdk_model_defaults(settings)
    resolved_model = (model or settings.llm.model or "").strip()
    if not resolved_model:
        raise RuntimeError(
            "No LLM model configured. Set STRIX_LLM env or pass model= to run_strix_scan().",
        )
    if resolved_model != (settings.llm.model or "").strip() and not codex.subscription_model(
        resolved_model
    ):
        configure_sdk_api_route(resolved_model, settings)
    logger.info("LLM model resolved: %s", resolved_model)
    chat_completions_tools = uses_chat_completions_tool_schema(resolved_model, settings)
    strict_tool_schemas = supports_strict_tool_schemas(resolved_model)
    if not strict_tool_schemas:
        logger.info("Sending non-strict tool schemas: %s caps strict tools", resolved_model)
    supports_images = model_supports_images(resolved_model)
    if not supports_images:
        logger.info("Leaving out image tools: %s does not accept images", resolved_model)

    if budget_policy not in ("stop", "pause"):
        raise ValueError(f"unknown budget_policy: {budget_policy!r}")
    if coordinator is None:
        coordinator = AgentCoordinator()
    coordinator.set_snapshot_path(agents_path)
    coordinator.set_budget_policy(budget_policy)
    coordinator.root_finish_tool = root_finish_tool.name

    from strix.tools.coverage.tools import hydrate_coverage_from_disk
    from strix.tools.notes.tools import hydrate_notes_from_disk
    from strix.tools.threat_model.tools import hydrate_threat_models_from_disk
    from strix.tools.todo.tools import hydrate_todos_from_disk

    hydrate_todos_from_disk(state_dir)
    hydrate_notes_from_disk(state_dir)
    hydrate_coverage_from_disk(state_dir)
    hydrate_threat_models_from_disk(state_dir)

    report_state = get_global_report_state()
    if report_state is None or report_state.run_id != scan_id:
        report_state = ReportState(scan_id)
        set_global_report_state(report_state)

    from strix.core.gap_run import GapRun

    gap_run = GapRun.load(scan_id, state_dir)
    report_state.gap_run = gap_run
    set_global_gap_run(gap_run)

    # Populate candidates if not already present
    if not gap_run.candidates:
        c_list = scan_config.get("candidates") or []
        if isinstance(c_list, list) and c_list:
            for idx, c in enumerate(c_list):
                if isinstance(c, dict):
                    gap_run.attach_candidate(
                        candidate_id=str(c.get("id") or f"cand-{idx + 1}"),
                        title=str(c.get("name") or c.get("title") or f"Candidate {idx + 1}"),
                        endpoint=str(c.get("endpoint") or "/"),
                        category=str(c.get("category") or "general"),
                        score=float(c.get("score") or c.get("composite_score") or 0.5),
                        rank=int(c.get("rank") or c.get("priority_rank") or (idx + 1)),
                        target=str(c.get("target") or ""),
                    )
        else:
            q_file = state_dir / "gap1_queue.json"
            if not q_file.is_file():
                import os

                raw_q = os.environ.get("STRIX_GAP1_QUEUE", "")
                if raw_q and Path(raw_q).is_file():
                    q_file = Path(raw_q)
            if q_file.is_file():
                try:
                    q_data = json.loads(q_file.read_text(encoding="utf-8"))
                    c_items = q_data.get("candidates", [])
                    if isinstance(c_items, list):
                        for idx, c in enumerate(c_items):
                            if isinstance(c, dict):
                                gap_run.attach_candidate(
                                    candidate_id=str(
                                        c.get("candidate_id") or c.get("id") or f"cand-{idx + 1}"
                                    ),
                                    title=str(
                                        c.get("title") or c.get("name") or f"Candidate {idx + 1}"
                                    ),
                                    endpoint=str(c.get("endpoint") or "/"),
                                    category=str(c.get("category") or "general"),
                                    score=float(c.get("priority_score") or c.get("score") or 0.5),
                                    rank=int(c.get("gap1_rank") or c.get("rank") or (idx + 1)),
                                    target=str(c.get("target") or ""),
                                )
                except Exception:
                    pass

    scan_targets_list = build_scan_targets(scan_config)
    decision_engine = gap_run.sync_decision_engine(authorized_targets=scan_targets_list)

    root_id: str | None = None
    if is_resume:
        try:
            snap = json.loads(agents_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Cannot resume scan {scan_id}: agents.json is unreadable: {exc}",
            ) from exc
        if not agents_db.exists():
            raise RuntimeError(
                f"Cannot resume scan {scan_id}: missing SDK session database at {agents_db}",
            )
        await coordinator.restore(snap)
        report_state = get_global_report_state()
        if report_state is not None:
            budget_stopped, reserve_stopped = recomputed_budget_flags(
                report_state.get_total_llm_cost(),
                max_budget_usd,
                interactive=interactive,
                budget_policy=budget_policy,
            )
            # Under the pause policy the hooks re-park at the first call if the
            # spend is still at the limit, so a restored pause flag would only
            # hold agents back after the limit was raised.
            await coordinator.reset_budget_stops(
                budget_stopped=budget_stopped,
                reserve_stopped=reserve_stopped,
                budget_paused=(
                    interactive and budget_policy != "pause" and coordinator.budget_paused
                ),
            )
        for aid, parent in coordinator.parent_of.items():
            if parent is None:
                root_id = aid
                break
        if root_id is None:
            raise RuntimeError(
                f"Cannot resume scan {scan_id}: agents.json has no root agent (parent=None)",
            )
        logger.info(
            "Resume: restored coordinator with %d agent(s); root=%s",
            len(coordinator.statuses),
            root_id,
        )
    else:
        root_id = uuid.uuid4().hex[:8]

    logger.info("Bringing up sandbox session for scan %s", scan_id)
    set_scan_phase("sandbox_init")
    bundle = await session_manager.create_or_reuse(
        scan_id,
        image=image,
        local_sources=local_sources or [],
        extra_files=extra_files,
        status_sink=status_sink,
    )
    report("Waiting for the first model response")
    logger.info("Sandbox ready for scan %s", scan_id)
    set_scan_phase("agent_setup")

    sandbox_session = bundle["session"]

    async def _spill_to_workspace(output_id: str, text: str) -> str | None:
        """Write an oversized tool result into the sandbox; return its path or None."""
        path = f"{WORKSPACE_SPILL_DIR}/{output_id}.txt"
        try:
            await sandbox_session.write(Path(path), io.BytesIO(text.encode("utf-8")))
        except Exception:
            logger.exception("failed to spill tool output to sandbox workspace")
            return None
        return path

    configure_spill_writer(_spill_to_workspace)

    sessions_to_close: list[SQLiteSession] = []
    mcp_registry: McpRegistry | None = None

    try:
        targets = scan_config.get("targets") or []
        scan_mode = str(scan_config.get("scan_mode") or "deep")
        is_whitebox = any(t.get("type") == "local_code" for t in targets)
        diff_scope = scan_config.get("diff_scope")
        is_diff_scoped = bool(isinstance(diff_scope, dict) and diff_scope.get("active"))
        skills = list(scan_config.get("skills") or [])
        root_task = build_root_task(scan_config)
        model_settings = make_model_settings(
            settings.llm.reasoning_effort,
            model_name=resolved_model,
            force_required_tool_choice=settings.llm.force_required_tool_choice,
            parallel_tool_calls=settings.llm.parallel_tool_calls,
            request_timeout=settings.llm.timeout,
            prompt_cache=settings.llm.prompt_cache,
            extra_headers=settings.llm.extra_headers,
            extra_body=settings.llm.extra_body,
        )
        run_config = RunConfig(
            model=resolved_model,
            model_provider=StrixProvider(),
            model_settings=model_settings,
            sandbox=SandboxRunConfig(client=bundle["client"], session=bundle["session"]),
            trace_include_sensitive_data=False,
            # A hallucinated tool name is a recoverable model mistake, not a scan-ending
            # error: hand it back as a tool result so the agent can correct itself.
            tool_not_found_behavior="return_error_to_model",
        )
        hooks = ReportUsageHooks(
            model=resolved_model,
            max_budget_usd=max_budget_usd,
            max_turns=max_turns,
            interactive=interactive,
            budget_policy=budget_policy,
            record_tool_timings=getattr(
                getattr(settings, "telemetry", None), "run_record_timings", False
            ),
        )
        coordinator.set_budget_limit_setter(hooks.set_max_budget_usd)
        if interactive and budget_policy != "pause":
            coordinator.set_budget_extender(hooks.extend_budget)

        scope_context = build_scope_context(scan_config)

        # Attach the run's MCP connections and hold their live sessions in a
        # per-run registry. The connections are source-agnostic: a caller
        # (the SaaS/pro product) can supply them as mcp_connection_requests, and
        # when it does not the command-line path reads them from
        # ~/.strix/mcp-servers.json here. Either way one shared engine routine
        # does the connecting and populating. Nothing is registered as an agent
        # tool: every agent reaches these connections on demand through the
        # list_mcps / describe_mcp / call_mcp tools, guided by brief static prompt
        # guidance when any connection exists. Fail-open: a missing config, or a
        # server that will not connect, must never break a run.
        from strix.tools.mcp import (
            McpConnectionRequest,
            McpRegistry,
            load_user_mcp_configs,
        )

        mcp_registry = McpRegistry()
        try:
            if mcp_connection_requests is None:
                # Command-line default: read the user's file and wrap each config
                # in a bare request (no provider or transform), so this path is
                # exactly the old behavior.
                mcp_requests = [
                    McpConnectionRequest(config=config) for config in load_user_mcp_configs()
                ]
            else:
                mcp_requests = mcp_connection_requests
            if mcp_requests:
                for request in mcp_requests:
                    mcp_registry.register(request)
                _record_mcp_connections(mcp_registry.names())
                report(
                    f"MCP: configured {len(mcp_registry)} connection(s); "
                    "connecting and listing tools"
                )
                scope_context["mcp_available"] = True
                scope_context["mcp_connections"] = _mcp_prompt_roster(mcp_registry)

                def _emit_mcp_status() -> None:
                    scope_context["mcp_connections"] = _mcp_prompt_roster(mcp_registry)
                    roster = _mcp_roster_payload(mcp_registry)
                    _persist_mcp_status(roster)
                    if mcp_status_sink is not None:
                        try:
                            mcp_status_sink(roster)
                        except Exception:
                            logger.exception("MCP status sink failed")

                mcp_registry.set_status_sink(_emit_mcp_status)
                _emit_mcp_status()
                warmup_task = mcp_registry.start_warmup(max_concurrency=6)
                await asyncio.wait(
                    {warmup_task},
                    timeout=_MCP_PROMPT_WARMUP_TIMEOUT_SECONDS,
                )
        except Exception:
            logger.exception("Failed to configure user MCP servers; continuing without them")

        if gap_run.candidates:
            scope_context["gap_candidates"] = [c.to_dict() for c in gap_run.candidates.values()]

        cand_block = ""
        if gap_run.candidates:
            cand_lines = [
                "### AI-VAPT GAP-1 Prioritized Candidate Queue",
                "The following prioritized vulnerability candidates have been discovered and ranked for investigation:",
            ]
            for c in gap_run.candidates.values():
                cand_lines.append(
                    f"- **[{c.id}]** #{c.rank} {c.title} (Endpoint: `{c.endpoint}`, Category: `{c.category}`, Score: {c.score:.2f}) [Status: {c.status.upper()}]"
                )
            cand_lines.extend(
                [
                    "",
                    "Investigation Protocol:",
                    "1. Investigate candidates in prioritized rank order.",
                    "2. For each probe, record the exact outcome using `record_probe_outcome`.",
                    "3. If a probe fails up to the failure threshold (k), evaluate the recommended alternative candidate and execute an actual pivot.",
                    "4. If a vulnerability is confirmed with reproducible request/response, file it using `create_vulnerability_report` and verify it using `record_vulnerability_outcome`.",
                ]
            )
            cand_block = "\n".join(cand_lines)

        root_context = _merge_root_prompt_context(scope_context, extra_system_prompt_context)
        effective_override = root_instructions_override
        if cand_block:
            effective_override = (
                f"{root_instructions_override}\n\n{cand_block}"
                if root_instructions_override
                else cand_block
            )

        root_instructions = _compose_root_instructions_override(
            effective_override,
            skills=skills,
            scan_mode=scan_mode,
            is_whitebox=is_whitebox,
            is_diff_scoped=is_diff_scoped,
            interactive=interactive,
            parallel_tool_calls=settings.llm.parallel_tool_calls,
            system_prompt_context=root_context,
            supports_images=supports_images,
            report_tool=report_tool.name,
            coverage_tools=coverage_tools,
            replace_scan_prompt=replace_root_scan_prompt,
        )

        root_agent = build_strix_agent(
            name="Root Agent",
            skills=skills,
            is_root=True,
            scan_mode=scan_mode,
            is_whitebox=is_whitebox,
            is_diff_scoped=is_diff_scoped,
            interactive=interactive,
            parallel_tool_calls=settings.llm.parallel_tool_calls,
            chat_completions_tools=chat_completions_tools,
            strict_tool_schemas=strict_tool_schemas,
            system_prompt_context=root_context,
            instructions_override=root_instructions,
            supports_images=supports_images,
            finish_tool=root_finish_tool,
            report_tool=report_tool,
            coverage_tools=coverage_tools,
        )

        if not is_resume:
            await coordinator.register(
                root_id,
                "Root Agent",
                parent_id=None,
                task=root_task,
                skills=skills,
            )

        child_agent_builder = make_child_factory(
            scan_mode=scan_mode,
            is_whitebox=is_whitebox,
            is_diff_scoped=is_diff_scoped,
            interactive=interactive,
            parallel_tool_calls=settings.llm.parallel_tool_calls,
            chat_completions_tools=chat_completions_tools,
            strict_tool_schemas=strict_tool_schemas,
            system_prompt_context=scope_context,
            supports_images=supports_images,
            report_tool=report_tool,
            coverage_tools=coverage_tools,
        )

        async def spawn_child_agent(**kwargs: Any) -> dict[str, Any]:
            return await start_child_agent(
                coordinator=coordinator,
                factory=child_agent_builder,
                agents_db_path=agents_db,
                sessions_to_close=sessions_to_close,
                run_config=run_config,
                max_turns=max_turns,
                interactive=interactive,
                event_sink=event_sink,
                hooks=hooks,
                **kwargs,
            )

        context: dict[str, Any] = {
            "coordinator": coordinator,
            "sandbox_session": bundle["session"],
            "caido_client": bundle["caido_client"],
            "mcp_registry": mcp_registry,
            "agent_id": root_id,
            "parent_id": None,
            "interactive": interactive,
            "spawn_child_agent": spawn_child_agent,
            "scan_targets": scan_targets_list,
            "max_context_images": settings.runtime.max_context_images,
            "supports_images": supports_images,
            "coverage_tools": coverage_tools,
            "gap_run": gap_run,
            "decision_engine": decision_engine,
            "scan_id": scan_id,
            SUBAGENT_TURN_LIMITS_KEY: dict(subagent_turn_limits or {}),
        }

        root_session = open_agent_session(root_id, agents_db)
        sessions_to_close.append(root_session)
        await coordinator.attach_runtime(root_id, session=root_session)

        if is_resume:
            await respawn_subagents(
                coordinator=coordinator,
                factory=child_agent_builder,
                agents_db_path=agents_db,
                sessions_to_close=sessions_to_close,
                run_config=run_config,
                max_turns=max_turns,
                interactive=interactive,
                parent_ctx=context,
                root_id=root_id,
                event_sink=event_sink,
                hooks=hooks,
            )

        initial_input: Any = [] if is_resume else root_task

        # Resume + new ``--instruction``: SDK replay drives root from
        # agents.db with ``initial_input=[]``, so a brand-new instruction
        # passed on the resume CLI would otherwise be silently ignored.
        # Inject it as a fresh user message in root's SDK session; the
        # next run cycle will replay it with the rest of the session.
        resume_instruction = str(scan_config.get("resume_instruction") or "").strip()
        if is_resume and resume_instruction:
            await coordinator.send(
                root_id,
                {
                    "from": "user",
                    "type": "instruction",
                    "priority": "high",
                    "content": resume_instruction,
                },
            )
            logger.info(
                "Resume: injected new instruction into root SDK session (len=%d)",
                len(resume_instruction),
            )

        async with coordinator._lock:
            root_status = coordinator.statuses.get(root_id)

        # --- Guaranteed real candidate investigation -----------------------
        # Probe every GAP-1 candidate with live HTTP requests and record
        # genuine probe outcomes. This runs regardless of whether the model
        # delegates to subagents, so the assessment always executes real
        # security tools against the target instead of only describing intent.
        target_url = ""
        for _t in scan_config.get("targets", []) or []:
            if _t.get("type") == "web_application":
                target_url = str(_t.get("details", {}).get("target_url", ""))
                break
        # The runner executes on the host; a Docker-rewritten host.docker.internal
        # target is not reachable from the host, so probe the loopback address.
        if "host.docker.internal" in target_url:
            target_url = target_url.replace("host.docker.internal", "127.0.0.1")
        if gap_run.candidates and target_url:
            set_scan_phase("gap1_investigation")
            logger.info(
                "Starting automated GAP-1 investigation of %d candidate(s) against %s",
                len(gap_run.candidates),
                target_url,
            )
            try:
                await _investigate_gap1_candidates(
                    gap_run=gap_run,
                    decision_engine=decision_engine,
                    report_state=report_state,
                    scan_targets=scan_targets_list,
                    target_url=target_url,
                    root_id=root_id,
                    event_sink=event_sink,
                )
            except Exception:
                logger.exception("GAP-1 investigation failed; continuing to agent loop")
            # Re-hydrate the report state from the (possibly updated) gap run.
            try:
                summary = gap_run.summary
                report_state.gap1_candidates_identified = summary["candidates_identified"]
                report_state.gap1_candidates_investigated = summary["candidates_investigated"]
                report_state.gap2_pivots = summary["pivots_executed"]
                report_state.save_run_data()
            except Exception:
                logger.exception("failed to sync gap run summary to report state")

            # The automated probes are genuine HTTP execution, but they are
            # only PREPARATORY evidence gathering. They must never replace the
            # autonomous model loop or produce a success report by themselves:
            # doing so would report a completed assessment with zero LLM calls
            # (the false-completion defect seen in earlier runs). Hand the
            # probe outcomes to the model and let it drive the remainder of
            # the assessment; truthful completion is only written by the
            # finish_scan tool / the agent loop exit path below.
            logger.info(
                "Automated GAP-1 probes finished for %d candidate(s); "
                "handing control to the autonomous model loop",
                len(gap_run.candidates),
            )

        set_scan_phase("agent_loop")
        result = await run_agent_loop(
            agent=root_agent,
            initial_input=initial_input,
            run_config=run_config,
            context=context,
            max_turns=max_turns,
            coordinator=coordinator,
            agent_id=root_id,
            interactive=interactive,
            session=root_session,
            start_parked=bool(interactive and is_resume and root_status != "running"),
            event_sink=event_sink,
            hooks=hooks,
        )
        if not interactive and result is not None:
            final = getattr(result, "final_output", None)
            # Lifecycle tools mark the root completed.
            async with coordinator._lock:
                root_completed = coordinator.statuses.get(root_id) == "completed"
            if not root_completed:
                logger.error(
                    "Scan %s ended without calling finish_scan. The agent "
                    "emitted a text-only turn instead of a lifecycle tool call, "
                    "so no executive report was written. Final output (first "
                    "300 chars): %r",
                    scan_id,
                    str(final)[:300],
                )
                _note_exit_reason("missing_finish_scan")
                report_state = get_global_report_state()
                if (
                    report_state is not None
                    and report_state.run_record.get("status") != "completed"
                ):
                    report_state.save_run_data(status="stopped")
        return result  # noqa: TRY300
    except BudgetExceededError as exc:
        logger.info("Scan %s stopped: %s", scan_id, exc)
        _note_exit_reason("budget_exceeded")
        if root_id is not None:
            with contextlib.suppress(Exception):
                await coordinator.set_status(root_id, "stopped")
        report_state = get_global_report_state()
        if report_state is not None and report_state.run_record.get("status") != "completed":
            report_state.save_run_data(status="stopped")
        return None
    except MaxTurnsExceeded as exc:
        logger.info("Scan %s stopped: turn limit reached (%s)", scan_id, exc)
        _note_exit_reason("turn_limit_reached")
        if root_id is not None:
            with contextlib.suppress(Exception):
                await coordinator.set_status(root_id, "stopped")
        report_state = get_global_report_state()
        if report_state is not None:
            report_state.save_run_data(mark_complete=True)
        return None
    except RateLimitError as exc:
        logger.warning(
            "Scan %s stopped: persistent rate limit from the LLM provider (%s). "
            "Resume with 'strix --resume %s' once the limit clears.",
            scan_id,
            exc,
            scan_id,
        )
        _note_exit_reason("rate_limited")
        if root_id is not None:
            with contextlib.suppress(Exception):
                await coordinator.set_status(root_id, "stopped")
        report_state = get_global_report_state()
        if report_state is not None and report_state.run_record.get("status") != "completed":
            report_state.save_run_data(status="failed")
        return None
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Scan %s interrupted by the user", scan_id)
        if root_id is not None:
            with contextlib.suppress(Exception):
                await coordinator.set_status(root_id, "running")
        raise
    except BaseException:
        logger.exception("Strix scan %s failed", scan_id)
        if root_id is not None:
            with contextlib.suppress(Exception):
                await coordinator.set_status(root_id, "failed")
        raise
    finally:
        configure_spill_writer(None)
        with contextlib.suppress(Exception):
            if gap_run is not None:
                gap_run.save()
            current_rs = get_global_report_state()
            if current_rs is not None:
                current_rs.save_run_data()
        # Settle descendants before closing sessions: on a clean finish a child
        # can still be mid-turn, and closing its session underneath it crashes it.
        if root_id is not None:
            with contextlib.suppress(Exception):
                await coordinator.cancel_descendants(root_id)
        for s in sessions_to_close:
            with contextlib.suppress(Exception):
                s.close()
        if mcp_registry is not None:
            with contextlib.suppress(Exception):
                await mcp_registry.close()
        with contextlib.suppress(Exception):
            await coordinator._maybe_snapshot()
        if cleanup_on_exit:
            logger.info("Tearing down sandbox session for scan %s", scan_id)
            await session_manager.cleanup(scan_id)
        logger.info("Strix scan %s done", scan_id)
        teardown_logging()
