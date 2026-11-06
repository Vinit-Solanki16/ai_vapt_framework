"""Regression tests for Phase 5: Root Cause Fixes for Live AI-VAPT Execution.

Verifies:
1. Subprocess live turn tracking via per-run strix.log rather than stdout.
2. Turn budget clamping (Quick=50, Standard=100, Deep=250, clamping > 250).
3. Elimination of obsolete 500-turn options across settings and schemas.
4. GAP1 candidate state progression (PENDING -> ATTEMPTING -> VALIDATED/ABANDONED).
5. GAP2 dynamic pivot synchronization into pivot_events and metrics.
6. OpenRouter daily quota exhaustion fast failure (no infinite retries) and actionable error message.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from strix.config.settings import DEFAULT_MAX_TURNS
from strix.core.execution import _is_permanent_quota_error, _is_transient_model_error
from strix.interface import api
from strix.interface.api import (
    app,
    _RUNS,
    _extract_clean_error,
    _execute_run_worker,
)
from strix.interface.schemas import RunRequest

client = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parent.parent


def test_turn_budget_native_strix_limits_and_validation():
    """Verify native Strix default (500), supported ranges (1-1000), and validation errors."""
    # 1. Default max turns in settings is 500 (native Strix)
    assert DEFAULT_MAX_TURNS == 500

    # 2. Values are not clamped; actual requested limits are preserved
    assert RunRequest(max_turns=50).max_turns == 50
    assert RunRequest(max_turns=100).max_turns == 100
    assert RunRequest(max_turns=250).max_turns == 250
    assert RunRequest(max_turns=500).max_turns == 500
    assert RunRequest(max_turns=1000).max_turns == 1000
    assert RunRequest(max_turns=400).max_turns == 400

    # 3. Unsupported values (> 1000 or < 1) raise ValidationError (no silent clamping)
    with pytest.raises(Exception):
        RunRequest(max_turns=1001)

    with pytest.raises(Exception):
        RunRequest(max_turns=0)

    with pytest.raises(Exception):
        RunRequest(max_turns=-10)


def test_native_500_and_1000_options_present_in_html():
    """Verify that execution-limits-select in index.html offers 50, 100, 250, 500, 1000 and custom."""
    html_path = REPO_ROOT / "strix" / "interface" / "web" / "index.html"
    assert html_path.is_file()
    html_text = html_path.read_text(encoding="utf-8")

    assert '<option value="50">' in html_text
    assert '<option value="100">' in html_text
    assert '<option value="250">' in html_text
    assert '<option value="500"' in html_text
    assert '<option value="1000">' in html_text
    assert '<option value="__custom__">' in html_text
    assert 'id="custom-turns-input"' in html_text


def test_real_subprocess_log_tailing_turn_tracking(tmp_path: Path):
    """Verify that turns logged to strix.log by a real subprocess are tracked live."""
    run_id = f"test-log-tail-{int(time.time() * 1000)}"
    fake_strix_runs = tmp_path / "strix_runs"
    fake_strix_runs.mkdir(parents=True, exist_ok=True)
    control_dir = fake_strix_runs / run_id / "control"
    control_dir.mkdir(parents=True, exist_ok=True)

    # Subprocess writes turn events to strix.log with no turn output to stdout
    script = (
        "import sys, time, os, json\n"
        "from pathlib import Path\n"
        f"run_dir = Path({str(fake_strix_runs / 'sub-run-1')!r})\n"
        "run_dir.mkdir(parents=True, exist_ok=True)\n"
        "log_file = run_dir / 'strix.log'\n"
        "print('Output strix_runs/sub-run-1', flush=True)\n"
        "print('╭─── Rich UI Header ───╮', flush=True)\n"
        "with open(log_file, 'a') as f:\n"
        "    f.write('INFO - Starting scan\\n')\n"
        "    f.flush()\n"
        "    time.sleep(0.05)\n"
        "    f.write('DEBUG - openai.agents: Starting turn 1, current_agent=Root Agent\\n')\n"
        "    f.flush()\n"
        "    time.sleep(0.05)\n"
        "    f.write('DEBUG - openai.agents: Starting turn 2, current_agent=Root Agent\\n')\n"
        "    f.flush()\n"
        "    time.sleep(0.05)\n"
        "    f.write('DEBUG - openai.agents: Starting turn 3, current_agent=Web Agent\\n')\n"
        "    f.flush()\n"
        "(run_dir / 'run.json').write_text(json.dumps({'status': 'completed', 'vulnerabilities': []}))\n"
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
        "candidates": [{"id": "c1", "name": "SQLi", "state": "PENDING"}],
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
    with patch("strix.interface.api.runs_base_dir", return_value=fake_strix_runs), \
         patch("strix.interface.api.PROJECT_ROOT", tmp_path), \
         patch("strix.interface.api._is_docker_available", return_value=True), \
         patch("strix.core.triage.exploit_assessor.run_gap1_triage", return_value=[]), \
         patch("subprocess.Popen") as mock_popen:

        real_proc = orig_popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        mock_popen.return_value = real_proc

        _execute_run_worker(run_id, req, "test-key")

    assert run_entry["status"] == "completed"
    progress = run_entry["progress"]
    # Turns in strix.log advanced to turn 3
    assert progress["current"] == 3
    assert progress["total"] == 50
    assert progress["percent"] == 100  # Final completion reaches 100


def test_gap1_gap2_state_progression_from_gap_state_json(tmp_path: Path):
    """Verify that candidates transition from PENDING to VALIDATED/ABANDONED based on gap_state.json."""
    run_id = f"test-gap-sync-{int(time.time() * 1000)}"
    fake_strix_runs = tmp_path / "strix_runs"
    fake_strix_runs.mkdir(parents=True, exist_ok=True)
    control_dir = fake_strix_runs / run_id / "control"
    control_dir.mkdir(parents=True, exist_ok=True)

    # Pre-populate gap_state.json with 1 completed positive, 1 completed negative, 1 exhausted, 1 attempting
    gap_state = {
        "attempts": {"c1": 1, "c2": 1, "c3": 2, "c4": 1},
        "completed": ["c1", "c2"],
        "exhausted": ["c3"],
        "announced": True,
        "probe_outcomes": [
            {"candidate_id": "c1", "status": "positive", "detail": "SQLi confirmed"},
            {"candidate_id": "c2", "status": "negative", "detail": "XSS ruled out"},
            {"candidate_id": "c3", "status": "inconclusive", "detail": "Timeout"},
        ],
    }
    (control_dir / "gap_state.json").write_text(json.dumps(gap_state), encoding="utf-8")

    # Add a GAP-2 pivot event to decision_trace.jsonl
    pivot_line = json.dumps({
        "timestamp": "2026-11-06T00:01:00Z",
        "event": "GAP2_PIVOT",
        "candidate_id": "c3",
        "next_candidate": "c4",
    }) + "\n"
    (control_dir / "decision_trace.jsonl").write_text(pivot_line, encoding="utf-8")

    # Subprocess run folder
    sub_dir = fake_strix_runs / "sub-run-2"
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / "strix.log").write_text("DEBUG - openai.agents: Starting turn 5, current_agent=Root Agent\n")
    (sub_dir / "run.json").write_text(json.dumps({"status": "completed", "vulnerabilities": []}))

    candidates_list = [
        {"id": "c1", "name": "SQL Injection", "endpoint": "/api/search"},
        {"id": "c2", "name": "Reflected XSS", "endpoint": "/contact"},
        {"id": "c3", "name": "CSRF Profile", "endpoint": "/profile"},
        {"id": "c4", "name": "IDOR Invoice", "endpoint": "/invoice"},
    ]

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
        "candidates": list(candidates_list),
        "findings": [],
        "stats": {"attempts": 0, "pivots": 0, "findings": 0},
    }
    _RUNS[run_id] = run_entry

    req = RunRequest(
        target_url="http://127.0.0.1:3000",
        mode="autonomous",
        scan_mode="standard",
        max_turns=100,
    )

    orig_popen = subprocess.Popen
    with patch("strix.interface.api.runs_base_dir", return_value=fake_strix_runs), \
         patch("strix.interface.api.PROJECT_ROOT", tmp_path), \
         patch("strix.interface.api._is_docker_available", return_value=True), \
         patch("strix.core.triage.exploit_assessor.run_gap1_triage", return_value=candidates_list), \
         patch("subprocess.Popen") as mock_popen:

        real_proc = orig_popen(
            [sys.executable, "-c", "import sys; print('Output strix_runs/sub-run-2', flush=True); sys.exit(0)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        mock_popen.return_value = real_proc

        _execute_run_worker(run_id, req, "test-key")

    cands_by_id = {c["id"]: c for c in run_entry["candidates"]}
    # c1 was positive -> VALIDATED
    assert cands_by_id["c1"]["state"] == "VALIDATED"
    # c2 was negative -> ABANDONED (ruled out)
    assert cands_by_id["c2"]["state"] == "ABANDONED"
    # c3 was exhausted -> ABANDONED
    assert cands_by_id["c3"]["state"] == "ABANDONED"
    # c4 had attempts -> ATTEMPTING
    assert cands_by_id["c4"]["state"] == "ATTEMPTING"

    # Pivot event synced
    assert len(run_entry["pivot_events"]) >= 1
    assert run_entry["pivot_events"][0]["candidate_id"] == "c3"


def test_openrouter_daily_quota_429_fast_failure():
    """Verify that 429 daily quota exhaustion is treated as permanent and fails cleanly without retries."""
    daily_quota_err = Exception(
        'litellm.RateLimitError: RateLimitError: OpenrouterException - '
        '{"error":{"message":"Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day",'
        '"code":429,"metadata":{"limit_source":"openrouter_free_tier_daily"}}}'
    )

    # 1. Permanent quota check returns True
    assert _is_permanent_quota_error(daily_quota_err) is True

    # 2. Transient error check returns False (bypasses retry loop)
    assert _is_transient_model_error(daily_quota_err) is False

    # 3. Clean error extraction provides clear, actionable notification
    extracted = _extract_clean_error(
        stderr_lines=[str(daily_quota_err)],
        stdout_lines=[],
        fallback="Scan failed",
    )
    assert "daily free quota exceeded" in extracted.lower()
    assert "50 requests/day" in extracted.lower()


def test_csv_report_export_and_persistence(tmp_path):
    """Verify that CSV export works for runs and generates compliant CSV output."""
    run_id = "test-csv-run-001"
    run_data = {
        "run_id": run_id,
        "status": "completed",
        "target_url": "http://127.0.0.1:3000/",
        "findings": [
            {
                "id": "vuln-xss-01",
                "title": "Reflected XSS",
                "severity": "HIGH",
                "cvss_score": 7.5,
                "cwe_id": "CWE-79",
                "owasp_category": "A03:2021 - Injection",
                "location": "/search?q=test",
                "target": "http://127.0.0.1:3000/",
                "remediation_summary": "Encode HTML output",
            }
        ],
    }
    _RUNS[run_id] = run_data

    # 1. Test CSV format retrieval
    res = client.get(f"/runs/{run_id}/report?format=csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    csv_text = res.text
    assert "id,title,severity,cvss_score,cwe_id,owasp_category,location,target,remediation_summary" in csv_text
    assert "vuln-xss-01,Reflected XSS,HIGH,7.5,CWE-79,A03:2021 - Injection,/search?q=test,http://127.0.0.1:3000/,Encode HTML output" in csv_text

    # 2. Test download disposition
    res_dl = client.get(f"/runs/{run_id}/report?format=csv&download=1")
    assert res_dl.status_code == 200
    assert res_dl.headers.get("content-disposition") == f'attachment; filename="vapt_findings_{run_id}.csv"'

    # Cleanup
    _RUNS.pop(run_id, None)
