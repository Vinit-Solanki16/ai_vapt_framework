"""Local Ollama service prober and query utility for STRIX AI-VAPT."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any


logger = logging.getLogger("strix.llm.ollama")

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_PROBE_TIMEOUT = 2.0


def get_ollama_base_url() -> str:
    """Resolve Ollama base URL from environment or default."""
    raw = (
        os.getenv("OLLAMA_API_BASE")
        or os.getenv("OLLAMA_BASE_URL")
        or os.getenv("OLLAMA_HOST")
        or ""
    ).strip()
    if not raw:
        return DEFAULT_OLLAMA_URL
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raw = f"http://{raw}"
    return raw.rstrip("/")


def probe_ollama(
    model_name: str | None = None,
    base_url: str | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> dict[str, Any]:
    """Probe live Ollama service reachability and installed models list."""
    url = (base_url or get_ollama_base_url()).rstrip("/")
    tags_url = f"{url}/api/tags"

    try:
        req = urllib.request.Request(
            tags_url,
            headers={"User-Agent": "STRIX-AI-VAPT/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return {
                    "available": False,
                    "reachable": False,
                    "model_installed": False,
                    "status": "UNAVAILABLE",
                    "base_url": url,
                    "models": [],
                    "error": f"Ollama responded with HTTP {resp.status}",
                }
            raw = resp.read()
            data = json.loads(raw.decode("utf-8"))

        installed_models: list[str] = [
            m.get("name", "")
            for m in data.get("models", [])
            if isinstance(m, dict) and m.get("name")
        ]

        target = (model_name or "qwen2.5:1.5b").strip()
        model_found = any(
            target.lower() in m.lower() or m.lower().startswith(target.lower())
            for m in installed_models
        )

        return {
            "available": True,
            "reachable": True,
            "model_installed": model_found,
            "status": "READY",
            "base_url": url,
            "target_model": target,
            "models": installed_models,
            "message": f"Ollama reachable ({len(installed_models)} model(s) available)",
        }

    except Exception as exc:
        return {
            "available": False,
            "reachable": False,
            "model_installed": False,
            "status": "UNAVAILABLE",
            "base_url": url,
            "models": [],
            "error": str(exc),
            "message": "Local Ollama service unreachable at 127.0.0.1:11434",
        }
