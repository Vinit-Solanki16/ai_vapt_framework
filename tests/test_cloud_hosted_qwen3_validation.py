"""Comprehensive Phase 6 automated regression suite for Cloud Hosted AI-VAPT provider.

Contains:
1. Deterministic unit/API tests with mocked HTTP responses (fast, offline, reproducible).
2. Clean profile lifecycle management (creation, activation, retrieval, deletion/cleanup).
3. Tool-calling protocol, schema serialization, and multi-turn error recovery.
4. Context-window budgeting and fallback handling.
5. Opt-in live integration tests (skipped by default unless AI_VAPT_LIVE_CLOUD_ENDPOINT is set).

No hardcoded tunnel URLs, keys, or credentials.
"""

from __future__ import annotations

import io
import json
import os
import urllib.request
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import strix.config.loader as config_loader
from strix.core.inputs import _accepts_required_tool_choice
from strix.interface.api import (
    _get_cloud_profiles,
    app,
)
from strix.llm.cloud_provider import (
    discover_cloud_models,
    test_cloud_connection,
    verify_cloud_structured_tools,
)
from strix.llm.context_budget import context_window


@pytest.fixture
def client():
    return TestClient(app)


# ============================================================================
# 1. Deterministic Unit & API Tests with Mocked External Requests
# ============================================================================


