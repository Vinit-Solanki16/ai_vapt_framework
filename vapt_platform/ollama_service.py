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
DEFAULT_REQUEST_TIMEOUT_S = 60.0
DEFAULT_NUM_CTX = 4096


def get_ollama_base_url() -> str:
    """Resolve the Ollama base URL from environment or default.

    Supports OLLAMA_BASE_URL and OLLAMA_HOST. Normalizes naked
    host:port strings by prepending http:// and strips trailing slashes.
    """
    raw = (os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or "").strip()
    if not raw:
        return DEFAULT_OLLAMA_URL
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raw = f"http://{raw}"
    return raw.rstrip("/")


def get_ollama_request_timeout() -> float:
    """Resolve request/inference timeout in seconds from environment or default."""
    raw = (os.getenv("OLLAMA_TIMEOUT_S") or os.getenv("OLLAMA_REQUEST_TIMEOUT_S") or "").strip()
    try:
        val = float(raw)
        return val if val > 0 else DEFAULT_REQUEST_TIMEOUT_S
    except (ValueError, TypeError):
        return DEFAULT_REQUEST_TIMEOUT_S


def get_ollama_num_ctx() -> int:
    """Resolve context window size (num_ctx) from environment or default."""
    raw = (os.getenv("OLLAMA_NUM_CTX") or "").strip()
    try:
        val = int(raw)
        return val if val > 0 else DEFAULT_NUM_CTX
    except (ValueError, TypeError):
        return DEFAULT_NUM_CTX


def get_ollama_num_predict() -> Optional[int]:
    """Resolve maximum completion tokens (num_predict) from environment or None."""
    raw = (os.getenv("OLLAMA_NUM_PREDICT") or "").strip()
    try:
        val = int(raw)
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None


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


def ollama_status(model_name: Optional[str] = None) -> dict[str, Any]:
    """Status report for the configured or baseline model."""
    from vapt_platform.model_config import default_ollama_model_from_env

    target = model_name or default_ollama_model_from_env()
    return probe_ollama(target)


def _clean_json_text(text: str) -> str:
    """Extract clean JSON text from model output, stripping markdown codeblocks."""
    s = (text or "").strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def query_ollama_structured(
    prompt: str,
    schema_cls: type,
    system_prompt: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    num_ctx: Optional[int] = None,
    num_predict: Optional[int] = None,
) -> tuple[Optional[Any], bool, Optional[str]]:
    """Query Ollama HTTP API with structured JSON output and schema validation.

    Args:
        prompt: User prompt content.
        schema_cls: Pydantic model class to validate the structured output against.
        system_prompt: Optional system instruction prompt.
        model_name: Target model name (defaults to resolved default model).
        base_url: Ollama base URL override.
        timeout: Socket/request timeout in seconds.
        num_ctx: Context token window size.
        num_predict: Max output tokens.

    Returns:
        tuple of (parsed_result_or_None, llm_response_received_bool, error_message_or_None)
    """
    from vapt_platform.model_config import default_ollama_model_from_env

    target = (model_name or default_ollama_model_from_env()).strip()
    url = (base_url or get_ollama_base_url()).rstrip("/")
    chat_url = f"{url}/api/chat"
    req_timeout = timeout if timeout is not None else get_ollama_request_timeout()
    ctx = num_ctx if num_ctx is not None else get_ollama_num_ctx()
    predict = num_predict if num_predict is not None else get_ollama_num_predict()

    options: dict[str, Any] = {
        "temperature": 0.1,
        "num_ctx": ctx,
    }
    if predict is not None:
        options["num_predict"] = predict

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    body_dict = {
        "model": target,
        "messages": messages,
        "format": "json",
        "stream": False,
        "options": options,
    }

    req_data = json.dumps(body_dict).encode("utf-8")
    req = urllib.request.Request(
        chat_url,
        data=req_data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "AI-VAPT-Framework/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=req_timeout) as resp:
            status_code = resp.status
            raw_body = resp.read()
    except urllib.error.HTTPError as e:
        err_msg = f"Ollama at {url} returned HTTP {e.code}: {e.reason}"
        log.warning(err_msg)
        return None, False, err_msg
    except urllib.error.URLError as e:
        err_msg = f"Ollama connection failed at {chat_url}: {e.reason}"
        log.warning(err_msg)
        return None, False, err_msg
    except TimeoutError:
        err_msg = f"Ollama request timed out after {req_timeout}s at {chat_url}"
        log.warning(err_msg)
        return None, False, err_msg
    except Exception as e:
        err_msg = f"Ollama query failed unexpectedly: {e}"
        log.warning(err_msg)
        return None, False, err_msg

    if status_code != 200:
        return None, False, f"Ollama returned HTTP status {status_code}"

    # An HTTP 200 response arrived from the LLM endpoint
    llm_response_received = True

    try:
        data = json.loads(raw_body.decode("utf-8"))
        raw_content = data.get("message", {}).get("content", "")
        if not raw_content:
            raw_content = data.get("response", "")
    except Exception as e:
        return None, llm_response_received, f"Invalid JSON envelope from Ollama: {e}"

    if not raw_content:
        return None, llm_response_received, f"Ollama returned empty response content for model '{target}'"

    clean_content = _clean_json_text(raw_content)

    try:
        # Schema validation
        if hasattr(schema_cls, "model_validate_json"):
            parsed = schema_cls.model_validate_json(clean_content)
        else:
            json_dict = json.loads(clean_content)
            parsed = schema_cls(**json_dict)
        return parsed, llm_response_received, None
    except Exception as e:
        val_err = f"Malformed structured output from '{target}': {e}"
        log.warning(val_err)
        return None, llm_response_received, val_err
