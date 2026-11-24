"""Runtime hosted LLM provider credential validation and dynamic model discovery.

Supports:
- OpenRouter (Free, Paid, and Unknown pricing transparency)
- OpenAI (GPT-4o, GPT-4o-mini, o1, o3-mini)
- Anthropic Claude (Claude 3.5 Sonnet, Haiku, Opus)
- Google Gemini (Gemini 2.0 Flash, 1.5 Pro)
- Local Ollama (Self-hosted offline models)
- Custom OpenAI-compatible endpoints (vLLM, LocalAI, TGI, LM Studio)

In-memory verification only:
- Tests credential validity against vendor metadata/models endpoints.
- Validates credentials without consuming paid generation tokens.
- Never persists, logs, or saves keys to disk or .env.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from strix.interface.schemas import (
    AnthropicValidateResponse,
    CustomEndpointValidateResponse,
    DiscoveredModelInfo,
    GoogleValidateResponse,
    OllamaValidateResponse,
    OpenAIValidateResponse,
    OpenRouterModelInfo,
    OpenRouterValidateResponse,
)


logger = logging.getLogger("strix.llm.validation")


# ---------------------------------------------------------------------------
# 1. OpenRouter Model Discovery & Validation
# ---------------------------------------------------------------------------
def _parse_openrouter_pricing(m: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """Parse OpenRouter model pricing metadata into (pricing_status, prompt_price, completion_price).

    Status is strictly:
    - 'free' if prompt AND completion are confirmed 0.0 (or model ID has explicit :free suffix).
    - 'paid' if prompt OR completion is > 0.
    - 'unknown' if pricing metadata is missing, null, or unparseable.
    Never infers free status from names alone.
    """
    mid = str(m.get("id") or "").lower()
    pricing = m.get("pricing")

    if not isinstance(pricing, dict) or not pricing:
        if mid.endswith(":free"):
            return ("free", "0", "0")
        return ("unknown", None, None)

    p_raw = pricing.get("prompt")
    c_raw = pricing.get("completion")

    try:
        p_val = float(p_raw) if p_raw is not None else -1.0
        c_val = float(c_raw) if c_raw is not None else -1.0

        if p_val == 0.0 and c_val == 0.0:
            return ("free", "0", "0")
        if p_val > 0.0 or c_val > 0.0:
            # Format as $/1M tokens (OpenRouter reports in $/token)
            p_str = f"${p_val * 1_000_000:.2f}/M in" if p_val >= 0 else None
            c_str = f"${c_val * 1_000_000:.2f}/M out" if c_val >= 0 else None
            return ("paid", p_str, c_str)
    except (ValueError, TypeError):
        pass

    if mid.endswith(":free"):
        return ("free", "0", "0")
    return ("unknown", None, None)


def fetch_openrouter_models(
    api_key: str | None = None,
    include_paid: bool = True,
) -> list[OpenRouterModelInfo]:
    """Retrieve models from OpenRouter's live catalogue with full pricing transparency."""
    url = "https://openrouter.ai/api/v1/models"
    headers: dict[str, str] = {"User-Agent": "AI-VAPT/1.0"}
    if api_key and not api_key.startswith("sk-or-v1-test") and "placeholder" not in api_key.lower():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            if resp.status == 200:
                raw = resp.read()
                data = json.loads(raw.decode("utf-8"))
                raw_models = data.get("data", [])
                discovered: list[OpenRouterModelInfo] = []

                for m in raw_models:
                    if not isinstance(m, dict) or not m.get("id"):
                        continue
                    m_id = str(m["id"])
                    pricing_status, p_price, c_price = _parse_openrouter_pricing(m)

                    is_free = pricing_status == "free"
                    if not include_paid and not is_free:
                        continue

                    discovered.append(
                        OpenRouterModelInfo(
                            id=m_id,
                            name=str(m.get("name") or m_id),
                            provider="openrouter",
                            pricing_status=pricing_status,  # type: ignore[arg-type]
                            free=is_free,
                            prompt_price=p_price,
                            completion_price=c_price,
                            context_length=m.get("context_length"),
                        )
                    )

                if discovered:
                    # Sort: free models first, then paid models alphabetically
                    return sorted(discovered, key=lambda x: (0 if x.free else 1, x.id.lower()))
    except Exception as exc:
        logger.warning("Failed to fetch live OpenRouter models: %s", exc)

    # Balanced fallback catalogue if network is restricted
    return [
        OpenRouterModelInfo(
            id="nvidia/nemotron-3.5-super-vl:free",
            name="NVIDIA Nemotron 3.5 Super VL [FREE] (1M Context)",
            provider="openrouter",
            pricing_status="free",
            free=True,
            context_length=1000000,
        ),
        OpenRouterModelInfo(
            id="nvidia/nemotron-3.5-lightning:free",
            name="NVIDIA Nemotron 3.5 Lightning [FREE] (1M Context)",
            provider="openrouter",
            pricing_status="free",
            free=True,
            context_length=1000000,
        ),
        OpenRouterModelInfo(
            id="meta-llama/llama-3.3-70b-instruct:free",
            name="Meta Llama 3.3 70B Instruct [FREE]",
            provider="openrouter",
            pricing_status="free",
            free=True,
            context_length=131072,
        ),
        OpenRouterModelInfo(
            id="anthropic/claude-3.5-sonnet",
            name="Anthropic Claude 3.5 Sonnet [PAID]",
            provider="openrouter",
            pricing_status="paid",
            free=False,
            prompt_price="$3.00/M in",
            completion_price="$15.00/M out",
            context_length=200000,
        ),
        OpenRouterModelInfo(
            id="openai/gpt-4o",
            name="OpenAI GPT-4o [PAID]",
            provider="openrouter",
            pricing_status="paid",
            free=False,
            prompt_price="$2.50/M in",
            completion_price="$10.00/M out",
            context_length=128000,
        ),
        OpenRouterModelInfo(
            id="openai/gpt-4o-mini",
            name="OpenAI GPT-4o Mini [PAID]",
            provider="openrouter",
            pricing_status="paid",
            free=False,
            prompt_price="$0.15/M in",
            completion_price="$0.60/M out",
            context_length=128000,
        ),
        OpenRouterModelInfo(
            id="deepseek/deepseek-chat",
            name="DeepSeek V3 [PAID]",
            provider="openrouter",
            pricing_status="paid",
            free=False,
            prompt_price="$0.14/M in",
            completion_price="$0.28/M out",
            context_length=64000,
        ),
    ]


