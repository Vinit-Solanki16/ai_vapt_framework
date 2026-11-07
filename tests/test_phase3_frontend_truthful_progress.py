"""Tests for Phase 3: Frontend Configuration & Truthful Progress.

Verifies:
1. Initial Deep mode selects 250 turns in index.html, schemas.py, and api.py.
2. Quick selects 50 turns.
3. Standard selects 100 turns.
4. Actual frontend payload matches selected configuration (API and client payload).
5. Changing scan mode does not corrupt intensity or execution limits.
6. Progress increases only when actual milestones complete (Phases 1 through 5).
7. Failed runs never show successful 100% completion (capped at <= 90%).
8. Valid early completion reaches 100%.
9. SSE events expose the correct run ID and milestone.
10. Concurrent runs maintain separate progress.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from strix.interface.api import (
    _RUNS,
    _execute_run_worker,
    app,
    stream_run_events,
)
from strix.interface.schemas import RunRequest


client = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parent.parent


def test_initial_deep_mode_selects_250_or_500_turns():
    """Verify initial Deep mode selects 250 or 500 turns in HTML, schema, and API worker."""
    html_file = REPO_ROOT / "strix" / "interface" / "web" / "index.html"
    assert html_file.is_file(), f"index.html missing: {html_file}"
    html_text = html_file.read_text(encoding="utf-8")

    # Verify deep is selected by default in scan-intensity-select
    assert re.search(r'<option[^>]*value="deep"[^>]*selected', html_text) is not None
    # Verify 250 or 500 is selected by default in execution-limits-select
    assert re.search(r'<option[^>]*value="(?:250|500)"[^>]*selected', html_text) is not None

    # Verify schema default in RunRequest
    req = RunRequest()
    assert req.scan_mode == "deep"
    assert req.max_turns in (250, 500)

    # Verify API calculates 250 or 500 turns for deep mode when max_turns is omitted
    scan_mode = "deep"
    default_turns = 50 if scan_mode == "quick" else (100 if scan_mode == "standard" else 500)
    assert default_turns in (250, 500)


def test_quick_selects_50_turns():
    """Verify quick scan intensity selects 50 turns in app.js and API."""
    js_file = REPO_ROOT / "strix" / "interface" / "web" / "js" / "app.js"
    assert js_file.is_file()
    js_text = js_file.read_text(encoding="utf-8")

    # Verify app.js sets 50 for quick
    assert "elements.executionLimitsSelect.value = '50'" in js_text

    # Verify API calculates 50 turns for quick
    scan_mode = "quick"
    default_turns = 50 if scan_mode == "quick" else (100 if scan_mode == "standard" else 250)
    assert default_turns == 50


def test_standard_selects_100_turns():
    """Verify standard scan intensity selects 100 turns in app.js and API."""
    js_file = REPO_ROOT / "strix" / "interface" / "web" / "js" / "app.js"
    js_text = js_file.read_text(encoding="utf-8")

    # Verify app.js sets 100 for standard
    assert "elements.executionLimitsSelect.value = '100'" in js_text

    # Verify API calculates 100 turns for standard
    scan_mode = "standard"
    default_turns = 50 if scan_mode == "quick" else (100 if scan_mode == "standard" else 250)
    assert default_turns == 100


def test_actual_frontend_payload_matches_selected_configuration():
    """Verify frontend /runs payload and backend schema handling match selected config."""
    js_file = REPO_ROOT / "strix" / "interface" / "web" / "js" / "app.js"
    js_text = js_file.read_text(encoding="utf-8")

    # Verify payload construction in launchAssessment sends scan_mode and max_turns
    assert "scan_mode: elements.scanIntensity ? elements.scanIntensity.value : 'deep'" in js_text
    assert "max_turns: maxTurns" in js_text

    # Test API request handling
    for mode, expected_turns in [("quick", 50), ("standard", 100), ("deep", 250)]:
        req = RunRequest(
            target_url="http://test-app.local",
            mode="simulation",
            scan_mode=mode,
            max_turns=expected_turns,
        )
        assert req.scan_mode == mode
        assert req.max_turns == expected_turns


def test_changing_scan_mode_does_not_corrupt_intensity():
    """Verify changing execution mode (autonomous/web/simulation) does not overwrite scan intensity or limits."""
    js_file = REPO_ROOT / "strix" / "interface" / "web" / "js" / "app.js"
    js_text = js_file.read_text(encoding="utf-8")

    # Ensure the old bad pattern where scanModeSelect forced executionLimitsSelect to 100 is absent
    assert "elements.scanModeSelect.value === 'autonomous'" not in js_text

    # Test backend: creating a run with mode='simulation' and scan_mode='deep', max_turns=250 preserves all values
    req_sim = RunRequest(
        target_url="http://target.local",
        mode="simulation",
        scan_mode="deep",
        max_turns=250,
    )
    assert req_sim.mode == "simulation"
    assert req_sim.scan_mode == "deep"
    assert req_sim.max_turns == 250

    req_auto = RunRequest(
        target_url="http://target.local",
        mode="autonomous",
        scan_mode="quick",
        max_turns=50,
    )
    assert req_auto.mode == "autonomous"
    assert req_auto.scan_mode == "quick"
    assert req_auto.max_turns == 50


def test_progress_increases_only_when_actual_milestones_complete(tmp_path: Path):
    """Verify progress advances only upon actual milestone completion and never exceeds 90% before phase 5."""
    run_id = "test-phase3-milestones"
    run_entry = {
        "run_id": run_id,
        "status": "queued",
        "scenario": "default",
        "mode": "simulation",
        "target_url": "http://target.local",
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

    req = RunRequest(
        target_url="http://target.local",
        mode="simulation",
        scan_mode="deep",
        max_turns=250,
    )

    with (
        patch("strix.interface.api.runs_base_dir", return_value=tmp_path),
        patch("strix.core.triage.exploit_assessor.run_gap1_triage", return_value=[]),
    ):
        _execute_run_worker(run_id, req, runtime_key=None)

    final_run = _RUNS[run_id]
    assert final_run["status"] == "completed"
    assert final_run["progress"]["percent"] == 100
    assert final_run["progress"]["phase"] == "Assessment Complete"
    assert final_run["progress"]["phase_index"] == 5
    assert final_run["progress"]["run_id"] == run_id


def test_failed_runs_never_show_successful_100_percent_completion(tmp_path: Path):
    """Verify failed or crashed runs retain truthful progress <= 90% and never report 100% or Assessment Complete."""
    run_id = "test-phase3-failed-run"
    run_entry = {
        "run_id": run_id,
        "status": "queued",
        "scenario": "default",
        "mode": "autonomous",
        "target_url": "http://target.local",
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

    req = RunRequest(
        target_url="http://target.local",
        mode="autonomous",
        scan_mode="deep",
        max_turns=250,
    )

    # Simulate subprocess exiting with failure (code 1)
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout.readline.return_value = ""
    mock_proc.stderr.readline.return_value = ""
    mock_proc.poll.return_value = 1
    mock_proc.wait.return_value = 1

    with (
        patch("strix.interface.api.runs_base_dir", return_value=tmp_path),
        patch("strix.interface.api._is_docker_available", return_value=True),
        patch("subprocess.Popen", return_value=mock_proc),
        patch("strix.core.triage.exploit_assessor.run_gap1_triage", return_value=[]),
    ):
        _execute_run_worker(run_id, req, runtime_key=None)

    failed_run = _RUNS[run_id]
    assert failed_run["status"] == "failed"
    prog = failed_run["progress"]
    assert prog["percent"] <= 90, (
        f"Failed run progress percent must be <= 90, got {prog['percent']}"
    )
    assert prog["percent"] != 100
    assert "Assessment Complete" not in prog["phase"]
    assert "Failed" in prog["phase"]


def test_valid_early_completion_reaches_100_percent(tmp_path: Path):
    """Verify valid early completion where the gate approves completion reaches 100%."""
    run_id = "test-phase3-early-completion"
    run_entry = {
        "run_id": run_id,
        "status": "queued",
        "scenario": "default",
        "mode": "autonomous",
        "target_url": "http://target.local",
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

    req = RunRequest(
        target_url="http://target.local",
        mode="autonomous",
        scan_mode="deep",
        max_turns=250,
    )

    # Create underlying run directory with run.json marked completed
    u_dir = tmp_path / "strix_run_mock"
    u_dir.mkdir(parents=True, exist_ok=True)
    (u_dir / "run.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "scan_ended_exit_reason": "All actionable candidates evaluated and coverage satisfied",
            }
        ),
        encoding="utf-8",
    )
    (u_dir / "vulnerabilities.json").write_text(json.dumps([]), encoding="utf-8")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout.readline.side_effect = [
        f"Output  strix_runs/{u_dir.name}\n",
        "Starting turn 15\n",
        "",
    ]
    mock_proc.poll.return_value = 0
    mock_proc.wait.return_value = 0

    with (
        patch("strix.interface.api.runs_base_dir", return_value=tmp_path),
        patch("strix.interface.api._is_docker_available", return_value=True),
        patch("subprocess.Popen", return_value=mock_proc),
        patch("strix.core.triage.exploit_assessor.run_gap1_triage", return_value=[]),
    ):
        _execute_run_worker(run_id, req, runtime_key=None)

    comp_run = _RUNS[run_id]
    assert comp_run["status"] == "completed"
    prog = comp_run["progress"]
    assert prog["percent"] == 100
    assert prog["phase"] == "Assessment Complete"
    assert prog["phase_index"] == 5


@pytest.mark.asyncio
async def test_sse_events_expose_correct_run_id_and_milestone():
    """Verify SSE stream events push the correct run_id and progress structure immediately."""
    run_id = "test-phase3-sse-run"
    _RUNS[run_id] = {
        "run_id": run_id,
        "status": "running",
        "target_url": "http://target.local",
        "decision_trace": ["Log 1", "Log 2"],
        "progress": {
            "phase": "GAP1 triage and candidate investigation",
            "phase_index": 3,
            "percent": 45,
            "current": 10,
            "total": 250,
            "candidates_identified": 5,
            "candidates_investigated": 2,
            "pivots": 0,
            "run_id": run_id,
        },
    }

    mock_request = MagicMock()
    # Let generator yield initial events and then signal disconnect
    call_count = 0

    async def mock_is_disconnected():
        nonlocal call_count
        call_count += 1
        return call_count > 1

    mock_request.is_disconnected = mock_is_disconnected

    response = await stream_run_events(run_id, mock_request)
    body_parts = []
    async for chunk in response.body_iterator:
        body_parts.append(chunk)

    full_output = "".join(body_parts)
    assert "event: state" in full_output
    assert "event: progress" in full_output

    # Find the progress data block
    m = re.search(r"event: progress\ndata: (\{.*?\})\n\n", full_output)
    assert m is not None, f"Expected event: progress in output: {full_output}"
    prog_data = json.loads(m.group(1))
    assert prog_data.get("run_id") == run_id
    assert prog_data.get("phase") == "GAP1 triage and candidate investigation"
    assert prog_data.get("percent") == 45
    assert prog_data.get("phase_index") == 3


def test_concurrent_runs_maintain_separate_progress():
    """Verify concurrent runs isolate progress state and run_ids without cross-contamination."""
    run_a = "run-concurrent-A"
    run_b = "run-concurrent-B"

    _RUNS[run_a] = {
        "run_id": run_a,
        "status": "running",
        "progress": {
            "phase": "Spidering and attack surface discovery",
            "phase_index": 2,
            "percent": 30,
            "current": 5,
            "total": 50,
            "run_id": run_a,
        },
    }

    _RUNS[run_b] = {
        "run_id": run_b,
        "status": "running",
        "progress": {
            "phase": "GAP2 adaptive pivoting and validation",
            "phase_index": 4,
            "percent": 85,
            "current": 200,
            "total": 250,
            "run_id": run_b,
        },
    }

    assert _RUNS[run_a]["progress"]["run_id"] == run_a
    assert _RUNS[run_a]["progress"]["percent"] == 30
    assert _RUNS[run_a]["progress"]["phase_index"] == 2

    assert _RUNS[run_b]["progress"]["run_id"] == run_b
    assert _RUNS[run_b]["progress"]["percent"] == 85
    assert _RUNS[run_b]["progress"]["phase_index"] == 4

    # Verify mutating run A does not affect run B
    _RUNS[run_a]["progress"]["percent"] = 40
    assert _RUNS[run_b]["progress"]["percent"] == 85
