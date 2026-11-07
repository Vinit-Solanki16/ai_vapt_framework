"""LiteLLM model-name resolution for local cost estimates."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, cast


_EXCLUDED_PREFIXES = ("github_copilot/", "microsoft_365_copilot/")


@lru_cache(maxsize=512)
def resolve_litellm_model(model: str) -> str | None:
    """Return a provider-qualified model name that LiteLLM can price."""
    try:
        import litellm

        normalized = model.strip()
        for prefix in ("litellm/", "any-llm/", "openai/"):
            if normalized.startswith(prefix):
                normalized = normalized.removeprefix(prefix)
                break
        if not normalized or normalized.startswith(_EXCLUDED_PREFIXES):
            return None

        model_cost = cast(
            "dict[str, dict[str, Any]]",
            getattr(litellm, "model_cost"),  # noqa: B009
        )
        bare_entry = model_cost.get(normalized)
        if "/" not in normalized and isinstance(bare_entry, dict):
            provider = bare_entry.get("litellm_provider")
            if isinstance(provider, str) and provider:
                if f"{provider}/".startswith(_EXCLUDED_PREFIXES):
                    return None
                return f"{provider}/{normalized}"
        if "/" in normalized and isinstance(bare_entry, dict):
            return normalized

        names = [normalized]
        if "/" in normalized:
            names.append(normalized.rsplit("/", 1)[-1])
        for name in names:
            matches = sorted(
                key
                for key in model_cost
                if key.endswith(f"/{name}") and not key.startswith(_EXCLUDED_PREFIXES)
            )
            if not matches:
                continue
            for prefix in ("xai/", "openai/", "anthropic/", "google/", "deepseek/", "mistral/"):
                candidate = f"{prefix}{name}"
                if candidate in matches:
                    return candidate
            prices = {
                (
                    model_cost[key].get("input_cost_per_token"),
                    model_cost[key].get("output_cost_per_token"),
                )
                for key in matches
                if isinstance(model_cost.get(key), dict)
            }
            if len(matches) == 1 or len(prices) == 1:
                return matches[0]
        return None  # noqa: TRY300
    except Exception:  # noqa: BLE001
        return None
