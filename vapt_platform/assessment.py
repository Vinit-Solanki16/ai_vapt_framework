"""Pluggable assessment abstraction for the VAPT platform.

Provides a clean boundary between:
  - deterministic assessment (offline, reproducible)
  - AI/LLM assessment (local Ollama, or the optional hosted OpenRouter /
    OpenAI providers)

Always tracks provenance so downstream consumers know exactly how a
candidate was graded.

Architecture:
    assessment_mode:
        deterministic -> deterministic_assessor
        ai            -> llm assessor for the SELECTED provider, with an
                         explicitly reported deterministic fallback

Provider selection is explicit and never silent: choosing a hosted provider
without its API key raises immediately, a runtime failure falls back to the
deterministic assessor while keeping the selected provider in the provenance
(never switched), and the classified cause is carried on ``AssessmentResult.error``.

The AI assessor NEVER directly controls execution. It only provides
a quality recommendation that the existing decision engine consumes.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from decision_engine.core.assessor import deterministic_assessor
from decision_engine.core.schemas import ActionCandidate, QualityRank
from vapt_platform.model_config import resolve_model

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Assessment Result
# ---------------------------------------------------------------------------

@dataclass
class AssessmentResult:
    """Provenance-aware assessment result.

    Fields:
        quality_rank: The assessed quality (HIGH/MEDIUM/LOW)
        source: "deterministic" or "llm"
        provider: "ollama", "openrouter", "openai", or None
        model: Actual model name (e.g., "llama3.2:3b") or None
        fallback: True if AI was requested but deterministic was used
        reasoning: Optional reasoning text from LLM
        error: Optional error message if fallback occurred
    """
    quality_rank: QualityRank = QualityRank.LOW
    source: str = "deterministic"
    provider: Optional[str] = None
    model: Optional[str] = None
    fallback: bool = False
    reasoning: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality_rank": self.quality_rank.value,
            "source": self.source,
            "provider": self.provider,
            "model": self.model,
            "fallback": self.fallback,
            "reasoning": self.reasoning,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# LLM Assessor
# ---------------------------------------------------------------------------

def _try_ollama_assess(
    candidate: ActionCandidate, model_name: Optional[str] = None,
    errors: Optional[list] = None,
) -> Optional[AssessmentResult]:
    """Attempt to assess a candidate using Ollama."""
    model = resolve_model("ollama", model_name)
    try:
        from core.exploit_assessor import assess_exploit_quality, get_llm

        # Check if Ollama is reachable first
        try:
            llm = get_llm(provider="ollama", model_name=model)
        except Exception as e:
            log.warning(f"Ollama not available: {e}")
            if errors is not None:
                errors.append(_describe("ollama", e))
            return None

        a = assess_exploit_quality(candidate.id, provider="ollama", model_name=model)
        return AssessmentResult(
            quality_rank=QualityRank(a.usability_rank.value),
            source="llm",
            provider="ollama",
            model=model,
            fallback=False,
            reasoning=a.reasoning,
        )
    except Exception as e:
        log.warning(f"Ollama assessment failed for {candidate.id}: {e}")
        if errors is not None:
            errors.append(_describe("ollama", e))
        return None


def _try_openai_assess(
    candidate: ActionCandidate, api_key: Optional[str] = None,
    model_name: Optional[str] = None, errors: Optional[list] = None,
) -> Optional[AssessmentResult]:
    """Attempt to assess a candidate using OpenAI."""
    model = resolve_model("openai", model_name)
    try:
        from core.exploit_assessor import assess_exploit_quality, get_llm

        try:
            llm = get_llm(provider="openai", model_name=model, api_key=api_key)
        except Exception as e:
            log.warning(f"OpenAI not available: {e}")
            if errors is not None:
                errors.append(_describe("openai", e))
            return None

        a = assess_exploit_quality(
            candidate.id, provider="openai", model_name=model, api_key=api_key,
        )
        return AssessmentResult(
            quality_rank=QualityRank(a.usability_rank.value),
            source="llm",
            provider="openai",
            model=model,
            fallback=False,
            reasoning=a.reasoning,
        )
    except Exception as e:
        log.warning(f"OpenAI assessment failed for {candidate.id}: {e}")
        if errors is not None:
            errors.append(_describe("openai", e))
        return None


def _describe(provider: str, exc: BaseException) -> str:
    """Redacted, category-tagged one-liner for a provider failure."""
    from vapt_platform.provider_errors import describe_error

    return describe_error(exc, provider=provider)


def _try_openrouter_assess(
    candidate: ActionCandidate, api_key: Optional[str] = None,
    model_name: Optional[str] = None, errors: Optional[list] = None,
) -> Optional[AssessmentResult]:
    """Attempt to assess a candidate using the optional OpenRouter provider.

    Returns None on any provider failure so the caller can apply the
    *explicitly reported* deterministic fallback. The configured provider is
    never switched to another one — OpenRouter failures stay labelled as
    OpenRouter failures.
    """
    model = resolve_model("openrouter", model_name)
    try:
        from core.exploit_assessor import assess_exploit_quality, get_llm

        try:
            llm = get_llm(provider="openrouter", model_name=model, api_key=api_key)
        except Exception as e:
            # Missing key / missing optional package are configuration errors.
            log.warning(f"OpenRouter not available: {e}")
            if errors is not None:
                errors.append(_describe("openrouter", e))
            return None

        a = assess_exploit_quality(
            candidate.id, provider="openrouter", model_name=model,
            api_key=api_key,
        )
        return AssessmentResult(
            quality_rank=QualityRank(a.usability_rank.value),
            source="llm",
            provider="openrouter",
            model=model,
            fallback=False,
            reasoning=a.reasoning,
        )
    except Exception as e:
        log.warning(f"OpenRouter assessment failed for {candidate.id}: {e}")
        if errors is not None:
            errors.append(_describe("openrouter", e))
        return None


# ---------------------------------------------------------------------------
# Pluggable Assessor
# ---------------------------------------------------------------------------

def create_assessor(
    mode: str = "deterministic",
    provider: str = "ollama",
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
):
    """Create a pluggable assessor function.

    Args:
        mode: "deterministic" or "ai"
        provider: "ollama", "openrouter" or "openai" (used when mode="ai")
        api_key: Hosted-provider API key (optional; ollama needs none)
        model_name: Explicit model override. When None, the authoritative
            provider default from ``vapt_platform.model_config`` is used
            (llama3.2:3b for ollama — the official thesis baseline).

    Returns:
        A callable with signature:
            (candidate: ActionCandidate) -> AssessmentResult

    Raises:
        RuntimeError: when OpenRouter is EXPLICITLY selected and
            ``OPENROUTER_API_KEY`` is absent. This is a configuration error,
            so it fails fast rather than silently degrading.

    Provider-specific missing-key semantics (INTENTIONAL difference):

        * ``openrouter`` — raises at construction time. The user made an
          explicit opt-in choice, so a missing credential must be an
          actionable error, never a concealed deterministic fallback.
        * ``openai``     — LEGACY behavior, deliberately preserved: a missing
          key does NOT raise here. ``get_llm`` raises when the client is
          built, ``_try_openai_assess`` catches it, and the result is an
          explicitly-tagged deterministic fallback (``fallback=True``).
          Changing this would silently alter pre-existing OpenAI semantics.
        * ``ollama``     — local, no key involved.
    """
    if mode == "deterministic":
        def _deterministic(candidate: ActionCandidate) -> AssessmentResult:
            rank = deterministic_assessor(candidate)
            return AssessmentResult(
                quality_rank=rank,
                source="deterministic",
            )
        return _deterministic

    # mode == "ai"
    resolved_model = resolve_model(provider, model_name)

    # OpenRouter only: fail fast on a misconfigured OPT-IN provider. This is
    # deliberately NOT applied to "openai", whose legacy fallback semantics
    # are preserved unchanged (see the docstring above).
    if (provider or "").strip().lower() == "openrouter":
        from vapt_platform.model_config import api_key_env_for

        key_env = api_key_env_for(provider) or "OPENROUTER_API_KEY"
        if not (api_key or os.getenv(key_env)):
            raise RuntimeError(
                f"OpenRouter provider selected but {key_env} is not set. "
                f"Export {key_env} or pass api_key=..., or use "
                "provider='ollama' for the offline/local path. No fallback to "
                "another provider is performed."
            )

    def _ai_assess(candidate: ActionCandidate) -> AssessmentResult:
        # Try ONLY the configured provider. A failure never dispatches to a
        # different one — the provenance below always names the provider the
        # user actually selected.
        errors: list[str] = []
        if provider == "openrouter":
            result = _try_openrouter_assess(
                candidate, api_key=api_key, model_name=resolved_model,
                errors=errors,
            )
        elif provider == "openai":
            result = _try_openai_assess(
                candidate, api_key=api_key, model_name=resolved_model,
                errors=errors,
            )
        else:
            result = _try_ollama_assess(
                candidate, model_name=resolved_model, errors=errors,
            )

        if result is not None:
            return result

        # Explicit, visible deterministic fallback (never concealed): the
        # result is tagged fallback=True and names the classified cause.
        log.warning(
            f"AI assessment unavailable for {candidate.id}; "
            f"falling back to deterministic"
        )
        rank = deterministic_assessor(candidate)
        detail = "; ".join(errors[:1]) if errors else "unavailable"
        return AssessmentResult(
            quality_rank=rank,
            source="deterministic",
            provider=provider,
            model=resolved_model,
            fallback=True,
            error=f"{provider} unavailable; deterministic fallback used "
                  f"({detail})",
        )

    return _ai_assess


# ---------------------------------------------------------------------------
# Convenience: assess a list of candidates
# ---------------------------------------------------------------------------

def assess_candidates_with_provenance(
    candidates: list[ActionCandidate],
    mode: str = "deterministic",
    provider: str = "ollama",
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> list[AssessmentResult]:
    """Assess a list of candidates using the configured mode.

    Returns a list of AssessmentResult objects, one per candidate.
    """
    assessor = create_assessor(
        mode=mode, provider=provider, api_key=api_key, model_name=model_name,
    )
    return [assessor(c) for c in candidates]
