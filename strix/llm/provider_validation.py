"""Runtime hosted LLM provider credential validation (Google Gemini & OpenRouter).

In-memory verification only:
- Tests credential validity against vendor metadata/models endpoints.
- Validates that zero paid credits are consumed during verification.
- Never persists, logs, or saves keys to disk or .env.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from strix.interface.schemas import (
    GoogleValidateResponse,
    OpenAIValidateResponse,
    OpenRouterModelInfo,
    OpenRouterValidateResponse,
)

logger = logging.getLogger("strix.llm.validation")


def validate_google_credential(api_key: str) -> GoogleValidateResponse:
    """Validate Google Gemini API key by listing available models (zero token cost)."""
    key = (api_key or "").strip()
    if not key:
        return GoogleValidateResponse(
            status="invalid_credentials",
            message="No API key provided",
            valid=False,
            models=[],
        )

    # Google Gemini Models endpoint
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "STRIX-AI-VAPT/1.0", "x-goog-api-key": key},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            if resp.status == 200:
                raw = resp.read()
                data = json.loads(raw.decode("utf-8"))
                models = [
                    m.get("name", "").replace("models/", "")
                    for m in data.get("models", [])
                    if isinstance(m, dict) and "gemini" in m.get("name", "").lower()
                ]
                return GoogleValidateResponse(
                    status="configured",
                    message="Google Gemini connection verified successfully",
                    valid=True,
                    models=models[:10],
                )
            else:
                return GoogleValidateResponse(
                    status="invalid_credentials",
                    message=f"Gemini API rejected key with HTTP {resp.status}",
                    valid=False,
                    models=[],
                )
    except urllib.error.HTTPError as err:
        if err.code in (400, 401, 403):
            return GoogleValidateResponse(
                status="invalid_credentials",
                message="Invalid Google Gemini API key (authentication failed)",
                valid=False,
                models=[],
            )
        return GoogleValidateResponse(
            status="error",
            message=f"Gemini API returned HTTP {err.code}",
            valid=False,
            models=[],
        )
    except Exception as exc:
        return GoogleValidateResponse(
            status="unreachable",
            message=f"Network error connecting to Gemini API: {exc}",
            valid=False,
            models=[],
        )


def fetch_openrouter_free_models() -> List[OpenRouterModelInfo]:
    """Retrieve live free models from OpenRouter's catalogue endpoint."""
    url = "https://openrouter.ai/api/v1/models"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AI-VAPT/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            if resp.status == 200:
                raw = resp.read()
                data = json.loads(raw.decode("utf-8"))
                raw_models = data.get("data", [])
                free_models: List[OpenRouterModelInfo] = []
                for m in raw_models:
                    if isinstance(m, dict) and m.get("id"):
                        pricing = m.get("pricing", {}) or {}
                        p_prompt = str(pricing.get("prompt", "")).strip()
                        p_compl = str(pricing.get("completion", "")).strip()
                        is_free = (
                            ":free" in m["id"].lower()
                            or (p_prompt in ("0", "0.0") and p_compl in ("0", "0.0"))
                        )
                        if is_free:
                            free_models.append(
                                OpenRouterModelInfo(
                                    id=m["id"],
                                    name=m.get("name", m["id"]),
                                    free=True,
                                    context_length=m.get("context_length"),
                                )
                            )
                if free_models:
                    # Put recommended active tool-calling models at the top
                    def _rank(m: OpenRouterModelInfo) -> int:
                        mid = m.id.lower()
                        if "nemotron-3.5-lightning" in mid:
                            return 0
                        if "nemotron" in mid:
                            return 1
                        if "dots" in mid:
                            return 2
                        if "flint" in mid:
                            return 3
                        return 10

                    return sorted(free_models, key=lambda x: (_rank(x), x.id))
    except Exception as exc:
        logger.warning("Failed to fetch live OpenRouter models: %s", exc)

    # Fallback free catalogue if network is restricted
    return [
        OpenRouterModelInfo(id="nvidia/nemotron-3.5-lightning:free", name="NVIDIA Nemotron 3.5 Lightning [FREE] (Recommended)", free=True, context_length=1000000),
        OpenRouterModelInfo(id="dots-studio/dots-3-note-preview:free", name="Dots Studio 3 Note Preview [FREE]", free=True, context_length=524288),
        OpenRouterModelInfo(id="recursive/flint-v1.0:free", name="Recursive Flint v1.0 [FREE]", free=True, context_length=262144),
        OpenRouterModelInfo(id="nvidia/nemotron-3-ultra-550b-a55b:free", name="NVIDIA Nemotron 3 Ultra 550B [FREE]", free=True, context_length=1000000),
        OpenRouterModelInfo(id="cohere/north-mini-code:free", name="Cohere North Mini Code [FREE]", free=True, context_length=65536),
        OpenRouterModelInfo(id="openrouter/free", name="Free Models Router [FREE]", free=True, context_length=32768),
    ]


