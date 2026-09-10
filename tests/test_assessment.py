"""Tests for the pluggable AI assessment bridge."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from decision_engine.core.schemas import ActionCandidate, Outcome, QualityRank
from vapt_platform.assessment import (
    AssessmentResult,
    assess_candidates_with_provenance,
    create_assessor,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_candidate():
    return ActionCandidate(
        id="CVE-2021-44228",
        probability=0.95,
        ground_truth=Outcome.SUCCESS,
    )


@pytest.fixture
def sample_candidates():
    return [
        ActionCandidate(id="CVE-2021-44228", probability=0.95, ground_truth=Outcome.SUCCESS),
        ActionCandidate(id="CVE-2023-38408", probability=0.8, ground_truth=Outcome.FAIL_TIMEOUT),
        ActionCandidate(id="CVE-XXXX-0000", probability=0.3),
    ]


# ---------------------------------------------------------------------------
# Deterministic assessor tests
# ---------------------------------------------------------------------------

class TestDeterministicAssessor:
    def test_create_deterministic(self, sample_candidate):
        assessor = create_assessor(mode="deterministic")
        result = assessor(sample_candidate)
        assert isinstance(result, AssessmentResult)
        assert result.source == "deterministic"
        assert result.fallback is False

    def test_deterministic_high_for_success(self, sample_candidate):
        assessor = create_assessor(mode="deterministic")
        result = assessor(sample_candidate)
        assert result.quality_rank == QualityRank.HIGH

    def test_deterministic_low_for_no_label(self):
        c = ActionCandidate(id="CVE-XXXX-0000", probability=0.3)
        assessor = create_assessor(mode="deterministic")
        result = assessor(c)
        assert result.quality_rank == QualityRank.LOW

    def test_deterministic_medium_for_high_prob(self):
        c = ActionCandidate(id="CVE-XXXX-0000", probability=0.95)
        assessor = create_assessor(mode="deterministic")
        result = assessor(c)
        assert result.quality_rank == QualityRank.MEDIUM


# ---------------------------------------------------------------------------
# AI assessor with mocked provider
# ---------------------------------------------------------------------------

class TestAIAssessorMocked:
    def test_ai_assessor_with_mocked_ollama(self, sample_candidate):
        mock_assessment = MagicMock()
        mock_assessment.usability_rank.value = "HIGH"
        mock_assessment.reasoning = "Test reasoning"

        with patch("vapt_platform.assessment._try_ollama_assess", return_value=AssessmentResult(
            quality_rank=QualityRank.HIGH,
            source="llm",
            provider="ollama",
            model="llama3.2:3b",
            fallback=False,
            reasoning="Test reasoning",
        )):
            assessor = create_assessor(mode="ai", provider="ollama")
            result = assessor(sample_candidate)

        assert result.source == "llm"
        assert result.provider == "ollama"
        assert result.model == "llama3.2:3b"
        assert result.fallback is False
        assert result.quality_rank == QualityRank.HIGH

    def test_ai_assessor_fallback_on_error(self, sample_candidate):
        with patch("vapt_platform.assessment._try_ollama_assess", return_value=None):
            assessor = create_assessor(mode="ai", provider="ollama")
            result = assessor(sample_candidate)

        assert result.source == "deterministic"
        assert result.fallback is True
        assert result.provider == "ollama"
        assert result.error is not None


# ---------------------------------------------------------------------------
# Assessment result tests
# ---------------------------------------------------------------------------

class TestAssessmentResult:
    def test_to_dict(self):
        result = AssessmentResult(
            quality_rank=QualityRank.HIGH,
            source="llm",
            provider="ollama",
            model="llama3.2:3b",
            fallback=False,
            reasoning="Test",
        )
        d = result.to_dict()
        assert d["quality_rank"] == "HIGH"
        assert d["source"] == "llm"
        assert d["provider"] == "ollama"
        assert d["fallback"] is False

    def test_default_values(self):
        result = AssessmentResult()
        assert result.quality_rank == QualityRank.LOW
        assert result.source == "deterministic"
        assert result.fallback is False


# ---------------------------------------------------------------------------
# Batch assessment tests
# ---------------------------------------------------------------------------

class TestBatchAssessment:
    def test_assess_multiple_candidates(self, sample_candidates):
        results = assess_candidates_with_provenance(
            sample_candidates,
            mode="deterministic",
        )
        assert len(results) == 3
        assert all(isinstance(r, AssessmentResult) for r in results)
        assert all(r.source == "deterministic" for r in results)

    def test_empty_list(self):
        results = assess_candidates_with_provenance([], mode="deterministic")
        assert results == []
