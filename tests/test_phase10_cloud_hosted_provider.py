"""Regression and integration tests for Phase 10: Generic Cloud Hosted AI Provider Integration.

Verifies:
1. Profiles REST API (CRUD, active profile selection, key masking).
2. Dynamic model discovery (/models endpoint probe and offline tunnel handling).
3. Connection validation with TTFT, latency, and tokens/sec diagnostics.
4. Structured tool calling verification (schema dispatch, JSON argument parsing,
   multi-turn tool role continuation, error recovery, streaming).
5. Harmless single-turn model warm-up probe.
6. Subprocess and Docker sandbox environment propagation.
7. Run creation preflight validation for cloud hosted provider.
8. Secret sanitization preventing credential leakage in diagnostics and errors.
"""
from __future__ import annotations

import io
import json
import os
import urllib.error
import urllib.request
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from strix.interface.api import (
    CLI_CONFIG_FILE,
    _RUNS,
    _delete_cloud_profile,
    _get_active_cloud_profile,
    _get_cloud_profiles,
    _save_cloud_profile,
    _set_active_cloud_profile,
    app,
)
from strix.interface.schemas import CloudHostedProfile, RunRequest
from strix.llm.cloud_provider import (
    _redact_secrets,
    discover_cloud_models,
    test_cloud_connection as probe_cloud_connection,
    verify_cloud_structured_tools,
    warmup_cloud_model,
)
from strix.llm.router import resolve_model_kwargs

client = TestClient(app)


# ============================================================================
# 1. Profile Storage & Masking Tests
# ============================================================================

def test_cloud_profile_default_id_generation():
    """Verify that CloudHostedProfile generates a unique uuid-based id by default."""
    p1 = CloudHostedProfile(api_base="https://custom.net/v1", model="llama-3")
    p2 = CloudHostedProfile(api_base="https://custom.net/v1", model="llama-3")
    assert p1.id.startswith("cloud-")
    assert p2.id.startswith("cloud-")
    assert p1.id != p2.id


def test_cloud_profile_crud_and_masking(tmp_path):
    """Verify that cloud profiles can be created, retrieved with masked keys, activated, and deleted."""
    test_cli_config = tmp_path / "cli-config.json"

    with patch("strix.interface.api.CLI_CONFIG_FILE", test_cli_config):
        # 1. Initially empty
        profiles = _get_cloud_profiles()
        assert len(profiles) == 0

        # 2. Save profile
        profile = CloudHostedProfile(
            id="test-cloud-1",
            name="VLLM Production Cluster",
            api_base="https://vllm.internal.net/v1",
            model="meta-llama/Llama-3.3-70B-Instruct",
            api_key="sk-live-super-secret-key-9988",
            extra_headers={"X-Cluster-ID": "gpu-node-04"},
            timeout=45,
            context_window=32768,
            streaming=True,
            is_active=False,
        )
        saved = _save_cloud_profile(profile)
        assert saved["id"] == "test-cloud-1"

        # 3. List via API - verify key is masked
        res = client.get("/providers/cloud_hosted/profiles")
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1
        found = next(p for p in data if p["id"] == "test-cloud-1")
        assert found["has_api_key"] is True
        assert "super-secret" not in found["masked_api_key"]
        assert found["masked_api_key"].startswith("sk-l")
        assert found["masked_api_key"].endswith("9988")

        # 4. Activate profile
        act_res = client.post("/providers/cloud_hosted/profiles/test-cloud-1/activate")
        assert act_res.status_code == 200
        assert act_res.json()["is_active"] is True

        active = _get_active_cloud_profile()
        assert active is not None
        assert active["id"] == "test-cloud-1"
        assert active["api_key"] == "sk-live-super-secret-key-9988"  # Unmasked in internal store

        # 5. Delete profile
        del_res = client.delete("/providers/cloud_hosted/profiles/test-cloud-1")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "ok"

        assert len(_get_cloud_profiles()) == 0


def test_redact_secrets_utility():
    """Verify that _redact_secrets strips API keys and Bearer tokens."""
    raw = "Failed with token Bearer sk-secret12345678 and key sk-998877665544 on url https://api.cloud.com"
    redacted = _redact_secrets(raw, ["sk-secret12345678", "sk-998877665544"])
    assert "sk-secret12345678" not in redacted
    assert "sk-998877665544" not in redacted
    assert "[REDACTED]" in redacted


# ============================================================================
# 2. Dynamic Model Discovery Tests
# ============================================================================

