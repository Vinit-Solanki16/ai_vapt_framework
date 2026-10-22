"""Ollama service probe and model availability verification (Phase 2).

Provides live inspection of the local Ollama instance:
  - Reachability check against the Ollama HTTP API (GET /api/tags).
  - Verification that the requested model (e.g. llama3.2:3b baseline) is installed.
  - Actionable guidance when Ollama or the required model is missing.
  - Zero auto-downloads: models must be pulled explicitly by user action.

Never claims offline AI capability when Ollama is stopped or the required model
is not installed.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from vapt_platform.model_config import DEFAULT_OLLAMA_MODEL

log = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_PROBE_TIMEOUT_S = 1.5


def get_ollama_base_url() -> str:
    """Resolve the Ollama base URL from environment or default.

    Supports OLLAMA_HOST (standard Ollama env var). Normalizes naked
    host:port strings by prepending http:// and strips trailing slashes.
    """
    raw = (os.getenv("OLLAMA_HOST") or "").strip()
    if not raw:
        return DEFAULT_OLLAMA_URL
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raw = f"http://{raw}"
    return raw.rstrip("/")


def _model_matches(candidate_name: str, target_model: str) -> bool:
    """Determine whether an installed Ollama model matches target_model.

    Handles tag variations (e.g. 'llama3.2:3b' matches 'llama3.2:3b:latest'
    and 'llama3.2:3b').
    """
    c = (candidate_name or "").strip().lower()
    t = (target_model or "").strip().lower()
    if not c or not t:
        return False
    if c == t:
        return True
    if c == f"{t}:latest":
        return True
    if t.endswith(":latest") and c == t[:-7]:
        return True
    # If target has no tag (e.g. 'llama3.2'), matches 'llama3.2:latest' or 'llama3.2:3b'
    if ":" not in t and c.split(":")[0] == t:
        return True
    return False


def probe_ollama(
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT_S,
) -> dict[str, Any]:
    """Probe live Ollama service reachability and model availability.

    Args:
        model_name: Target model to verify (defaults to DEFAULT_OLLAMA_MODEL).
        base_url: Ollama base URL override (defaults to get_ollama_base_url()).
        timeout: Socket timeout in seconds.

    Returns:
        A dictionary with:
            - available: bool (True only if service is reachable AND model is installed)
            - reachable: bool (True if HTTP API responded)
            - model_installed: bool (True if target model is present in tags)
            - status: 'READY' | 'UNAVAILABLE' | 'MODEL_UNAVAILABLE'
            - model: target model name
            - base_url: probed base URL
            - installed_models: list of installed model names
            - error: actionable error message if not available
            - actionable_message: short guidance for UI display
    """
    target = (model_name or DEFAULT_OLLAMA_MODEL).strip()
    url = (base_url or get_ollama_base_url()).rstrip("/")
    tags_url = f"{url}/api/tags"

    try:
        req = urllib.request.Request(
            tags_url,
            headers={"User-Agent": "AI-VAPT-Framework/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
            if status_code != 200:
                return {
                    "available": False,
                    "reachable": False,
                    "model_installed": False,
                    "status": "UNAVAILABLE",
                    "model": target,
                    "base_url": url,
                    "installed_models": [],
                    "error": (
                        f"Ollama at {url} responded with unexpected HTTP status {status_code}."
                    ),
                    "actionable_message": f"Ollama at {url} returned HTTP {status_code}.",
                }
            raw_body = resp.read()
            data = json.loads(raw_body.decode("utf-8"))

        models_list = data.get("models", [])
        installed_names = [
            m.get("name", "") for m in models_list if isinstance(m, dict) and m.get("name")
        ]

        model_found = any(_model_matches(name, target) for name in installed_names)

        if model_found:
            return {
                "available": True,
                "reachable": True,
                "model_installed": True,
                "status": "READY",
                "model": target,
                "base_url": url,
                "installed_models": installed_names,
                "error": None,
                "actionable_message": f"Ollama is running with model '{target}'.",
            }
        else:
            return {
                "available": False,
                "reachable": True,
                "model_installed": False,
                "status": "MODEL_UNAVAILABLE",
                "model": target,
                "base_url": url,
                "installed_models": installed_names,
                "error": (
                    f"Ollama is running at {url}, but model '{target}' is not installed. "
                    f"Run `ollama pull {target}` to download it, or select an online provider."
                ),
                "actionable_message": (
                    f"Model '{target}' not installed. Run `ollama pull {target}`."
                ),
            }

    except urllib.error.URLError as e:
        log.debug(f"Ollama probe failed at {tags_url}: {e}")
        return {
            "available": False,
            "reachable": False,
            "model_installed": False,
            "status": "UNAVAILABLE",
            "model": target,
            "base_url": url,
            "installed_models": [],
            "error": (
                f"Ollama service is not reachable at {url}. "
                "Start it with `ollama serve` or switch to OpenRouter (online API)."
            ),
            "actionable_message": (
                f"Ollama not running at {url}. Start with `ollama serve` or use online AI."
            ),
        }
    except Exception as e:
        log.debug(f"Ollama probe unexpected error: {e}")
        return {
            "available": False,
            "reachable": False,
            "model_installed": False,
            "status": "UNAVAILABLE",
            "model": target,
            "base_url": url,
            "installed_models": [],
            "error": f"Failed to probe Ollama at {url}: {e}",
            "actionable_message": f"Ollama probe error: {e}",
        }


def ollama_status() -> dict[str, Any]:
    """Default status report for the thesis baseline model."""
    return probe_ollama(DEFAULT_OLLAMA_MODEL)