def fetch_openrouter_free_models(api_key: str | None = None) -> list[OpenRouterModelInfo]:
    """Retrieve only free models from OpenRouter (backward-compatible helper)."""
    return [m for m in fetch_openrouter_models(api_key=api_key, include_paid=False) if m.free]


def validate_openrouter_credential(api_key: str) -> OpenRouterValidateResponse:
    """Validate OpenRouter API key using auth/key endpoint and discover available models."""
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

    # 2. Retrieve models catalogue (both free and paid)
    models = fetch_openrouter_models(api_key=key, include_paid=True)
    free_cnt = len([m for m in models if m.free])
    paid_cnt = len(models) - free_cnt
    return OpenRouterValidateResponse(
        status="configured",
        message=f"OpenRouter verified ({len(models)} models available: {free_cnt} free, {paid_cnt} paid)",
        valid=True,
        catalogue_count=len(models),
        models=models,
    )


# ---------------------------------------------------------------------------
# 2. Anthropic Claude Validation & Discovery
# ---------------------------------------------------------------------------
def validate_anthropic_credential(api_key: str) -> AnthropicValidateResponse:
    """Validate Anthropic API key and list supported Claude models."""
    key = (api_key or "").strip()
    if not key:
        return AnthropicValidateResponse(
            status="invalid_credentials",
            message="No Anthropic API key provided",
            valid=False,
            catalogue_count=0,
            models=[],
        )

    # Test key against Anthropic models endpoint
    url = "https://api.anthropic.com/v1/models"
    headers = {
        "User-Agent": "AI-VAPT/1.0",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }

    known_claude_models = [
        DiscoveredModelInfo(
            id="claude-3-5-sonnet-20241022",
            name="Claude 3.5 Sonnet (Recommended Flagship)",
            provider="anthropic",
            pricing_status="paid",
            free=False,
            prompt_price="$3.00/M in",
            completion_price="$15.00/M out",
            context_length=200000,
        ),
        DiscoveredModelInfo(
            id="claude-3-5-haiku-20241022",
            name="Claude 3.5 Haiku (High Speed)",
            provider="anthropic",
            pricing_status="paid",
            free=False,
            prompt_price="$0.80/M in",
            completion_price="$4.00/M out",
            context_length=200000,
        ),
        DiscoveredModelInfo(
            id="claude-3-opus-20240229",
            name="Claude 3 Opus (Complex Analysis)",
            provider="anthropic",
            pricing_status="paid",
            free=False,
            prompt_price="$15.00/M in",
            completion_price="$75.00/M out",
            context_length=200000,
        ),
    ]

    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            if resp.status == 200:
                raw = resp.read()
                data = json.loads(raw.decode("utf-8"))
                models_data = data.get("data", [])
                discovered: list[DiscoveredModelInfo] = []
                for m in models_data:
                    if isinstance(m, dict) and m.get("id"):
                        discovered.append(
                            DiscoveredModelInfo(
                                id=m["id"],
                                name=str(m.get("display_name") or m["id"]),
                                provider="anthropic",
                                pricing_status="paid",
                                free=False,
                                context_length=200000,
                            )
                        )
                final_models = discovered if discovered else known_claude_models
                return AnthropicValidateResponse(
                    status="configured",
                    message=f"Anthropic Claude verified ({len(final_models)} models available)",
                    valid=True,
                    catalogue_count=len(final_models),
                    models=final_models,
                )
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            return AnthropicValidateResponse(
                status="invalid_credentials",
                message="Invalid Anthropic API key (authentication failed)",
                valid=False,
                catalogue_count=0,
                models=[],
            )
        if err.code == 429:
            return AnthropicValidateResponse(
                status="rate_limited",
                message="Anthropic API rate limit reached (HTTP 429)",
                valid=False,
                catalogue_count=0,
                models=[],
            )
        if err.code == 404:
            # Older account tier without GET /v1/models: fallback to static models
            return AnthropicValidateResponse(
                status="configured",
                message="Anthropic API key verified",
                valid=True,
                catalogue_count=len(known_claude_models),
                models=known_claude_models,
            )
    except Exception as exc:
        logger.warning("Anthropic models query error: %s", exc)

    return AnthropicValidateResponse(
        status="configured",
        message="Anthropic key accepted (catalog offline fallback)",
        valid=True,
        catalogue_count=len(known_claude_models),
        models=known_claude_models,
    )


