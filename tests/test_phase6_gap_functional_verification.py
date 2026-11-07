"""Phase 6: End-to-end functional verification tests for GAP1 and GAP2.

Verifies:
1. GAP1 candidate queue consumption and prioritization order.
2. Candidate matching via IDs, bracketed tags, endpoints, and titles.
3. Positive outcome recording (vulnerability reported) completing candidate.
4. Negative outcome recording (surface safe/ruled out) completing candidate.
5. Inconclusive probe recording incrementing attempts without false completion.
6. GAP2 dynamic pivot generation when failure threshold k=2 is reached.
7. GAP2 pivot guidance delivery directly inside tool return payloads (record_coverage, update_coverage, reporting).
8. Tool error handling (recorded without false completion or premature exhaustion).
9. Completion gate enforcement ensuring uninvestigated candidates block completion.
10. Subagent outcome protocol and prompt injection.
11. Telemetry and milestone synchronization in API runner.
12. Strict per-run state isolation across concurrent assessments.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from strix.core import gap_bridge
from strix.core.gap_bridge import (
    GapRunState,
    candidate_id_for,
    gap1_instruction_block,
    load_queue,
    next_candidate,
    record_outcome,
    record_probe_result,
    reset_state,
)
from strix.core.inputs import child_initial_input
from strix.tools.coverage.tools import (
    _record_impl,
    _update_impl,
    reset_coverage_state,
)
from strix.tools.finish.tool import _evaluate_completion_gate


def _create_sample_queue(control_dir: Path) -> list[dict[str, Any]]:
    candidates = [
        {
            "candidate_id": "c1",
            "title": "SQL Injection in Search",
            "endpoint": "/rest/products/search",
            "method": "GET",
            "gap1_rank": 1,
            "quality_rank": "high",
            "priority_score": 95.0,
            "assessment_reasoning": "Direct parameter reflection in SQL query",
        },
        {
            "candidate_id": "c2",
            "title": "XSS in Customer Feedback",
            "endpoint": "/api/feedbacks",
            "method": "POST",
            "gap1_rank": 2,
            "quality_rank": "medium",
            "priority_score": 80.0,
            "assessment_reasoning": "Unescaped comment rendering in administration view",
        },
        {
            "candidate_id": "c3",
            "title": "IDOR in User Profile",
            "endpoint": "/rest/user/profile",
            "method": "GET",
            "gap1_rank": 3,
            "quality_rank": "medium",
            "priority_score": 75.0,
            "assessment_reasoning": "Sequential integer ID parameter with no ownership check",
        },
    ]
    queue_payload = {
        "original_order": ["c1", "c2", "c3"],
        "ranked_order": ["c1", "c2", "c3"],
        "candidates": candidates,
    }
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "gap1_queue.json").write_text(json.dumps(queue_payload), encoding="utf-8")
    return candidates


@pytest.fixture(autouse=True)
def cleanup_states(tmp_path: Path):
    reset_state()
    reset_coverage_state()
    yield
    reset_state()
    reset_coverage_state()


def test_gap1_queue_consumption_and_prioritization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 1: GAP-1 candidate queue is loaded in prioritized order and first candidate is selected."""
    control_dir = tmp_path / "run_test1"
    monkeypatch.setenv("STRIX_GAP_CONTROL_DIR", str(control_dir))
    monkeypatch.setenv("STRIX_GAP1_ENABLED", "1")
    _create_sample_queue(control_dir)

    # Verify queue loaded correctly
    queue = load_queue(control_dir)
    assert len(queue) == 3
    assert queue[0]["candidate_id"] == "c1"
    assert queue[1]["candidate_id"] == "c2"
    assert queue[2]["candidate_id"] == "c3"

    # Verify prompt instruction block contains prioritized candidates
    prompt = gap1_instruction_block(control_dir)
    assert "AI_VAPT GAP-1 prioritized candidate queue" in prompt
    assert "[c1] SQL Injection in Search" in prompt
    assert "[c2] XSS in Customer Feedback" in prompt
    assert "[c3] IDOR in User Profile" in prompt
    assert "Investigation & Outcome Recording Instructions:" in prompt

    # Verify next_candidate returns the first unassessed candidate (c1)
    first = next_candidate(control_dir)
    assert first is not None
    assert first["candidate_id"] == "c1"


