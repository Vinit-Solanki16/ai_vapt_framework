"""Dynamic multi-provider model routing for STRIX AI-VAPT.

Maps Web Console provider and model selections directly to LiteLLM parameters
with in-memory credential safety (zero .env pollution).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from strix.llm.ollama_service import get_ollama_base_url


def resolve_model_kwargs(
    provider: str,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
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
        target_model = model or "meta-llama/llama-3.2-3b-instruct:free"
        resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        return {
            "model": f"openrouter/{target_model}" if not target_model.startswith("openrouter/") else target_model,
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

    # Default fallback
    return {
        "model": model or "ollama/qwen2.5:1.5b",
        "api_base": get_ollama_base_url(),
    }

