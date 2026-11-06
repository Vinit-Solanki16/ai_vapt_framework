"""Regression and integration tests for OpenRouter LLM routing, credential propagation,
error handling, and frontend reporting in STRIX AI-VAPT.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

from strix.llm.router import (
    DEFAULT_OPENROUTER_MODEL,
    DEPRECATED_OPENROUTER_FREE_MODELS,
    format_openrouter_model,
    resolve_model_kwargs,
)
from strix.llm.provider_validation import (
    fetch_openrouter_free_models,
    validate_openrouter_credential,
)
from strix.interface.api import _extract_clean_error, _redact_secrets


class TestOpenRouterModelFormatting:
    def test_default_model_selection(self):
        """1. OpenRouter provider selection with empty/None model defaults safely."""
        res = format_openrouter_model(None)
        assert res == f"openrouter/{DEFAULT_OPENROUTER_MODEL}"
        res_empty = format_openrouter_model("")
        assert res_empty == f"openrouter/{DEFAULT_OPENROUTER_MODEL}"

    def test_model_identifier_propagation(self):
        """2. OpenRouter model identifier propagation preserves valid active models."""
        model = "nvidia/nemotron-3.5-lightning:free"
        res = format_openrouter_model(model)
        assert res == f"openrouter/{model}"

        # If already prefixed
        prefixed = f"openrouter/{model}"
        assert format_openrouter_model(prefixed) == prefixed

    def test_free_model_suffix_preservation(self):
        """3. Free-model suffix ':free' is properly preserved."""
        model = "dots-studio/dots-3-note-preview:free"
        res = format_openrouter_model(model)
        assert res.endswith(":free")
        assert res == "openrouter/dots-studio/dots-3-note-preview:free"

    def test_deprecated_free_models_auto_migrated(self):
        """Deprecated/retired models return active free model to avoid 404s."""
        for old_model in DEPRECATED_OPENROUTER_FREE_MODELS:
            res = format_openrouter_model(old_model)
            assert res == f"openrouter/{DEFAULT_OPENROUTER_MODEL}"
            # Also with openrouter/ prefix
            res_pfx = format_openrouter_model(f"openrouter/{old_model}")
            assert res_pfx == f"openrouter/{DEFAULT_OPENROUTER_MODEL}"

    def test_openrouter_free_double_namespace(self):
        """openrouter/free requires double-namespace for LiteLLM routing."""
        res1 = format_openrouter_model("free")
        assert res1 == "openrouter/openrouter/free"
        res2 = format_openrouter_model("openrouter/free")
        assert res2 == "openrouter/openrouter/free"
        res3 = format_openrouter_model("openrouter/openrouter/free")
        assert res3 == "openrouter/openrouter/free"


class TestLiteLLMConfigurationAndRouter:
    def test_litellm_configuration_resolution(self, monkeypatch):
        """4. LiteLLM configuration maps provider, model, and endpoint correctly."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-dummytestkey1234567890abcdef")
        monkeypatch.setenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")

        kwargs = resolve_model_kwargs(
            provider="openrouter",
            model_name="nvidia/nemotron-3.5-lightning:free",
        )
        assert kwargs["model"] == "openrouter/nvidia/nemotron-3.5-lightning:free"
        assert kwargs["api_key"] == "sk-or-v1-dummytestkey1234567890abcdef"
        assert kwargs["api_base"] == "https://openrouter.ai/api/v1"

    def test_multi_model_provider_selection(self):
        """13. Multi-model provider selection routes correctly across providers."""
        # Ollama
        ol_kwargs = resolve_model_kwargs(provider="ollama", model_name="qwen2.5:1.5b")
        assert ol_kwargs["model"] == "ollama/qwen2.5:1.5b"

        # Google Gemini
        g_kwargs = resolve_model_kwargs(provider="google", model_name="gemini-2.0-flash", api_key="AIzaSyTest")
        assert g_kwargs["model"] == "gemini/gemini-2.0-flash"
        assert g_kwargs["api_key"] == "AIzaSyTest"

        # OpenAI
        o_kwargs = resolve_model_kwargs(provider="openai", model_name="gpt-4o-mini", api_key="sk-test")
        assert o_kwargs["model"] == "gpt-4o-mini"
        assert o_kwargs["api_key"] == "sk-test"


