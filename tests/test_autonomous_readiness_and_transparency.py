"""Tests for AI-VAPT autonomous execution readiness, diagnostics, and execution transparency.

Covers:
1. Docker unavailable when autonomous mode requested -> returns HTTP 400 or marks run blocked.
2. Docker available -> autonomous runner selected.
3. Explicit lightweight scanner selection (mode="lightweight").
4. Accurate execution-mode reporting in run.json and reports.
5. Zero fabricated LLM usage or turns in lightweight mode.
6. GET /system/readiness diagnostics response.
7. Missing provider configuration -> configuration_required.
8. Provider connectivity failure -> provider_unavailable.
9. Web and CLI configuration consistency.
10. Correct reporting when autonomous execution is unavailable.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from strix.core.diagnostics import ReadinessStatus, evaluate_runtime_readiness
from strix.interface.api import (
    _RUNS,
    _execute_run_worker,
    _generate_markdown_report,
    app,
)
from strix.interface.readiness import check_runtime_readiness
from strix.interface.schemas import RunRequest
from strix.report.builder import render_html_report


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


# 1. Docker unavailable when autonomous mode requested -> returns HTTP 400 or marks run blocked
def test_docker_unavailable_autonomous_rejected(test_client: TestClient):
    with patch("strix.interface.api._is_docker_available", return_value=False):
        res = test_client.post(
            "/runs",
            json={
                "target_url": "http://127.0.0.1:4280",
                "mode": "autonomous",
                "target_scope_acknowledged": True,
            },
        )
        assert res.status_code == 400
        detail = res.json().get("detail", "")
        assert "Autonomous multi-agent execution requires Docker" in detail
        assert "mode='lightweight'" in detail


def test_docker_unavailable_worker_marks_run_blocked(tmp_path: Path):
    run_id = "test-blocked-run"
    _RUNS[run_id] = {
        "run_id": run_id,
        "status": "queued",
        "scenario": "web_application",
        "mode": "autonomous",
        "target_url": "http://127.0.0.1:4280",
        "events": [],
        "findings": [],
        "candidates": [],
    }

    req = RunRequest(
        target_url="http://127.0.0.1:4280",
        mode="autonomous",
        scan_mode="quick",
        max_turns=5,
    )

    with (
        patch("strix.interface.api.runs_base_dir", return_value=tmp_path),
        patch("strix.interface.api._is_docker_available", return_value=False),
    ):
        _execute_run_worker(run_id, req, None)

    entry = _RUNS[run_id]
    assert entry["status"] == "blocked"
    assert entry["execution_mode"] == "blocked"
    assert "Docker runtime (daemon and CLI) is unavailable" in entry["error"]
    assert any(e.get("event") == "RUN_BLOCKED" for e in entry["events"])


# 2. Docker available -> autonomous runner selected
def test_docker_available_autonomous_runner_selected(tmp_path: Path):
    run_id = "test-docker-available-run"
    _RUNS[run_id] = {
        "run_id": run_id,
        "status": "queued",
        "scenario": "web_application",
        "mode": "autonomous",
        "target_url": "http://127.0.0.1:4280",
        "events": [],
        "findings": [],
        "candidates": [],
    }

    req = RunRequest(
        target_url="http://127.0.0.1:4280",
        mode="autonomous",
        scan_mode="quick",
        max_turns=5,
    )

    mock_proc = MagicMock()
    mock_proc.poll.side_effect = [None, 0]
    mock_proc.returncode = 0
    mock_proc.stdout.readline.return_value = ""
    mock_proc.stderr.read.return_value = ""

    with (
        patch("strix.interface.api.runs_base_dir", return_value=tmp_path),
        patch("strix.interface.api._is_docker_available", return_value=True),
        patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
    ):
        _execute_run_worker(run_id, req, "test-runtime-key")

    assert mock_popen.called
    entry = _RUNS[run_id]
    assert entry["execution_mode"] == "autonomous_multi_agent"


# 3. Explicit lightweight scanner selection (mode="lightweight")
def test_explicit_lightweight_scanner_selection(test_client: TestClient, tmp_path: Path):
    with (
        patch("strix.interface.api.runs_base_dir", return_value=tmp_path),
        patch("strix.interface.api._is_docker_available", return_value=False),
    ):
        res = test_client.post(
            "/runs",
            json={
                "target_url": "http://127.0.0.1:4280",
                "mode": "lightweight",
                "target_scope_acknowledged": True,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["execution_mode"] == "lightweight_active_scanner"
        assert data["status"] in ("running", "queued")


# 4. Accurate execution-mode reporting in run.json and reports
def test_accurate_execution_mode_reporting(tmp_path: Path):
    run_entry = {
        "run_id": "run-test-reporting",
        "status": "completed",
        "scenario": "web_application",
        "target_url": "http://127.0.0.1:4280",
        "execution_mode": "lightweight_active_scanner",
        "active_agent": "In-Process Active Scanner",
        "findings": [],
        "candidates": [],
        "events": [],
    }

    # Markdown report check
    md = _generate_markdown_report(run_entry)
    assert "**Execution Engine:** AI-VAPT Lightweight In-Process Active Scanner (No Docker)" in md
    assert "**Execution Mode:** LIGHTWEIGHT_ACTIVE_SCANNER" in md
    assert "A lightweight in-process active vulnerability scan was conducted" in md

    # HTML report check
    html = render_html_report(run_entry)
    assert "Lightweight Active Scanner (In-Process)" in html


# 5. Zero fabricated LLM usage or turns in lightweight mode
def test_zero_fabricated_llm_usage_in_lightweight_mode(tmp_path: Path):
    run_id = "test-lightweight-transparency"
    _RUNS[run_id] = {
        "run_id": run_id,
        "status": "queued",
        "scenario": "web_application",
        "mode": "lightweight",
        "target_url": "http://127.0.0.1:4280",
        "events": [],
        "findings": [],
        "candidates": [],
        "stats": {},
    }

    req = RunRequest(
        target_url="http://127.0.0.1:4280",
        mode="lightweight",
        scan_mode="quick",
        max_turns=5,
    )

    with (
        patch("strix.interface.api.runs_base_dir", return_value=tmp_path),
        patch("strix.interface.api._is_docker_available", return_value=False),
        patch(
            "strix.interface.api._probe_web_candidate",
            return_value=(False, "Clean endpoint", ""),
        ),
    ):
        _execute_run_worker(run_id, req, None)

    entry = _RUNS[run_id]
    assert entry["execution_mode"] == "lightweight_active_scanner"
    stats = entry.get("stats", {})
    assert stats.get("cost_usd", 0.0) == 0.0
    assert stats.get("input_tokens", 0) == 0
    assert stats.get("output_tokens", 0) == 0

    # Ensure no fabricated turns were logged
    for ev in entry["events"]:
        assert ev.get("event") != "TURN_STARTED"
        assert "Autonomous turn" not in ev.get("message", "")


# 6. GET /system/readiness diagnostics response
def test_get_system_readiness_endpoint(test_client: TestClient):
    res = test_client.get("/system/readiness")
    assert res.status_code == 200
    data = res.json()
    assert "overall_status" in data
    assert "components" in data
    assert "autonomous_ready" in data
    assert "lightweight_ready" in data
    assert "actionable_recommendations" in data

    components = data["components"]
    assert "python_environment" in components
    assert "docker_runtime" in components
    assert "llm_provider" in components
    assert "application_storage" in components


# 7. Missing provider configuration -> configuration_required
def test_missing_provider_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("STRIX_LLM", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    with patch("pathlib.Path.home", return_value=tmp_path):
        resp = check_runtime_readiness(api_key="", model="")
        comp = resp.components.get("llm_provider")
        assert comp is not None
        assert comp.status in (
            "configuration_required",
            "provider_unavailable",
        )


# 8. Provider connectivity failure -> provider_unavailable
def test_provider_connectivity_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-mock-invalid-key")
    monkeypatch.setenv("STRIX_LLM", "openrouter/google/gemini-2.5-flash")

    mock_resp = MagicMock()
    mock_resp.status = "invalid_credentials"
    mock_resp.valid = False
    mock_resp.message = "Key rejected by provider"

    with (
        patch("pathlib.Path.home", return_value=tmp_path),
        patch(
            "strix.llm.provider_validation.validate_openrouter_credential", return_value=mock_resp
        ),
    ):
        result = evaluate_runtime_readiness(test_network=True)
        prov_checks = [c for c in result.checks if c.category == "provider"]
        assert any(c.status == ReadinessStatus.PROVIDER_UNAVAILABLE for c in prov_checks)


# 9. Web and CLI configuration consistency
def test_web_and_cli_configuration_consistency():
    diag = evaluate_runtime_readiness(test_network=False)
    readiness = check_runtime_readiness()

    docker_diag = next(c for c in diag.checks if c.id == "docker_cli")
    docker_readiness = readiness.components["docker_runtime"]

    assert docker_diag.passed == docker_readiness.details["cli_available"]


# 10. Correct reporting when autonomous execution is unavailable
def test_reporting_when_autonomous_execution_unavailable(tmp_path: Path):
    run_entry = {
        "run_id": "run-blocked-test",
        "status": "blocked",
        "scenario": "web_application",
        "target_url": "http://127.0.0.1:4280",
        "execution_mode": "blocked",
        "active_agent": "Autonomous Multi-Agent Core",
        "error": "Autonomous execution blocked: Docker runtime unavailable.",
        "findings": [],
        "candidates": [],
        "events": [
            {
                "timestamp": "2026-11-10T00:00:00Z",
                "event": "RUN_BLOCKED",
                "message": "Docker unavailable",
            }
        ],
    }

    md = _generate_markdown_report(run_entry)
    assert "**Execution Mode:** BLOCKED" in md
    assert "Autonomous execution blocked: Docker runtime unavailable." in md
    # Must not report clean or zero findings as a verified assessment
    assert "Assessment not performed or blocked" in md

    html = render_html_report(run_entry)
    assert "Blocked (Runtime Dependencies Unavailable)" in html