def test_test_cloud_connection_mocked_success():
    """Verify test_cloud_connection correctly parses successful models and completion."""
    models_response = json.dumps({
        "object": "list",
        "data": [{"id": "mock-qwen-30b", "aliases": ["mock-model-deep"]}],
    }).encode("utf-8")

    chat_response = json.dumps({
        "choices": [{"message": {"role": "assistant", "content": "pong"}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 2},
    }).encode("utf-8")

    def mock_urlopen(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        resp = MagicMock()
        resp.status = 200
        if "/models" in url:
            resp.read.return_value = models_response
        else:
            resp.read.return_value = chat_response
        resp.__enter__.return_value = resp
        return resp

    with patch.object(urllib.request, "urlopen", side_effect=mock_urlopen):
        res = test_cloud_connection(
            api_base="https://mock-cloud.internal/v1",
            model="mock-model-deep",
            api_key="mock-key",
        )
        assert res.valid is True
        assert res.status == "configured"
        assert res.chat_completion_ok is True
        assert "mock-qwen-30b" in res.models


def test_test_cloud_connection_mocked_failure():
    """Verify test_cloud_connection handles HTTP 502 Bad Gateway gracefully."""
    err = urllib.error.HTTPError(
        url="https://mock-cloud.internal/v1/models",
        code=502,
        msg="Bad Gateway",
        hdrs={},
        fp=io.BytesIO(b'{"error": "Cloudflare tunnel offline"}'),
    )

    with patch.object(urllib.request, "urlopen", side_effect=err):
        res = test_cloud_connection(
            api_base="https://mock-cloud.internal/v1",
            model="mock-model-deep",
        )
        assert res.valid is False
        assert res.status in ("error", "unreachable")
        assert "502" in res.message or "Bad Gateway" in res.message


def test_discover_cloud_models_mocked():
    """Verify discover_cloud_models parses both standard id and nested aliases."""
    payload = json.dumps({
        "data": [
            {"id": "qwen3-coder", "aliases": ["kaggle-model-deep", "kaggle-model-fast"]}
        ]
    }).encode("utf-8")

    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = payload
    resp.__enter__.return_value = resp

    with patch.object(urllib.request, "urlopen", return_value=resp):
        res = discover_cloud_models(api_base="https://mock-cloud.internal/v1")
        assert res.get("valid") is True
        models = res.get("models", [])
        assert "qwen3-coder" in models
        assert "kaggle-model-deep" in models


def test_verify_cloud_tools_mocked_success():
    """Verify verify_cloud_structured_tools validates structured tool-calling execution."""
    tool_call_reply = json.dumps({
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-123",
                            "type": "function",
                            "function": {
                                "name": "check_service_port",
                                "arguments": json.dumps({"host": "127.0.0.1", "port": 80}),
                            },
                        }
                    ],
                }
            }
        ]
    }).encode("utf-8")

    followup_reply = json.dumps({
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Port 80 on host 127.0.0.1 is open and running HTTP service.",
                }
            }
        ]
    }).encode("utf-8")

    call_count = 0

    def mock_urlopen(req, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = tool_call_reply if call_count == 1 else followup_reply
        resp.__enter__.return_value = resp
        return resp

    with patch.object(urllib.request, "urlopen", side_effect=mock_urlopen):
        res = verify_cloud_structured_tools(
            api_base="https://mock-cloud.internal/v1",
            model="mock-model-deep",
        )
        assert res.valid is True
        assert res.status == "supported"
        assert res.tool_diagnostics.supported is True
        assert res.tool_diagnostics.tool_call_generated is True
        assert res.tool_diagnostics.arguments_parsed is True
        assert res.tool_diagnostics.tool_name == "check_service_port"


# ============================================================================
# 2. Profile Creation, Retrieval, Activation & Cleanup Tests
# ============================================================================


def test_cloud_profile_lifecycle(client):
    """Verify complete CRUD lifecycle: create, retrieve, activate, and delete profile."""
    profile_data = {
        "name": "Automated Lifecycle Test Profile",
        "api_base": "https://test-cloud.internal/v1",
        "api_key": "mock-test-key",
        "model": "test-qwen-model",
        "model_alias": "test-alias",
        "context_window": 65536,
        "max_output_tokens": 2048,
        "timeout": 120,
        "streaming": True,
        "is_active": False,
    }

    # 1. Create
    resp = client.post("/providers/cloud_hosted/profiles", json=profile_data)
    assert resp.status_code == 200
    created = resp.json()
    profile_id = created["id"]
    assert created["name"] == profile_data["name"]
    assert created["has_api_key"] is True
    assert "masked_api_key" in created

    try:
        # 2. Retrieve
        list_resp = client.get("/providers/cloud_hosted/profiles")
        assert list_resp.status_code == 200
        profiles = list_resp.json()
        assert any(p["id"] == profile_id for p in profiles)

        # 3. Activate
        act_resp = client.post(f"/providers/cloud_hosted/profiles/{profile_id}/activate")
        assert act_resp.status_code == 200
        assert act_resp.json()["is_active"] is True

    finally:
        # 4. Cleanup (Always delete test profile)
        del_resp = client.delete(f"/providers/cloud_hosted/profiles/{profile_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "ok"

    # Verify deleted
    profiles_after = _get_cloud_profiles()
    assert not any(p.get("id") == profile_id for p in profiles_after)


# ============================================================================
# 3. Tool-Calling Protocol & Multi-Turn Verification Tests
# ============================================================================


def test_accepts_required_tool_choice_protocol():
    """Verify model routing accurately identifies tool choice support."""
    assert _accepts_required_tool_choice("openai/kaggle-model-deep") is True
    assert _accepts_required_tool_choice("openai/gpt-4o") is True
    assert _accepts_required_tool_choice("ollama/llama3.2") is True
    assert _accepts_required_tool_choice("openrouter/meta-llama/llama-3-70b") is True


# ============================================================================
# 4. Context-Window Budgeting & Fallback Handling Tests
# ============================================================================


def test_context_window_budgeting_configured_fallback():
    """Verify context_window respects STRIX_CONTEXT_FALLBACK_TOKENS without hardcoding."""
    with patch.dict(os.environ, {"STRIX_CONTEXT_FALLBACK_TOKENS": "131072"}):
        config_loader._cached = None
        assert context_window("openai/custom-unmapped-model") == 131072

    with patch.dict(os.environ, {"STRIX_CONTEXT_FALLBACK_TOKENS": "65536"}):
        config_loader._cached = None
        assert context_window("openai/another-unmapped-model") == 65536


# ============================================================================
# 5. Opt-In Live Integration Tests (Requires AI_VAPT_LIVE_CLOUD_ENDPOINT)
# ============================================================================


@pytest.mark.skipif(
    not os.environ.get("AI_VAPT_LIVE_CLOUD_ENDPOINT"),
    reason="Live cloud endpoint not configured; set AI_VAPT_LIVE_CLOUD_ENDPOINT to enable.",
)
def test_live_cloud_endpoint_integration(client):
    """Opt-in live integration test executed only when explicitly configured by operator."""
    endpoint = os.environ["AI_VAPT_LIVE_CLOUD_ENDPOINT"]
    model = os.environ.get("AI_VAPT_LIVE_CLOUD_MODEL", "kaggle-model-deep")
    api_key = os.environ.get("AI_VAPT_LIVE_CLOUD_KEY", "none")

    resp = client.post(
        "/providers/cloud_hosted/validate",
        json={"api_base": endpoint, "api_key": api_key, "model": model},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["chat_completion_ok"] is True