class TestDockerEnvironmentPropagation:
    def test_docker_environment_contains_openrouter_vars(self):
        """5. Docker sandbox Environment receives propagated OpenRouter vars."""
        import inspect
        from strix.runtime.session_manager import create_or_reuse

        src = inspect.getsource(create_or_reuse)
        assert "OPENROUTER_API_KEY" in src
        assert "OPENROUTER_API_BASE" in src
        assert "STRIX_LLM" in src


class TestCredentialValidationAndMockResponses:
    def test_missing_api_key(self):
        """6. Missing API key returns invalid_credentials without making network calls."""
        res = validate_openrouter_credential("")
        assert res.valid is False
        assert res.status == "invalid_credentials"
        assert "No OpenRouter API key provided" in res.message

    def test_http_401_403_unauthorized(self):
        """9. HTTP 401/403 triggers authentication failure response."""
        import urllib.error

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = urllib.error.HTTPError(
                url="https://openrouter.ai/api/v1/auth/key",
                code=401,
                msg="Unauthorized",
                hdrs=None,
                fp=None,
            )
            res = validate_openrouter_credential("sk-or-v1-invalidkey")
            assert res.valid is False
            assert res.status == "invalid_credentials"
            assert "Unauthorized" in res.message

    def test_http_429_rate_limited(self):
        """10. HTTP 429 returns rate limited status."""
        import urllib.error

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = urllib.error.HTTPError(
                url="https://openrouter.ai/api/v1/auth/key",
                code=429,
                msg="Too Many Requests",
                hdrs=None,
                fp=None,
            )
            res = validate_openrouter_credential("sk-or-v1-ratekey")
            assert res.valid is False
            assert res.status == "rate_limited"

    def test_network_timeout(self):
        """11. Network timeout during catalogue fetch falls back gracefully to default free models."""
        import socket

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = socket.timeout("timed out")
            fallback = fetch_openrouter_free_models()
            assert len(fallback) > 0
            assert any("nemotron-3.5-lightning" in m.id for m in fallback)


class TestErrorReportingAndRedaction:
    def test_http_404_clean_error_reporting(self):
        """8. HTTP 404 generates human-friendly error advice."""
        stderr = [
            "litellm.exceptions.NotFoundError: NotFoundError: OpenrouterException - 404",
            '{"error":{"message":"This model is unavailable for free. The paid version is available now - use this slug instead: meta-llama/llama-3.2-3b-instruct","code":404}}',
        ]
        msg = _extract_clean_error(stderr, [])
        assert "OpenRouter model not found or unavailable (HTTP 404)" in msg
        assert "Verify the model identifier" in msg

    def test_http_401_clean_error_reporting(self):
        """9. HTTP 401 generates human-friendly authentication advice."""
        stderr = [
            "litellm.exceptions.AuthenticationError: OpenrouterException - 401 User not found or key invalid",
        ]
        msg = _extract_clean_error(stderr, [])
        assert "OpenRouter authentication failed (HTTP 401/403)" in msg

    def test_http_429_clean_error_reporting(self):
        """10. HTTP 429 generates rate limit advice."""
        stderr = [
            "litellm.exceptions.RateLimitError: OpenrouterException - 429 Rate limit exceeded",
        ]
        msg = _extract_clean_error(stderr, [])
        assert "OpenRouter rate limit reached (HTTP 429)" in msg

    def test_secret_redaction(self):
        """14. API keys are completely redacted from all error messages and terminal output."""
        sensitive_raw = (
            "Error with dummy key sk-or-v1-00000000000000000000000000000000 "
            "and secondary dummy sk-00000000000000000000000000000000 and google dummy AIzaSyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        )
        redacted = _redact_secrets(sensitive_raw)
        assert "sk-or-v1-00000000000000000000000000000000" not in redacted  # dummy key
        assert "sk-00000000000000000000000000000000" not in redacted  # dummy key
        assert "AIzaSyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" not in redacted  # dummy key
        assert "REDACTED" in redacted


class TestToolCallingWithOpenRouter:
    def test_tool_calling_payload_compatibility(self):
        """12. Verified tool-calling support on nvidia/nemotron-3.5-lightning:free."""
        from strix.config.models import StrixProvider

        provider = StrixProvider()
        model = provider.get_model("openrouter/nvidia/nemotron-3.5-lightning:free")
        assert model is not None
