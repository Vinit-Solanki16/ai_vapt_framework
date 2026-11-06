"""Tests for Multi-Model Configuration and Provider Routing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from strix.llm.ollama_service import get_ollama_base_url, probe_ollama
from strix.llm.provider_validation import (
    validate_google_credential,
    validate_openrouter_credential,
)
from strix.llm.router import resolve_model_kwargs


def test_ollama_base_url_resolution():
    """Verify default and overridden Ollama base URLs."""
    assert "http" in get_ollama_base_url()


def test_resolve_model_kwargs():
    """Verify LiteLLM argument generation for different providers."""
    # Ollama
    kwargs = resolve_model_kwargs("ollama", "qwen2.5:1.5b")
    assert kwargs["model"] == "ollama/qwen2.5:1.5b"
    assert "api_base" in kwargs

    # Google
    kwargs = resolve_model_kwargs("google", "gemini-2.0-flash", api_key="test-key")
    assert kwargs["model"] == "gemini/gemini-2.0-flash"
    assert kwargs["api_key"] == "test-key"

    # OpenRouter
    kwargs = resolve_model_kwargs(
        "openrouter", "meta-llama/llama-3.2-3b-instruct:free", api_key="or-key"
    )
    assert "openrouter/" in kwargs["model"]
    assert kwargs["api_key"] == "or-key"


def test_validate_google_empty_key():
    """Verify empty key fails validation gracefully."""
    res = validate_google_credential("")
    assert res.valid is False
    assert res.status == "invalid_credentials"


def test_validate_openrouter_empty_key():
    """Verify empty key fails validation gracefully."""
    res = validate_openrouter_credential("")
    assert res.valid is False
    assert res.status == "invalid_credentials"


@patch("urllib.request.urlopen")
def test_probe_ollama_success(mock_urlopen):
    """Verify probe_ollama parses models correctly on HTTP 200."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = (
        b'{"models": [{"name": "qwen2.5:1.5b:latest"}, {"name": "llama3.2:3b"}]}'
    )
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    result = probe_ollama("qwen2.5:1.5b")
    assert result["available"] is True
    assert result["reachable"] is True
    assert "qwen2.5:1.5b:latest" in result["models"]
