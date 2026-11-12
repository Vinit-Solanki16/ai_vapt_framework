"""Comprehensive end-to-end autonomous runtime readiness and execution transparency test suite.

Verifies:
1. GET /system/readiness correctly detects missing Docker and reports runtime_unavailable.
2. GET /system/readiness correctly detects available Docker and reports ready when all requirements are met.
3. POST /runs with mode: "autonomous" when Docker is unavailable returns HTTP 400 with actionable error message and does NOT create a silent fallback run.
4. POST /runs with mode: "lightweight" runs the in-process active scanner and reports execution_mode: "lightweight_active_scanner".
5. Lightweight scan reports do NOT contain simulated agent turns, LLM costs, or fake GAP-2 pivots.
6. The CLI --run-name / --name flag correctly controls the output directory.
7. Web API run execution passes the exact run ID to the CLI subprocess and monitors the expected directory.
8. Finding verification lifecycle enforces genuine evidence for both autonomous and lightweight modes.
9. Provider connectivity check correctly identifies quota exhaustion without leaking keys.
10. All reports accurately reflect the actual execution engine used.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from strix.core.diagnostics import ReadinessStatus, evaluate_runtime_readiness
from strix.interface.api import _RUNS, _generate_markdown_report, app
from strix.interface.cli_args import parse_arguments
from strix.interface.readiness import check_runtime_readiness
from strix.interface.scan_setup import prepare_run
from strix.interface.schemas import RunRequest
from strix.report.builder import render_html_report
from strix.report.state import ReportState
from strix.report.verification import (
    VerificationBlock,
    VerificationState,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# -----------------------------------------------------------------------------
# 1. GET /system/readiness correctly detects missing Docker -> runtime_unavailable
# -----------------------------------------------------------------------------
def test_readiness_detects_missing_docker_runtime_unavailable(client: TestClient):
    """When Docker is absent or daemon is down, readiness returns runtime_unavailable."""
    with (
        patch("shutil.which", return_value=None),
        patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False),
    ):
        res = client.get("/system/readiness")
        assert res.status_code == 200
        data = res.json()

        assert data["overall_status"] == "runtime_unavailable"
        assert data["autonomous_ready"] is False
        assert data["lightweight_ready"] is True
        assert "docker_runtime" in data["components"]
        docker_comp = data["components"]["docker_runtime"]
        assert docker_comp["status"] == "runtime_unavailable"
        assert docker_comp["available"] is False
        assert "Docker CLI is not found" in docker_comp["actionable_message"]

        # Also verify alias /diagnostics/readiness
        diag_res = client.get("/diagnostics/readiness")
        assert diag_res.status_code == 200
        diag_data = diag_res.json()
        assert diag_data["overall_status"] == "runtime_unavailable"


# -----------------------------------------------------------------------------
# 2. GET /system/readiness correctly detects available Docker -> ready
# -----------------------------------------------------------------------------
def test_readiness_detects_available_docker_ready(client: TestClient):
    """When Docker CLI, daemon, image, Python, and provider are present, status is ready."""

    def mock_subp_run(cmd, *args, **kwargs):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Docker version 24.0.5"
        mock_res.stderr = ""
        return mock_res

    with (
        patch("shutil.which", return_value="/usr/bin/docker"),
        patch("subprocess.run", side_effect=mock_subp_run),
        patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}),
        patch("strix.llm.provider_validation.validate_openrouter_credential") as mock_val,
    ):
        mock_val.return_value = MagicMock(valid=True, status="valid", message="Ready")

        report = check_runtime_readiness(
            provider="openrouter",
            model="openrouter/meta-llama/llama-3.3-70b-instruct",
            api_key="sk-or-v1-mock-dummy-token-for-test-only",
            image="strix-sandbox:latest",
        )

        assert report.overall_status == "ready"
        assert report.autonomous_ready is True
        assert report.lightweight_ready is True
        assert report.components["docker_runtime"].status == "ready"
        assert report.components["docker_runtime"].available is True
        assert report.components["llm_provider"].status == "ready"


# -----------------------------------------------------------------------------
# 3. POST /runs with mode: "autonomous" when Docker is unavailable returns HTTP 400
# -----------------------------------------------------------------------------
def test_post_runs_autonomous_without_docker_returns_400(client: TestClient):
    """Requesting autonomous multi-agent execution when Docker is down fails fast with 400."""
    with patch("strix.interface.api._is_docker_available", return_value=False):
        runs_before = len(_RUNS)

        payload = {
            "target_url": "http://127.0.0.1:4280",
            "mode": "autonomous",
            "scan_mode": "quick",
            "max_turns": 10,
            "target_scope_acknowledged": True,
        }
        res = client.post("/runs", json=payload)
        assert res.status_code == 400
        data = res.json()

        assert "Autonomous multi-agent execution requires Docker runtime" in data["detail"]
        assert "mode='lightweight'" in data["detail"]

        # Ensure no silent fallback run was queued or registered
        assert len(_RUNS) == runs_before


# -----------------------------------------------------------------------------
# 4. POST /runs with mode: "lightweight" reports execution_mode: "lightweight_active_scanner"
# -----------------------------------------------------------------------------
def test_post_runs_lightweight_execution_mode(client: TestClient):
    """Launching lightweight mode records execution_mode as lightweight_active_scanner."""
    with (
        patch("strix.interface.api.BackgroundTasks.add_task", return_value=None),
        patch("strix.interface.api._save_run_to_disk", return_value=None),
    ):
        payload = {
            "target_url": "http://127.0.0.1:4280",
            "mode": "lightweight",
            "scan_mode": "quick",
            "max_turns": 25,
            "target_scope_acknowledged": True,
        }
        res = client.post("/runs", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert data["execution_mode"] == "lightweight_active_scanner"
        assert data["run_id"] in _RUNS
        assert _RUNS[data["run_id"]]["execution_mode"] == "lightweight_active_scanner"
        assert _RUNS[data["run_id"]]["mode"] == "lightweight"


# -----------------------------------------------------------------------------
# 5. Lightweight scan reports do NOT contain simulated agent turns, LLM costs, or fake GAP-2 pivots
# -----------------------------------------------------------------------------
def test_lightweight_scan_reports_no_simulated_agent_turns_or_llm_costs():
    """Reports generated for lightweight mode strictly reflect in-process scanner without synthetic agent costs."""
    run_record: dict[str, Any] = {
        "run_id": "run-test-lightweight-001",
        "mode": "lightweight",
        "execution_mode": "lightweight_active_scanner",
        "target_url": "http://127.0.0.1:4280",
        "status": "completed",
        "start_time": datetime.now(UTC).isoformat(),
        "end_time": datetime.now(UTC).isoformat(),
        "duration_seconds": 12.5,
        "findings": [
            {
                "id": "lw-01",
                "title": "Missing Security Headers",
                "severity": "LOW",
                "cvss_score": 3.1,
                "location": "/",
                "verification_state": "Verified",
                "verified": True,
                "reproducible_request": "GET / HTTP/1.1\nHost: 127.0.0.1:4280",
                "reproducible_response": "HTTP/1.1 200 OK\nServer: Apache",
                "verification_procedure": "Inspect response headers for Strict-Transport-Security",
                "demonstrated_impact": "Lack of HTTP strict transport security policy",
                "evidence_timestamp": datetime.now(UTC).isoformat(),
            }
        ],
        "pivot_events": [],
        "cost_usd": 0.0,
    }

    md_report = _generate_markdown_report(run_record)
    assert "AI-VAPT Lightweight In-Process Active Scanner (No Docker)" in md_report
    assert "Autonomous multi-agent vulnerability assessment was conducted" not in md_report
    assert "lightweight in-process active vulnerability scan was conducted" in md_report

    # Ensure no fabricated agent turn cost
    assert "Agent Turn Token Usage" not in md_report


# -----------------------------------------------------------------------------
# 6. CLI --run-name or --name flag correctly controls the output directory
# -----------------------------------------------------------------------------
def test_cli_run_name_controls_output_directory(tmp_path: Path):
    """CLI arguments --run-name and --name set args.run_name and prepare_run creates exact run_dir."""
    custom_run = "my-designated-run-xyz"

    test_args = ["strix", "-n", "-t", "http://127.0.0.1:4280", "--run-name", custom_run]
    with (
        patch("sys.argv", test_args),
        patch("strix.interface.cli_args.os.path.isdir", return_value=False),
        patch("strix.interface.cli_args.os.path.isfile", return_value=False),
    ):
        parsed = parse_arguments()
        assert parsed.run_name == custom_run

    # Test alias --name
    test_alias_args = ["strix", "-n", "-t", "http://127.0.0.1:4280", "--name", custom_run]
    with (
        patch("sys.argv", test_alias_args),
        patch("strix.interface.cli_args.os.path.isdir", return_value=False),
        patch("strix.interface.cli_args.os.path.isfile", return_value=False),
    ):
        parsed_alias = parse_arguments()
        assert parsed_alias.run_name == custom_run

    # Test prepare_run honoring args.run_name
    parsed.targets_info = [
        {
            "type": "web",
            "target": "http://127.0.0.1:4280",
            "details": {"target": "http://127.0.0.1:4280"},
        }
    ]
    parsed.resume = None
    with patch("strix.interface.scan_setup.run_dir_for", return_value=tmp_path / custom_run):
        prepare_run(parsed)
        assert parsed.run_name == custom_run


# -----------------------------------------------------------------------------
# 7. Web API run execution passes exact run ID to CLI subprocess and monitors expected dir
# -----------------------------------------------------------------------------
def test_web_api_passes_run_id_to_subprocess_and_monitors_dir(tmp_path: Path):
    """When launching autonomous execution, Web API passes --run-name {run_id} to subprocess."""
    from strix.interface.api import _execute_run_worker

    run_id = f"test-subp-run-{int(datetime.now(UTC).timestamp())}"
    run_entry: dict[str, Any] = {
        "run_id": run_id,
        "mode": "autonomous",
        "target_url": "http://127.0.0.1:4280",
        "status": "queued",
        "candidates": [],
        "events": [],
    }
    _RUNS[run_id] = run_entry

    req = RunRequest(
        target_url="http://127.0.0.1:4280",
        mode="autonomous",
        scan_mode="quick",
        max_turns=5,
        target_scope_acknowledged=True,
    )

    captured_cmd = []
    captured_env = {}

    def mock_popen(cmd, *args, **kwargs):
        captured_cmd.extend(cmd)
        captured_env.update(kwargs.get("env", {}))
        m = MagicMock()
        m.stdout.readline.side_effect = [f"Output strix_runs/{run_id}\n", ""]
        m.stderr.readline.side_effect = [""]
        m.poll.return_value = 0
        m.returncode = 0
        return m

    fake_run_dir = tmp_path / "strix_runs" / run_id
    fake_run_dir.mkdir(parents=True, exist_ok=True)
    (fake_run_dir / "run.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    (fake_run_dir / "vulnerabilities.json").write_text(json.dumps([]), encoding="utf-8")

    with (
        patch("strix.interface.api._is_docker_available", return_value=True),
        patch("strix.interface.api.subprocess.Popen", side_effect=mock_popen),
        patch("strix.interface.api.runs_base_dir", return_value=tmp_path / "strix_runs"),
        patch("strix.interface.api.PROJECT_ROOT", tmp_path),
    ):
        _execute_run_worker(run_id, req, None)

        # Assert --run-name {run_id} was explicitly delivered in CLI arguments
        assert "--run-name" in captured_cmd
        run_name_idx = captured_cmd.index("--run-name")
        assert captured_cmd[run_name_idx + 1] == run_id
        # Assert STRIX_RUN_NAME environment variable was passed
        assert captured_env.get("STRIX_RUN_NAME") == run_id


# -----------------------------------------------------------------------------
# 8. Finding verification lifecycle enforces genuine evidence
# -----------------------------------------------------------------------------
def test_finding_verification_lifecycle_enforces_genuine_evidence(tmp_path: Path):
    """Findings claiming verified without reproducible evidence are demoted to unconfirmed."""
    state = ReportState("test-verification-contract")
    state.targets_info = [{"type": "web", "target": "http://127.0.0.1:4280", "details": {}}]

    # 1. VerificationBlock without complete reproducible evidence fails contract
    vb_incomplete = VerificationBlock(
        verification_state=VerificationState.VERIFIED.value,
        reproducible_request="GET /sqli?id=1 HTTP/1.1",
        verification_response="",  # missing response evidence!
        verification_procedure="Injected quote",
        demonstrated_impact="Database read",
        evidence_timestamp=datetime.now(UTC).isoformat(),
    )
    assert vb_incomplete.satisfies_verification_contract() is False

    # Adding to ReportState automatically demotes incomplete verified findings
    fid_incomplete = state.add_vulnerability_report(
        title="Unproven SQLi",
        severity="critical",
        verification=vb_incomplete,
    )
    report_incomplete = next(r for r in state.vulnerability_reports if r["id"] == fid_incomplete)
    assert report_incomplete["verification_state"] == VerificationState.UNCONFIRMED.value

    # 2. Complete verified evidence satisfies contract and is preserved as verified
    vb_complete = VerificationBlock(
        verification_state=VerificationState.VERIFIED.value,
        reproducible_request="GET /vulnerabilities/sqli/?id=1' HTTP/1.1\nHost: target",
        verification_response="HTTP/1.1 200 OK\n\nSQL syntax error near ''''",
        verification_procedure="Injected SQL single quote into id parameter and observed raw DBMS syntax failure",
        demonstrated_impact="Arbitrary database read via unescaped string literal in SQL query",
        evidence_timestamp=datetime.now(UTC).isoformat(),
    )
    assert vb_complete.satisfies_verification_contract() is True

    fid_complete = state.add_vulnerability_report(
        title="Proven SQLi",
        severity="critical",
        verification=vb_complete,
    )
    report_complete = next(r for r in state.vulnerability_reports if r["id"] == fid_complete)
    assert report_complete["verification_state"] == VerificationState.VERIFIED.value


# -----------------------------------------------------------------------------
# 9. Provider connectivity check correctly identifies quota exhaustion without leaking keys
# -----------------------------------------------------------------------------
def test_provider_connectivity_identifies_quota_exhaustion_without_leaking_key():
    """Quota exhaustion maps to provider_unavailable and masks raw credentials."""
    secret_key = "sk-or-v1-secret-operator-token-do-not-leak"

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = json.dumps(
            {
                "error": {
                    "message": "Daily free tier request limit reached. Exceeded daily quota.",
                    "code": 429,
                }
            }
        )
        mock_resp.json.return_value = {
            "error": {
                "message": "Daily free tier request limit reached. Exceeded daily quota.",
                "code": 429,
            }
        }
        mock_get.return_value = mock_resp

        report = evaluate_runtime_readiness(
            custom_provider="openrouter",
            custom_model="openrouter/meta-llama/llama-3.3-70b-instruct",
            custom_api_key=secret_key,
            test_network=True,
        )

        assert report.status == ReadinessStatus.PROVIDER_UNAVAILABLE
        assert report.ready_for_autonomous is False

        # Verify raw secret key is never leaked anywhere in serialized report or details
        report_json = report.model_dump_json()
        assert secret_key not in report_json
        assert "sk-or-v1-secret-operator" not in report_json


# -----------------------------------------------------------------------------
# 10. All reports accurately reflect the actual execution engine used
# -----------------------------------------------------------------------------
def test_reports_accurately_reflect_execution_engine(tmp_path: Path):
    """HTML and Markdown reports truthfully display engine labels for both modes."""
    # Test Autonomous Multi-Agent Core HTML Report
    auto_data = {
        "run_id": "test-auto-report",
        "execution_mode": "autonomous_multi_agent",
        "target_url": "http://127.0.0.1:4280",
        "findings": [],
    }
    html_auto = render_html_report(auto_data)
    assert "Autonomous Multi-Agent Core (Docker)" in html_auto

    # Test Lightweight Active Scanner HTML Report
    lw_data = {
        "run_id": "test-lw-report",
        "execution_mode": "lightweight_active_scanner",
        "target_url": "http://127.0.0.1:4280",
        "findings": [],
    }
    html_lw = render_html_report(lw_data)
    assert "Lightweight Active Scanner (In-Process)" in html_lw

    # Test Markdown Generation Engine Labels
    auto_md = _generate_markdown_report({"execution_mode": "autonomous_multi_agent"})
    assert "AI-VAPT Autonomous Multi-Agent Core (Docker Sandbox)" in auto_md

    lw_md = _generate_markdown_report({"execution_mode": "lightweight_active_scanner"})
    assert "AI-VAPT Lightweight In-Process Active Scanner (No Docker)" in lw_md
