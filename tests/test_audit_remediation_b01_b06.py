"""Regression tests for Phase P2 audit findings B01–B06.

Coverage:
- B01: Honest heuristic vs model scorer provenance and quality evaluation.
- B02: Original discovery order vs ranked queue order with ranking_changed tracking.
- B03: Candidate ticket dispatch scheduler, priority enforcement, override tracking.
- B04: Separate PIVOT_DECIDED and PIVOT_VERIFIED states; decision time does not execute.
- B05: Missing native GAP state fails closed; does not infer execution from next candidate ID.
- B06: Native pivot counting requires linked tool invocation record; rejects caller-supplied flag.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from strix.core.triage.exploit_assessor import (
    ExploitAssessment,
    UsabilityRank,
    assess_exploit_quality,
    run_gap1_triage,
)
from strix.core.scheduler import CandidateScheduler, CandidateTicket
from strix.core.decision_engine.engine import DecisionEngine, Outcome
from strix.core.decision_engine.schemas import ActionCandidate, PivotActionType
from strix.core.gap_bridge import (
    GapRunState,
    note_event,
    queue_order,
    record_alternative_dispatched,
    record_alternative_tool_completed,
    record_outcome,
    record_pivot_verified,
    reset_state,
)
from strix.core.gap_run import GapRun, GapRunError
from strix.interface.api import genuine_pivot_key


# ---------------------------------------------------------------------------
# B01 Tests: Honest Scorer Provenance
# ---------------------------------------------------------------------------

def test_b01_heuristic_scorer_provenance() -> None:
    """Heuristic assessment must record scorer_type='heuristic' and explicit fallback reason."""
    assessment = assess_exploit_quality("sqli-vuln-01", provider="heuristic")
    assert assessment.scorer_type == "heuristic"
    assert assessment.fallback_reason == "deterministic_rule_engine"
    assert assessment.scoring_provenance["scorer_type"] == "heuristic"
    assert assessment.scoring_provenance["fallback_reason"] == "deterministic_rule_engine"
    assert "complexity_score" in assessment.features_used
    assert "network_noise" in assessment.features_used


def test_b01_model_scorer_provenance_when_configured() -> None:
    """Model assessment must record scorer_type='model' with model_name and no fallback reason."""
    assessment = assess_exploit_quality(
        "cmd-injection-01",
        provider="openai",
        model_name="gpt-4o-mini",
        api_key="sk-test-mock-key",
    )
    assert assessment.scorer_type == "model"
    assert assessment.model_name == "gpt-4o-mini"
    assert assessment.fallback_reason is None
    assert assessment.scoring_provenance["scorer_type"] == "model"
    assert assessment.scoring_provenance["model_name"] == "gpt-4o-mini"


def test_b01_triage_candidates_include_provenance() -> None:
    """run_gap1_triage must attach honest provenance to every returned candidate."""
    candidates = run_gap1_triage(scenario="default")
    assert len(candidates) > 0
    for cand in candidates:
        assert "scorer_type" in cand
        assert "scoring_provenance" in cand
        assert cand["scorer_type"] in ("heuristic", "model")
        assert cand["scoring_provenance"]["scorer_version"] == "1.0.0"


# ---------------------------------------------------------------------------
# B02 Tests: Discovery Order vs Ranked Order
# ---------------------------------------------------------------------------

def test_b02_discovery_order_and_ranking_changed() -> None:
    """run_gap1_triage must record discovery_order and detect when ranking changed."""
    candidates = run_gap1_triage(scenario="docker_pivot")
    assert len(candidates) >= 2

    orig_order = candidates[0].get("original_order")
    ranked_order = candidates[0].get("ranked_order")
    assert orig_order is not None
    assert ranked_order is not None
    assert len(orig_order) == len(ranked_order)

    # In docker_pivot or default scenario, verify candidates track discovery_order
    for idx, c in enumerate(candidates, 1):
        assert "discovery_order" in c
        assert "priority_rank" in c
        assert c["priority_rank"] == idx
        assert "ranking_changed" in c


def test_b02_queue_order_preserves_distinct_lists(tmp_path: Path) -> None:
    """gap1_queue.json must record both discovery order and ranked order distinctly."""
    control_dir = tmp_path / "control"
    control_dir.mkdir(parents=True)
    payload = {
        "candidates": [
            {"candidate_id": "c2", "discovery_order": 1, "gap1_rank": 2},
            {"candidate_id": "c1", "discovery_order": 2, "gap1_rank": 1},
        ],
        "original_order": ["c2", "c1"],
        "ranked_order": ["c1", "c2"],
        "ranking_changed": True,
    }
    (control_dir / "gap1_queue.json").write_text(json.dumps(payload), encoding="utf-8")

    orig, ranked = queue_order(control_dir)
    assert orig == ["c2", "c1"]
    assert ranked == ["c1", "c2"]
    assert orig != ranked


# ---------------------------------------------------------------------------
# B03 Tests: Candidate Ticket Scheduler & Dispatch Enforcement
# ---------------------------------------------------------------------------

def test_b03_scheduler_priority_dispatch() -> None:
    """Scheduler must dispatch tickets strictly in priority order."""
    queue = [
        {"id": "cand-high", "priority_rank": 1, "discovery_order": 2},
        {"id": "cand-med", "priority_rank": 2, "discovery_order": 1},
        {"id": "cand-low", "priority_rank": 3, "discovery_order": 3},
    ]
    scheduler = CandidateScheduler(run_id="run-test001", queue=queue)
    assert scheduler.ranking_changed is True

    t1 = scheduler.dispatch_next()
    assert t1 is not None
    assert t1.candidate_id == "cand-high"
    assert t1.dispatch_priority == 1
    assert t1.dispatched_order == 1

    t2 = scheduler.dispatch_next()
    assert t2 is not None
    assert t2.candidate_id == "cand-med"
    assert t2.dispatch_priority == 2
    assert t2.dispatched_order == 2


def test_b03_scheduler_blocks_unranked_dispatch_without_override() -> None:
    """Adversarial request for a lower-ranked candidate must be blocked without override reason."""
    queue = [
        {"id": "cand-p1", "priority_rank": 1},
        {"id": "cand-p2", "priority_rank": 2},
    ]
    scheduler = CandidateScheduler(run_id="run-adv001", queue=queue)

    # Attempt to dispatch cand-p2 before cand-p1 without override reason
    authorized, ticket, reason = scheduler.authorize_dispatch("cand-p2", override_reason="")
    assert authorized is False
    assert ticket is None
    assert "Unranked dispatch rejected" in reason
    assert "cand-p1" in reason


def test_b03_scheduler_authorizes_unranked_dispatch_with_override() -> None:
    """Adversarial request for a lower-ranked candidate is allowed when an authorized override is logged."""
    queue = [
        {"id": "cand-p1", "priority_rank": 1},
        {"id": "cand-p2", "priority_rank": 2},
    ]
    scheduler = CandidateScheduler(run_id="run-adv002", queue=queue)

    authorized, ticket, reason = scheduler.authorize_dispatch(
        "cand-p2",
        override_reason="Operator requested targeted check on endpoint /admin",
    )
    assert authorized is True
    assert ticket is not None
    assert ticket.status == "OVERRIDDEN"
    assert ticket.override_reason == "Operator requested targeted check on endpoint /admin"
    assert ticket.dispatched_order == 1

    audit = scheduler.audit_trail()
    assert len(audit["overrides"]) == 1
    assert audit["overrides"][0]["candidate_id"] == "cand-p2"


# ---------------------------------------------------------------------------
# B04 Tests: GAP-2 Separate Decision and Execution Stages
# ---------------------------------------------------------------------------

def test_b04_decision_engine_sets_pivot_executed_false_at_decision_time() -> None:
    """DecisionEngine.record_outcome must NOT set pivot_executed=True at decision time."""
    engine = DecisionEngine(pivot_threshold=2)
    engine.initialize([
        ActionCandidate(id="cand-1", max_attempts=2),
        ActionCandidate(id="cand-2", max_attempts=2),
    ])

    # First attempt fails -> retry
    act1 = engine.record_outcome("cand-1", Outcome.FAIL_TIMEOUT)
    assert act1.action == PivotActionType.RETRY

    # Second attempt fails -> threshold reached -> REDIRECT decided
    act2 = engine.record_outcome("cand-1", Outcome.FAIL_TIMEOUT)
    assert act2.action == PivotActionType.REDIRECT
    assert act2.to_candidate == "cand-2"

    # Verify event at decision time has pivot_executed=False
    decision_events = [e for e in engine.pivot_events if e.to_candidate == "cand-2"]
    assert len(decision_events) == 1
    dec_event = decision_events[0]
    assert dec_event.event == "PIVOT_DECIDED"
    assert dec_event.pivot_executed is False
    assert dec_event.pivot_status == "PIVOT_DECIDED"


def test_b04_gap_bridge_records_pivot_decided_with_executed_false(tmp_path: Path) -> None:
    """gap_bridge.record_outcome must emit PIVOT_DECIDED with pivot_executed=False."""
    control_dir = tmp_path / "control"
    control_dir.mkdir(parents=True)
    reset_state(control_dir)

    payload = {
        "candidates": [
            {"candidate_id": "cand-a", "title": "cand-a", "endpoint": "/a"},
            {"candidate_id": "cand-b", "title": "cand-b", "endpoint": "/b"},
        ]
    }
    (control_dir / "gap1_queue.json").write_text(json.dumps(payload), encoding="utf-8")

    st = GapRunState(control_dir, threshold_override=1)

    res = record_outcome(
        title="cand-a",
        endpoint="/a",
        target="http://127.0.0.1",
        success=False,
        directory=control_dir,
        state=st,
        probe_status="inconclusive",
    )
    assert res["pivot"] is True
    assert res["pivot_executed"] is False
    assert res["pivot_status"] == "PIVOT_DECIDED"

    # Verify decision trace has pivot_executed=False
    trace_file = control_dir / "decision_trace.jsonl"
    lines = [json.loads(l) for l in trace_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    pivot_lines = [l for l in lines if l.get("event") == "PIVOT_DECIDED"]
    assert len(pivot_lines) == 1
    assert pivot_lines[0]["pivot_executed"] is False


def test_b04_verified_pivot_requires_tool_invocation_id(tmp_path: Path) -> None:
    """record_pivot_verified requires a non-empty tool_invocation_id and sets pivot_executed=True."""
    control_dir = tmp_path / "control"
    control_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="tool_invocation_id"):
        record_pivot_verified("cand-a", "cand-b", "", directory=control_dir)

    ev = record_pivot_verified("cand-a", "cand-b", "INVOC-0091", directory=control_dir)
    assert ev["event"] == "PIVOT_VERIFIED"
    assert ev["pivot_executed"] is True
    assert ev["tool_invocation_id"] == "INVOC-0091"


# ---------------------------------------------------------------------------
# B05 Tests: Missing Native GAP State Fails Closed
# ---------------------------------------------------------------------------

def test_b05_missing_native_gap_state_does_not_infer_execution() -> None:
    """When native gap_state.json is missing or unavailable, executed must be False."""
    from strix.interface.api import engine_executed_alternatives

    # Non-existent file
    missing_file = Path("/tmp/nonexistent_gap_state_xyz123.json")
    evidence = engine_executed_alternatives(missing_file)
    assert evidence == set()

    # None file
    assert engine_executed_alternatives(None) == set()


def test_b05_genuine_pivot_key_rejects_non_executed_events() -> None:
    """genuine_pivot_key returns None when pivot_executed is False or not explicitly True."""
    # False
    assert genuine_pivot_key({
        "event": "GAP2_PIVOT",
        "candidate_id": "c1",
        "next_candidate": "c2",
        "pivot_executed": False,
    }) is None

    # Missing
    assert genuine_pivot_key({
        "event": "GAP2_PIVOT",
        "candidate_id": "c1",
        "next_candidate": "c2",
    }) is None

    # True with valid distinct candidates
    key = genuine_pivot_key({
        "event": "GAP2_PIVOT",
        "candidate_id": "c1",
        "next_candidate": "c2",
        "pivot_executed": True,
    })
    assert key == ("c1", "c2")


# ---------------------------------------------------------------------------
# B06 Tests: Native Pivot Counting Requires Linked Tool Invocation
# ---------------------------------------------------------------------------

def test_b06_gap_run_rejects_caller_supplied_flag_without_tool_id(tmp_path: Path) -> None:
    """GapRun.record_probe_outcome forces pivot_executed=False if tool_invocation_id is missing."""
    gap_run = GapRun("run-b06-01", state_dir=tmp_path)
    gap_run.attach_candidate("cand-1", "Test Cand 1", "/", category="general")
    gap_run.attach_candidate("cand-2", "Test Cand 2", "/alt", category="general")

    # Caller passes pivot_executed=True without tool_invocation_id
    entry = gap_run.record_probe_outcome(
        "cand-1",
        outcome="negative",
        alternative_candidate="cand-2",
        pivot_executed=True,
        pivot_result="positive",
        tool_invocation_id=None,
    )
    assert entry["pivot_executed"] is False
    assert gap_run.pivot_count() == 0


def test_b06_gap_run_accepts_pivot_with_verified_tool_id(tmp_path: Path) -> None:
    """GapRun increments pivot_count when a valid tool_invocation_id is provided."""
    gap_run = GapRun("run-b06-02", state_dir=tmp_path)
    gap_run.attach_candidate("cand-1", "Test Cand 1", "/", category="general")
    gap_run.attach_candidate("cand-2", "Test Cand 2", "/alt", category="general")

    entry = gap_run.record_probe_outcome(
        "cand-1",
        outcome="negative",
        alternative_candidate="cand-2",
        pivot_executed=True,
        pivot_result="positive",
        tool_invocation_id="TOOL-INVOC-7788",
    )
    assert entry["pivot_executed"] is True
    assert entry["tool_invocation_id"] == "TOOL-INVOC-7788"
    assert gap_run.pivot_count() == 1
