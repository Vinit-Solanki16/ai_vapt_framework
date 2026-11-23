"""In-memory runtime credential and model configuration manager.

Provides unified runtime credential state across:
- Frontend key entry and validation (/providers/*/validate)
- Dynamic model discovery (/providers/*/models)
- Readiness probes (/system/readiness, /diagnostics/readiness)
- Assessment creation (/runs)
- Strix autonomous agent execution environment

Enforces:
- Multi-provider support (OpenRouter, OpenAI, Anthropic Claude, Google Gemini, Ollama, Custom)
- In-memory precedence over missing or placeholder environment / .env keys
- Strict redaction (keys are never exposed in logs or API responses)
- Transparent synchronization to os.environ for child subprocesses
- Base URL management for custom and local endpoints
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path


logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_RUNTIME_CREDENTIALS: dict[str, str] = {}
_RUNTIME_MODELS: dict[str, str] = {}
_RUNTIME_BASE_URLS: dict[str, str] = {}

# Known placeholder prefixes and patterns that must never be treated as live credentials
_PLACEHOLDER_MARKERS = (
    "sk-or-v1-test",
    "placeholder",
    "changeme",
    "your-api-key",
    "your_api_key",
    "your-key-here",
    "example-key",
)


def is_placeholder_credential(key: str | None) -> bool:
    """Check if a credential string is empty, null, or a known placeholder token."""
    if not key:
        return True
    cleaned = str(key).strip()
    if not cleaned or cleaned.lower() in ("none", "null", "undefined", "false", "0"):
        return True
    lower = cleaned.lower()
    return cleaned.startswith("sk-or-v1-test") or any(
        marker in lower for marker in _PLACEHOLDER_MARKERS
    )


def _read_strix_cli_config() -> dict[str, str]:
    """Safely read persisted CLI config file if present."""
    cfg_path = Path.home() / ".strix" / "cli-config.json"
    if cfg_path.is_file():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                env = data.get("env", {})
                if isinstance(env, dict):
                    return {k: str(v) for k, v in env.items() if v is not None}
                return {k: str(v) for k, v in data.items() if v is not None}
        except Exception:
            pass
    return {}


def set_runtime_credential(
    provider: str,
    api_key: str,
    model: str | None = None,
    api_base: str | None = None,
    sync_to_environ: bool = False,
) -> None:
    """Register an authenticated runtime credential in-memory.

    Fixes finding A05:
    - Never mutates shared global os.environ['LLM_API_KEY'] across providers.
    - Preserves per-run credential isolation.
    """
    prov = (provider or "openrouter").lower().strip()
    clean_key = (api_key or "").strip()

    with _LOCK:
        if clean_key and not is_placeholder_credential(clean_key):
            _RUNTIME_CREDENTIALS[prov] = clean_key

            # Only set provider-specific env vars if sync_to_environ is explicitly requested
            if sync_to_environ:
                if prov == "openrouter":
                    os.environ["OPENROUTER_API_KEY"] = clean_key
                elif prov == "anthropic":
                    os.environ["ANTHROPIC_API_KEY"] = clean_key
                elif prov == "google":
                    os.environ["GEMINI_API_KEY"] = clean_key
                elif prov == "openai":
                    os.environ["OPENAI_API_KEY"] = clean_key

        if api_base and str(api_base).strip():
            clean_base = str(api_base).strip().rstrip("/")
            _RUNTIME_BASE_URLS[prov] = clean_base
            if sync_to_environ:
                if prov in ("cloud_hosted", "custom_cloud", "custom"):
                    os.environ["OPENAI_BASE_URL"] = clean_base
                elif prov == "ollama":
                    os.environ["OLLAMA_API_BASE"] = clean_base

        if model and str(model).strip():
            clean_model = str(model).strip()
            _RUNTIME_MODELS[prov] = clean_model
            if sync_to_environ:
                from strix.llm.router import format_openrouter_model

                if prov == "openrouter":
                    os.environ["STRIX_LLM"] = format_openrouter_model(clean_model)
                else:
                    os.environ["STRIX_LLM"] = clean_model

        try:
            from strix.config import loader

            loader._cached = None
        except Exception:
            pass


def build_isolated_subprocess_env(
    provider: str,
    api_key: str | None = None,
    model: str | None = None,
    api_base: str | None = None,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build an isolated environment dictionary for a specific subprocess or run (A05 fix).

    Ensures that parallel runs with different providers never leak keys or base URLs.
    """
    prov = (provider or "openrouter").lower().strip()
    env = dict(base_env if base_env is not None else os.environ)

    # Resolve active key specifically for this provider
    key = api_key or get_runtime_credential(prov)
    if key and not is_placeholder_credential(key):
        env["LLM_API_KEY"] = key
        if prov == "openrouter":
            env["OPENROUTER_API_KEY"] = key
            env["STRIX_LLM_PROVIDER"] = "openrouter"
        elif prov == "anthropic":
            env["ANTHROPIC_API_KEY"] = key
            env["STRIX_LLM_PROVIDER"] = "anthropic"
        elif prov == "google":
            env["GEMINI_API_KEY"] = key
            env["STRIX_LLM_PROVIDER"] = "google"
        elif prov == "openai":
            env["OPENAI_API_KEY"] = key
            env["STRIX_LLM_PROVIDER"] = "openai"
        elif prov in ("cloud_hosted", "custom_cloud", "custom"):
            env["OPENAI_API_KEY"] = key
            env["STRIX_LLM_PROVIDER"] = "cloud_hosted"

    base = api_base or get_runtime_base_url(prov)
    if base:
        if prov in ("cloud_hosted", "custom_cloud", "custom"):
            env["OPENAI_BASE_URL"] = base
            env["LLM_API_BASE"] = base
        elif prov == "ollama":
            env["OLLAMA_API_BASE"] = base
            env["OLLAMA_HOST"] = base

    mdl = model or _RUNTIME_MODELS.get(prov)
    if mdl:
        from strix.llm.router import format_openrouter_model

        if prov == "openrouter":
            env["STRIX_LLM"] = format_openrouter_model(mdl)
        else:
            env["STRIX_LLM"] = mdl

    env["STRIX_NO_PERSIST_CONFIG"] = "1"
    return env


