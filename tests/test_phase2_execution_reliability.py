"""Tests for Phase 2: Execution Reliability.

Verifies:
1. Subprocess exit code 1 when ending without calling finish_scan.
2. RateLimitError causes the subprocess to exit with code 1.
3. BudgetExceededError causes the subprocess to exit with code 1.
4. Valid zero-finding completion causes the subprocess to exit with code 0.
5. API marks run as incomplete/failed when subprocess exits 0 but run.json status is not completed.
6. API marks run as completed when run.json status is completed with 0 findings.
7. Error extraction strips Rich box-drawing characters and returns clean error message.
8. Subprocess failure preserves partial findings in API response.
9. No-Docker execution completes without padding turns to max_turns.
10. GAP completion gate blocks premature completion in subprocess execution context.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from strix.core import gap_bridge
from strix.interface import api
from strix.interface.api import (
    _RUNS,
    _clean_terminal_line,
    _execute_run_worker,
    _extract_clean_error,
    _is_decorative_line,
)


importlib.import_module("strix.interface.main")
main_mod = sys.modules["strix.interface.main"]
from strix.interface.schemas import RunRequest
from strix.report.state import ReportState, set_global_report_state


@pytest.fixture(autouse=True)
def clean_global_state():
    set_global_report_state(None)
    yield
    set_global_report_state(None)


def _patch_main_preflight(
    monkeypatch: pytest.MonkeyPatch, args: argparse.Namespace, tmp_path: Path
):
    monkeypatch.setattr(main_mod, "start_import_warmup", lambda: None)
    monkeypatch.setattr(main_mod, "wait_for_import_warmup", lambda: None)
    monkeypatch.setattr(main_mod, "start_background_check", lambda: None)
    monkeypatch.setattr(main_mod, "check_docker_installed", lambda: None)
    monkeypatch.setattr(main_mod, "pull_docker_image", lambda: None)
    monkeypatch.setattr(main_mod, "validate_environment", lambda: None)
    monkeypatch.setattr(main_mod, "_bootstrap_scan", lambda _args: None)
    monkeypatch.setattr(main_mod, "_fall_back_to_headless", lambda _args: None)
    monkeypatch.setattr(main_mod, "display_completion_message", lambda _args, _p: None)
    monkeypatch.setattr(main_mod, "run_dir_for", lambda _r: tmp_path)
    monkeypatch.setattr(main_mod, "parse_arguments", lambda: args)


def test_1_subprocess_exit_code_1_without_finish_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Subprocess must exit with code 1 if it terminates without calling finish_scan."""
    report_state = ReportState(tmp_path)
    set_global_report_state(report_state)

    args = argparse.Namespace(
        non_interactive=True,
        needs_setup=False,
        resume_picker=False,
        run_name="test-run",
        targets=[],
        fail_on=None,
    )

    async def mock_run_cli(_args):
        # Emulates agent returning without finish_scan
        return None

    monkeypatch.setattr("strix.interface.cli.run_cli", mock_run_cli)
    _patch_main_preflight(monkeypatch, args, tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.main()

    assert exc_info.value.code == 1
    assert report_state.run_record.get("status") == "stopped"


def test_2_rate_limit_error_exit_code_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """RateLimitError marks status failed and causes subprocess to exit with code 1."""
    report_state = ReportState(tmp_path)
    set_global_report_state(report_state)

    args = argparse.Namespace(
        non_interactive=True,
        needs_setup=False,
        resume_picker=False,
        run_name="test-run-rl",
        targets=[],
        fail_on=None,
    )

    async def mock_run_cli(_args):
        report_state.scan_ended_exit_reason = "rate_limited"
        report_state.save_run_data(status="failed")

    monkeypatch.setattr("strix.interface.cli.run_cli", mock_run_cli)
    _patch_main_preflight(monkeypatch, args, tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.main()

    assert exc_info.value.code == 1
    assert report_state.run_record.get("status") == "failed"


def test_3_budget_exceeded_error_exit_code_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """BudgetExceededError marks status stopped and causes subprocess to exit with code 1."""
    report_state = ReportState(tmp_path)
    set_global_report_state(report_state)

    args = argparse.Namespace(
        non_interactive=True,
        needs_setup=False,
        resume_picker=False,
        run_name="test-run-budget",
        targets=[],
        fail_on=None,
    )

    async def mock_run_cli(_args):
        report_state.scan_ended_exit_reason = "budget_exceeded"
        report_state.save_run_data(status="stopped")

    monkeypatch.setattr("strix.interface.cli.run_cli", mock_run_cli)
    _patch_main_preflight(monkeypatch, args, tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.main()

    assert exc_info.value.code == 1
    assert report_state.run_record.get("status") == "stopped"


def test_4_valid_zero_finding_completion_exit_code_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Valid completed scan with 0 findings must exit with code 0 (no exception/exit 1)."""
    report_state = ReportState(tmp_path)
    set_global_report_state(report_state)

    args = argparse.Namespace(
        non_interactive=True,
        needs_setup=False,
        resume_picker=False,
        run_name="test-run-zero",
        targets=[],
        fail_on=None,
    )

    async def mock_run_cli(_args):
        # Simulate finish_scan being called
        report_state.update_scan_final_fields(
            executive_summary="Clean system",
            methodology="OWASP",
            technical_analysis="No issues found",
            recommendations="Maintain patch cadence",
        )

    monkeypatch.setattr("strix.interface.cli.run_cli", mock_run_cli)
    _patch_main_preflight(monkeypatch, args, tmp_path)

    # Should not raise SystemExit(1) or SystemExit(2)
    main_mod.main()
    assert report_state.run_record.get("status") == "completed"
    assert len(report_state.vulnerability_reports) == 0


def test_5_api_marks_run_failed_when_run_json_not_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """API marks run as failed if returncode is 0 but run.json status is 'stopped'."""
    monkeypatch.setattr("strix.core.paths.runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr(api, "runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr(api, "_is_docker_available", lambda: True)

    run_id = "run-test-incomplete"
    u_dir = tmp_path / "strix-underlying-01"
    u_dir.mkdir(parents=True, exist_ok=True)
    # Write underlying run.json with status="stopped" (e.g. premature exit)
    (u_dir / "run.json").write_text(
        json.dumps(
            {
                "status": "stopped",
                "scan_ended_exit_reason": "missing_finish_scan",
            }
        )
    )

    req = RunRequest(
        scenario="autonomous_test",
        mode="autonomous",
        scan_mode="deep",
        target_url="http://127.0.0.1:8080",
        max_turns=20,
    )
    run_entry = {
        "run_id": run_id,
        "status": "queued",
        "scenario": req.scenario,
        "mode": req.mode,
        "target_url": "http://127.0.0.1:8080",
        "created_at": "2026-10-30T00:00:00Z",
        "completed_at": None,
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
        "stats": {"attempts": 0, "pivots": 0, "findings": 0},
    }
    _RUNS[run_id] = run_entry

    # Mock subprocess to exit with code 0 and emit underlying run name
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout.readline.side_effect = [
        "Starting scan\n",
        f"Output  strix_runs/{u_dir.name}\n",
        "",
    ]
    mock_proc.stderr.readline.side_effect = [""]
    mock_proc.wait.return_value = 0

    monkeypatch.setattr(api.subprocess, "Popen", lambda *a, **kw: mock_proc)
    monkeypatch.setattr("strix.core.triage.exploit_assessor.run_gap1_triage", lambda *a, **kw: [])

    _execute_run_worker(run_id, req, None)

    assert run_entry["status"] == "failed"
    assert "satisfying completion requirements" in run_entry.get("error", "")


def test_6_api_marks_run_completed_with_zero_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """API marks run as completed when run.json status is 'completed' with 0 findings."""
    monkeypatch.setattr("strix.core.paths.runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr(api, "runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr(api, "_is_docker_available", lambda: True)

    run_id = "run-test-zero-findings"
    u_dir = tmp_path / "strix-underlying-zero"
    u_dir.mkdir(parents=True, exist_ok=True)
    (u_dir / "run.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "scan_results": {"executive_summary": "All secure"},
            }
        )
    )
    (u_dir / "vulnerabilities.json").write_text("[]")

    req = RunRequest(
        scenario="autonomous_test",
        mode="autonomous",
        scan_mode="quick",
        target_url="http://127.0.0.1:8080",
        max_turns=10,
    )
    run_entry = {
        "run_id": run_id,
        "status": "queued",
        "scenario": req.scenario,
        "mode": req.mode,
        "target_url": "http://127.0.0.1:8080",
        "created_at": "2026-10-30T00:00:00Z",
        "completed_at": None,
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
        "stats": {"attempts": 0, "pivots": 0, "findings": 0},
    }
    _RUNS[run_id] = run_entry

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout.readline.side_effect = [
        f"Output  strix_runs/{u_dir.name}\n",
        "",
    ]
    mock_proc.stderr.readline.side_effect = [""]
    mock_proc.wait.return_value = 0

    monkeypatch.setattr(api.subprocess, "Popen", lambda *a, **kw: mock_proc)
    monkeypatch.setattr("strix.core.triage.exploit_assessor.run_gap1_triage", lambda *a, **kw: [])

    _execute_run_worker(run_id, req, None)

    assert run_entry["status"] == "completed"
    assert len(run_entry["findings"]) == 0
    assert run_entry["progress"]["percent"] == 100


def test_7_error_extraction_strips_rich_box_characters():
    """Verify that Rich box borders and decorative glyphs are cleanly stripped."""
    stderr_input = [
        "╭──────────────────────────────────────────────────────────╮",
        "│ RateLimitError: LLM API token rate limit reached (429)   │",
        "╰──────────────────────────────────────────────────────────╯",
    ]
    err = _extract_clean_error(stderr_input, [], fallback="Default error")
    assert "RateLimitError: LLM API token rate limit reached (429)" in err
    for ch in ("╭", "│", "╰", "─", "╮", "╯"):
        assert ch not in err

    # Line cleaner unit checks
    assert _is_decorative_line("╭───────────────────────╮") is True
    assert _is_decorative_line("│ Hello World │") is False
    assert (
        _clean_terminal_line("│   SyntaxError: invalid token   │") == "SyntaxError: invalid token"
    )


def test_8_subprocess_failure_preserves_partial_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Partial findings in vulnerabilities.json must be preserved even if subprocess fails."""
    monkeypatch.setattr("strix.core.paths.runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr(api, "runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr(api, "_is_docker_available", lambda: True)

    run_id = "run-test-partial-harvest"
    u_dir = tmp_path / "strix-underlying-partial"
    u_dir.mkdir(parents=True, exist_ok=True)
    # Subprocess stopped due to budget or crash
    (u_dir / "run.json").write_text(
        json.dumps(
            {
                "status": "stopped",
                "scan_ended_exit_reason": "budget_exceeded",
            }
        )
    )
    (u_dir / "vulnerabilities.json").write_text(
        json.dumps(
            [
                {
                    "id": "vuln-01",
                    "title": "SQL Injection in Search Form",
                    "severity": "HIGH",
                    "endpoint": "/search",
                    "detail": "' OR 1=1-- payload returned database error",
                },
                {
                    "id": "vuln-02",
                    "title": "Missing Security Headers",
                    "severity": "LOW",
                    "endpoint": "/",
                    "detail": "Strict-Transport-Security header absent",
                },
            ]
        )
    )

    req = RunRequest(
        scenario="autonomous_test",
        mode="autonomous",
        scan_mode="deep",
        target_url="http://127.0.0.1:8080",
        max_turns=50,
    )
    run_entry = {
        "run_id": run_id,
        "status": "queued",
        "scenario": req.scenario,
        "mode": req.mode,
        "target_url": "http://127.0.0.1:8080",
        "created_at": "2026-10-30T00:00:00Z",
        "completed_at": None,
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
        "stats": {"attempts": 0, "pivots": 0, "findings": 0},
    }
    _RUNS[run_id] = run_entry

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout.readline.side_effect = [
        f"Output  strix_runs/{u_dir.name}\n",
        "",
    ]
    mock_proc.stderr.readline.side_effect = [
        "BudgetExceededError: Scan exceeded maximum budget limit of $2.00\n",
        "",
    ]
    mock_proc.wait.return_value = 1

    monkeypatch.setattr(api.subprocess, "Popen", lambda *a, **kw: mock_proc)
    monkeypatch.setattr("strix.core.triage.exploit_assessor.run_gap1_triage", lambda *a, **kw: [])

    _execute_run_worker(run_id, req, None)

    assert run_entry["status"] == "failed"
    assert "BudgetExceededError" in run_entry.get("error", "")
    # Findings must be preserved!
    assert len(run_entry["findings"]) >= 2
    assert any(f.get("id") == "vuln-01" for f in run_entry["findings"])
    assert any(f.get("id") == "vuln-02" for f in run_entry["findings"])


def test_9_no_docker_execution_does_not_pad_turns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """In no-Docker execution, turns must not be padded up to max_turns."""
    monkeypatch.setattr("strix.core.paths.runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr(api, "runs_base_dir", lambda: tmp_path)
    monkeypatch.setattr(api, "_is_docker_available", lambda: False)

    run_id = "run-test-no-padding"
    req = RunRequest(
        scenario="simulation_test",
        mode="simulation",
        scan_mode="deep",
        target_url="http://127.0.0.1:8080",
        max_turns=100,  # High limit
        max_attempts=2,
    )
    run_entry = {
        "run_id": run_id,
        "status": "queued",
        "scenario": req.scenario,
        "mode": req.mode,
        "target_url": "http://127.0.0.1:8080",
        "created_at": "2026-10-30T00:00:00Z",
        "completed_at": None,
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
        "stats": {"attempts": 0, "pivots": 0, "findings": 0},
    }
    _RUNS[run_id] = run_entry

    _execute_run_worker(run_id, req, None)

    assert run_entry["status"] == "completed"
    # Must NOT have run all 100 turns synthetically
    assert run_entry["stats"]["attempts"] < 50
    assert run_entry["progress"]["current"] < 50


def test_10_gap_completion_gate_in_subprocess_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Completion gate blocks finish_scan when uninvestigated candidates remain in queue."""
    control_dir = tmp_path / "control"
    control_dir.mkdir(parents=True, exist_ok=True)

    # Populate candidate queue
    queue_payload = {
        "candidates": [
            {
                "candidate_id": "cand-01",
                "title": "SQL Injection in Login",
                "endpoint": "/login",
                "target": "http://test.local",
            },
            {
                "candidate_id": "cand-02",
                "title": "SSRF in Webhook",
                "endpoint": "/webhook",
                "target": "http://test.local",
            },
        ]
    }
    (control_dir / "gap1_queue.json").write_text(json.dumps(queue_payload))

    monkeypatch.setenv("STRIX_GAP_CONTROL_DIR", str(control_dir))
    monkeypatch.setenv("STRIX_GAP1_ENABLED", "1")

    from strix.tools.finish.tool import _evaluate_completion_gate

    # Gate evaluation should reject completion because neither cand-01 nor cand-02 was covered
    gate = _evaluate_completion_gate(control_dir=control_dir)
    assert gate["permitted"] is False
    assert "Premature completion rejected" in gate.get("error", "")
    assert set(gate["remaining_candidates"]) == {"cand-01", "cand-02"}

    # Now mark cand-01 as negative outcome (covered/safe) and cand-02 as exhausted
    gap_bridge.record_outcome(
        directory=control_dir,
        candidate_id="cand-01",
        title="SQL Injection in Login",
        endpoint="/login",
        target="http://test.local",
        probe_status="negative",
    )
    run_state = gap_bridge.get_run_state(control_dir)
    run_state.mark_exhausted("cand-02")

    # Now gate must permit completion!
    gate_after = _evaluate_completion_gate(control_dir=control_dir)
    assert gate_after["permitted"] is True
