"""Single authoritative source for assessor model configuration.

Phase 33A: model names were previously duplicated as literals in several
layers (``core/exploit_assessor.get_llm``, ``vapt_platform/assessment``,
``vapt_platform/application``, ``prototype/engine_integration``,
``services/api``, both frontends). This module is the one place that
defines the defaults and the set of models each provider supports, so a
model name is never hardcoded in more than one layer.

Llama 3.2 3B remains the official thesis baseline and the production
default. Qwen 2.5 3B is registered as an experimental comparison arm
only — it is opt-in and never selected implicitly.

Nothing here changes the research core, GAP-1, or GAP-2. It is pure
configuration resolution.
"""
from __future__ import annotations

from typing import Optional

# --- Official baseline / production default (do not change silently) -------
DEFAULT_OLLAMA_MODEL = "llama3.2:3b"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

# --- Models exposed per provider -------------------------------------------
# Ordered: first entry is the default for that provider.
OLLAMA_MODELS: tuple[str, ...] = (
    DEFAULT_OLLAMA_MODEL,   # baseline (thesis)
    "qwen2.5:3b",           # experimental comparison arm (Phase 33A)
)
OPENAI_MODELS: tuple[str, ...] = (
    DEFAULT_OPENAI_MODEL,
)

# Label used for the experimental arm so UI/reporting can distinguish it
# without hardcoding the tag string in multiple places.
EXPERIMENTAL_MODELS: dict[str, str] = {
    "qwen2.5:3b": "experimental comparison arm (not the baseline)",
}


def models_for_provider(provider: Optional[str]) -> tuple[str, ...]:
    """Return the known models for a provider (empty if unknown)."""
    p = (provider or "").lower()
    if p == "ollama":
        return OLLAMA_MODELS
    if p == "openai":
        return OPENAI_MODELS
    return ()


def default_model_for(provider: Optional[str]) -> str:
    """Return the authoritative default model name for a provider."""
    p = (provider or "").lower()
    if p == "openai":
        return DEFAULT_OPENAI_MODEL
    return DEFAULT_OLLAMA_MODEL


def resolve_model(provider: Optional[str], requested: Optional[str] = None) -> str:
    """Resolve the model to use: explicit request wins, else provider default.

    An unknown/blank request falls back to the provider default so the
    baseline is never lost by accident.
    """
    req = (requested or "").strip()
    if req:
        return req
    return default_model_for(provider)


def is_experimental(model: Optional[str]) -> bool:
    """True when the model is a registered experimental (non-baseline) arm."""
    return (model or "").strip() in EXPERIMENTAL_MODELS


def is_baseline(model: Optional[str]) -> bool:
    """True when the model is the official thesis baseline."""
    return (model or "").strip() == DEFAULT_OLLAMA_MODEL