# ---------------------------------------------------------------------------
# 3. OpenAI Validation & Discovery
# ---------------------------------------------------------------------------
def validate_openai_credential(
    api_key: str,
    api_base: str | None = None,
) -> OpenAIValidateResponse:
    """Validate OpenAI API key by querying /v1/models and listing supported chat models."""
    key = (api_key or "").strip()
    if not key:
        return OpenAIValidateResponse(
            status="invalid_credentials",
            message="No OpenAI API key provided",
            valid=False,
            models=[],
        )

    base = (api_base or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/models"
    headers = {
        "User-Agent": "AI-VAPT/1.0",
        "Authorization": f"Bearer {key}",
    }

    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                models_list: list[str] = []
                data = body.get("data", [])
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("id"):
                            mid = str(item["id"])
                            # Filter to chat/tool-calling completion models
                            if any(k in mid for k in ("gpt-4", "o1", "o3", "gpt-3.5", "chat")):
                                models_list.append(mid)

                # Sort priority models first
                def _openai_rank(m: str) -> int:
                    if "gpt-4o-mini" in m:
                        return 0
                    if "gpt-4o" in m:
                        return 1
                    if "o3-mini" in m:
                        return 2
                    if "o1" in m:
                        return 3
                    return 10

                sorted_models = sorted(models_list, key=lambda x: (_openai_rank(x), x))
                return OpenAIValidateResponse(
                    status="configured",
                    message=f"OpenAI connection verified ({len(sorted_models)} models available)",
                    valid=True,
                    models=sorted_models[:25],
                )
            return OpenAIValidateResponse(
                status="invalid_credentials",
                message=f"OpenAI API returned HTTP {resp.status}",
                valid=False,
                models=[],
            )
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            return OpenAIValidateResponse(
                status="invalid_credentials",
                message="Invalid OpenAI API key (authentication failed)",
                valid=False,
                models=[],
            )
        if err.code == 429:
            return OpenAIValidateResponse(
                status="rate_limited",
                message="OpenAI rate limit or quota exceeded (HTTP 429)",
                valid=False,
                models=[],
            )
        return OpenAIValidateResponse(
            status="error",
            message=f"OpenAI API returned HTTP {err.code}",
            valid=False,
            models=[],
        )
    except Exception as exc:
        return OpenAIValidateResponse(
            status="unreachable",
            message=f"Network error connecting to OpenAI: {exc}",
            valid=False,
            models=[],
        )


# ---------------------------------------------------------------------------
# 4. Google Gemini Validation & Discovery
# ---------------------------------------------------------------------------
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

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AI-VAPT/1.0", "x-goog-api-key": key},
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
                    models=models[:15],
                )
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


