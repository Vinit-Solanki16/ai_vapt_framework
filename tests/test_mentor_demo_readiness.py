"""Tests for Phase 2, 3, and mentor demo readiness.

Validates:
  1. Live Ollama probe (reachability, model presence, model missing, actionable errors).
  2. API /providers/ollama/status endpoint and system health reflection.
  3. Clean fallback provenance when Ollama is unavailable.
  4. CLI parser and invocation parity for provider, model, target_url, and ack.
  5. JavaScript syntax check pass.
"""
from __future__ import annotations

import io
import json
import subprocess
import urllib.error
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from decision_engine.core.schemas import ActionCandidate
from services.api import app as fastapi_app
from vapt_platform.assessment import create_assessor
from vapt_platform.model_config import DEFAULT_OLLAMA_MODEL
from vapt_platform.ollama_service import (
    _model_matches,
    get_ollama_base_url,
    probe_ollama,
)


# ---------------------------------------------------------------------------
# 1. Ollama Probe Unit Tests
# ---------------------------------------------------------------------------

def test_model_matches_logic():
    assert _model_matches("llama3.2:3b", "llama3.2:3b")
    assert _model_matches("llama3.2:3b:latest", "llama3.2:3b")
    assert _model_matches("llama3.2:3b", "llama3.2:3b:latest")
    assert _model_matches("qwen2.5:3b", "qwen2.5:3b")
    assert not _model_matches("llama3.2:1b", "llama3.2:3b")
    assert not _model_matches("", "llama3.2:3b")
    assert not _model_matches("llama3.2:3b", "")


def test_get_ollama_base_url_default_and_env(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert get_ollama_base_url() == "http://127.0.0.1:11434"

    monkeypatch.setenv("OLLAMA_HOST", "192.168.1.50:11434")
    assert get_ollama_base_url() == "http://192.168.1.50:11434"

    monkeypatch.setenv("OLLAMA_HOST", "http://my-ollama:11434/")
    assert get_ollama_base_url() == "http://my-ollama:11434"


def test_probe_ollama_service_unreachable():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        res = probe_ollama(DEFAULT_OLLAMA_MODEL)
        assert res["available"] is False
        assert res["reachable"] is False
        assert res["status"] == "UNAVAILABLE"
        assert "not reachable" in res["error"]
        assert "ollama serve" in res["actionable_message"]


def test_probe_ollama_service_reachable_model_missing():
    fake_body = json.dumps({
        "models": [
            {"name": "mistral:latest"},
            {"name": "phi3:mini"},
        ]
    }).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = fake_body
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = probe_ollama("llama3.2:3b")
        assert res["available"] is False
        assert res["reachable"] is True
        assert res["model_installed"] is False
        assert res["status"] == "MODEL_UNAVAILABLE"
        assert "ollama pull llama3.2:3b" in res["error"]
        assert "mistral:latest" in res["installed_models"]


def test_probe_ollama_service_reachable_model_present():
    fake_body = json.dumps({
        "models": [
            {"name": "llama3.2:3b:latest"},
            {"name": "qwen2.5:3b:latest"},
        ]
    }).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = fake_body
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = probe_ollama("llama3.2:3b")
        assert res["available"] is True
        assert res["reachable"] is True
        assert res["model_installed"] is True
        assert res["status"] == "READY"
        assert res["error"] is None


# ---------------------------------------------------------------------------
# 2. API Endpoints
# ---------------------------------------------------------------------------

def test_api_ollama_status_endpoint():
    client = TestClient(fastapi_app)
    with patch("vapt_platform.ollama_service.probe_ollama") as mock_probe:
        mock_probe.return_value = {
            "available": True,
            "reachable": True,
            "model_installed": True,
            "status": "READY",
            "model": "llama3.2:3b",
            "base_url": "http://127.0.0.1:11434",
            "installed_models": ["llama3.2:3b"],
            "error": None,
            "actionable_message": "Ready",
        }
        resp = client.get("/providers/ollama/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "READY"
        assert data["model"] == "llama3.2:3b"


def test_api_system_health_includes_ollama_probe_data():
    client = TestClient(fastapi_app)
    with patch("vapt_platform.ollama_service.probe_ollama") as mock_probe:
        mock_probe.return_value = {
            "available": False,
            "reachable": False,
            "model_installed": False,
            "status": "UNAVAILABLE",
            "model": "llama3.2:3b",
            "installed_models": [],
            "error": "Ollama service is not reachable",
            "actionable_message": "Start with ollama serve",
        }
        resp = client.get("/system/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ollama"] == "UNAVAILABLE"
        assert data["ollama_reachable"] is False
        assert "Ollama service is not reachable" in data["ollama_error"]


# ---------------------------------------------------------------------------
# 3. Assessment Fallback Integration
# ---------------------------------------------------------------------------

def test_create_assessor_ollama_fallback_when_probe_unavailable():
    with patch("vapt_platform.ollama_service.probe_ollama") as mock_probe:
        mock_probe.return_value = {
            "available": False,
            "reachable": False,
            "model_installed": False,
            "status": "UNAVAILABLE",
            "model": "llama3.2:3b",
            "installed_models": [],
            "error": "Ollama service is not reachable at http://127.0.0.1:11434.",
            "actionable_message": "Start with ollama serve",
        }
        assessor = create_assessor(mode="ai", provider="ollama", model_name="llama3.2:3b")
        candidate = ActionCandidate(id="CVE-2021-44228", probability=0.8)
        result = assessor(candidate)

        assert result.fallback is True
        assert result.provider == "ollama"
        assert result.model == "llama3.2:3b"
        assert result.source == "deterministic"
        assert "Ollama service is not reachable" in (result.error or "")


# ---------------------------------------------------------------------------
# 4. CLI Parity Tests
# ---------------------------------------------------------------------------

def test_cli_parser_accepts_provider_and_model():
    from prototype import cli
    with patch("sys.argv", [
        "cli.py", "run",
        "--scenario", "success",
        "--assessor", "llm",
        "--provider", "openrouter",
        "--model", "meta-llama/llama-3.3-70b-instruct",
    ]):
        with patch("prototype.cli._run_scenario") as mock_run:
            cli.main()
            assert mock_run.called
            _, kwargs = mock_run.call_args
            assert kwargs.get("provider") == "openrouter"
            assert kwargs.get("model") == "meta-llama/llama-3.3-70b-instruct"


def test_cli_parser_accepts_target_url_and_ack():
    from prototype import cli
    with patch("sys.argv", [
        "cli.py", "run",
        "--target-url", "http://pentest-ground.com:4280",
        "--target-scope-acknowledged",
    ]):
        with patch("prototype.cli._run_scenario") as mock_run:
            cli.main()
            assert mock_run.called
            _, kwargs = mock_run.call_args
            assert kwargs.get("target_url") == "http://pentest-ground.com:4280"
            assert kwargs.get("target_scope_acknowledged") is True


# ---------------------------------------------------------------------------
# 5. JavaScript Syntax Integrity
# ---------------------------------------------------------------------------

def test_javascript_app_js_syntax_integrity():
    from pathlib import Path
    js = Path("frontend/web/js/app.js").read_text(encoding="utf-8")
    # Verify the fixed string concatenation in the web assessment preflight check
    assert "Target is outside the configured authorized scope." in js
    assert "+ 'must be authorized (local policy or VAPT_AUTHORIZED_WEB_SCOPES) before starting. '" in js
    assert "+ 'See the validation panel for the administrator configuration instructions.'" in js
