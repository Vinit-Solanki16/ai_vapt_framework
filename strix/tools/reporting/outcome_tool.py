"""Outcome tooling: recording finding verification + GAP probe outcomes.

Findings start as "discovered" and move through the verification lifecycle:

    discovered -> candidate -> under_investigation -> exploitation_attempted
    -> verified    | unconfirmed | false_positive | blocked | inconclusive

``record_vulnerability_outcome`` is how any agent (and the driver) end-to-end a
finding: it sets the explicit verification state, stores the reproducible
request/response/procedure/impact/timestamp/confidence/severity/remediation
block, and aligns the coverage ledger with the finding's true outcome. The
root driver calls it after each investigation so that a finding can never be
presented as "confirmed" without evidence in the report artifacts.

``record_probe_outcome`` is GAP2: it records one probe of one candidate,
including the probe outcome, the reason for a retry or abandonment, the
alternative candidate that was selected, whether an actual pivot executed, and
the pivot result. This is what makes "actual pivots" visible in reports, not
artificial pivot counts.
"""

from __future__ import annotations

import json
from typing import Any, cast

from agents import RunContextWrapper, function_tool

from strix.report.verification import (
    CategoryTest,
    VerificationBlock,
    VerificationState,
    validate_category_outcome,
)


def _get_report_state(caller_agent_id: str | None) -> Any:
    from strix.report.state import get_global_report_state

    return get_global_report_state()


def _findings_status(report_state: Any) -> dict[str, CategoryTest]:
    if report_state is None:
        return {}
    return cast("dict[str, CategoryTest]", report_state.findings_status)


def _caller_identity(ctx: RunContextWrapper) -> tuple[str | None, str | None]:
    inner = ctx.context if isinstance(ctx.context, dict) else {}
    raw_agent_id = inner.get("agent_id")
    agent_id = raw_agent_id if isinstance(raw_agent_id, str) else None
    return agent_id, None


# ---------------------------------------------------------------------------
# Verification + finding outcome
# ---------------------------------------------------------------------------


@function_tool(timeout=180, strict_mode=False)
async def record_vulnerability_outcome(
    ctx: RunContextWrapper,
    report_id: str,
    *,
    verification_state: str,
    reproducible_request: str = "",
    verification_response: str = "",
    verification_procedure: str = "",
    demonstrated_impact: str = "",
    evidence_timestamp: str = "",
    confidence: str = "",
    confidence_rationale: str = "",
    severity: str = "",
    remediation: str = "",
    coverage_outcome: str = "needs_follow_up",
    category: str = "",
    category_title: str = "",
) -> str:
    """Record the explicit verification state of one finding.

    Updates ``verification`` on the finding, sets the report-level
    ``verification_state``, aligns the coverage ledger with the outcome, and
    updates the findings_status category ledger. The report artifacts are
    written on next save so they never present an unverified finding as
    confirmed.

    Args:
        report_id: Unique identifier of the vulnerability report being updated.
        verification_state: One of the nine verification lifecycle states (e.g. 'discovered', 'candidate', 'under_investigation', 'exploitation_attempted', 'verified', 'unconfirmed', 'false_positive', 'blocked', 'inconclusive').
        reproducible_request: Exact HTTP request string that reproduces the vulnerability.
        verification_response: HTTP response body or headers observed during the verification probe.
        verification_procedure: Concrete steps executed to verify the finding.
        demonstrated_impact: Real observed security impact demonstrated by the exploit proof.
        evidence_timestamp: ISO-8601 UTC timestamp when the verification evidence was captured.
        confidence: Assessor confidence level ('high', 'medium', 'low', 'none').
        confidence_rationale: Explanation supporting the confidence rating.
        severity: Finding severity rating ('critical', 'high', 'medium', 'low', 'info').
        remediation: Specific actionable remediation advice for resolving the finding.
        coverage_outcome: Coverage ledger outcome aligned to this finding ('reported', 'needs_follow_up').
        category: Vulnerability category key (e.g. 'sql_injection', 'xss', 'idor').
        category_title: Display title for the vulnerability category.
    """
    caller_agent_id, _ = _caller_identity(ctx)
    report_state = _get_report_state(caller_agent_id)
    if report_state is None:
        return json.dumps({"success": False, "error": "No report state available for this scan"})

    if not verification_state or verification_state.strip() == "":
        return json.dumps({"success": False, "error": "verification_state is required"})

    requested_state = verification_state.strip().lower()
    if requested_state not in VerificationState.__members__.values():
        return json.dumps(
            {
                "success": False,
                "error": (
                    f"verification_state must be one of "
                    f"{sorted(VerificationState.__members__.values())}, got {verification_state!r}"
                ),
            }
        )

    # Attach the verification block to the finding.
    block = VerificationBlock(
        verification_state=requested_state,
        reproducible_request=reproducible_request,
        verification_response=verification_response,
        verification_procedure=verification_procedure,
        demonstrated_impact=demonstrated_impact,
        evidence_timestamp=(evidence_timestamp or ""),
        confidence=(confidence or "").strip().lower(),
        confidence_rationale=(confidence_rationale or "").strip(),
        severity=(severity or "").strip().lower(),
        remediation=remediation,
    )

    # Contract gate: if verified is claimed without full reproducible evidence, downgrade to unconfirmed.
    if requested_state == VerificationState.VERIFIED.value:
        if not block.satisfies_verification_contract():
            requested_state = VerificationState.UNCONFIRMED.value
            block.verification_state = VerificationState.UNCONFIRMED.value

    # Align the coverage ledger with the finding.
    aligned_outcome = _align_coverage_outcome(coverage_outcome, requested_state)

    # Update the category test ledger for the optional category.
    if category:
        category_key = category.strip().lower()
        meta = _findings_status(report_state).setdefault(
            category_key,
            CategoryTest(category=category_key, title=category_title.strip()),
        )
        meta.tested = True
        meta.outcome = validate_category_outcome("failed")
        meta.evidence = f"verification_state={requested_state}; coverage={aligned_outcome}"

    report = report_state.update_verification(
        report_id,
        verification_state=requested_state,
        verification_block=block,
        coverage_outcome=aligned_outcome,
    )
    return json.dumps(
        {
            "success": True,
            "message": f"verification_state -> {requested_state}",
            "report_id": report_id,
            "verification": block.to_dict(),
            "coverage_outcome": aligned_outcome,
        },
        ensure_ascii=False,
        default=str,
    )