def set_runtime_base_url(provider: str, base_url: str) -> None:
    """Store custom base URL for a provider."""
    prov = (provider or "custom").lower().strip()
    clean_base = (base_url or "").strip().rstrip("/")
    with _LOCK:
        if clean_base:
            _RUNTIME_BASE_URLS[prov] = clean_base
            if prov in ("cloud_hosted", "custom_cloud", "custom"):
                os.environ["OPENAI_BASE_URL"] = clean_base
                os.environ["LLM_API_BASE"] = clean_base
            elif prov == "ollama":
                os.environ["OLLAMA_API_BASE"] = clean_base
                os.environ["OLLAMA_HOST"] = clean_base


def get_runtime_base_url(provider: str, override_base: str | None = None) -> str | None:
    """Retrieve base URL for a provider."""
    prov = (provider or "custom").lower().strip()
    if override_base and str(override_base).strip():
        return str(override_base).strip().rstrip("/")

    with _LOCK:
        if _RUNTIME_BASE_URLS.get(prov):
            return _RUNTIME_BASE_URLS[prov]

    if prov == "ollama":
        return (
            os.environ.get("OLLAMA_API_BASE")
            or os.environ.get("OLLAMA_HOST")
            or "http://127.0.0.1:11434"
        )
    if prov in ("cloud_hosted", "custom_cloud", "custom"):
        return (
            os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("LLM_API_BASE")
            or "https://api.openai.com/v1"
        )
    if prov == "openrouter":
        return os.environ.get("OPENROUTER_API_BASE") or "https://openrouter.ai/api/v1"
    if prov == "openai":
        return os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    return None


