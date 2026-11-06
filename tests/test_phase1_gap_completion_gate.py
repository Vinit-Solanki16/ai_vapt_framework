"""Tests for Phase 1: GAP-1/GAP-2 Architecture and Completion Gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from strix.core import gap_bridge
from strix.tools.coverage.tools import _record_impl, hydrate_coverage_from_disk
from strix.tools.finish.tool import _evaluate_completion_gate, finish_scan
from strix.tools.reporting.tool import _attach_gap2


@pytest.fixture(autouse=True)
def _clean_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    gap_bridge.reset_state()
    monkeypatch.delenv(gap_bridge.CONTROL_DIR_ENV, raising=False)
    monkeypatch.delenv(gap_bridge.QUEUE_ENV, raising=False)
    monkeypatch.delenv(gap_bridge.THRESHOLD_ENV, raising=False)
    hydrate_coverage_from_disk(tmp_path / "state")
    yield
    gap_bridge.reset_state()


def _create_control_dir(
    tmp_path: Path, run_name: str, candidates: list[dict] | None = None
) -> Path:
    control = tmp_path / run_name / "control"
    control.mkdir(parents=True, exist_ok=True)
    if candidates is None:
        candidates = [
            {
                "candidate_id": "c1",
                "gap1_rank": 1,
                "title": "SQL Injection in Login",
                "endpoint": "/api/login",
                "method": "POST",
                "quality_rank": "high",
                "priority_score": 0.9,
            },
            {
                "candidate_id": "c2",
                "gap1_rank": 2,
                "title": "Sensitive Info Exposure in Metrics",
                "endpoint": "/metrics",
                "method": "GET",
                "quality_rank": "medium",
                "priority_score": 0.6,
            },
        ]
    payload = {
        "original_order": [c["candidate_id"] for c in candidates],
        "ranked_order": [c["candidate_id"] for c in candidates],
        "ranking_changed": False,
        "candidates": candidates,
    }
    (control / "gap1_queue.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return control


def test_simultaneous_runs_maintain_independent_gap_state(tmp_path: Path):
    """Test 1: Verify two simultaneous runs maintain independent GAP state and files."""
    ctrl_1 = _create_control_dir(tmp_path, "run_alpha")
    ctrl_2 = _create_control_dir(tmp_path, "run_beta")

    # Run 1 records 2 failures on c1 with threshold=2 -> pivots
    res1_a = gap_bridge.record_outcome(
        title="SQL Injection in Login",
        endpoint="/api/login",
        success=False,
        detail="Payload blocked by WAF",
        directory=ctrl_1,
    )
    assert res1_a["attempts"] == 1
    assert res1_a["pivot"] is False

    res1_b = gap_bridge.record_outcome(
        title="SQL Injection in Login",
        endpoint="/api/login",
        success=False,
        detail="Payload blocked again",
        directory=ctrl_1,
    )
    assert res1_b["attempts"] == 2
    assert res1_b["pivot"] is True
    assert res1_b["next_candidate"]["candidate_id"] == "c2"

    state_1 = gap_bridge.get_run_state(ctrl_1)
    assert "c1" in state_1.exhausted
    assert state_1.attempts.get("c1") == 2
    assert (ctrl_1 / "gap_state.json").is_file()

    # Run 2 state MUST remain pristine (independent run)
    state_2 = gap_bridge.get_run_state(ctrl_2)
    assert "c1" not in state_2.exhausted
    assert state_2.attempts.get("c1", 0) == 0

    # Run 2 records a success on c1
    res2 = gap_bridge.record_outcome(
        title="SQL Injection in Login",
        endpoint="/api/login",
        success=True,
        detail="Confirmed exploit",
        directory=ctrl_2,
    )
    assert res2["attempts"] == 1
    assert "c1" in state_2.completed
    assert "c1" not in state_1.completed


def test_negative_probe_results_reach_gap2(tmp_path: Path):
    """Test 2: Negative probe results (clean/no issue) complete candidate and advance queue."""
    ctrl = _create_control_dir(tmp_path, "run_test")
    state = gap_bridge.get_run_state(ctrl)

    outcome = gap_bridge.record_probe_result(
        title="SQL Injection in Login",
        endpoint="/api/login",
        outcome="negative",
        detail="Parameterized queries verified; benign canary inputs produce no error",
        directory=ctrl,
    )

    assert outcome["status"] == "negative"
    assert outcome["attempts"] == 1
    assert outcome["pivot"] is False
    assert "c1" in state.completed
    assert outcome["next_candidate"]["candidate_id"] == "c2"

    trace = (ctrl / "decision_trace.jsonl").read_text(encoding="utf-8")
    assert "GAP2_NEGATIVE_CONFIRMED" in trace
    assert "c1" in trace


def test_coverage_records_sync_negative_outcomes_to_gap2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test 2b: Verify record_coverage with no_issue_found synchronizes to GAP-2."""
    ctrl = _create_control_dir(tmp_path, "run_cov")
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(ctrl))

    res = _record_impl(
        surface="/api/login",
        risk_area="SQL Injection in Login",
        outcome="no_issue_found",
        evidence="Thoroughly fuzzed; strictly sanitized.",
        agent_id="agent-recon",
        agent_name="Recon Agent",
    )
    assert res["success"] is True

    state = gap_bridge.get_run_state(ctrl)
    assert "c1" in state.completed
    assert state.attempts.get("c1") == 1