# ---------------------------------------------------------------------------
# GAP probe outcome (GAP2)
# ---------------------------------------------------------------------------


@function_tool(timeout=180, strict_mode=False)
async def record_probe_outcome(
    ctx: RunContextWrapper,
    candidate_id: str,
    *,
    probe_outcome: str,
    detail: str = "",
    retry_reason: str = "",
    alternative_candidate: str = "",
    pivot_executed: bool = False,
    pivot_result: str = "",
) -> str:
    """Record one GAP2 probe of one candidate.

    Stores the probe outcome, the reason for retry or abandonment, the
    alternative candidate selected, whether an actual pivot executed, and the
    pivot result. The driver retains authoritative state and only marks a
    candidate "abandoned" or increments attempts / pivots when the recorded
    events are real, so there are no artificial pivot counts.

    Args:
        candidate_id: the GAP candidate that was probed.
        probe_outcome: positive | negative | inconclusive | error.
        detail: what the probe actually returned.
        retry_reason: why the candidate was retried or abandoned.
        alternative_candidate: the candidate selected as a result of the
            negative/inconclusive probe (empty if none).
        pivot_executed: True only when a real pivot was executed.
        pivot_result: the outcome of the pivot (positive | negative |
            inconclusive | skipped).
    """
    caller_agent_id, _ = _caller_identity(ctx)
    report_state = _get_report_state(caller_agent_id)
    if report_state is None:
        return json.dumps({"success": False, "error": "No report state available for this scan"})

    # Get GapRun instance (per-run state)
    gap_run = getattr(report_state, "gap_run", None)
    if gap_run is None:
        from strix.report.state import get_global_gap_run

        gap_run = get_global_gap_run()

    # Scope validation for alternative candidate if pivot is claimed
    if alternative_candidate or pivot_executed:
        scan_targets: list[str] = []
        inner_ctx = ctx.context if isinstance(ctx.context, dict) else {}
        ctx_targets = inner_ctx.get("scan_targets")
        if isinstance(ctx_targets, list):
            scan_targets.extend(str(t) for t in ctx_targets if t)
        elif report_state.run_record.get("targets_info"):
            for t in report_state.run_record.get("targets_info", []):
                if isinstance(t, dict):
                    val = t.get("value") or t.get("workspace_path")
                    if val:
                        scan_targets.append(str(val))

        if alternative_candidate and gap_run:
            alt_c = gap_run.candidates.get(alternative_candidate)
            if alt_c:
                target_check = (alt_c.target or alt_c.endpoint or "").strip()
                if (
                    target_check
                    and not target_check.startswith("/")
                    and not target_check.startswith("//")
                ):
                    import urllib.parse

                    parsed = urllib.parse.urlsplit(
                        target_check if "://" in target_check else f"http://{target_check}"
                    )
                    host = (parsed.hostname or "").lower()
                    if host and scan_targets:
                        in_scope = False
                        for auth in scan_targets:
                            auth_parsed = urllib.parse.urlsplit(
                                auth if "://" in auth else f"http://{auth}"
                            )
                            auth_host = (auth_parsed.hostname or auth).lower()
                            if host == auth_host or host.endswith(f".{auth_host}"):
                                in_scope = True
                                break
                            if host in (
                                "localhost",
                                "127.0.0.1",
                                "host.docker.internal",
                            ) and auth_host in (
                                "localhost",
                                "127.0.0.1",
                                "host.docker.internal",
                            ):
                                in_scope = True
                                break
                        if not in_scope:
                            return json.dumps(
                                {
                                    "success": False,
                                    "error": f"Alternative candidate '{alternative_candidate}' ({target_check}) is outside authorized scan scope",
                                },
                                ensure_ascii=False,
                            )

    norm_outcome = (probe_outcome or "negative").strip().lower()

    # 1. Update GapRun
    if gap_run is not None:
        if candidate_id not in gap_run.candidates:
            gap_run.attach_candidate(
                candidate_id=candidate_id,
                title=detail or candidate_id,
                endpoint="/",
                category="general",
            )
        gap_run_outcome = (
            norm_outcome
            if norm_outcome in ("positive", "negative", "inconclusive", "error")
            else ("error" if norm_outcome == "blocked" else "negative")
        )
        gap_run.record_probe_outcome(
            candidate_id,
            outcome=gap_run_outcome,
            detail=detail,
            retry_reason=retry_reason,
            alternative_candidate=alternative_candidate,
            pivot_executed=bool(pivot_executed),
            pivot_result=pivot_result or ("positive" if pivot_executed else ""),
        )
        if norm_outcome == "blocked":
            gap_run.record_blocked(candidate_id, reason=detail or retry_reason or "blocked")

    # 2. Update DecisionEngine if bound
    inner_ctx = ctx.context if isinstance(ctx.context, dict) else {}
    decision_engine = inner_ctx.get("decision_engine")
    if decision_engine is None and gap_run is not None:
        decision_engine = getattr(gap_run, "decision_engine", None)

    recommended_next = None
    if decision_engine is not None:
        from strix.core.decision_engine.schemas import Outcome

        if norm_outcome == "positive":
            out_enum = Outcome.SUCCESS
        elif norm_outcome == "blocked":
            out_enum = Outcome.FAIL_BLOCKED
        elif norm_outcome == "error":
            out_enum = Outcome.FAIL_ERROR
        else:
            out_enum = Outcome.FAIL_TIMEOUT

        action = decision_engine.record_outcome(
            candidate_id,
            out_enum,
            detail=detail,
            probe_outcome=norm_outcome,
            reason=retry_reason,
        )
        recommended_next = getattr(action, "to_candidate", None)

    # 3. Synchronize file-based gap_bridge if active
    try:
        from strix.core.gap_bridge import control_dir
        from strix.core.gap_bridge import record_outcome as bridge_record_outcome

        if control_dir() is not None:
            bridge_record_outcome(
                title=candidate_id,
                endpoint="",
                target="",
                success=(norm_outcome == "positive"),
                detail=detail,
                probe_status=norm_outcome,
            )
    except Exception:
        pass

    # 4. Sync ReportState candidate accounting
    if gap_run is not None:
        summary = gap_run.summary
        report_state.gap1_candidates_identified = summary["candidates_identified"]
        report_state.gap1_candidates_investigated = summary["candidates_investigated"]
        report_state.gap2_pivots = summary["pivots_executed"]
        report_state.save_run_data()

    cand = gap_run.candidates.get(candidate_id) if gap_run else None

    return json.dumps(
        {
            "success": True,
            "message": "probe recorded",
            "candidate_id": candidate_id,
            "probe_outcome": norm_outcome,
            "candidate_state": cand.status if cand else "investigated",
            "attempts": cand.attempts if cand else 1,
            "max_attempts": cand.max_attempts if cand else 2,
            "detail": detail,
            "retry_reason": retry_reason,
            "alternative_candidate": alternative_candidate,
            "pivot_executed": bool(pivot_executed),
            "pivot_result": pivot_result,
            "pivots_total": gap_run.pivot_count() if gap_run else 0,
            "recommended_next_candidate": recommended_next,
            "invariant_holds": (gap_run.summary["invariant_holds"] if gap_run else True),
        },
        ensure_ascii=False,
        default=str,
    )


# ---------------------------------------------------------------------------
# Internal support
# ---------------------------------------------------------------------------


def _align_coverage_outcome(coverage_outcome: str, verification_state: str) -> str:
    """Derive a coverage outcome that matches the finding's verification state."""
    key = (coverage_outcome or "").strip().lower()
    if key in {"verified", "positive"}:
        return "reported"
    if key in {"false_positive", "no_issue_found", "ruled_out"}:
        return key
    if key == "blocked" or verification_state == VerificationState.BLOCKED.value:
        return "blocked"
    if key in {"untestable"}:
        return "needs_follow_up"
    # confirmed findings sync with verification state.
    if verification_state in {
        VerificationState.VERIFIED.value,
        VerificationState.EXPLOITATION_ATTEMPTED.value,
    }:
        return "reported"
    if verification_state == VerificationState.UNCONFIRMED.value:
        return "needs_follow_up"
    if verification_state in {
        VerificationState.INCONCLUSIVE.value,
        VerificationState.FALSE_POSITIVE.value,
    }:
        return verification_state
    # discovered / candidate / under_investigation default to needs_follow_up.
    return "needs_follow_up"