def get_runtime_credential(
    provider: str,
    override_key: str | None = None,
) -> str | None:
    """Resolve active credential for provider in order of precedence:

    1. Explicit override_key (if non-empty and not a placeholder).
    2. In-memory runtime credential registered via frontend validation or settings.
    3. System environment variables (ANTHROPIC_API_KEY, OPENROUTER_API_KEY, etc.) if not a placeholder.
    4. Persisted CLI config (~/.strix/cli-config.json) if not a placeholder.
    5. Returns placeholder if only placeholder exists (allowing caller to detect placeholder state).
    6. None if no credential exists.
    """
    prov = (provider or "openrouter").lower().strip()

    # 1. Non-placeholder explicit override
    if override_key and str(override_key).strip():
        k = str(override_key).strip()
        if not is_placeholder_credential(k):
            return k

    with _LOCK:
        # 2. In-memory runtime credential
        mem_key = _RUNTIME_CREDENTIALS.get(prov)
        if mem_key and not is_placeholder_credential(mem_key):
            return mem_key

    # 3. System environment variables (strictly provider-specific to prevent cross-leakage, A05 fix)
    env_key: str | None = None
    if prov == "openrouter":
        env_key = os.environ.get("OPENROUTER_API_KEY")
    elif prov == "anthropic":
        env_key = os.environ.get("ANTHROPIC_API_KEY")
    elif prov == "google":
        env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    elif prov == "openai":
        env_key = os.environ.get("OPENAI_API_KEY")
    elif prov in ("cloud_hosted", "custom_cloud", "custom"):
        env_key = os.environ.get("CUSTOM_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")

    if not env_key:
        active_prov = (os.environ.get("STRIX_LLM_PROVIDER") or "").lower().strip()
        if active_prov == prov:
            env_key = os.environ.get("LLM_API_KEY")

    if env_key and not is_placeholder_credential(env_key):
        return env_key

    # 4. CLI configuration file
    cli_cfg = _read_strix_cli_config()
    cli_key: str | None = None
    if prov == "openrouter":
        cli_key = cli_cfg.get("OPENROUTER_API_KEY")
    elif prov == "anthropic":
        cli_key = cli_cfg.get("ANTHROPIC_API_KEY")
    elif prov == "google":
        cli_key = cli_cfg.get("GEMINI_API_KEY")
    elif prov == "openai":
        cli_key = cli_cfg.get("OPENAI_API_KEY")
    elif prov in ("cloud_hosted", "custom_cloud", "custom"):
        cli_key = cli_cfg.get("CUSTOM_LLM_API_KEY") or cli_cfg.get("OPENAI_API_KEY")

    if not cli_key:
        active_prov = (cli_cfg.get("STRIX_LLM_PROVIDER") or "").lower().strip()
        if active_prov == prov:
            cli_key = cli_cfg.get("LLM_API_KEY")

    if cli_key and not is_placeholder_credential(cli_key):
        return cli_key

    # 5. If only placeholders exist, return in precedence order so caller can report placeholder state
    if override_key and str(override_key).strip():
        return str(override_key).strip()
    with _LOCK:
        if mem_key:
            return mem_key
    if env_key:
        return env_key
    if cli_key:
        return cli_key

    return None


def get_runtime_model(
    provider: str,
    override_model: str | None = None,
) -> str | None:
    """Resolve active model identifier for provider in order of precedence:

    1. Explicit override_model (if provided).
    2. In-memory runtime model selection from frontend.
    3. Environment variable STRIX_LLM.
    4. Persisted CLI config STRIX_LLM.
    5. None if no model has been selected.
    """
    prov = (provider or "openrouter").lower().strip()

    if override_model and str(override_model).strip():
        return str(override_model).strip()

    with _LOCK:
        if _RUNTIME_MODELS.get(prov):
            return _RUNTIME_MODELS[prov]

    env_model = os.environ.get("STRIX_LLM", "").strip()
    if env_model:
        return env_model

    cli_cfg = _read_strix_cli_config()
    cli_model = cli_cfg.get("STRIX_LLM", "").strip()
    if cli_model:
        return cli_model

    return None


def mask_credential(key: str | None) -> str:
    """Mask sensitive API keys for safe display in UI or logs."""
    if not key or is_placeholder_credential(key):
        return ""
    clean = str(key).strip()
    if len(clean) <= 10:
        return "***"
    if clean.startswith("sk-or-"):
        return f"sk-or-...{clean[-6:]}"
    if clean.startswith("sk-ant-"):
        return f"sk-ant-...{clean[-6:]}"
    if clean.startswith("sk-"):
        return f"sk-...{clean[-6:]}"
    if clean.startswith("AIza"):
        return f"AIza...{clean[-6:]}"
    return f"{clean[:4]}...{clean[-4:]}"


def clear_runtime_credentials() -> None:
    """Reset all in-memory runtime credentials, models, and base URLs (used for test isolation)."""
    with _LOCK:
        _RUNTIME_CREDENTIALS.clear()
        _RUNTIME_MODELS.clear()
        _RUNTIME_BASE_URLS.clear()