def test_tool_errors_not_recorded_as_negative_security_findings(tmp_path: Path):
    """Test 3: Tool execution errors must NOT be recorded as security proofs or safe conclusions."""
    ctrl = _create_control_dir(tmp_path, "run_err")
    state = gap_bridge.get_run_state(ctrl)

    outcome = gap_bridge.record_probe_result(
        title="SQL Injection in Login",
        endpoint="/api/login",
        outcome="error",
        detail="ConnectionRefusedError: Failed to reach sandbox proxy",
        directory=ctrl,
    )

    assert outcome["status"] == "error"
    # Must NOT mark as completed/safe
    assert "c1" not in state.completed
    # Must NOT increment failure attempts towards abandonment
    assert state.attempts.get("c1", 0) == 0

    trace = (ctrl / "decision_trace.jsonl").read_text(encoding="utf-8")
    assert "GAP2_TOOL_ERROR" in trace


def test_attach_gap2_tool_error_preserves_error_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test 3b: _attach_gap2 with is_tool_error preserves error semantic."""
    ctrl = _create_control_dir(tmp_path, "run_attach_err")
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(ctrl))

    result = _attach_gap2(
        {"success": False, "error": "Invalid CVSS vector"},
        title="SQL Injection in Login",
        endpoint="/api/login",
        target="http://target.local",
        success=False,
        detail="cvss calculation error",
        is_tool_error=True,
        probe_status="error",
    )

    assert result["gap2"]["status"] == "error"
    state = gap_bridge.get_run_state(ctrl)
    assert "c1" not in state.completed
    assert state.attempts.get("c1", 0) == 0


def test_premature_finish_scan_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 4: Premature finish_scan call rejected when uninvestigated candidates remain."""
    ctrl = _create_control_dir(tmp_path, "run_premature")
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(ctrl))

    gate = _evaluate_completion_gate(control_dir=ctrl)
    assert gate["permitted"] is False
    assert "Premature completion rejected" in gate["error"]
    assert "c1" in gate["remaining_candidates"]
    assert "c2" in gate["remaining_candidates"]
    assert "Action items:" in gate["actionable_instructions"]


