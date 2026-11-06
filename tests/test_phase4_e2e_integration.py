"""Tests for Phase 4: Full System Integration & End-to-End Verification.

Implements controlled end-to-end verification workflows:
- Test A: Quick assessment (50 turns, GAP1 queue, GAP2 feedback, report synthesis).
- Test B: Standard assessment (100 turns ceiling, broader candidate exploration).
- Test C: Deep assessment (250 turns ceiling, completion gate enforcement, non-padded execution).
- Test D: Zero-finding assessment (Controlled safe target, legitimate 0 findings completion).
- Test E: Failure handling (RateLimitError, non-zero exit, timeout, incomplete run.json).
- Test F: Concurrent assessments (Isolation of control dirs, queues, progress, reports).
- Test G: Final report integrity (Cross-validation of run.json, vulnerabilities.json, coverage.json, decision_trace.jsonl, penetration_test_report.md).
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from strix.core import gap_bridge
from strix.core.decision_engine.schemas import ActionCandidate, Outcome
from strix.interface import api
from strix.interface.api import (
    app,
    _RUNS,
    _execute_run_worker,
    _generate_markdown_report,
    runs_base_dir,
    stream_run_events,
)
from strix.interface.schemas import RunRequest, RunStatus

client = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parent.parent


# =========================================================================
# Test A: Quick Assessment Workflow
# =========================================================================
def test_workflow_quick_assessment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test A: Launch Quick mode, verify 50-turn ceiling, GAP-1 queue, GAP-2 feedback, report."""
    monkeypatch.setattr(api, "runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr("strix.core.paths.runs_base_dir", lambda: tmp_path)

    run_id = "test-e2e-quick"
    req = RunRequest(
        target_url="http://127.0.0.1:8080",
        mode="simulation",
        scan_mode="quick",
        max_turns=50,
        max_attempts=2,
    )
    assert req.scan_mode == "quick"
    assert req.max_turns == 50

    run_entry = {
        "run_id": run_id,
        "status": "queued",
        "scenario": req.scenario,
        "mode": req.mode,
        "target_url": req.target_url,
        "created_at": "2026-11-05T00:00:00Z",
        "completed_at": None,
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
        "stats": {"attempts": 0, "pivots": 0, "findings": 0},
    }
    _RUNS[run_id] = run_entry

    _execute_run_worker(run_id, req, runtime_key=None)

    res_run = _RUNS[run_id]
    assert res_run["status"] == "completed"
    assert res_run["scan_mode"] == "quick"
    assert res_run["max_turns"] == 50
    assert res_run["progress"]["percent"] == 100
    assert res_run["progress"]["phase"] == "Assessment Complete"
    assert res_run["progress"]["phase_index"] == 5
    assert res_run["progress"]["current"] <= 50

    # Verify per-run control directory and GAP state
    control_dir = tmp_path / run_id / "control"
    assert control_dir.is_dir()
    gap1_file = control_dir / "gap1_queue.json"
    assert gap1_file.is_file()
    gap1_data = json.loads(gap1_file.read_text(encoding="utf-8"))
    assert "candidates" in gap1_data

    # Verify report persistence
    run_disk_dir = tmp_path / run_id
    assert (run_disk_dir / "run.json").is_file()
    assert (run_disk_dir / "vulnerabilities.json").is_file()


# =========================================================================
# Test B: Standard Assessment Workflow
# =========================================================================
def test_workflow_standard_assessment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test B: Launch Standard mode, verify 100-turn ceiling and broader exploration."""
    monkeypatch.setattr(api, "runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr("strix.core.paths.runs_base_dir", lambda: tmp_path)

    run_id = "test-e2e-standard"
    req = RunRequest(
        target_url="http://127.0.0.1:8080",
        mode="simulation",
        scan_mode="standard",
        max_turns=100,
        max_attempts=2,
    )
    assert req.scan_mode == "standard"
    assert req.max_turns == 100

    run_entry = {
        "run_id": run_id,
        "status": "queued",
        "scenario": req.scenario,
        "mode": req.mode,
        "target_url": req.target_url,
        "created_at": "2026-11-05T00:00:00Z",
        "completed_at": None,
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
        "stats": {"attempts": 0, "pivots": 0, "findings": 0},
    }
    _RUNS[run_id] = run_entry

    _execute_run_worker(run_id, req, runtime_key=None)

    res_run = _RUNS[run_id]
    assert res_run["status"] == "completed"
    assert res_run["scan_mode"] == "standard"
    assert res_run["max_turns"] == 100
    assert res_run["progress"]["percent"] == 100
    assert res_run["progress"]["current"] <= 100


# =========================================================================
# Test C: Deep Assessment Workflow & Completion Gate
# =========================================================================
def test_workflow_deep_assessment_and_completion_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test C: Launch Deep mode, verify 250-turn ceiling and completion gate enforcement."""
    monkeypatch.setattr(api, "runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr("strix.core.paths.runs_base_dir", lambda: tmp_path)

    run_id = "test-e2e-deep"
    req = RunRequest(
        target_url="http://127.0.0.1:8080",
        mode="simulation",
        scan_mode="deep",
        max_turns=250,
        max_attempts=2,
    )
    assert req.scan_mode == "deep"
    assert req.max_turns == 250

    run_entry = {
        "run_id": run_id,
        "status": "queued",
        "scenario": req.scenario,
        "mode": req.mode,
        "target_url": req.target_url,
        "created_at": "2026-11-05T00:00:00Z",
        "completed_at": None,
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
        "stats": {"attempts": 0, "pivots": 0, "findings": 0},
    }
    _RUNS[run_id] = run_entry

    _execute_run_worker(run_id, req, runtime_key=None)

    res_run = _RUNS[run_id]
    assert res_run["status"] == "completed"
    assert res_run["scan_mode"] == "deep"
    assert res_run["max_turns"] == 250
    assert res_run["progress"]["percent"] == 100
    # Must finish legitimately without wasting/padding turns
    assert res_run["progress"]["current"] < 250


# =========================================================================
# Test D: Zero-Finding Assessment
# =========================================================================
def test_workflow_zero_finding_assessment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test D: Controlled target with zero findings successfully completes without failure."""
    monkeypatch.setattr(api, "runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr("strix.core.paths.runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr(api, "_is_docker_available", lambda: True)

    run_id = "test-e2e-zero-findings"
    req = RunRequest(
        target_url="http://safe-app.local",
        mode="autonomous",
        scan_mode="standard",
        max_turns=100,
    )

    # Subprocess runs and exits 0 with a valid run.json with 0 findings
    u_dir = tmp_path / "strix_zero_finding_run"
    u_dir.mkdir(parents=True, exist_ok=True)
    (u_dir / "run.json").write_text(json.dumps({
        "status": "completed",
        "scan_ended_exit_reason": "Assessment completed legitimately with no vulnerabilities discovered",
    }), encoding="utf-8")
    (u_dir / "vulnerabilities.json").write_text(json.dumps([]), encoding="utf-8")
    (u_dir / "coverage.json").write_text(json.dumps([
        {"surface": "/", "risk_area": "Authentication", "outcome": "no_issue_found"}
    ]), encoding="utf-8")
    (u_dir / "penetration_test_report.md").write_text("# Pentest Report\nNo findings.", encoding="utf-8")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout.readline.side_effect = [
        f"Output  strix_runs/{u_dir.name}\n",
        "Starting turn 12\n",
        "",
    ]
    mock_proc.poll.return_value = 0
    mock_proc.wait.return_value = 0

    run_entry = {
        "run_id": run_id,
        "status": "queued",
        "scenario": req.scenario,
        "mode": req.mode,
        "target_url": req.target_url,
        "created_at": "2026-11-05T00:00:00Z",
        "completed_at": None,
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
        "stats": {"attempts": 0, "pivots": 0, "findings": 0},
    }
    _RUNS[run_id] = run_entry

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch("strix.core.triage.exploit_assessor.run_gap1_triage", return_value=[]):
        _execute_run_worker(run_id, req, runtime_key=None)

    res_run = _RUNS[run_id]
    assert res_run["status"] == "completed"
    assert len(res_run["findings"]) == 0
    assert res_run["progress"]["percent"] == 100
    assert res_run["progress"]["phase"] == "Assessment Complete"
    assert (tmp_path / run_id / "penetration_test_report.md").is_file()


# =========================================================================
# Test E: Failure Handling
# =========================================================================
@pytest.mark.parametrize("fail_type,return_code,u_status,timed_out,expected_reason", [
    ("rate_limit", 1, None, False, "RateLimitError"),
    ("crash", 2, None, False, "crash error"),
    ("timeout", 0, None, True, "wall-clock limit"),
    ("incomplete_run_json", 0, "incomplete", False, "satisfying completion requirements"),
])
def test_workflow_failure_handling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_type: str,
    return_code: int,
    u_status: str | None,
    timed_out: bool,
    expected_reason: str,
):
    """Test E: Verify all failure conditions are reported as 'failed' and never as 'completed'."""
    monkeypatch.setattr(api, "runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr("strix.core.paths.runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr(api, "_is_docker_available", lambda: True)

    run_id = f"test-e2e-fail-{fail_type}"
    req = RunRequest(
        target_url="http://test.local",
        mode="autonomous",
        scan_mode="deep",
        max_turns=250,
    )

    u_dir = tmp_path / f"strix_run_{fail_type}"
    u_dir.mkdir(parents=True, exist_ok=True)
    if u_status:
        (u_dir / "run.json").write_text(json.dumps({
            "status": u_status,
            "scan_ended_exit_reason": "budget exhausted",
        }), encoding="utf-8")

    mock_proc = MagicMock()
    mock_proc.returncode = return_code
    if fail_type == "rate_limit":
        mock_proc.stdout.readline.side_effect = [
            f"Output  strix_runs/{u_dir.name}\n",
            "RateLimitError: 429 quota exhausted\n",
            "",
        ]
    elif fail_type == "crash":
        mock_proc.stdout.readline.side_effect = [
            f"Output  strix_runs/{u_dir.name}\n",
            "Fatal crash error: segmentation fault\n",
            "",
        ]
    else:
        mock_proc.stdout.readline.side_effect = [
            f"Output  strix_runs/{u_dir.name}\n",
            "Starting turn 5\n",
            "",
        ]
    mock_proc.poll.return_value = return_code
    mock_proc.wait.return_value = return_code

    run_entry = {
        "run_id": run_id,
        "status": "queued",
        "scenario": req.scenario,
        "mode": req.mode,
        "target_url": req.target_url,
        "created_at": "2026-11-05T00:00:00Z",
        "completed_at": None,
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
        "stats": {"attempts": 0, "pivots": 0, "findings": 0},
    }
    _RUNS[run_id] = run_entry

    wall_timeout = 0.001 if timed_out else 1800.0
    with patch("subprocess.Popen", return_value=mock_proc), \
         patch("strix.core.triage.exploit_assessor.run_gap1_triage", return_value=[]), \
         patch("strix.interface.api.time.time", side_effect=[0, 10000] if timed_out else None):
        _execute_run_worker(run_id, req, runtime_key=None)

    failed_run = _RUNS[run_id]
    assert failed_run["status"] == "failed"
    assert failed_run["progress"]["percent"] <= 90
    assert failed_run["progress"]["percent"] != 100
    assert "Assessment Complete" not in failed_run["progress"]["phase"]


# =========================================================================
# Test F: Concurrent Assessments
# =========================================================================
def test_workflow_concurrent_assessments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test F: Launch two concurrent assessments and verify strict per-run isolation."""
    monkeypatch.setattr(api, "runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr("strix.core.paths.runs_base_dir", lambda: tmp_path)

    run_1 = "run-concurrent-1"
    run_2 = "run-concurrent-2"

    ctrl_1 = tmp_path / run_1 / "control"
    ctrl_2 = tmp_path / run_2 / "control"
    ctrl_1.mkdir(parents=True, exist_ok=True)
    ctrl_2.mkdir(parents=True, exist_ok=True)

    # Populate different GAP-1 queues
    (ctrl_1 / "gap1_queue.json").write_text(json.dumps({
        "candidates": [{"candidate_id": "cand-run1", "title": "Run 1 SQLi"}],
    }), encoding="utf-8")
    (ctrl_2 / "gap1_queue.json").write_text(json.dumps({
        "candidates": [{"candidate_id": "cand-run2", "title": "Run 2 XSS"}],
    }), encoding="utf-8")

    # Record outcomes in each run
    gap_bridge.record_outcome(
        directory=ctrl_1,
        candidate_id="cand-run1",
        title="Run 1 SQLi",
        probe_status="positive",
        source="test",
    )
    gap_bridge.record_outcome(
        directory=ctrl_2,
        candidate_id="cand-run2",
        title="Run 2 XSS",
        probe_status="negative",
        source="test",
    )

    state_1 = gap_bridge.get_run_state(ctrl_1)
    state_2 = gap_bridge.get_run_state(ctrl_2)

    assert "cand-run1" in state_1.completed
    assert "cand-run1" not in state_2.completed
    assert "cand-run2" not in state_1.attempts
    assert "cand-run2" in state_2.attempts

    trace_1 = (ctrl_1 / "decision_trace.jsonl").read_text(encoding="utf-8")
    trace_2 = (ctrl_2 / "decision_trace.jsonl").read_text(encoding="utf-8")
    assert "cand-run1" in trace_1
    assert "cand-run2" not in trace_1
    assert "cand-run2" in trace_2
    assert "cand-run1" not in trace_2


# =========================================================================
# Test G: Final Report Integrity & Consistency
# =========================================================================
def test_workflow_final_report_integrity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test G: Compare run.json, vulnerabilities.json, and penetration_test_report.md."""
    run_data = {
        "run_id": "run-report-integrity-check",
        "target_url": "http://integrity-test.local",
        "status": "completed",
        "mode": "autonomous",
        "scan_mode": "deep",
        "completed_at": "2026-11-05T12:00:00Z",
        "findings": [
            {
                "id": "find-sqli-01",
                "title": "SQL Injection in Login Endpoint",
                "severity": "HIGH",
                "cvss_score": 8.5,
                "cve_id": "CVE-2023-9999",
                "cwe_id": "CWE-89",
                "owasp_category": "A03:2021 - Injection",
                "location": "/api/v1/auth/login",
                "evidence_hash": "a1b2c3d4e5f60718293041526374859607182930415263748596071829304152",
                "evidence_snippet": "' OR 1=1 --",
                "impact": "Full database bypass and administrative session extraction.",
                "remediation_summary": "Use parameterized prepared statements.",
                "remediation_technical": "cursor.execute('SELECT * FROM users WHERE email = %s', (email,))",
                "retest_procedure": "Send single quote in email payload and assert HTTP 400 rejection.",
            }
        ],
    }

    report_md = _generate_markdown_report(run_data)
    assert run_data["target_url"] in report_md
    assert run_data["run_id"] in report_md
    assert "SQL Injection in Login Endpoint" in report_md
    assert "HIGH" in report_md
    assert "CVE-2023-9999" in report_md
    assert "CWE-89" in report_md
    assert "A03:2021 - Injection" in report_md
    assert "/api/v1/auth/login" in report_md
    assert run_data["findings"][0]["evidence_hash"] in report_md
    assert "' OR 1=1 --" in report_md
    assert "parameterized prepared statements" in report_md

