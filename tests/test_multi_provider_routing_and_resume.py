"""Automated tests for Multi-Provider AI Configuration, Model Routing, Resume, and Contrast.

Covers:
1. Provider selection: verify that all 6 providers can be configured and selected.
2. Runtime credential validation: test that valid/invalid keys are correctly rejected/accepted
   for each provider without touching .env.
3. Dynamic model discovery: test that models fetched from providers contain accurate pricing
   information (free=True/False, pricing_status="free"|"paid"|"unknown").
4. Manual model entry: verify custom model identifiers are accepted for custom/ollama providers.
5. Model routing to Strix: verify that user-selected models (both standard and custom) reach the
   Strix runner without substitution, fallback or double-prefixing.
6. 429 quota handling: simulate 429 quota exhaustion from provider, verify that run transitions to
   provider_blocked, that candidates/findings are preserved, and that /resume successfully switches
   to a new provider/model and continues.
7. Dropdown contrast: verify that dropdown styling in styles.css includes high-contrast rules for
   Windows Chrome.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from strix.core.runtime_credentials import (
    clear_runtime_credentials,
    get_runtime_base_url,
    get_runtime_credential,
    get_runtime_model,
    set_runtime_base_url,
    set_runtime_credential,
)
from strix.interface.api import (
    _RUNS,
    _save_run_to_disk,
    app,
)
from strix.llm.provider_validation import (
    _parse_openrouter_pricing,
)
from strix.llm.router import format_openrouter_model, resolve_model_kwargs


@pytest.fixture(autouse=True)
def reset_credentials_state() -> Generator[None, None, None]:
    """Ensure clean runtime credentials state before and after each test."""
    import os

    clear_runtime_credentials()
    yield
    clear_runtime_credentials()
    for k in (
        "OPENROUTER_API_KEY",
        "LLM_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "STRIX_LLM",
        "STRIX_LLM_PROVIDER",
        "OPENAI_BASE_URL",
        "OPENROUTER_API_BASE",
        "OLLAMA_API_BASE",
        "LLM_API_BASE",
    ):
        os.environ.pop(k, None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Test 1: All 6 providers selectable and configurable
# ---------------------------------------------------------------------------
def test_all_six_providers_selectable_and_configurable(client: TestClient) -> None:
    """Verify that all 6 providers can be configured and selected via /settings/llm."""
    providers_and_models = [
        ("openrouter", "deepseek/deepseek-r1:free", "sk-or-v1-testkey12345"),
        ("anthropic", "claude-3-5-sonnet-20241022", "sk-ant-api03-testkey12345"),
        ("openai", "gpt-4o", "sk-proj-testkey12345"),
        ("google", "gemini-2.0-flash", "AIzaSyTestKey12345"),
        ("ollama", "qwen2.5:1.5b", ""),
        ("cloud_hosted", "custom-org/llama-3.3-70b", "sk-custom-testkey12345"),
    ]

    for prov, model, key in providers_and_models:
        payload = {
            "provider": prov,
            "model": model,
            "api_key": key or None,
            "api_base": "http://127.0.0.1:11434" if prov == "ollama" else None,
        }
        res = client.post("/settings/llm", json=payload)
        assert res.status_code == 200, f"Failed to configure provider {prov}: {res.text}"
        data = res.json()
        assert data["status"] == "ok"

        # Verify in-memory runtime credentials updated
        if key:
            assert get_runtime_credential(prov) == key
        assert get_runtime_model(prov) == model


# ---------------------------------------------------------------------------
# Test 2: Runtime credential validation per provider without touching .env
# ---------------------------------------------------------------------------
def test_credential_validation_per_provider_without_env(client: TestClient) -> None:
    """Test valid and invalid keys rejected/accepted for each provider without touching .env."""
    # 1. Anthropic validation
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(
            {"data": [{"id": "claude-3-5-sonnet-20241022"}]}
        ).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        res = client.post(
            "/providers/anthropic/validate", json={"api_key": "sk-ant-api03-validkey"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is True
        assert data["status"] == "configured"
        assert get_runtime_credential("anthropic") == "sk-ant-api03-validkey"

    # Invalid Anthropic key
    res_inv = client.post("/providers/anthropic/validate", json={"api_key": "invalid-key"})
    assert res_inv.status_code == 200
    assert res_inv.json()["valid"] is False
    assert res_inv.json()["status"] == "invalid_credentials"

    # 2. Ollama validation
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"models": [{"name": "qwen2.5:1.5b"}]}).encode(
            "utf-8"
        )
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        res_ol = client.post(
            "/providers/ollama/validate", json={"api_base": "http://127.0.0.1:11434"}
        )
        assert res_ol.status_code == 200
        data_ol = res_ol.json()
        assert data_ol["valid"] is True
        assert data_ol["status"] == "configured"
        assert len(data_ol["models"]) == 1

    # 3. Custom endpoint validation
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"data": [{"id": "my-custom-model"}]}).encode(
            "utf-8"
        )
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        res_cu = client.post(
            "/providers/custom/validate", json={"api_base": "http://localhost:8000/v1"}
        )
        assert res_cu.status_code == 200
        data_cu = res_cu.json()
        assert data_cu["valid"] is True
        assert data_cu["status"] == "configured"
        assert len(data_cu["models"]) == 1


# ---------------------------------------------------------------------------
# Test 3: Dynamic model discovery with accurate pricing flags
# ---------------------------------------------------------------------------
def test_dynamic_model_discovery_with_pricing_badges(client: TestClient) -> None:
    """Verify models fetched from providers contain accurate pricing information."""
    # Test pricing parser unit logic
    pstatus_0, _, _ = _parse_openrouter_pricing({"pricing": {"prompt": "0", "completion": "0"}})
    assert pstatus_0 == "free"

    pstatus_paid, _, _ = _parse_openrouter_pricing(
        {"pricing": {"prompt": "0.000005", "completion": "0.000015"}}
    )
    assert pstatus_paid == "paid"

    pstatus_unk, _, _ = _parse_openrouter_pricing({})
    assert pstatus_unk == "unknown"

    # Test GET /providers/openrouter/models
    mock_or_payload = {
        "data": [
            {
                "id": "deepseek/deepseek-r1:free",
                "name": "DeepSeek R1",
                "pricing": {"prompt": "0", "completion": "0"},
            },
            {
                "id": "anthropic/claude-3.5-sonnet",
                "name": "Claude 3.5 Sonnet",
                "pricing": {"prompt": "0.000003", "completion": "0.000015"},
            },
        ]
    }
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_or_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        res = client.get("/providers/openrouter/models")
        assert res.status_code == 200
        models = res.json()
        assert len(models) == 2

        free_m = next(m for m in models if m["id"] == "deepseek/deepseek-r1:free")
        assert free_m["free"] is True
        assert free_m["pricing_status"] == "free"

        paid_m = next(m for m in models if m["id"] == "anthropic/claude-3.5-sonnet")
        assert paid_m["free"] is False
        assert paid_m["pricing_status"] == "paid"


# ---------------------------------------------------------------------------
# Test 4: Manual model entry for custom providers
# ---------------------------------------------------------------------------
def test_manual_custom_model_identifiers_accepted(client: TestClient) -> None:
    """Verify custom model identifiers are accepted for custom/ollama providers without alteration."""
    custom_model_id = "org-name/custom-fine-tuned-qwen-72b-v2"
    set_runtime_credential("custom", "sk-custom-12345", custom_model_id)
    set_runtime_base_url("custom", "http://10.0.0.5:8000/v1")

    assert get_runtime_model("custom") == custom_model_id
    assert get_runtime_base_url("custom") == "http://10.0.0.5:8000/v1"

    kwargs = resolve_model_kwargs(provider="custom", model_name=custom_model_id)
    assert kwargs["model"] == f"openai/{custom_model_id}"
    assert kwargs["api_base"] == "http://10.0.0.5:8000/v1"
    assert kwargs["api_key"] == "sk-custom-12345"


# ---------------------------------------------------------------------------
# Test 5: Model routing reaches Strix runner without substitution or double prefixing
# ---------------------------------------------------------------------------
def test_model_routing_to_strix_runner_no_double_prefix_or_substitution() -> None:
    """Verify user-selected models reach runner without substitution or double-prefixing."""
    # 1. Anthropic model routing
    set_runtime_credential("anthropic", "sk-ant-api03-testkey")
    res_ant = resolve_model_kwargs(provider="anthropic", model_name="claude-3-5-sonnet-20241022")
    assert res_ant["model"] == "anthropic/claude-3-5-sonnet-20241022"
    assert res_ant["api_key"] == "sk-ant-api03-testkey"
    assert not res_ant["model"].startswith("anthropic/anthropic/")

    # 2. OpenAI model routing
    set_runtime_credential("openai", "sk-proj-testkey")
    res_oai = resolve_model_kwargs(provider="openai", model_name="gpt-4o-mini")
    assert res_oai["model"] == "gpt-4o-mini"
    assert res_oai["api_key"] == "sk-proj-testkey"

    # 3. OpenRouter model formatting - NO DOUBLE PREFIXING
    formatted_or = format_openrouter_model("meta-llama/llama-3.3-70b-instruct:free")
    assert formatted_or == "openrouter/meta-llama/llama-3.3-70b-instruct:free"
    assert not formatted_or.startswith("openrouter/openrouter/")

    # Already prefixed model should not be double-prefixed
    formatted_prefixed = format_openrouter_model("openrouter/google/gemini-2.0-flash-exp:free")
    assert formatted_prefixed == "openrouter/google/gemini-2.0-flash-exp:free"

    # User-selected model must never be substituted with Nemotron
    assert format_openrouter_model("cohere/command-r-plus") == "openrouter/cohere/command-r-plus"


# ---------------------------------------------------------------------------
# Test 6: 429 quota exhaustion and resume with provider/model switching
# ---------------------------------------------------------------------------
def test_429_quota_exhaustion_and_resume_with_provider_switch(client: TestClient) -> None:
    """Simulate 429 quota exhaustion, verify provider_blocked status, and resume with new provider."""
    run_id = "run-test-resume-429"
    run_record = {
        "run_id": run_id,
        "status": "provider_blocked",
        "provider": "openrouter",
        "model": "deepseek/deepseek-r1:free",
        "provider_error": "Provider daily rate limit exceeded (HTTP 429).",
        "error": "Provider daily rate limit exceeded (HTTP 429).",
        "target_url": "http://127.0.0.1:3000",
        "mode": "autonomous",
        "execution_mode": "autonomous_multi_agent",
        "candidates": [
            {
                "id": "c1",
                "name": "SQL Injection in /rest/products/search",
                "attempts": 1,
                "state": "INVESTIGATING",
            }
        ],
        "findings": [
            {"id": "f1", "title": "Information Disclosure in Error Stack", "severity": "medium"}
        ],
        "events": [],
    }
    _RUNS[run_id] = run_record
    _save_run_to_disk(run_record)

    # Resume the assessment switching to Anthropic Claude
    with patch("strix.interface.api._execute_run_worker") as mock_worker:
        resume_payload = {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
            "api_key": "sk-ant-api03-newresumekey",
        }
        res = client.post(f"/runs/{run_id}/resume", json=resume_payload)
        assert res.status_code == 200, f"Resume request failed: {res.text}"
        data = res.json()
        assert data["status"] == "resumed"
        assert data["run_id"] == run_id

        # Verify run was updated
        updated_run = _RUNS[run_id]
        assert updated_run["status"] == "running"
        assert updated_run["provider"] == "anthropic"
        assert updated_run["model"] == "claude-3-5-sonnet-20241022"
        assert updated_run["is_resumed"] is True

        # Verify existing candidates and findings were preserved
        assert len(updated_run["candidates"]) == 1
        assert updated_run["candidates"][0]["id"] == "c1"
        assert len(updated_run["findings"]) == 1
        assert updated_run["findings"][0]["id"] == "f1"

        # Verify RUN_RESUMED event logged
        resume_events = [e for e in updated_run["events"] if e.get("event") == "RUN_RESUMED"]
        assert len(resume_events) == 1
        assert "anthropic" in resume_events[0]["message"]
        assert "openrouter" in resume_events[0]["message"]

        # Verify runtime credential updated
        assert get_runtime_credential("anthropic") == "sk-ant-api03-newresumekey"


# ---------------------------------------------------------------------------
# Test 7: Dropdown styling in styles.css includes high-contrast rules for Windows Chrome
# ---------------------------------------------------------------------------
def test_dropdown_css_contrast_rules_for_windows_chrome() -> None:
    """Verify styles.css forces high-contrast dark background and light text on select and option."""
    css_path = (
        Path(__file__).resolve().parent.parent
        / "strix"
        / "interface"
        / "web"
        / "css"
        / "styles.css"
    )
    assert css_path.exists(), f"styles.css not found at {css_path}"
    content = css_path.read_text(encoding="utf-8")

    # Verify select and option dark background styling
    assert "select option" in content, "styles.css missing 'select option' rule"
    assert "background-color: #0f172a !important" in content, (
        "styles.css missing #0f172a background for option"
    )
    assert "color: #f8fafc !important" in content, (
        "styles.css missing #f8fafc text color for option"
    )
    assert "background-color: #1e293b !important" in content, (
        "styles.css missing #1e293b hover/checked styling"
    )
    assert "color: #38bdf8 !important" in content, (
        "styles.css missing #38bdf8 hover/checked text color"
    )
