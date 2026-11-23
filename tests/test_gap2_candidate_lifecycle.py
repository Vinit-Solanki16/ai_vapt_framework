"""Deterministic regression tests for the GAP-2 candidate lifecycle.

These pin down the distinction between preparatory reconnaissance and genuine
agent investigation:

    preparatory probe  -> evidence only, never an attempt or an exhaustion
    agent investigation -> a real attempt that can exhaust a candidate
    pivot decision      -> a recorded choice, not yet a pivot
    alternative execution -> the only thing that makes a pivot genuine

The tests are intentionally deterministic (no model, no network) so the state
machine can be trusted before a live Web Console run is attempted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from strix.core.decision_engine.engine import DecisionEngine
from strix.core.decision_engine.schemas import ActionCandidate, CandidateState, Outcome
from strix.core.gap_run import GapRun


def _gap(tmp_path: Path, *, ids: tuple[str, ...] = ("c1", "c2")) -> GapRun:
    state_dir = tmp_path / ".state"
    state_dir.mkdir(exist_ok=True)
    run = GapRun("lifecycle-test", state_dir, threshold=2)
    for rank, cid in enumerate(ids, 1):
        run.attach_candidate(
            cid,
            f"Candidate {cid}",
            f"/{cid}",
            "general",
            score=0.9 - rank / 10,
            rank=rank,
            target="http://127.0.0.1:3000/",
        )
    return run


def test_1_preparatory_probes_do_not_exhaust_alternative_pool(tmp_path: Path) -> None:
    """Bounded GET probes are evidence, not agent attempts; c2 stays eligible."""
    run = _gap(tmp_path)
    for _ in range(2):
        run.record_probe_outcome(
            "c1", outcome="inconclusive", detail="bounded GET probe", preparatory=True
        )

    c1 = run.candidates["c1"]
    assert c1.attempts == 0, "preparatory probes must not consume agent attempts"
    assert c1.preparatory_probes == 2
    assert c1.status == "discovered", "preparatory probes must not change agent status"
    assert len(c1.preparatory_outcomes) == 2, "preparatory evidence must be preserved"

    eligible = {e["id"] for e in run.eligible_alternatives(exclude="c1")}
    assert eligible == {"c2"}

    engine = run.sync_decision_engine(authorized_targets=["http://127.0.0.1:3000/"])
    assert engine.candidates["c1"].state != CandidateState.ABANDONED
    assert engine.candidates["c2"].state == CandidateState.PENDING
    alternative = engine.get_next_available_candidate()
    assert alternative is not None
    assert alternative.id == "c2"


def test_2_genuine_agent_attempts_counted_correctly(tmp_path: Path) -> None:
    """Only non-preparatory probes increment the agent attempt counter."""
    run = _gap(tmp_path)
    run.record_probe_outcome("c1", outcome="inconclusive", detail="prep", preparatory=True)
    run.record_probe_outcome("c1", outcome="inconclusive", detail="prep", preparatory=True)
    run.record_probe_outcome("c1", outcome="inconclusive", detail="agent tool probe")

    c1 = run.candidates["c1"]
    assert c1.preparatory_probes == 2
    assert c1.attempts == 1
    assert c1.status == "investigated"

    run.record_probe_outcome("c1", outcome="negative", detail="agent retry")
    assert c1.attempts == 2
    assert c1.status == "abandoned"


def test_3_exhausted_candidate_not_represented_as_pending(tmp_path: Path) -> None:
    """A genuinely exhausted candidate must not be offered as an alternative."""
    run = _gap(tmp_path)
    run.record_probe_outcome("c1", outcome="negative", detail="agent failure 1")
    run.record_probe_outcome("c1", outcome="negative", detail="agent failure 2")

    engine = run.sync_decision_engine(authorized_targets=["http://127.0.0.1:3000/"])
    assert engine.candidates["c1"].state == CandidateState.ABANDONED
    assert engine.get_next_available_candidate().id == "c2"
    assert "c1" not in {e["id"] for e in run.eligible_alternatives()}


def test_4_negative_outcome_redirect_when_alternative_exists() -> None:
    """A real negative outcome produces REDIRECT to a valid pending candidate."""
    engine = DecisionEngine(pivot_threshold=2, authorized_targets=["http://127.0.0.1:3000/"])
    engine.initialize(
        [
            ActionCandidate(id="c1", endpoint="/c1", target="http://127.0.0.1:3000/"),
            ActionCandidate(id="c2", endpoint="/c2", target="http://127.0.0.1:3000/"),
        ]
    )
    first = engine.record_outcome("c1", Outcome.FAIL_TIMEOUT)
    assert first.action.value == "RETRY"
    second = engine.record_outcome("c1", Outcome.FAIL_TIMEOUT)
    assert second.action.value == "REDIRECT"
    assert second.to_candidate == "c2"


def test_5_no_redirect_when_no_eligible_alternative() -> None:
    """A candidate pool of one cannot produce a redirect after exhaustion."""
    engine = DecisionEngine(pivot_threshold=2, authorized_targets=["http://127.0.0.1:3000/"])
    engine.initialize([ActionCandidate(id="c1", endpoint="/c1", target="http://127.0.0.1:3000/")])
    engine.record_outcome("c1", Outcome.FAIL_TIMEOUT)
    result = engine.record_outcome("c1", Outcome.FAIL_TIMEOUT)
    assert result.action.value == "COMPLETE"
    assert result.to_candidate is None


def test_6_pivot_counted_only_after_alternative_execution(tmp_path: Path) -> None:
    """A recorded decision alone is not a pivot; execution makes it genuine."""
    run = _gap(tmp_path)
    run.record_pivot("c1", "c2", "inconclusive", detail="threshold reached")
    assert run.pivot_count() == 0
    assert run.summary["pivots_executed"] == 0

    run.record_probe_outcome("c2", outcome="inconclusive", detail="executed alternative")
    assert run.pivot_count() == 1
    assert run.summary["pivots_executed"] == 1


def test_7_decision_linked_to_executed_alternative(tmp_path: Path) -> None:
    """The original decision is linked to the executed alternative in state."""
    run = _gap(tmp_path)
    run.record_pivot("c1", "c2", "inconclusive", detail="negative outcome redirected")
    run.record_probe_outcome("c2", outcome="inconclusive", detail="live probe of alternative")

    persisted = json.loads((tmp_path / ".state" / "gap_state.json").read_text(encoding="utf-8"))
    decisions = [
        e
        for e in persisted["decision_trace"]
        if e.get("type") == "pivot_decision" and e.get("alternative_candidate")
    ]
    executed = {str(e.get("candidate_id")) for e in persisted["probe_outcomes"]}
    linked = [d for d in decisions if str(d.get("alternative_candidate")) in executed]
    assert len(linked) == 1
    assert linked[0]["candidate_id"] == "c1"
    assert linked[0]["alternative_candidate"] == "c2"
    assert run.pivot_count() == 1


def test_pivot_execution_links_to_original_decision_not_self(tmp_path: Path) -> None:
    """Executing an alternative must not create a self-referential decision."""
    run = _gap(tmp_path)
    run.record_probe_outcome("c1", outcome="inconclusive", detail="GET /c1 unproductive")
    run.record_probe_outcome("c1", outcome="inconclusive", detail="POST /c1 unproductive")

    # The DecisionEngine emitted REDIRECT: record the originating decision.
    run.record_pivot("c1", "c2", "inconclusive", detail="threshold reached")

    # The agent executes the selected alternative and reports pivot_executed.
    run.record_probe_outcome(
        "c2",
        outcome="inconclusive",
        detail="GET /c2 executed as the alternative",
        alternative_candidate="c2",
        pivot_executed=True,
        pivot_result="inconclusive",
    )

    decisions = [e for e in run.decision_trace if e.get("type") == "pivot_decision"]
    assert len(decisions) == 1, "no self-referential second decision"
    assert decisions[0]["candidate_id"] == "c1"
    assert decisions[0]["alternative_candidate"] == "c2"
    assert decisions[0]["executed"] is True
    assert run.pivot_count() == 1


def test_engine_executed_alternatives_excludes_preparatory(tmp_path: Path) -> None:
    """Only real engine probes prove an alternative was dispatched/executed."""
    from strix.interface.api import engine_executed_alternatives

    gap_file = tmp_path / "gap_state.json"
    gap_file.write_text(
        json.dumps(
            {
                "probe_outcomes": [
                    {"candidate_id": "c1", "preparatory": True},
                    {"candidate_id": "c2", "preparatory": True},
                    {"candidate_id": "c2"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert engine_executed_alternatives(gap_file) == {"c2"}
    assert engine_executed_alternatives(tmp_path / "missing.json") == set()


def test_preparatory_probe_is_not_alternative_execution() -> None:
    """A pre-decision preparatory probe cannot satisfy execution evidence."""
    from strix.interface.api import pivot_execution_after_decision

    decision = {"alternative_candidate": "c2", "at": "2026-11-18 10:00:00 UTC"}
    prep_probe = {
        "candidate_id": "c2",
        "at": "2026-11-18 09:59:00 UTC",
        "preparatory": True,
    }
    assert pivot_execution_after_decision(decision, [prep_probe]) is False

    agent_probe = {
        "candidate_id": "c2",
        "at": "2026-11-18 10:00:30 UTC",
        "pivot_executed": True,
    }
    assert pivot_execution_after_decision(decision, [prep_probe, agent_probe]) is True


def test_pivot_event_dedup_counts_one_genuine_pivot() -> None:
    """Bridge + native records of one executed pivot count once, not twice."""
    from strix.interface.api import dedupe_pivot_events, genuine_pivot_key

    bridge_event = {
        "event": "GAP2_PIVOT",
        "candidate_id": "c1",
        "next_candidate": "c2",
        "pivot_executed": True,
    }
    native_event = {
        "type": "pivot_decision",
        "candidate_id": "c1",
        "alternative_candidate": "c2",
        "next_candidate": "c2",
        "pivot_executed": True,
    }
    self_pivot = {
        "type": "pivot_decision",
        "candidate_id": "c2",
        "alternative_candidate": "c2",
        "next_candidate": "c2",
        "pivot_executed": True,
    }
    deduped = dedupe_pivot_events([bridge_event, native_event, self_pivot])
    assert len(deduped) == 2  # genuine pair + self-pivot event (not counted)
    assert sum(1 for e in deduped if genuine_pivot_key(e)) == 1
    assert genuine_pivot_key(bridge_event) == ("c1", "c2")
    assert genuine_pivot_key(self_pivot) is None


@pytest.mark.asyncio
async def test_outcome_tool_records_original_decision_on_redirect(tmp_path: Path) -> None:
    """The REDIRECT returned by the engine is persisted with its origin."""
    from unittest.mock import MagicMock

    from strix.core.decision_engine.engine import DecisionEngine
    from strix.core.decision_engine.schemas import ActionCandidate
    from strix.report.state import ReportState, set_global_report_state
    from strix.tools.reporting.outcome_tool import record_probe_outcome

    report_state = ReportState("pivot-tool-test")
    report_state._run_dir = tmp_path
    set_global_report_state(report_state)
    run = GapRun("pivot-tool-test", tmp_path, threshold=2)
    run.attach_candidate("c1", "Candidate 1", "/c1", "general", target="http://127.0.0.1:3000/")
    run.attach_candidate("c2", "Candidate 2", "/c2", "general", target="http://127.0.0.1:3000/")
    report_state.gap_run = run
    engine = DecisionEngine(pivot_threshold=2, authorized_targets=["http://127.0.0.1:3000/"])
    engine.initialize(
        [
            ActionCandidate(id="c1", endpoint="/c1", target="http://127.0.0.1:3000/"),
            ActionCandidate(id="c2", endpoint="/c2", target="http://127.0.0.1:3000/"),
        ]
    )
    ctx = MagicMock()
    ctx.tool_name = "record_probe_outcome"
    ctx.run_config = None
    ctx.context = {
        "agent_id": "root-agent",
        "gap_run": run,
        "decision_engine": engine,
        "scan_targets": ["http://127.0.0.1:3000/"],
    }

    for _ in range(2):
        result = await record_probe_outcome.on_invoke_tool(
            ctx,
            json.dumps(
                {
                    "candidate_id": "c1",
                    "probe_outcome": "inconclusive",
                    "detail": "real unproductive probe",
                }
            ),
        )
    data = json.loads(result)
    assert data["recommended_next_candidate"] == "c2"
    decisions = [e for e in run.decision_trace if e.get("type") == "pivot_decision"]
    assert len(decisions) == 1
    assert decisions[0]["candidate_id"] == "c1"
    assert decisions[0]["alternative_candidate"] == "c2"
    assert run.pivot_count() == 0  # decision alone is not a pivot


@pytest.mark.asyncio
async def test_verification_tool_reports_failure_for_unknown_report(tmp_path: Path) -> None:
    """A verification call for an uncreated finding must not claim success."""
    from unittest.mock import MagicMock

    from strix.report.state import ReportState, set_global_report_state
    from strix.tools.reporting.outcome_tool import record_vulnerability_outcome

    report_state = ReportState("verify-tool-test")
    report_state._run_dir = tmp_path
    set_global_report_state(report_state)

    ctx = MagicMock()
    ctx.tool_name = "record_vulnerability_outcome"
    ctx.run_config = None
    ctx.context = {"agent_id": "root-agent", "scan_id": "verify-tool-test"}

    response = await record_vulnerability_outcome.on_invoke_tool(
        ctx,
        json.dumps(
            {
                "report_id": "vuln-does-not-exist",
                "verification_state": "verified",
                "reproducible_request": "POST /rest/user/login ...",
                "verification_response": "HTTP 200 admin token",
                "verification_procedure": "baseline 401 then injection",
                "demonstrated_impact": "admin auth bypass",
                "evidence_timestamp": "2026-11-18T07:08:00 UTC",
            }
        ),
    )
    data = json.loads(response)
    assert data["success"] is False
    assert "create_vulnerability_report first" in data["error"]
    assert data["verification_state"] is None
