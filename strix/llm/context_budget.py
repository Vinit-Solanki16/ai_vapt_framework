"""Model-aware token budgets, resolved dynamically from LiteLLM model metadata,
remote provider model discovery (/models), explicit operator settings, and runtime
error feedback with a configurable fallback.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

from strix.config import load_settings


logger = logging.getLogger(__name__)

# LiteLLM keys models without the routing prefix users type (``openai/``,
# ``litellm/``, ``ollama/`` ...). Strip a leading provider segment on lookup.
_STRIPPABLE_PREFIXES = (
    "openai/",
    "chatgpt/",
    "litellm/",
    "any-llm/",
    "ollama/",
    "ollama_chat/",
)

_DEFAULT_OUTPUT_TOKENS = 8_192
_CACHE_FILE: Path = Path.home() / ".strix" / "model-contexts.json"

_DETECTED_CONTEXT_LIMITS: dict[str, int] = {}


def _load_cached_context_limits() -> None:
    """Load persistent model context limits from ~/.strix/model-contexts.json."""
    if not _CACHE_FILE.is_file():
        return
    try:
        raw = _CACHE_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, int) and 2048 <= v <= 10_000_000:
                    _DETECTED_CONTEXT_LIMITS[str(k)] = v
    except Exception:
        logger.debug("Failed to load model context cache from %s", _CACHE_FILE)


def _save_cached_context_limits() -> None:
    """Persist discovered model context limits atomically to disk."""
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(_DETECTED_CONTEXT_LIMITS, indent=2), encoding="utf-8")
        tmp.replace(_CACHE_FILE)
    except Exception:
        logger.debug("Failed to persist model context cache to %s", _CACHE_FILE)


# Populate cache on module import
_load_cached_context_limits()


def _lookup_key(model: str) -> str:
    for prefix in _STRIPPABLE_PREFIXES:
        if model.startswith(prefix):
            return model[len(prefix) :]
    return model


def extract_model_context_length(item: Any) -> int | None:
    """Extract context window length from provider model metadata dict."""
    if not isinstance(item, dict):
        return None

    # 1. Direct fields: n_ctx, context_length, context_window, max_model_len, etc.
    for key in (
        "context_length",
        "context_window",
        "max_model_len",
        "max_position_embeddings",
        "max_input_tokens",
        "max_tokens",
        "n_ctx",
    ):
        val = item.get(key)
        if isinstance(val, int) and 2048 <= val <= 10_000_000:
            return val
        if isinstance(val, str) and val.isdigit():
            v_int = int(val)
            if 2048 <= v_int <= 10_000_000:
                return v_int

    # 2. Nested sub-dictionaries: meta, details, parameters, config
    for parent_key in ("meta", "details", "parameters", "config", "architecture"):
        parent = item.get(parent_key)
        if isinstance(parent, dict):
            for key in (
                "n_ctx",
                "context_length",
                "context_window",
                "max_model_len",
                "max_position_embeddings",
                "max_input_tokens",
                "n_ctx_train",
            ):
                val = parent.get(key)
                if isinstance(val, int) and 2048 <= val <= 10_000_000:
                    return val
                if isinstance(val, str) and val.isdigit():
                    v_int = int(val)
                    if 2048 <= v_int <= 10_000_000:
                        return v_int

    return None


def record_detected_context_limit(model: str, limit: int) -> None:
    """Record an authoritative context limit discovered from provider endpoints or error feedback."""
    if limit >= 2048:
        model_str = str(model).strip()
        lookup = _lookup_key(model_str)
        _DETECTED_CONTEXT_LIMITS[model_str] = limit
        _DETECTED_CONTEXT_LIMITS[lookup] = limit
        _DETECTED_CONTEXT_LIMITS[f"openai/{lookup}"] = limit
        _save_cached_context_limits()
        logger.info(
            "Recorded dynamic context limit for %r (%r): %d tokens", model_str, lookup, limit
        )


def probe_endpoint_model_context(
    api_base: str,
    model: str,
    api_key: str | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout: float = 4.0,
) -> int | None:
    """Fast probe against {api_base}/models to discover model's native context window."""
    base = (api_base or "").strip().rstrip("/")
    if not base:
        return None
    url = f"{base}/models"
    headers: dict[str, str] = {
        "User-Agent": "STRIX-AI-VAPT/1.0",
        "Accept": "application/json",
    }
    if api_key and api_key.strip() and api_key.strip().lower() != "none":
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    if extra_headers and isinstance(extra_headers, dict):
        for k, v in extra_headers.items():
            if k and v is not None:
                headers[str(k).strip()] = str(v).strip()

    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                raw = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(raw)
                items = data.get("data") or data.get("models") or []
                if isinstance(items, list):
                    lookup = _lookup_key(model).lower()
                    for item in items:
                        if isinstance(item, dict):
                            item_id = str(item.get("id") or item.get("name") or "").lower()
                            aliases = [
                                str(a).lower()
                                for a in (item.get("aliases") or [])
                                if isinstance(a, str)
                            ]
                            if item_id == lookup or lookup in aliases:
                                ctx = extract_model_context_length(item)
                                if ctx:
                                    record_detected_context_limit(model, ctx)
                                    return ctx
    except Exception as exc:
        logger.debug("Fast /models probe failed on %s: %s", url, exc)
    return None


