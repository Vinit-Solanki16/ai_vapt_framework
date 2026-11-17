"""Dynamic multi-provider model routing for STRIX AI-VAPT.

Maps Web Console provider and model selections directly to LiteLLM parameters
with in-memory credential safety (zero .env pollution).
Supports: OpenRouter, OpenAI, Anthropic Claude, Google Gemini, Ollama, and Custom endpoints.
"""

from __future__ import annotations

import os
from typing import Any

from strix.llm.ollama_service import get_ollama_base_url


# Standard OpenRouter default reference for fallback
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3.5-super-vl:free"

# Historical / retired OpenRouter free models mapped to active verified tool-calling models
DEPRECATED_OPENROUTER_FREE_MODELS: dict[str, str] = {
    "meta-llama/llama-3.2-3b-instruct:free": "nvidia/nemotron-3.5-lightning:free",
    "mistralai/mistral-7b-instruct:free": "nvidia/nemotron-3.5-lightning:free",
}


def format_openrouter_model(model_name: str | None = None) -> str:
    """Format and normalize an OpenRouter model identifier for LiteLLM routing.

    Handles:
    - Double-namespace slug requirement for LiteLLM routing (openrouter/free -> openrouter/openrouter/free).
    - Preserving user-selected model IDs (both free and paid) without altering them.
    - Ensuring LiteLLM routes all OpenRouter requests through the openrouter provider prefix.
    """
    raw = (model_name or "").strip()
    if not raw:
        return f"openrouter/{DEFAULT_OPENROUTER_MODEL}"

    # Extract bare model slug without leading openrouter/ prefix for inspection
    slug = raw
    if slug.startswith("openrouter/"):
        slug = slug[len("openrouter/") :]

    # Auto-migrate deprecated models that now return HTTP 404
    if slug in DEPRECATED_OPENROUTER_FREE_MODELS:
        slug = DEPRECATED_OPENROUTER_FREE_MODELS[slug]

    # Special handling for openrouter/free:
    # LiteLLM strips the first provider prefix 'openrouter/'.
    # If passed 'openrouter/free', LiteLLM sends 'free' to OpenRouter API -> 404.
    # To send slug 'openrouter/free' to OpenRouter, LiteLLM must receive 'openrouter/openrouter/free'.
    if slug == "free" or slug == "openrouter/free":
        return "openrouter/openrouter/free"
    if slug.startswith("openrouter/openrouter/"):
        return slug

    # Ensure LiteLLM routes all OpenRouter models through the openrouter provider prefix
    return f"openrouter/{slug}"


def resolve_model_kwargs(
    provider: str,
    model_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve provider, model, and credentials into LiteLLM call arguments.

    Respects in-memory runtime credentials with zero silent model substitution.
    """
    from strix.core.runtime_credentials import (
        get_runtime_base_url,
        get_runtime_credential,
        get_runtime_model,
    )

    prov = (provider or "openrouter").strip().lower()
    raw_model = (model_name or "").strip() or get_runtime_model(prov) or ""

    if prov == "anthropic":
        target_model = raw_model or "claude-3-5-sonnet-20241022"
        if not target_model.startswith("anthropic/"):
            target_model = f"anthropic/{target_model}"
        resolved_key = (
            api_key
            or get_runtime_credential("anthropic")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("LLM_API_KEY")
        )
        return {
            "model": target_model,
            "api_key": resolved_key,
        }

    if prov == "openrouter":
        target_model = format_openrouter_model(raw_model)
        resolved_key = (
            api_key
            or get_runtime_credential("openrouter")
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
        resolved_base = (
            api_base
            or get_runtime_base_url("openrouter")
            or os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
        )
        return {
            "model": target_model,
            "api_key": resolved_key,
            "api_base": resolved_base,
        }

    if prov == "openai":
        target_model = raw_model or "gpt-4o-mini"
        resolved_key = (
            api_key
            or get_runtime_credential("openai")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("LLM_API_KEY")
        )
        openai_base = (
            api_base or get_runtime_base_url("openai") or os.environ.get("OPENAI_BASE_URL")
        )
        out: dict[str, Any] = {
            "model": target_model,
            "api_key": resolved_key,
        }
        if openai_base:
            out["api_base"] = openai_base
        return out

    if prov == "google":
        target_model = raw_model or "gemini-2.0-flash"
        if not target_model.startswith("gemini/") and not target_model.startswith("google/"):
            target_model = f"gemini/{target_model}"
        resolved_key = (
            api_key
            or get_runtime_credential("google")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("LLM_API_KEY")
        )
        return {
            "model": target_model,
            "api_key": resolved_key,
        }

    if prov == "ollama":
        target_model = raw_model or "qwen2.5:1.5b"
        resolved_base = api_base or get_runtime_base_url("ollama") or get_ollama_base_url()
        return {
            "model": f"ollama/{target_model}"
            if not target_model.startswith("ollama/")
            else target_model,
            "api_base": resolved_base,
        }

    if prov in ("cloud_hosted", "custom_cloud", "custom"):
        target_model = raw_model or "custom-model"
        if not target_model.startswith("openai/"):
            target_model = f"openai/{target_model}"
        resolved_key = (
            api_key
            or get_runtime_credential(prov)
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or "none"
        )
        resolved_base = (
            api_base
            or get_runtime_base_url(prov)
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("LLM_API_BASE")
            or "https://api.openai.com/v1"
        )
        out_kwargs: dict[str, Any] = {
            "model": target_model,
            "api_key": resolved_key,
            "api_base": resolved_base,
        }
        if extra_headers:
            out_kwargs["extra_headers"] = extra_headers
        elif os.environ.get("LLM_EXTRA_HEADERS"):
            try:
                import json

                out_kwargs["extra_headers"] = json.loads(os.environ["LLM_EXTRA_HEADERS"])
            except Exception:
                pass
        return out_kwargs

    # Default fallback for unrecognized provider
    return {
        "model": raw_model or "default",
        "api_key": api_key or get_runtime_credential(prov),
    }
