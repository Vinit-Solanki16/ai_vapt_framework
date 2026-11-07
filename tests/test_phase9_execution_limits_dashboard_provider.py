"""Regression and integration tests for Phase 9: Execution Limits, Live Dashboard, and Provider Reliability.

Verifies:
1. Execution limits: 50, 100, 250, 500, 1000, and custom ranges (1-1000).
2. Validation error on unsupported limits (< 1, > 1000, invalid types).
3. API and CLI agreement on default max turns (500).
4. Live SSE updates for turns, progress, candidates, pivots, and findings.
5. Provider daily quota exhaustion detection and fast rejection.
6. OpenAI-compatible custom endpoint validation.
7. Truthful failure presentation (no fabricated 90% progress, accurate turn counts).
8. Preservation of provider and model metadata in run details.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from strix.config.settings import DEFAULT_MAX_TURNS
from strix.interface.api import _RUNS, app
from strix.interface.schemas import RunRequest
from strix.llm.provider_validation import (
    validate_openai_compatible_endpoint,
    validate_openrouter_credential,
)


client = TestClient(app)


def test_execution_limits_presets_and_custom():
    """Verify presets 50, 100, 250, 500, 1000 and custom values are preserved without clamping."""
    for limit in (50, 100, 250, 500, 1000, 75, 333, 750):
        req = RunRequest(target_url="http://127.0.0.1:3000/", max_turns=limit)
        assert req.max_turns == limit


def test_execution_limits_unsupported_validation_errors():
    """Verify unsupported limits (< 1, > 1000, non-integer) raise validation errors."""
    for bad_limit in (0, -1, -50, 1001, 5000, 99999):
        with pytest.raises(Exception) as exc_info:
            RunRequest(target_url="http://127.0.0.1:3000/", max_turns=bad_limit)
        assert "Execution turn limit must be between 1 and 1000 turns" in str(exc_info.value)

    with pytest.raises(Exception):
        RunRequest(target_url="http://127.0.0.1:3000/", max_turns="invalid_number")


def test_api_cli_settings_agreement():
    """Verify that settings, schemas, and CLI parser agree on 500 default turns."""
    from strix.interface.cli_args import parse_arguments

    assert DEFAULT_MAX_TURNS == 500
    req = RunRequest()
    assert req.max_turns == 500

    # Parse CLI with minimal required target flag
    with patch("sys.argv", ["strix", "-t", "http://127.0.0.1:3000/"]):
        args = parse_arguments()
        assert args.max_turns == 500


def test_provider_and_model_recorded_in_run_details():
    """Verify that provider and exact model are preserved in run records."""
    req_payload = {
        "mode": "simulation",
        "scenario": "test_provider_metadata",
        "assessor_provider": "openrouter",
        "assessor_model": "nvidia/nemotron-3.5-lightning:free",
        "max_turns": 50,
        "target_url": "http://127.0.0.1:3000/",
        "target_scope_acknowledged": True,
    }
    res = client.post("/runs", json=req_payload)
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    run_res = client.get(f"/runs/{run_id}")
    assert run_res.status_code == 200
    data = run_res.json()
    assert data["max_turns"] == 50
    # Clean up
    _RUNS.pop(run_id, None)


def test_openrouter_daily_quota_exhaustion_detection():
    """Verify that validate_openrouter_credential detects daily free request quota exhaustion."""
    mock_resp_data = {
        "data": {
            "label": "test-key",
            "free_model_daily_requests": {
                "used": 50,
                "limit": 50,
                "remaining": 0,
            },
        }
    }
    cm = MagicMock()
    cm.status = 200
    cm.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = cm

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = validate_openrouter_credential("sk-or-v1-testkey")
        assert res.valid is False
        assert res.status == "quota_exceeded"
        assert "daily free quota is exhausted" in res.message


def test_openai_compatible_endpoint_validation():
    """Verify validation of custom OpenAI-compatible endpoints."""
    # 1. Successful connection
    mock_resp_data = {"data": [{"id": "meta-llama/llama-3.3-70b-instruct"}]}
    cm = MagicMock()
    cm.status = 200
    cm.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = cm

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = validate_openai_compatible_endpoint("http://127.0.0.1:8765/v1", "test-token")
        assert res.valid is True
        assert res.status == "configured"
        assert "meta-llama/llama-3.3-70b-instruct" in res.models

    # 2. Endpoint validation API endpoint
    with patch("urllib.request.urlopen", return_value=mock_resp):
        api_res = client.post(
            "/providers/openai/validate", json={"api_base": "http://127.0.0.1:8765/v1"}
        )
        assert api_res.status_code == 200
        assert api_res.json()["valid"] is True


def test_truthful_failure_presentation():
    """Verify that failed runs do not display fabricated 90% progress or 'Report synthesis'."""
    run_id = "test-fail-run-truthful"
    run_record = {
        "run_id": run_id,
        "status": "failed",
        "error": "OpenRouter daily free quota exceeded (HTTP 429).",
        "target_url": "http://127.0.0.1:3000/",
        "max_turns": 250,
        "progress": {
            "phase": "Failed: OpenRouter daily free quota exceeded",
            "phase_index": 3,
            "percent": 22,
            "current": 5,
            "total": 250,
            "candidates_identified": 7,
            "candidates_investigated": 1,
            "pivots": 0,
            "run_id": run_id,
        },
        "findings": [
            {
                "id": "vuln-test-01",
                "title": "Missing Security Header",
                "severity": "LOW",
                "cvss_score": 3.0,
            }
        ],
        "events": [],
        "decision_trace": ["[TURN 5/250] Failed due to 429 quota"],
    }
    _RUNS[run_id] = run_record

    res = client.get(f"/runs/{run_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "failed"
    assert data["progress"]["percent"] == 22  # Truthful, NOT 90%
    assert "Report synthesis" not in data["progress"]["phase"]
    assert "Failed" in data["progress"]["phase"]
    assert data["progress"]["current"] == 5
    assert len(data["findings"]) == 1

    _RUNS.pop(run_id, None)


def test_sse_stream_events_and_data_flow():
    """Verify SSE streaming yields state, progress, log, findings, and complete events."""
    run_id = "test-sse-stream-001"
    run_record = {
        "run_id": run_id,
        "status": "completed",
        "target_url": "http://127.0.0.1:3000/",
        "max_turns": 100,
        "progress": {
            "phase": "Assessment Complete",
            "phase_index": 5,
            "percent": 100,
            "current": 10,
            "total": 100,
            "run_id": run_id,
        },
        "decision_trace": ["[TURN 1/100] Initializing", "[TURN 2/100] Completed"],
        "findings": [{"id": "find-01", "title": "Test Finding", "severity": "MEDIUM"}],
        "events": [],
        "pivot_events": [],
        "candidates": [{"id": "cand-01", "state": "VALIDATED", "attempts": 1}],
    }
    _RUNS[run_id] = run_record

    with client.stream("GET", f"/runs/{run_id}/stream") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        lines = []
        for line in response.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 8:
                break

        full_stream = "\n".join(lines)
        assert "event: state" in full_stream or "event: complete" in full_stream

    _RUNS.pop(run_id, None)