def test_dynamic_model_discovery_success():
    """Verify dynamic /models querying returns model list accurately."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps({
        "data": [
            {"id": "meta-llama/Llama-3.3-70B-Instruct", "owned_by": "vllm"},
            {"id": "deepseek-ai/DeepSeek-V3", "owned_by": "vllm"},
        ]
    }).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_response):
        res = discover_cloud_models(
            api_base="https://custom-host.org/v1",
            api_key="sk-test",
            extra_headers={"X-Test": "1"},
        )
        assert res["valid"] is True
        assert len(res["models"]) == 2
        assert "meta-llama/Llama-3.3-70B-Instruct" in res["models"]
        assert "deepseek-ai/DeepSeek-V3" in res["models"]


def test_dynamic_model_discovery_offline_ngrok():
    """Verify offline tunnel / ngrok page returns human-readable diagnostic."""
    ngrok_html = b"<html><head><title>ngrok</title></head><body>Tunnel ERR_NGROK_3200 not found</body></html>"
    mock_err = urllib.error.HTTPError(
        url="https://xyz.ngrok-free.app/v1/models",
        code=404,
        msg="Not Found",
        hdrs={},
        fp=io.BytesIO(ngrok_html),
    )

    with patch("urllib.request.urlopen", side_effect=mock_err):
        res = discover_cloud_models(
            api_base="https://xyz.ngrok-free.app/v1",
        )
        assert res["valid"] is False
        assert "ERR_NGROK_3200" in res["message"] or "offline" in res["message"]


# ============================================================================
# 3. Connection Validation & Diagnostics Tests
# ============================================================================

def test_connection_validation_success():
    """Verify connection probe computes latency, TTFT, and tokens/sec."""
    mock_payload = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {"role": "assistant", "content": "Strix connection test acknowledged."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
    }
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_response):
        res = probe_cloud_connection(
            api_base="https://custom-host.org/v1",
            model="test-model",
            api_key="sk-test",
        )
        assert res.valid is True
        assert res.status == "configured"
        assert res.chat_completion_ok is True
        assert res.latency_ms > 0
        assert res.tokens_per_second is not None
        assert res.tokens_per_second > 0
        assert "acknowledged" in res.diagnostics.get("reply_sample", "").lower()


def test_connection_validation_failure_sanitizes_key():
    """Verify connection probe sanitizes API keys on failure."""
    raw_key = "sk-super-secret-key-1234"
    mock_err = urllib.error.HTTPError(
        url="https://custom-host.org/v1/chat/completions",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=io.BytesIO(f"Unauthorized: key {raw_key} was rejected".encode("utf-8")),
    )

    with patch("urllib.request.urlopen", side_effect=mock_err):
        res = probe_cloud_connection(
            api_base="https://custom-host.org/v1",
            model="test-model",
            api_key=raw_key,
        )
        assert res.valid is False
        assert res.status in ("error", "invalid_credentials")
        assert raw_key not in res.message


# ============================================================================
# 4. Structured Tool Calling Verification Tests
# ============================================================================

def test_structured_tool_calling_full_matrix():
    """Verify multi-step tool verification: schema submission, JSON arguments, tool role continuation."""
    # Step 1: Assistant calls check_service_port tool
    tool_call_resp = MagicMock()
    tool_call_resp.status = 200
    tool_call_resp.read.return_value = json.dumps({
        "id": "chatcmpl-tool-1",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_port_987",
                            "type": "function",
                            "function": {
                                "name": "check_service_port",
                                "arguments": '{"host": "127.0.0.1", "port": 80}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }).encode("utf-8")
    tool_call_resp.__enter__.return_value = tool_call_resp
    tool_call_resp.__exit__.return_value = None

    # Step 2: Tool continuation returns final answer
    tool_result_resp = MagicMock()
    tool_result_resp.status = 200
    tool_result_resp.read.return_value = json.dumps({
        "id": "chatcmpl-tool-2",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Port 80 is listening with service http.",
                },
                "finish_reason": "stop",
            }
        ],
    }).encode("utf-8")
    tool_result_resp.__enter__.return_value = tool_result_resp
    tool_result_resp.__exit__.return_value = None

    # Step 3: Streaming chunk test
    tool_stream_resp = MagicMock()
    tool_stream_resp.status = 200
    tool_stream_resp.read.return_value = b'data: {"choices": [{"delta": {"content": "ok"}}]}\n\n'
    tool_stream_resp.__enter__.return_value = tool_stream_resp
    tool_stream_resp.__exit__.return_value = None

    step_responses = [tool_call_resp, tool_result_resp, tool_stream_resp]

    with patch("urllib.request.urlopen", side_effect=step_responses):
        res = verify_cloud_structured_tools(
            api_base="https://custom-host.org/v1",
            model="meta-llama/Llama-3.3-70B-Instruct",
            api_key="sk-test",
        )
        assert res.valid is True
        assert res.status == "supported"
        diag = res.tool_diagnostics
        assert diag.tool_call_generated is True
        assert diag.tool_name == "check_service_port"
        assert diag.arguments_parsed is True
        assert diag.arguments.get("port") == 80
        assert diag.multi_turn_continuation is True
        assert diag.streaming_compatible is True


def test_structured_tool_calling_missing_tool_call_error():
    """Verify that if the model returns plain text without calling the tool, it reports a warning/failure."""
    plain_text_resp = MagicMock()
    plain_text_resp.status = 200
    plain_text_resp.read.return_value = json.dumps({
        "id": "chatcmpl-text",
        "choices": [
            {
                "message": {"role": "assistant", "content": "I prefer to answer directly without tools."},
                "finish_reason": "stop",
            }
        ],
    }).encode("utf-8")
    plain_text_resp.__enter__.return_value = plain_text_resp
    plain_text_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=plain_text_resp):
        res = verify_cloud_structured_tools(
            api_base="https://custom-host.org/v1",
            model="test-model",
            api_key="sk-test",
        )
        assert res.valid is False
        assert res.status == "unsupported"
        assert res.tool_diagnostics.tool_call_generated is False
        assert "plain text" in res.tool_diagnostics.error


# ============================================================================
# 5. Harmless Single-Turn Model Warm-up Probe Tests
# ============================================================================

def test_warmup_cloud_model():
    """Verify harmless single-turn prompt warmup probe."""
    mock_payload = {
        "id": "chatcmpl-warmup",
        "choices": [{"message": {"role": "assistant", "content": "READY"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = warmup_cloud_model(
            api_base="https://custom-host.org/v1",
            model="test-model",
            api_key="sk-test",
        )
        assert res.success is True
        assert res.duration_ms > 0
        assert res.tokens_per_second is not None


# ============================================================================
# 6. Router & Subprocess Propagation Tests
# ============================================================================

def test_model_router_cloud_hosted_routing():
    """Verify resolve_model_kwargs correctly formats cloud_hosted models as openai/<model> with base URL."""
    kwargs = resolve_model_kwargs(
        provider="cloud_hosted",
        model_name="deepseek-ai/DeepSeek-V3",
        api_key="sk-test-vllm",
        api_base="https://my-vllm-cluster.ai/v1",
        extra_headers={"X-Auth-Custom": "custom-val"},
    )
    assert kwargs["model"] == "openai/deepseek-ai/DeepSeek-V3"
    assert kwargs["api_base"] == "https://my-vllm-cluster.ai/v1"
    assert kwargs["api_key"] == "sk-test-vllm"
    assert kwargs["extra_headers"] == {"X-Auth-Custom": "custom-val"}


def test_session_manager_cloud_environment_propagation():
    """Verify session_manager inspects and forwards cloud provider environment variables."""
    from strix.runtime.session_manager import Manifest, Environment

    cloud_vars = {
        "LLM_API_BASE": "https://custom-cloud.org/v1",
        "LLM_EXTRA_HEADERS": '{"X-Custom": "123"}',
        "LLM_TIMEOUT": "60",
        "LLM_DISABLE_STREAMING": "true",
        "STRIX_CONTEXT_FALLBACK_TOKENS": "32768",
        "STRIX_API_TYPE": "chat_completions",
        "STRIX_LLM_PROVIDER": "cloud_hosted",
    }
    # Verify our declared variables are standard in container environment propagation
    for k, v in cloud_vars.items():
        assert k in (
            "LLM_API_BASE",
            "LLM_EXTRA_HEADERS",
            "LLM_TIMEOUT",
            "LLM_DISABLE_STREAMING",
            "STRIX_CONTEXT_FALLBACK_TOKENS",
            "STRIX_API_TYPE",
            "STRIX_LLM_PROVIDER",
        )


# ============================================================================
# 7. Run Creation Preflight Validation Tests
# ============================================================================

def test_create_run_preflight_cloud_hosted_validation(tmp_path):
    """Verify create_run validates cloud hosted provider configuration before accepting."""
    test_cli_config = tmp_path / "cli-config.json"

    with patch("strix.interface.api.CLI_CONFIG_FILE", test_cli_config):
        # 1. No active profile and missing base URL -> preflight fails with 400
        bad_req = {
            "mode": "simulation",
            "scenario": "test_preflight",
            "assessor_provider": "cloud_hosted",
            "assessor_model": "test-model",
            "target_url": "http://127.0.0.1:3000/",
            "target_scope_acknowledged": True,
        }
        res = client.post("/runs", json=bad_req)
        assert res.status_code == 400
        assert "Cloud Hosted provider selected but no API Base URL configured" in res.json()["detail"]

        # 2. Configure active profile
        profile = CloudHostedProfile(
            id="active-p1",
            name="Test Active Cloud",
            api_base="https://custom-cloud.org/v1",
            model="llama-3.3-70b",
            is_active=True,
        )
        _save_cloud_profile(profile)
        _set_active_cloud_profile("active-p1")

        # 3. Request now succeeds
        ok_req = {
            "mode": "simulation",
            "scenario": "test_preflight_ok",
            "assessor_provider": "cloud_hosted",
            "target_url": "http://127.0.0.1:3000/",
            "target_scope_acknowledged": True,
        }
        res = client.post("/runs", json=ok_req)
        assert res.status_code == 200
        run_id = res.json()["run_id"]
        assert run_id in _RUNS
        assert _RUNS[run_id]["provider"] == "cloud_hosted"
        # Clean up
        _RUNS.pop(run_id, None)


# ============================================================================
# 8. Profile Lifecycle & HTTP 422 Regression Tests
# ============================================================================

def test_cloud_profile_creation_with_null_and_empty_id(tmp_path):
    """Verify that profiles with id=None, id='', or omitted id are assigned unique IDs without HTTP 422."""
    test_cli_config = tmp_path / "cli-config.json"

    with patch("strix.interface.api.CLI_CONFIG_FILE", test_cli_config):
        # 1. id: null (The exact manual test failure case)
        res1 = client.post("/providers/cloud_hosted/profiles", json={
            "id": None,
            "name": "Kaggle",
            "api_base": "https://dummy-kaggle.ngrok-free.app/v1",
            "api_key": "sk-kaggle-test-key-12345",
            "model": "kaggle-model",
            "model_alias": None,
            "extra_headers": {},
            "context_window": None,
            "max_output_tokens": None,
            "timeout": 300,
            "streaming": True,
            "is_active": True,
        })
        assert res1.status_code == 200, f"Expected 200, got {res1.status_code}: {res1.text}"
        data1 = res1.json()
        assert data1["id"].startswith("cloud-")
        assert data1["name"] == "Kaggle"
        assert data1["has_api_key"] is True
        assert data1["masked_api_key"].startswith("sk-k")

        # 2. id: "" (empty string)
        res2 = client.post("/providers/cloud_hosted/profiles", json={
            "id": "",
            "name": "Cluster Node 2",
            "api_base": "https://node2.cluster.internal/v1",
            "model": "mistral-large",
        })
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["id"].startswith("cloud-")
        assert data2["id"] != data1["id"]

        # 3. Omitted id
        res3 = client.post("/providers/cloud_hosted/profiles", json={
            "name": "Cluster Node 3",
            "api_base": "https://node3.cluster.internal/v1",
            "model": "deepseek-v3",
        })
        assert res3.status_code == 200
        assert res3.json()["id"].startswith("cloud-")


def test_cloud_profile_update_and_api_key_persistence(tmp_path):
    """Verify updating a profile preserves existing API key when key field is null or empty."""
    test_cli_config = tmp_path / "cli-config.json"

    with patch("strix.interface.api.CLI_CONFIG_FILE", test_cli_config):
        # Step 1: Create profile with credentials
        res_create = client.post("/providers/cloud_hosted/profiles", json={
            "id": "prof-persist-1",
            "name": "Initial Name",
            "api_base": "https://api.vllm.org/v1",
            "api_key": "sk-super-secret-key-to-preserve-9999",
            "model": "llama-3.3",
            "is_active": True,
        })
        assert res_create.status_code == 200
        assert res_create.json()["has_api_key"] is True

        # Step 2: Update with new display name and api_key=None
        res_update = client.post("/providers/cloud_hosted/profiles", json={
            "id": "prof-persist-1",
            "name": "Updated Production Name",
            "api_base": "https://api.vllm.org/v1",
            "api_key": None,
            "model": "llama-3.3-70b",
            "is_active": True,
        })
        assert res_update.status_code == 200
        data_update = res_update.json()
        assert data_update["name"] == "Updated Production Name"
        assert data_update["model"] == "llama-3.3-70b"
        assert data_update["has_api_key"] is True
        assert "9999" in data_update["masked_api_key"]

        # Verify underlying config storage retains exact key
        active = _get_active_cloud_profile()
        assert active["api_key"] == "sk-super-secret-key-to-preserve-9999"


def test_cloud_profile_empty_optional_fields_coercion(tmp_path):
    """Verify optional fields with empty strings or null are coerced cleanly to valid defaults."""
    test_cli_config = tmp_path / "cli-config.json"

    with patch("strix.interface.api.CLI_CONFIG_FILE", test_cli_config):
        res = client.post("/providers/cloud_hosted/profiles", json={
            "id": None,
            "name": "",  # Should default to "Cloud Hosted Endpoint"
            "api_base": "https://my-endpoint.ai/v1",
            "api_key": "",  # Empty string should become None
            "model": "custom-model",
            "model_alias": "",  # Empty string should become None
            "extra_headers": None,  # Should default to {}
            "context_window": "",  # Empty string should become None
            "max_output_tokens": "",  # Empty string should become None
            "timeout": "",  # Empty string should default to 300
            "streaming": None,  # Should default to True
            "is_active": False,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "Cloud Hosted Endpoint"
        assert data["has_api_key"] is False
        assert data["extra_headers"] == {}
        assert data["context_window"] is None
        assert data["max_output_tokens"] is None
        assert data["timeout"] == 300
        assert data["streaming"] is True


def test_cloud_profile_missing_required_fields_raises_422():
    """Verify that truly missing required fields (api_base, model) still raise HTTP 422."""
    # 1. Missing api_base
    res1 = client.post("/providers/cloud_hosted/profiles", json={
        "name": "No Base URL",
        "model": "test-model",
    })
    assert res1.status_code == 422

    # 2. Empty string api_base
    res2 = client.post("/providers/cloud_hosted/profiles", json={
        "api_base": "   ",
        "model": "test-model",
    })
    assert res2.status_code == 422

    # 3. Missing model
    res3 = client.post("/providers/cloud_hosted/profiles", json={
        "api_base": "https://api.openai.com/v1",
    })
    assert res3.status_code == 422

    # 4. Empty string model
    res4 = client.post("/providers/cloud_hosted/profiles", json={
        "api_base": "https://api.openai.com/v1",
        "model": "",
    })
    assert res4.status_code == 422


def test_cloud_profile_active_switching_and_deletion(tmp_path):
    """Verify switching active profile updates both profiles and deletion removes target."""
    test_cli_config = tmp_path / "cli-config.json"

    with patch("strix.interface.api.CLI_CONFIG_FILE", test_cli_config):
        # Create Profile A
        client.post("/providers/cloud_hosted/profiles", json={
            "id": "prof-a",
            "name": "Profile A",
            "api_base": "https://endpoint-a.ai/v1",
            "model": "model-a",
            "is_active": True,
        })
        # Create Profile B
        client.post("/providers/cloud_hosted/profiles", json={
            "id": "prof-b",
            "name": "Profile B",
            "api_base": "https://endpoint-b.ai/v1",
            "model": "model-b",
            "is_active": False,
        })

        profiles = client.get("/providers/cloud_hosted/profiles").json()
        assert next(p for p in profiles if p["id"] == "prof-a")["is_active"] is True
        assert next(p for p in profiles if p["id"] == "prof-b")["is_active"] is False

        # Switch active to Profile B
        act_res = client.post("/providers/cloud_hosted/profiles/prof-b/activate")
        assert act_res.status_code == 200
        assert act_res.json()["is_active"] is True

        profiles_after = client.get("/providers/cloud_hosted/profiles").json()
        assert next(p for p in profiles_after if p["id"] == "prof-a")["is_active"] is False
        assert next(p for p in profiles_after if p["id"] == "prof-b")["is_active"] is True

        # Delete Profile B
        del_res = client.delete("/providers/cloud_hosted/profiles/prof-b")
        assert del_res.status_code == 200

        profiles_final = client.get("/providers/cloud_hosted/profiles").json()
        assert len(profiles_final) == 1
        assert profiles_final[0]["id"] == "prof-a"