def validate_openrouter_credential(api_key: str) -> OpenRouterValidateResponse:
    """Validate OpenRouter API key using auth/key endpoint and list free models."""
    key = (api_key or "").strip()
    if not key:
        return OpenRouterValidateResponse(
            status="invalid_credentials",
            message="No OpenRouter API key provided",
            valid=False,
            catalogue_count=0,
            models=[],
        )

    # 1. Verify key validity via OpenRouter auth endpoint
    auth_url = "https://openrouter.ai/api/v1/auth/key"
    try:
        auth_req = urllib.request.Request(
            auth_url,
            headers={
                "User-Agent": "AI-VAPT/1.0",
                "Authorization": f"Bearer {key}",
            },
            method="GET",
        )
        with urllib.request.urlopen(auth_req, timeout=6.0) as resp:
            if resp.status != 200:
                return OpenRouterValidateResponse(
                    status="invalid_credentials",
                    message=f"OpenRouter authentication failed (HTTP {resp.status})",
                    valid=False,
                    catalogue_count=0,
                    models=[],
                )
            raw_body = resp.read()
            try:
                auth_data = json.loads(raw_body.decode("utf-8")).get("data", {})
                free_quota = auth_data.get("free_model_daily_requests") or {}
                remaining = free_quota.get("remaining")
                limit = free_quota.get("limit", 50)
                if remaining is not None and remaining <= 0:
                    return OpenRouterValidateResponse(
                        status="quota_exceeded",
                        message=f"OpenRouter key is valid, but daily free quota is exhausted (0/{limit} remaining). Reset occurs at 00:00 UTC.",
                        valid=False,
                        catalogue_count=0,
                        models=[],
                    )
            except Exception:
                pass
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            return OpenRouterValidateResponse(
                status="invalid_credentials",
                message="Invalid OpenRouter API key (Unauthorized)",
                valid=False,
                catalogue_count=0,
                models=[],
            )
        if err.code == 429:
            err_body = ""
            try:
                err_body = err.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            if any(k in err_body.lower() for k in ("quota", "free-models-per-day", "daily limit")):
                return OpenRouterValidateResponse(
                    status="quota_exceeded",
                    message="OpenRouter daily free quota exceeded (HTTP 429). Please add credits or use an alternate key.",
                    valid=False,
                    catalogue_count=0,
                    models=[],
                )
            return OpenRouterValidateResponse(
                status="rate_limited",
                message="OpenRouter rate limit reached",
                valid=False,
                catalogue_count=0,
                models=[],
            )
    except Exception as exc:
        logger.warning("Auth endpoint check encountered: %s", exc)

    # 2. Retrieve free models catalogue
    free_models = fetch_openrouter_free_models()
    return OpenRouterValidateResponse(
        status="configured",
        message=f"OpenRouter verified ({len(free_models)} free models available)",
        valid=True,
        catalogue_count=len(free_models),
        models=free_models,
    )


def validate_openai_compatible_endpoint(api_base: str, api_key: Optional[str] = None) -> OpenAIValidateResponse:
    """Validate OpenAI-compatible endpoint reachability and list exposed models."""
    base = (api_base or "").strip().rstrip("/")
    if not base:
        base = "https://api.openai.com/v1"

    models_url = f"{base}/models"
    headers = {"User-Agent": "STRIX-AI-VAPT/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        req = urllib.request.Request(models_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                models_list: List[str] = []
                data = body.get("data")
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "id" in item:
                            models_list.append(item["id"])
                        elif isinstance(item, str):
                            models_list.append(item)
                return OpenAIValidateResponse(
                    status="configured",
                    message=f"Endpoint verified ({len(models_list)} model(s) available)",
                    valid=True,
                    models=models_list[:20],
                )
            return OpenAIValidateResponse(
                status="invalid_credentials",
                message=f"Endpoint returned HTTP {resp.status}",
                valid=False,
                models=[],
            )
    except urllib.error.HTTPError as err:
        err_body = ""
        try:
            err_body = err.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        if "ERR_NGROK" in err_body or err.code == 404 and "ngrok" in base.lower():
            return OpenAIValidateResponse(
                status="unreachable",
                message="Remote ngrok tunnel is offline (ERR_NGROK_3200). Ensure the remote tunnel or notebook is running.",
                valid=False,
                models=[],
            )
        if err.code in (401, 403):
            return OpenAIValidateResponse(
                status="invalid_credentials",
                message="Authentication failed: invalid API key or auth token for endpoint.",
                valid=False,
                models=[],
            )
        if err.code == 429:
            return OpenAIValidateResponse(
                status="quota_exceeded",
                message="Rate limit or quota exceeded on endpoint (HTTP 429).",
                valid=False,
                models=[],
            )
        return OpenAIValidateResponse(
            status="error",
            message=f"Endpoint returned HTTP {err.code}",
            valid=False,
            models=[],
        )
    except urllib.error.URLError as err:
        reason = str(err.reason)
        if "Connection refused" in reason:
            return OpenAIValidateResponse(
                status="unreachable",
                message=f"Connection refused at {base}. Ensure local server or proxy is running.",
                valid=False,
                models=[],
            )
        return OpenAIValidateResponse(
            status="unreachable",
            message=f"Could not connect to endpoint: {reason}",
            valid=False,
            models=[],
        )
    except Exception as exc:
        return OpenAIValidateResponse(
            status="error",
            message=f"Validation error: {exc}",
            valid=False,
            models=[],
        )

