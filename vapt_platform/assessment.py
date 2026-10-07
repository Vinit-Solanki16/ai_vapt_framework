"""Pluggable assessment abstraction for the VAPT platform.

Provides a clean boundary between:
  - deterministic assessment (offline, reproducible)
  - AI/LLM assessment (Ollama or OpenAI)

Always tracks provenance so downstream consumers know exactly how a
candidate was graded.

Architecture:
    assessment_mode:
        deterministic -> deterministic_assessor
        ai            -> llm_assessor with deterministic fallback

The AI assessor NEVER directly controls execution. It only provides
a quality recommendation that the existing decision engine consumes.
"""
from __future__ import annotations

import logging
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
        provider: "ollama", "openai", or None
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
        return None


def _try_openai_assess(
    candidate: ActionCandidate, api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Optional[AssessmentResult]:
    """Attempt to assess a candidate using OpenAI."""
    model = resolve_model("openai", model_name)
    try:
        from core.exploit_assessor import assess_exploit_quality, get_llm

        try:
            llm = get_llm(provider="openai", model_name=model, api_key=api_key)
        except Exception as e:
            log.warning(f"OpenAI not available: {e}")
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
        provider: "ollama" or "openai" (used when mode="ai")
        api_key: OpenAI API key (optional)
        model_name: Explicit model override. When None, the authoritative
            provider default from ``vapt_platform.model_config`` is used
            (llama3.2:3b for ollama — the official thesis baseline).

    Returns:
        A callable with signature:
            (candidate: ActionCandidate) -> AssessmentResult
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

    def _ai_assess(candidate: ActionCandidate) -> AssessmentResult:
        # Try the configured provider
        if provider == "openai":
            result = _try_openai_assess(
                candidate, api_key=api_key, model_name=resolved_model,
            )
        else:
            result = _try_ollama_assess(candidate, model_name=resolved_model)

        if result is not None:
            return result

        # Fallback to deterministic
        log.warning(
            f"AI assessment unavailable for {candidate.id}; "
            f"falling back to deterministic"
        )
        rank = deterministic_assessor(candidate)
        return AssessmentResult(
            quality_rank=rank,
            source="deterministic",
            provider=provider,
            model=resolved_model,
            fallback=True,
            error=f"{provider} unavailable; deterministic fallback used",
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