def test_candidate_matching_resilience(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 2: Candidate resolution handles exact ID, bracketed ID, endpoint, and title."""
    control_dir = tmp_path / "run_test2"
    monkeypatch.setenv("STRIX_GAP_CONTROL_DIR", str(control_dir))
    _create_sample_queue(control_dir)

    # Match by exact ID
    assert candidate_id_for(title="c1", endpoint="", target="", directory=control_dir) == "c1"
    assert candidate_id_for(title="", endpoint="c2", target="", directory=control_dir) == "c2"

    # Match by bracketed tag in title
    assert (
        candidate_id_for(
            title="[c1] Testing SQL Injection", endpoint="", target="", directory=control_dir
        )
        == "c1"
    )
    assert (
        candidate_id_for(title="c3 in profile view", endpoint="", target="", directory=control_dir)
        == "c3"
    )

    # Match by endpoint
    assert (
        candidate_id_for(
            title="", endpoint="/rest/products/search", target="", directory=control_dir
        )
        == "c1"
    )
    assert (
        candidate_id_for(title="", endpoint="/api/feedbacks", target="", directory=control_dir)
        == "c2"
    )

    # Match by title substring
    assert (
        candidate_id_for(
            title="SQL Injection in Search", endpoint="", target="", directory=control_dir
        )
        == "c1"
    )
    assert (
        candidate_id_for(title="Customer Feedback", endpoint="", target="", directory=control_dir)
        == "c2"
    )


def test_positive_outcome_completes_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 3: Confirmed positive vulnerability records GAP2_SUCCESS and completes candidate."""
    control_dir = tmp_path / "run_test3"
    monkeypatch.setenv("STRIX_GAP_CONTROL_DIR", str(control_dir))
    monkeypatch.setenv("STRIX_GAP2_ENABLED", "1")
    _create_sample_queue(control_dir)

    res = record_outcome(
        candidate_id="c1",
        title="SQL Injection in Search",
        endpoint="/rest/products/search",
        probe_status="positive",
        detail="UNION SELECT confirmed 1=1 data leak",
        report_id="vuln-001",
        directory=control_dir,
    )

    assert res["status"] == "positive"
    assert res["pivot"] is False

    st = gap_bridge.get_run_state(control_dir)
    assert "c1" in st.completed
    assert "c1" not in st.exhausted
    assert st.attempts.get("c1", 0) == 1

    # Decision trace logged GAP2_SUCCESS
    trace_lines = (control_dir / "decision_trace.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in trace_lines]
    success_events = [e for e in events if e.get("event") == "GAP2_SUCCESS"]
    assert len(success_events) == 1
    assert success_events[0]["candidate_id"] == "c1"
    assert success_events[0]["report_id"] == "vuln-001"

    # Next candidate is c2
    assert next_candidate(control_dir)["candidate_id"] == "c2"


def test_negative_outcome_completes_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 4: Negative outcome (safe/ruled out) records GAP2_NEGATIVE_CONFIRMED and completes candidate."""
    control_dir = tmp_path / "run_test4"
    monkeypatch.setenv("STRIX_GAP_CONTROL_DIR", str(control_dir))
    monkeypatch.setenv("STRIX_GAP2_ENABLED", "1")
    _create_sample_queue(control_dir)

    # Record clean outcome via _record_impl
    cov_res = _record_impl(
        surface="/rest/products/search",
        risk_area="SQL Injection in Search",
        outcome="no_issue_found",
        evidence="Endpoint strictly uses parameterized prepared statements with integer binding",
        agent_id="test_agent",
        agent_name="TestAgent",
    )

    assert cov_res["success"] is True
    assert cov_res["outcome"] == "no_issue_found"
    assert cov_res.get("gap2", {}).get("status") == "negative"

    st = gap_bridge.get_run_state(control_dir)
    assert "c1" in st.completed
    assert "c1" not in st.exhausted
    assert st.attempts.get("c1", 0) == 1

    # Decision trace logged GAP2_NEGATIVE_CONFIRMED
    trace_lines = (control_dir / "decision_trace.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in trace_lines]
    neg_events = [e for e in events if e.get("event") == "GAP2_NEGATIVE_CONFIRMED"]
    assert len(neg_events) == 1
    assert neg_events[0]["candidate_id"] == "c1"

    # Next candidate advances to c2
    assert next_candidate(control_dir)["candidate_id"] == "c2"


def test_inconclusive_outcome_and_dynamic_pivot_at_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test 5 & 6: Inconclusive attempts increment until threshold k=2 triggers GAP2_PIVOT with guidance."""
    control_dir = tmp_path / "run_test5"
    monkeypatch.setenv("STRIX_GAP_CONTROL_DIR", str(control_dir))
    monkeypatch.setenv("STRIX_GAP2_ENABLED", "1")
    monkeypatch.setenv("STRIX_GAP2_THRESHOLD", "2")
    _create_sample_queue(control_dir)

    # Attempt 1: Inconclusive probe via _record_impl
    cov1 = _record_impl(
        surface="/rest/products/search",
        risk_area="SQL Injection in Search",
        outcome="needs_follow_up",
        evidence="WAF returned 403 on single quote; further probe required",
        agent_id="test_agent",
        agent_name="TestAgent",
    )
    assert cov1["success"] is True
    assert cov1.get("gap2", {}).get("attempts") == 1
    assert cov1.get("gap2", {}).get("pivot") is False
    assert "pivot_guidance" not in cov1

    st = gap_bridge.get_run_state(control_dir)
    assert st.attempts.get("c1") == 1
    assert "c1" not in st.exhausted
    assert "c1" not in st.completed
    # c1 is still active
    assert next_candidate(control_dir)["candidate_id"] == "c1"

    # Attempt 2: Second inconclusive probe via _update_impl
    cov2 = _update_impl(
        entry_id=cov1["entry_id"],
        outcome="needs_follow_up",
        evidence="Second obfuscated payload also blocked by Cloudflare; route exhausted",
        agent_id="test_agent",
        agent_name="TestAgent",
    )
    assert cov2["success"] is True
    assert cov2.get("gap2", {}).get("attempts") == 2
    assert cov2.get("gap2", {}).get("pivot") is True

    # Verify pivot guidance is returned in tool result
    assert "pivot_guidance" in cov2
    guidance = cov2["pivot_guidance"]
    assert "GAP-2 PIVOT: candidate c1 reached the failure threshold (2/2)" in guidance
    assert "pivot to XSS in Customer Feedback" in guidance

    # Verify state persistence
    st = gap_bridge.get_run_state(control_dir)
    assert "c1" in st.exhausted
    assert "c1" not in st.completed

    # Decision trace logged GAP2_PIVOT event
    trace_lines = (control_dir / "decision_trace.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in trace_lines]
    pivots = [e for e in events if e.get("event") == "GAP2_PIVOT"]
    assert len(pivots) == 1
    assert pivots[0]["candidate_id"] == "c1"
    assert pivots[0]["next_candidate"] == "c2"

    # GAP2 dynamically pivoted to candidate c2
    nxt = next_candidate(control_dir)
    assert nxt is not None
    assert nxt["candidate_id"] == "c2"


def test_tool_error_does_not_cause_false_completion_or_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test 7: Tool errors are logged as GAP2_TOOL_ERROR without counting as safety or failure exhaustion."""
    control_dir = tmp_path / "run_test7"
    monkeypatch.setenv("STRIX_GAP_CONTROL_DIR", str(control_dir))
    monkeypatch.setenv("STRIX_GAP2_ENABLED", "1")
    _create_sample_queue(control_dir)

    res = record_probe_result(
        title="SQL Injection in Search",
        endpoint="/rest/products/search",
        outcome="error",
        detail="Connection reset by peer during socket read",
        directory=control_dir,
    )

    assert res["status"] == "error"
    assert res["pivot"] is False

    st = gap_bridge.get_run_state(control_dir)
    assert "c1" not in st.completed
    assert "c1" not in st.exhausted
    assert st.attempts.get("c1", 0) == 0

    trace_lines = (control_dir / "decision_trace.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in trace_lines]
    error_events = [e for e in events if e.get("event") == "GAP2_TOOL_ERROR"]
    assert len(error_events) == 1
    assert error_events[0]["candidate_id"] == "c1"


def test_completion_gate_enforcement_with_gap1_and_gap2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test 8: Completion gate rejects finish_scan while unaddressed candidates exist, permits when all are resolved."""
    control_dir = tmp_path / "run_test8"
    monkeypatch.setenv("STRIX_GAP_CONTROL_DIR", str(control_dir))
    monkeypatch.setenv("STRIX_GAP1_ENABLED", "1")
    monkeypatch.setenv("STRIX_GAP2_ENABLED", "1")
    _create_sample_queue(control_dir)

    # Initially, all 3 candidates are unaddressed -> completion gate rejects
    gate1 = _evaluate_completion_gate(control_dir=control_dir)
    assert gate1["permitted"] is False
    assert "Premature completion rejected: 3 of 3 prioritized candidate(s)" in gate1["error"]

    # Candidate c1 is completed via positive finding
    record_outcome(
        candidate_id="c1",
        title="SQL Injection in Search",
        endpoint="/rest/products/search",
        probe_status="positive",
        directory=control_dir,
    )

    gate2 = _evaluate_completion_gate(control_dir=control_dir)
    assert gate2["permitted"] is False
    assert "2 of 3 prioritized candidate(s)" in gate2["error"]

    # Candidate c2 is exhausted via GAP2 pivot
    st = gap_bridge.get_run_state(control_dir)
    st.mark_exhausted("c2")

    gate3 = _evaluate_completion_gate(control_dir=control_dir)
    assert gate3["permitted"] is False
    assert "1 of 3 prioritized candidate(s)" in gate3["error"]

    # Candidate c3 is covered via _record_impl
    _record_impl(
        surface="/rest/user/profile",
        risk_area="IDOR in User Profile",
        outcome="no_issue_found",
        evidence="Access token claims verified on backend against requested user ID",
        agent_id="test_agent",
        agent_name="TestAgent",
    )

    # Now all 3 candidates are resolved (c1 positive, c2 exhausted, c3 clean)
    gate4 = _evaluate_completion_gate(control_dir=control_dir)
    assert gate4["permitted"] is True
    assert gate4["investigated_count"] == 3


def test_child_agent_outcome_protocol_injection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 9: Child agents receive the outcome protocol and identity in their initial prompt."""
    control_dir = tmp_path / "run_test9"
    monkeypatch.setenv("STRIX_GAP_CONTROL_DIR", str(control_dir))
    monkeypatch.setenv("STRIX_GAP1_ENABLED", "1")

    prompt_items = child_initial_input(
        name="SQLi Specialist",
        child_id="agent_sqli_1",
        parent_id="root_agent",
        task="Test SQL injection on candidate [c1] /rest/products/search",
        parent_history=[],
    )

    assert len(prompt_items) == 1
    content = prompt_items[0]["content"]
    assert "You are agent SQLi Specialist (agent_sqli_1); your parent is root_agent." in content
    assert "Test SQL injection on candidate [c1] /rest/products/search" in content
    assert "AI_VAPT Outcome Protocol:" in content
    assert (
        "record_coverage(surface=endpoint, risk_area=title, outcome='no_issue_found' or 'needs_follow_up')"
        in content
    )


def test_per_run_state_isolation_concurrent(tmp_path: Path):
    """Test 10: Two concurrent runs with distinct control directories maintain strictly isolated state."""
    dir_a = tmp_path / "run_A"
    dir_b = tmp_path / "run_B"

    _create_sample_queue(dir_a)
    _create_sample_queue(dir_b)

    state_a = gap_bridge.get_run_state(dir_a)
    state_b = gap_bridge.get_run_state(dir_b)

    # Run A records 1 attempt on c1
    record_outcome(
        candidate_id="c1",
        endpoint="/rest/products/search",
        probe_status="inconclusive",
        state=state_a,
    )
    # Run B records positive on c1
    record_outcome(
        candidate_id="c1", endpoint="/rest/products/search", probe_status="positive", state=state_b
    )

    assert state_a.attempts.get("c1") == 1
    assert "c1" not in state_a.completed

    assert state_b.attempts.get("c1", 0) == 1
    assert "c1" in state_b.completed

    # Fresh instance re-read from disk
    fresh_a = GapRunState(dir_a)
    fresh_b = GapRunState(dir_b)
    assert fresh_a.attempts.get("c1") == 1
    assert "c1" not in fresh_a.completed
    assert "c1" in fresh_b.completed


def test_api_telemetry_synchronization_with_gap1_and_gap2(tmp_path: Path):
    """Test 11: Real-time telemetry sync in API runner reflects candidate investigation, positive validation, and GAP2 pivot."""
    import subprocess
    import sys
    import time
    from unittest.mock import patch

    from strix.interface.api import _RUNS, _execute_run_worker
    from strix.interface.schemas import RunRequest

    run_id = f"test-gap-telemetry-{int(time.time() * 1000)}"
    fake_strix_runs = tmp_path / "strix_runs"
    fake_strix_runs.mkdir(parents=True, exist_ok=True)
    control_dir = fake_strix_runs / run_id / "control"
    control_dir.mkdir(parents=True, exist_ok=True)

    candidates_list = [
        {
            "id": "c1",
            "candidate_id": "c1",
            "name": "SQL Injection",
            "title": "SQL Injection",
            "endpoint": "/rest/products/search",
            "priority_score": 90.0,
        },
        {
            "id": "c2",
            "candidate_id": "c2",
            "name": "XSS Feedback",
            "title": "XSS Feedback",
            "endpoint": "/api/feedbacks",
            "priority_score": 80.0,
        },
        {
            "id": "c3",
            "candidate_id": "c3",
            "name": "IDOR Profile",
            "title": "IDOR Profile",
            "endpoint": "/rest/user/profile",
            "priority_score": 70.0,
        },
    ]
    queue_payload = {
        "original_order": ["c1", "c2", "c3"],
        "ranked_order": ["c1", "c2", "c3"],
        "candidates": candidates_list,
    }
    (control_dir / "gap1_queue.json").write_text(json.dumps(queue_payload), encoding="utf-8")

    # Mock subprocess that writes:
    # 1. c1 validated (positive finding)
    # 2. c2 exhausted via GAP2 pivot after 2 attempts
    script = (
        "import sys, time, json\n"
        "from pathlib import Path\n"
        f"run_dir = Path({str(fake_strix_runs / 'sub-run-gap')!r})\n"
        f"ctrl_dir = Path({str(control_dir)!r})\n"
        "run_dir.mkdir(parents=True, exist_ok=True)\n"
        "print('Output strix_runs/sub-run-gap', flush=True)\n"
        "with open(run_dir / 'strix.log', 'a') as f:\n"
        "    f.write('INFO - Starting scan\\n')\n"
        "    f.write('DEBUG - openai.agents: Starting turn 1, current_agent=Root Agent\\n')\n"
        "    f.flush()\n"
        "time.sleep(0.05)\n"
        "# Update gap_state: c1 completed (positive), c2 exhausted with 2 attempts\n"
        "state_data = {\n"
        "    'attempts': {'c1': 1, 'c2': 2},\n"
        "    'exhausted': ['c2'],\n"
        "    'completed': ['c1'],\n"
        "    'announced': True,\n"
        "    'probe_outcomes': [\n"
        "        {'candidate_id': 'c1', 'status': 'positive', 'detail': 'SQLi confirmed'},\n"
        "        {'candidate_id': 'c2', 'status': 'inconclusive', 'detail': 'Attempt 1'},\n"
        "        {'candidate_id': 'c2', 'status': 'inconclusive', 'detail': 'Attempt 2'}\n"
        "    ]\n"
        "}\n"
        "(ctrl_dir / 'gap_state.json').write_text(json.dumps(state_data))\n"
        "pivot_event = {\n"
        "    'event': 'GAP2_PIVOT',\n"
        "    'candidate_id': 'c2',\n"
        "    'outcome': 'ABANDON',\n"
        "    'attempts': 2,\n"
        "    'threshold': 2,\n"
        "    'next_candidate': 'c3',\n"
        "    'message': 'GAP-2 threshold reached for c2; abandon it and pivot to c3'\n"
        "}\n"
        "with open(ctrl_dir / 'decision_trace.jsonl', 'a') as tf:\n"
        "    tf.write(json.dumps(pivot_event) + '\\n')\n"
        "vulns = [{'title': 'SQL Injection', 'location': '/rest/products/search', 'severity': 'high'}]\n"
        "(run_dir / 'vulnerabilities.json').write_text(json.dumps(vulns))\n"
        "time.sleep(0.05)\n"
        "(run_dir / 'run.json').write_text(json.dumps({'status': 'completed', 'vulnerabilities': vulns}))\n"
        "sys.exit(0)\n"
    )

    run_entry: dict[str, Any] = {
        "run_id": run_id,
        "status": "queued",
        "scenario": "web_assessment",
        "mode": "autonomous",
        "target_url": "http://127.0.0.1:3000",
        "created_at": "2026-11-06T00:00:00Z",
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [
            {
                "id": "c1",
                "name": "SQL Injection",
                "endpoint": "/rest/products/search",
                "state": "PENDING",
            },
            {"id": "c2", "name": "XSS Feedback", "endpoint": "/api/feedbacks", "state": "PENDING"},
            {
                "id": "c3",
                "name": "IDOR Profile",
                "endpoint": "/rest/user/profile",
                "state": "PENDING",
            },
        ],
        "findings": [],
        "stats": {"attempts": 0, "pivots": 0, "findings": 0},
    }
    _RUNS[run_id] = run_entry

    req = RunRequest(
        target_url="http://127.0.0.1:3000",
        mode="autonomous",
        scan_mode="quick",
        max_turns=50,
    )

    orig_popen = subprocess.Popen
    with (
        patch("strix.interface.api.runs_base_dir", return_value=fake_strix_runs),
        patch("strix.interface.api.PROJECT_ROOT", tmp_path),
        patch("strix.interface.api._is_docker_available", return_value=True),
        patch("strix.core.triage.exploit_assessor.run_gap1_triage", return_value=candidates_list),
        patch("subprocess.Popen") as mock_popen,
    ):
        real_proc = orig_popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        mock_popen.return_value = real_proc

        _execute_run_worker(run_id, req, "test-key")

    final_entry = _RUNS[run_id]
    assert final_entry["status"] == "partial"

    c_map = {c["id"]: c for c in final_entry["candidates"]}
    # c1 was validated (positive)
    assert c_map["c1"]["state"] == "VALIDATED"
    # c2 was exhausted via GAP2 pivot
    assert c_map["c2"]["state"] == "ABANDONED"
    assert c_map["c2"]["attempts"] == 2
    # c3 remained untested -> NOT_TESTED
    assert c_map["c3"]["state"] == "NOT_TESTED"

    # Verifying investigated count and pivots count
    prog = final_entry.get("progress", {})
    assert prog.get("candidates_investigated") == 2
    assert prog.get("pivots") == 1
    assert "Assessment Partial" in prog.get("phase", "")
    assert len(final_entry.get("pivot_events", [])) == 1
    assert final_entry["pivot_events"][0]["candidate_id"] == "c2"
    assert final_entry["pivot_events"][0]["next_candidate"] == "c3"