@pytest.mark.asyncio
async def test_finish_scan_tool_call_rejected_when_uninvestigated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test 4b: Calling finish_scan directly via tool interface fails when gate blocks it."""
    from agents.tool_context import ToolContext

    ctrl = _create_control_dir(tmp_path, "run_tool_reject")
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(ctrl))

    ctx = ToolContext(
        context={"agent_id": "root", "parent_id": None},
        tool_name="finish_scan",
        tool_call_id="call-finish-1",
        tool_arguments="{}",
    )
    payload = {
        "executive_summary": "Summary",
        "methodology": "Methodology",
        "technical_analysis": "Analysis",
        "recommendations": "Recommendations",
    }
    raw = await finish_scan.on_invoke_tool(ctx, json.dumps(payload))
    res = json.loads(raw)
    assert res["success"] is False
    assert res["scan_completed"] is False
    assert "Premature completion rejected" in res["error"]
    assert "c1" in res["remaining_candidates"]


def test_valid_early_completion_accepted_when_candidates_investigated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test 5: Legitimate early completion is accepted when all candidates are resolved or exhausted."""
    ctrl = _create_control_dir(tmp_path, "run_valid")
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(ctrl))
    monkeypatch.setenv(gap_bridge.THRESHOLD_ENV, "2")

    # Candidate 1: Verified safe (negative probe)
    gap_bridge.record_probe_result(
        title="SQL Injection in Login",
        endpoint="/api/login",
        outcome="negative",
        detail="Validated no SQL injection",
        directory=ctrl,
    )

    # Candidate 2: Attempted 2 times -> pivoted/exhausted
    gap_bridge.record_outcome(
        title="Sensitive Info Exposure in Metrics",
        endpoint="/metrics",
        success=False,
        detail="Attempt 1 fail",
        directory=ctrl,
    )
    gap_bridge.record_outcome(
        title="Sensitive Info Exposure in Metrics",
        endpoint="/metrics",
        success=False,
        detail="Attempt 2 fail - pivot",
        directory=ctrl,
    )

    state = gap_bridge.get_run_state(ctrl)
    assert "c1" in state.completed
    assert "c2" in state.exhausted

    # Gate should permit completion
    gate = _evaluate_completion_gate(control_dir=ctrl)
    assert gate["permitted"] is True
    assert gate["investigated_count"] == 2
    assert gate["total_candidates"] == 2


def test_valid_completion_with_zero_findings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 5b: Assessment with 0 findings is completely accepted if candidates are investigated clean."""
    ctrl = _create_control_dir(tmp_path, "run_zero_findings")
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(ctrl))

    # Both candidates proven clean
    gap_bridge.record_probe_result(
        title="SQL Injection in Login",
        endpoint="/api/login",
        outcome="negative",
        detail="Tested clean",
        directory=ctrl,
    )
    gap_bridge.record_probe_result(
        title="Sensitive Info Exposure in Metrics",
        endpoint="/metrics",
        outcome="negative",
        detail="Tested clean",
        directory=ctrl,
    )

    gate = _evaluate_completion_gate(control_dir=ctrl)
    assert gate["permitted"] is True
    assert gate["investigated_count"] == 2


def test_empty_candidate_queues_handled_correctly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 6: Empty candidate queue permits completion without error."""
    ctrl = _create_control_dir(tmp_path, "run_empty", candidates=[])
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(ctrl))

    gate = _evaluate_completion_gate(control_dir=ctrl)
    assert gate["permitted"] is True


def test_duplicate_probe_recording_avoided(tmp_path: Path):
    """Test 7: Duplicate completed recordings do not corrupt state."""
    ctrl = _create_control_dir(tmp_path, "run_dup")

    res1 = gap_bridge.record_probe_result(
        title="SQL Injection in Login",
        endpoint="/api/login",
        outcome="negative",
        detail="Clean",
        directory=ctrl,
    )
    assert res1["status"] == "negative"
    assert res1.get("duplicate") is not True

    # Immediate duplicate call
    res2 = gap_bridge.record_probe_result(
        title="SQL Injection in Login",
        endpoint="/api/login",
        outcome="negative",
        detail="Clean",
        directory=ctrl,
    )
    assert res2.get("duplicate") is True
    assert res2["attempts"] == 1
