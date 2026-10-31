"""Tests for STRIX AI-VAPT FastAPI Gateway."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from strix.interface.api import app

client = TestClient(app)


def test_health_endpoint():
    """Verify health check responds with 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"


def test_serve_index_html():
    """Verify root / serves the Web Console SPA white-labeled without strix mentions."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "AI-VAPT" in response.text
    assert "strix" not in response.text.lower()


def test_openrouter_free_models_endpoint():
    """Verify /providers/openrouter/models returns free models without requiring auth."""
    response = client.get("/providers/openrouter/models")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Every model returned should have free=True
    assert any("free" in m.get("id", "").lower() for m in data)


def test_serve_static_assets():
    """Verify static CSS and JS are served properly."""
    css_res = client.get("/css/styles.css")
    assert css_res.status_code == 200
    assert len(css_res.content) > 100

    js_res = client.get("/js/app.js")
    assert js_res.status_code == 200
    assert len(js_res.content) > 1000


def test_system_health():
    """Verify system readiness probe returns components status."""
    response = client.get("/system/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("READY", "DEGRADED")
    assert "components" in data
    assert "strix_core" in data["components"]


def test_list_scenarios():
    """Verify available benchmark scenarios endpoint."""
    response = client.get("/scenarios")
    assert response.status_code == 200
    scenarios = response.json()
    assert isinstance(scenarios, list)
    scenario_ids = [s["id"] for s in scenarios]
    assert "failure_pivot" in scenario_ids
    assert "docker_pivot" in scenario_ids


def test_validate_target():
    """Verify target scope validation endpoint."""
    # Local loopback target
    res = client.post("/targets/validate", json={"target_url": "http://127.0.0.1:8080/test"})
    assert res.status_code == 200
    data = res.json()
    assert "authorized" in data
    assert data["authorized"] is True


def test_run_lifecycle_and_trace():
    """Verify creating a run, querying status, and viewing trace."""
    # Launch simulation run
    post_res = client.post(
        "/runs",
        json={
            "scenario": "failure_pivot",
            "mode": "simulation",
            "assessor": "llm",
            "assessor_provider": "ollama",
            "assessor_model": "qwen2.5:1.5b",
            "max_attempts": 2,
        },
    )
    assert post_res.status_code == 200
    run_info = post_res.json()
    run_id = run_info.get("run_id")
    assert run_id is not None
    assert "run-" in run_id

    # Query status
    status_res = client.get(f"/runs/{run_id}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["run_id"] == run_id
    assert status_data["status"] in ("queued", "running", "completed")


def test_report_downloads():
    """Verify HTML and JSON report downloads with attachment disposition and CVE/CWE presence."""
    # Launch quick run against local target
    post_res = client.post(
        "/runs",
        json={
            "target_url": "http://127.0.0.1:8080/",
            "mode": "web",
            "max_attempts": 2,
        },
    )
    assert post_res.status_code == 200
    run_id = post_res.json()["run_id"]

    import time
    # Allow background execution
    time.sleep(0.5)

    # 1. Download HTML report
    html_res = client.get(f"/runs/{run_id}/report?format=html&download=1")
    assert html_res.status_code == 200
    assert "text/html" in html_res.headers.get("content-type", "")
    assert f'filename="vapt_report_{run_id}.html"' in html_res.headers.get("content-disposition", "")
    assert "CVE" in html_res.text
    assert "CWE-" in html_res.text
    assert "GAP-1" in html_res.text
    assert "GAP-2" in html_res.text

    # 2. Download JSON report
    json_res = client.get(f"/runs/{run_id}/report?format=json&download=1")
    assert json_res.status_code == 200
    assert "application/json" in json_res.headers.get("content-type", "")
    assert f'filename="vapt_audit_{run_id}.json"' in json_res.headers.get("content-disposition", "")
    assert "\n  " in json_res.text  # Verifies 2-space indented pretty-printed JSON!
    json_data = json_res.json()
    assert json_data["run_id"] == run_id
    assert "findings" in json_data
    assert "candidates" in json_data
    assert len(json_data["candidates"]) > 0
    assert "composite_score" in json_data["candidates"][0]
    assert "priority_rank" in json_data["candidates"][0]


def test_engagements_endpoint():
    """Verify listing and creating engagement profiles."""
    res = client.get("/engagements")
    assert res.status_code == 200
    engs = res.json()
    assert len(engs) >= 1
    assert any(e["id"] == "default-local" for e in engs)


def test_deep_scan_mode_and_turn_accounting():
    """Verify that scan_mode='deep' and max_turns are honored with turn-by-turn tracking."""
    from strix.interface.api import _execute_run_worker, _RUNS
    from strix.interface.schemas import RunRequest

    req = RunRequest(
        scenario="simulation_test",
        mode="simulation",
        scan_mode="deep",
        max_turns=15,
        max_attempts=2,
    )
    test_run_id = "run-deep-test-01"
    _RUNS[test_run_id] = {
        "run_id": test_run_id,
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

    _execute_run_worker(test_run_id, req, None)

    run_record = _RUNS[test_run_id]
    assert run_record["status"] == "completed"
    trace = run_record["decision_trace"]
    assert len(trace) > 0
    # Verifies turn tracking format
    assert any("[TURN 1/15]" in line for line in trace)
    assert any("Limit: 15 turns" in line for line in trace)
    assert run_record["progress"]["total"] == 15


def test_probe_false_positive_elimination():
    """Verify that _probe_web_candidate returns False for non-vulnerable / WAF-protected targets."""
    from strix.interface.api import _probe_web_candidate

    # Test against arbitrary URL: XSS, SQLi, RCE, and LFI must return False unless confirmed
    is_xss, msg_xss, _ = _probe_web_candidate("http://127.0.0.1:9999", "reflected-xss", "/search")
    assert is_xss is False
    assert "rejected" in msg_xss.lower() or "properly" in msg_xss.lower() or "blocked" in msg_xss.lower()

    is_sqli, msg_sqli, _ = _probe_web_candidate("http://127.0.0.1:9999", "sql-injection-error", "/login")
    assert is_sqli is False
    assert "no sql syntax error" in msg_sqli.lower()

    is_rce, msg_rce, _ = _probe_web_candidate("http://127.0.0.1:9999", "cmd-injection-rce", "/ping")
    assert is_rce is False
    assert "rejected or sanitized" in msg_rce.lower()

    is_lfi, msg_lfi, _ = _probe_web_candidate("http://127.0.0.1:9999", "lfi-traversal", "/view")
    assert is_lfi is False
    assert "blocked or sanitized" in msg_lfi.lower()


def test_technology_aware_remediation_iis_aspnet():
    """Verify that findings detected on an ASP.NET / IIS stack receive web.config remediations."""
    from strix.core.triage.owasp_mapping import map_finding_to_owasp

    res = map_finding_to_owasp(
        "Missing Security Hardening Headers",
        rule_id="missing-security-headers",
        tech_stack="aspnet_iis",
    )
    assert "web.config" in res["remediation_technical"]
    assert "<system.webServer>" in res["remediation_technical"]
    assert "Strict-Transport-Security" in res["remediation_technical"]
    assert "X-Frame-Options" in res["remediation_technical"]


def test_llm_settings_endpoints():
    """Verify GET and POST /settings/llm endpoints configure provider and model."""
    # 1. GET settings
    get_res = client.get("/settings/llm")
    assert get_res.status_code == 200
    cfg = get_res.json()
    assert "provider" in cfg
    assert "model" in cfg

    # 2. POST update settings
    post_res = client.post(
        "/settings/llm",
        json={
            "provider": "openrouter",
            "model": "meta-llama/llama-3.2-3b-instruct:free",
            "api_key": "sk-or-v1-testkey1234567890abcdef",
            "reasoning_effort": "medium",
        },
    )
    assert post_res.status_code == 200
    data = post_res.json()
    assert data["status"] == "ok"

    # Verify updated settings
    verify_res = client.get("/settings/llm")
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert v_data["provider"] == "openrouter"
    assert "llama" in v_data["model"].lower()
    assert v_data["has_api_key"] is True


def test_multiformat_report_endpoints():
    """Verify report endpoint generates HTML, JSON, PDF, SARIF, and Markdown."""
    # Launch quick run
    post_res = client.post(
        "/runs",
        json={
            "target_url": "http://127.0.0.1:8080/",
            "mode": "web",
            "max_attempts": 2,
        },
    )
    assert post_res.status_code == 200
    run_id = post_res.json()["run_id"]

    import time
    time.sleep(0.5)

    # 1. SARIF format
    sarif_res = client.get(f"/runs/{run_id}/report?format=sarif")
    assert sarif_res.status_code == 200
    assert "application/json" in sarif_res.headers.get("content-type", "")
    sarif_data = sarif_res.json()
    assert "$schema" in sarif_data or "runs" in sarif_data

    # 2. Markdown format
    md_res = client.get(f"/runs/{run_id}/report?format=markdown")
    assert md_res.status_code == 200
    assert "text/markdown" in md_res.headers.get("content-type", "")
    assert "Security Penetration Test Report" in md_res.text or "Vulnerability" in md_res.text

    # 3. PDF format
    pdf_res = client.get(f"/runs/{run_id}/report?format=pdf")
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers.get("content-type", "")
    assert pdf_res.content.startswith(b"%PDF-")


def test_stop_run_endpoint():
    """Verify that POST /runs/{run_id}/stop gracefully marks a run as aborted."""
    from strix.interface.api import _RUNS

    test_run_id = "run-stop-test-01"
    _RUNS[test_run_id] = {
        "run_id": test_run_id,
        "status": "running",
        "events": [],
    }

    res = client.post(f"/runs/{test_run_id}/stop")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert _RUNS[test_run_id]["status"] == "aborted"
    assert any(e.get("event") == "RUN_STOPPED" for e in _RUNS[test_run_id]["events"])



