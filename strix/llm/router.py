"""Dynamic multi-provider model routing for STRIX AI-VAPT.

Maps Web Console provider and model selections directly to LiteLLM parameters
with in-memory credential safety (zero .env pollution).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from strix.llm.ollama_service import get_ollama_base_url

DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3.5-lightning:free"

# Historical / deprecated OpenRouter free models mapped to currently active, verified tool-calling models
DEPRECATED_OPENROUTER_FREE_MODELS = {
    "meta-llama/llama-3.2-3b-instruct:free": "nvidia/nemotron-3.5-lightning:free",
    "meta-llama/llama-3.3-70b-instruct:free": "nvidia/nemotron-3.5-lightning:free",
    "deepseek/deepseek-r1:free": "nvidia/nemotron-3.5-lightning:free",
    "google/gemini-2.0-flash-exp:free": "nvidia/nemotron-3.5-lightning:free",
    "qwen/qwen-2.5-coder-32b-instruct:free": "nvidia/nemotron-3.5-lightning:free",
    "mistralai/mistral-7b-instruct:free": "nvidia/nemotron-3.5-lightning:free",
}


def format_openrouter_model(model_name: Optional[str] = None) -> str:
    """Format and normalize an OpenRouter model identifier for LiteLLM routing.

    Handles:
    - Defaulting to an active tool-calling free model if None/empty.
    - Transparent migration of retired/deprecated free models.
    - Double-namespace slug requirement for LiteLLM routing (openrouter/free -> openrouter/openrouter/free).
    - Preserving valid prefixed models (openrouter/{author}/{model}:free).
    """
    raw = (model_name or "").strip()
    if not raw:
        return f"openrouter/{DEFAULT_OPENROUTER_MODEL}"

    # Extract bare model slug without leading openrouter/ prefix for inspection
    slug = raw
    if slug.startswith("openrouter/"):
        slug = slug[len("openrouter/"):]

    # Auto-migrate deprecated models that now return HTTP 404
    if slug in DEPRECATED_OPENROUTER_FREE_MODELS:
        slug = DEPRECATED_OPENROUTER_FREE_MODELS[slug]

    # Special handling for openrouter/free:
    # LiteLLM strips the first provider prefix 'openrouter/'.
    # If passed 'openrouter/free', LiteLLM sends 'free' to OpenRouter API -> 404.
    # To send slug 'openrouter/free' to OpenRouter, LiteLLM must receive 'openrouter/openrouter/free'.
    if slug == "free" or slug == "openrouter/free":
        return "openrouter/openrouter/free"
    elif slug.startswith("openrouter/openrouter/"):
        return slug

    if raw.startswith("openrouter/"):
        # Re-check if migration changed the slug
        return f"openrouter/{slug}"
    return f"openrouter/{slug}"


def resolve_model_kwargs(
    provider: str,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Resolve provider, model, and credentials into LiteLLM call arguments."""
    prov = (provider or "ollama").strip().lower()
    model = (model_name or "").strip()

    if prov == "ollama":
        target_model = model or "qwen2.5:1.5b"
        return {
            "model": f"ollama/{target_model}" if not target_model.startswith("ollama/") else target_model,
            "api_base": get_ollama_base_url(),
        }

    elif prov == "google":
        target_model = model or "gemini-2.0-flash"
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        return {
            "model": f"gemini/{target_model}" if not target_model.startswith("gemini/") else target_model,
            "api_key": resolved_key,
        }

    elif prov == "openrouter":
        target_model = format_openrouter_model(model)
        resolved_key = (
            api_key
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("LLM_API_KEY")
        )
        return {
            "model": target_model,
            "api_key": resolved_key,
            "api_base": os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1"),
        }

    elif prov == "openai":
        target_model = model or "gpt-4o-mini"
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        return {
            "model": target_model,
            "api_key": resolved_key,
        }

    elif prov in ("cloud_hosted", "custom_cloud", "custom"):
        target_model = model or "custom-model"
        if not target_model.startswith("openai/"):
            target_model = f"openai/{target_model}"
        resolved_key = (
            api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or "none"
        )
        resolved_base = (
            api_base
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("LLM_API_BASE")
            or "https://api.openai.com/v1"
        )
        out_kwargs: Dict[str, Any] = {
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

    # Default fallback
    return {
        "model": model or "ollama/qwen2.5:1.5b",
        "api_base": get_ollama_base_url(),
    }

