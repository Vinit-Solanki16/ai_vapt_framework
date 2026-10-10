"""Single authoritative source for assessor model configuration.

Phase 33A: model names were previously duplicated as literals in several
layers (``core/exploit_assessor.get_llm``, ``vapt_platform/assessment``,
``vapt_platform/application``, ``prototype/engine_integration``,
``services/api``, both frontends). This module is the one place that
defines the defaults and the set of models each provider supports, so a
model name is never hardcoded in more than one layer.

Llama 3.2 3B remains the official thesis baseline and the production
default. Qwen 2.5 3B is registered as an experimental comparison arm
only — it is opt-in and never selected implicitly. OpenRouter is an
OPTIONAL hosted provider: it is never selected implicitly, never
substituted for the local baseline, and its runs are recorded separately
from the historical Ollama experiments.

Nothing here changes the research core, GAP-1, or GAP-2. It is pure
configuration resolution.
"""
from __future__ import annotations

import os
from typing import Optional

# --- Official baseline / production default (do not change silently) -------
DEFAULT_OLLAMA_MODEL = "llama3.2:3b"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
#: Hosted default for the OPTIONAL OpenRouter provider. OpenRouter runs are a
#: separate, clearly-labelled arm — they are NEVER compared against, merged
#: into, or substituted for the historical Ollama/llama3.2:3b baseline runs.
DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct"

# --- Models exposed per provider -------------------------------------------
# Ordered: first entry is the default for that provider.
OLLAMA_MODELS: tuple[str, ...] = (
    DEFAULT_OLLAMA_MODEL,   # baseline (thesis)
    "qwen2.5:3b",           # experimental comparison arm (Phase 33A)
)
OPENAI_MODELS: tuple[str, ...] = (
    DEFAULT_OPENAI_MODEL,
)
OPENROUTER_MODELS: tuple[str, ...] = (
    DEFAULT_OPENROUTER_MODEL,
    "openai/gpt-4o-mini",
    "anthropic/claude-3.5-haiku",
)

# --- Provider registry ------------------------------------------------------
#: Providers the platform can dispatch to. The DEFAULT_PROVIDER is Ollama and
#: must never change implicitly — the thesis baseline depends on it.
DEFAULT_PROVIDER = "ollama"
KNOWN_PROVIDERS: tuple[str, ...] = ("ollama", "openrouter", "openai")

#: UI/report label for each provider (hosted vs local is never ambiguous).
PROVIDER_LABELS: dict[str, str] = {
    "ollama": "Ollama (local, offline)",
    "openrouter": "OpenRouter (hosted API)",
    "openai": "OpenAI (hosted API)",
}

#: Environment variable holding the API key for each hosted provider.
#: Local providers (ollama) have no key by design.
PROVIDER_API_KEY_ENV: dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
}

# Label used for the experimental arm so UI/reporting can distinguish it
# without hardcoding the tag string in multiple places.
EXPERIMENTAL_MODELS: dict[str, str] = {
    "qwen2.5:3b": "experimental comparison arm (not the baseline)",
}


def is_known_provider(provider: Optional[str]) -> bool:
    """True when *provider* is a registered dispatch target."""
    return (provider or "").strip().lower() in KNOWN_PROVIDERS


def default_openrouter_model_from_env() -> str:
    """Hosted OpenRouter default, overridable via ``OPENROUTER_MODEL``.

    Falls back to the compiled-in default when the var is unset or blank, so
    an absent variable never changes behaviour. Note the Ollama baseline is
    deliberately NOT env-overridable — the thesis baseline must stay fixed.
    """
    requested = (os.getenv("OPENROUTER_MODEL") or "").strip()
    return requested or DEFAULT_OPENROUTER_MODEL


def api_key_env_for(provider: Optional[str]) -> Optional[str]:
    """Return the API-key env var for a hosted provider (None for local)."""
    return PROVIDER_API_KEY_ENV.get((provider or "").strip().lower())


def models_for_provider(provider: Optional[str]) -> tuple[str, ...]:
    """Return the known models for a provider (empty if unknown)."""
    p = (provider or "").lower()
    if p == "ollama":
        return OLLAMA_MODELS
    if p == "openai":
        return OPENAI_MODELS
    if p == "openrouter":
        return OPENROUTER_MODELS
    return ()


def default_model_for(provider: Optional[str]) -> str:
    """Return the authoritative default model name for a provider.

    Unknown providers resolve to the Ollama baseline so the thesis default
    is never lost by accident.
    """
    p = (provider or "").lower()
    if p == "openai":
        return DEFAULT_OPENAI_MODEL
    if p == "openrouter":
        return default_openrouter_model_from_env()
    return DEFAULT_OLLAMA_MODEL


#: Hard ceiling on a model-name length. Long enough for any real provider
#: slug, short enough that a runaway value cannot bloat SDK calls or reports.
MAX_MODEL_NAME_LEN = 200


def is_valid_model_name(model: object) -> bool:
    """Syntactic sanity check for an explicit model name.

    Deliberately NOT an allowlist: ``OPENROUTER_MODEL`` must stay
    user-configurable, so any well-formed ``vendor/model`` slug is accepted
    even if it is not in :data:`OPENROUTER_MODELS` (the provider itself is the
    authority on whether it exists, and answers with a classified 404).

    Rejects only what can never be a legitimate identifier: non-strings,
    empty/over-long values, leading or trailing whitespace, internal
    whitespace, and control characters (which would otherwise be injected
    into logs and report provenance).
    """
    if not isinstance(model, str):
        return False
    if not model or len(model) > MAX_MODEL_NAME_LEN:
        return False
    if model != model.strip():
        return False
    if any(ch.isspace() for ch in model):
        return False
    return not any(ord(ch) < 32 or ord(ch) == 127 for ch in model)


def resolve_model(provider: Optional[str], requested: Optional[str] = None) -> str:
    """Resolve the model to use: explicit request wins, else provider default.

    A blank/None request falls back to the provider default so the baseline is
    never lost by accident.

    Raises:
        ValueError: when an explicit request is present but malformed (wrong
            type, empty after stripping, over-long, or containing whitespace /
            control characters). A malformed name is a configuration error and
            must fail loudly rather than be sent to an SDK or embedded in a
            report.
    """
    if requested is None:
        return _validated(default_model_for(provider), provider)
    if not isinstance(requested, str):
        raise ValueError(
            f"Model name must be a string, got {type(requested).__name__}."
        )
    req = requested.strip()
    if not req:
        return _validated(default_model_for(provider), provider)
    if not is_valid_model_name(req):
        raise ValueError(
            f"Malformed model name {requested!r}: must be 1..{MAX_MODEL_NAME_LEN} "
            "characters with no whitespace or control characters."
        )
    return req


def _validated(model: str, provider: Optional[str]) -> str:
    """Validate a provider default (possibly env-derived) before returning it.

    ``default_model_for`` must stay non-raising because the health endpoint
    calls it directly; validation happens here, on the path that actually
    constructs a client.
    """
    if not is_valid_model_name(model):
        raise ValueError(
            f"Malformed default model {model!r} for provider {provider!r} "
            f"(check OPENROUTER_MODEL). Expected 1..{MAX_MODEL_NAME_LEN} "
            "characters with no whitespace or control characters."
        )
    return model


def is_experimental(model: Optional[str]) -> bool:
    """True when the model is a registered experimental (non-baseline) arm."""
    return (model or "").strip() in EXPERIMENTAL_MODELS


def is_baseline(model: Optional[str]) -> bool:
    """True when the model is the official thesis baseline."""
    return (model or "").strip() == DEFAULT_OLLAMA_MODEL