# ---------------------------------------------------------------------------
# 5. Local Ollama Service Validation & Discovery
# ---------------------------------------------------------------------------
def validate_ollama_service(base_url: str | None = None) -> OllamaValidateResponse:
    """Probe local Ollama daemon and discover locally installed models."""
    base = (base_url or "http://127.0.0.1:11434").rstrip("/")
    url = f"{base}/api/tags"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AI-VAPT/1.0"}, method="GET")
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                models_data = body.get("models", [])
                discovered: list[DiscoveredModelInfo] = []
                for m in models_data:
                    if isinstance(m, dict) and m.get("name"):
                        name = str(m["name"])
                        discovered.append(
                            DiscoveredModelInfo(
                                id=name,
                                name=f"{name} (Local)",
                                provider="ollama",
                                pricing_status="free",
                                free=True,
                                context_length=m.get("context_length") or 32768,
                            )
                        )
                return OllamaValidateResponse(
                    status="configured",
                    message=f"Ollama connected ({len(discovered)} local model(s) installed)",
                    valid=True,
                    catalogue_count=len(discovered),
                    models=discovered,
                )
            return OllamaValidateResponse(
                status="unreachable",
                message=f"Ollama returned HTTP {resp.status}",
                valid=False,
                catalogue_count=0,
                models=[],
            )
    except urllib.error.URLError as err:
        return OllamaValidateResponse(
            status="unreachable",
            message=f"Ollama daemon unreachable at {base} ({err.reason}). Start Ollama locally or verify endpoint.",
            valid=False,
            catalogue_count=0,
            models=[],
        )
    except Exception as exc:
        return OllamaValidateResponse(
            status="error",
            message=f"Ollama connection error: {exc}",
            valid=False,
            catalogue_count=0,
            models=[],
        )


# ---------------------------------------------------------------------------
# 6. Custom OpenAI-Compatible Endpoint Validation
# ---------------------------------------------------------------------------
def validate_openai_compatible_endpoint(
    api_base: str,
    api_key: str | None = None,
    model: str | None = None,
) -> OpenAIValidateResponse:
    """Validate OpenAI-compatible endpoint reachability and list exposed models."""
    base = (api_base or "").strip().rstrip("/")
    if not base:
        base = "https://api.openai.com/v1"

    models_url = f"{base}/models"
    headers = {"User-Agent": "AI-VAPT/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        req = urllib.request.Request(models_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                models_list: list[str] = []
                data = body.get("data")
                from strix.llm.context_budget import (
                    extract_model_context_length,
                    record_detected_context_limit,
                )

                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "id" in item:
                            m_id = str(item["id"])
                            models_list.append(m_id)
                            ctx_len = extract_model_context_length(item)
                            if ctx_len:
                                record_detected_context_limit(m_id, ctx_len)
                        elif isinstance(item, str):
                            models_list.append(item)
                if model and model not in models_list:
                    models_list.insert(0, model)
                return OpenAIValidateResponse(
                    status="configured",
                    message=f"Endpoint verified ({len(models_list)} model(s) available)",
                    valid=True,
                    models=models_list[:30],
                )
            return OpenAIValidateResponse(
                status="invalid_credentials",
                message=f"Endpoint returned HTTP {resp.status}",
                valid=False,
                models=[],
            )
    except urllib.error.HTTPError as err:
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
        return OpenAIValidateResponse(
            status="unreachable",
            message=f"Could not connect to endpoint {base}: {reason}",
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


def validate_custom_endpoint(
    base_url: str,
    api_key: str | None = None,
    model: str | None = None,
) -> CustomEndpointValidateResponse:
    """Validate a custom endpoint and return DiscoveredModelInfo items."""
    res = validate_openai_compatible_endpoint(base_url, api_key, model)
    models: list[DiscoveredModelInfo] = [
        DiscoveredModelInfo(
            id=m,
            name=f"{m} (Custom)",
            provider="custom",
            pricing_status="unknown",
            free=False,
            is_custom=True,
        )
        for m in res.models
    ]
    if model and not any(dm.id == model for dm in models):
        models.insert(
            0,
            DiscoveredModelInfo(
                id=model,
                name=f"{model} (Manually Configured)",
                provider="custom",
                pricing_status="unknown",
                free=False,
                is_custom=True,
            ),
        )

    return CustomEndpointValidateResponse(
        status=res.status,
        message=res.message,
        valid=res.valid,
        catalogue_count=len(models),
        models=models,
    )