def resolve_and_record_model_context(
    model: str,
    settings: Any = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> int:
    """Resolve model context limit dynamically across all available channels."""
    lookup = _lookup_key(model)

    # 1. Check in-memory or persisted cache
    if model in _DETECTED_CONTEXT_LIMITS:
        return _DETECTED_CONTEXT_LIMITS[model]
    if lookup in _DETECTED_CONTEXT_LIMITS:
        return _DETECTED_CONTEXT_LIMITS[lookup]

    # 2. Check operator environment variable override
    env_override = os.environ.get("STRIX_MODEL_CONTEXT_WINDOW") or os.environ.get(
        "STRIX_CONTEXT_WINDOW"
    )
    if env_override and env_override.strip().isdigit():
        val = int(env_override.strip())
        if val >= 2048:
            record_detected_context_limit(model, val)
            return val

    # 3. Check LiteLLM model info database
    info = _model_info(model)
    if info.get("max_input_tokens", 0) > 0:
        return info["max_input_tokens"]

    # 4. Probe remote endpoint /models if base URL available
    cfg_base = api_base or (
        settings.llm.api_base if settings and getattr(settings, "llm", None) else None
    )
    if not cfg_base:
        cfg_base = os.environ.get("OPENAI_BASE_URL") or os.environ.get("STRIX_LLM_API_BASE")
    cfg_key = api_key or (
        settings.llm.api_key if settings and getattr(settings, "llm", None) else None
    )
    if not cfg_key:
        cfg_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")

    if cfg_base:
        probed_ctx = probe_endpoint_model_context(cfg_base, model, api_key=cfg_key)
        if probed_ctx:
            return probed_ctx

    # 5. Configured fallback
    if settings and getattr(settings, "context", None):
        return int(settings.context.fallback_context_tokens)
    return load_settings().context.fallback_context_tokens


def _safe_get_model_info(model: str) -> dict[str, Any] | None:
    try:
        import litellm

        return dict(litellm.get_model_info(model))
    except Exception:  # noqa: BLE001 - unmapped models raise; caller falls back.
        return None


@lru_cache(maxsize=128)
def _model_info(model: str) -> dict[str, int]:
    lookup_key = _lookup_key(model)
    candidates = (lookup_key,) if model.startswith("chatgpt/") else (model, lookup_key)
    for candidate in candidates:
        info = _safe_get_model_info(candidate)
        if info is not None:
            return {
                "max_input_tokens": int(
                    info.get("max_input_tokens") or info.get("max_tokens") or 0
                ),
                "max_output_tokens": int(info.get("max_output_tokens") or 0),
            }
    return {"max_input_tokens": 0, "max_output_tokens": 0}


def context_window(model: str) -> int:
    """Dynamic input token capacity for ``model``."""
    lookup = _lookup_key(model)
    if model in _DETECTED_CONTEXT_LIMITS:
        return _DETECTED_CONTEXT_LIMITS[model]
    if lookup in _DETECTED_CONTEXT_LIMITS:
        return _DETECTED_CONTEXT_LIMITS[lookup]

    env_override = os.environ.get("STRIX_MODEL_CONTEXT_WINDOW") or os.environ.get(
        "STRIX_CONTEXT_WINDOW"
    )
    if env_override and env_override.strip().isdigit():
        val = int(env_override.strip())
        if val >= 2048:
            record_detected_context_limit(model, val)
            return val

    resolved = _model_info(model)["max_input_tokens"]
    if resolved > 0:
        return resolved

    # Fallback to runtime resolution
    return resolve_and_record_model_context(model)


def output_limit(model: str) -> int:
    """Max output tokens for ``model`` (a conservative default when unmapped)."""
    return _model_info(model)["max_output_tokens"] or _DEFAULT_OUTPUT_TOKENS


def count_tokens(model: str, text: str) -> int:
    """Token count for ``text`` under ``model``.

    Falls back to UTF-8 byte length (a guaranteed upper bound) when LiteLLM
    can't count, so budget checks stay conservative.
    """
    if not text:
        return 0
    try:
        import litellm

        return int(litellm.token_counter(model=_lookup_key(model), text=text))
    except Exception:  # noqa: BLE001 - tokenizer may be unavailable for some models.
        return len(text.encode("utf-8"))
