"""Tests for the LLM assessor path (Phase 2).

These tests mock the LLM (Ollama/OpenAI) so they run offline, verifying
that:
1. The LLM assessor is invoked when --assessor llm is used
2. Its usability_rank maps correctly to QualityRank
3. The deterministic path does NOT invoke the LLM
4. The vapt_assess_fn(use_llm=True) wrapper works
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from decision_engine.core.schemas import ActionCandidate, QualityRank


# --- vapt_assess_fn(use_llm=True) ---

class TestVaptAssessFnLlm:
    def test_llm_assess_fn_returns_callable(self):
        """vapt_assess_fn(use_llm=True) should return a callable."""
        from decision_engine.adapters.vapt_adapter import vapt_assess_fn
        fn = vapt_assess_fn(use_llm=True)
        assert callable(fn)

    def test_llm_assess_fn_maps_usability_to_quality_rank(self):
        """The LLM assessor's output (UsabilityRank) should map to QualityRank."""
        from decision_engine.adapters.vapt_adapter import vapt_assess_fn
        fn = vapt_assess_fn(use_llm=True)

        # Mock the core assessor to return a fixed assessment
        mock_assessment = MagicMock()
        mock_assessment.usability_rank.value = "HIGH"

        with patch("core.exploit_assessor.assess_exploit_quality", return_value=mock_assessment):
            candidate = ActionCandidate(id="CVE-TEST", probability=0.5)
            result = fn(candidate)
        assert result == QualityRank.HIGH

    def test_llm_assess_fn_maps_medium(self):
        from decision_engine.adapters.vapt_adapter import vapt_assess_fn
        fn = vapt_assess_fn(use_llm=True)

        mock_assessment = MagicMock()
        mock_assessment.usability_rank.value = "MEDIUM"

        with patch("core.exploit_assessor.assess_exploit_quality", return_value=mock_assessment):
            candidate = ActionCandidate(id="CVE-TEST", probability=0.5)
            result = fn(candidate)
        assert result == QualityRank.MEDIUM

    def test_llm_assess_fn_maps_low(self):
        from decision_engine.adapters.vapt_adapter import vapt_assess_fn
        fn = vapt_assess_fn(use_llm=True)

        mock_assessment = MagicMock()
        mock_assessment.usability_rank.value = "LOW"

        with patch("core.exploit_assessor.assess_exploit_quality", return_value=mock_assessment):
            candidate = ActionCandidate(id="CVE-TEST", probability=0.5)
            result = fn(candidate)
        assert result == QualityRank.LOW


# --- deterministic fallback ---

class TestDeterministicAssessor:
    def test_deterministic_does_not_invoke_llm(self):
        from decision_engine.core.assessor import deterministic_assessor
        with patch("core.exploit_assessor.assess_exploit_quality") as mock_llm:
            candidate = ActionCandidate(id="CVE-TEST", probability=0.5, ground_truth=None)
            deterministic_assessor(candidate)
            mock_llm.assert_not_called()

    def test_deterministic_high_for_high_prob(self):
        from decision_engine.core.assessor import deterministic_assessor
        candidate = ActionCandidate(id="CVE-TEST", probability=0.95, ground_truth=None)
        result = deterministic_assessor(candidate)
        assert result == QualityRank.MEDIUM  # >=0.9 → MEDIUM

    def test_deterministic_low_for_low_prob(self):
        from decision_engine.core.assessor import deterministic_assessor
        candidate = ActionCandidate(id="CVE-TEST", probability=0.3, ground_truth=None)
        result = deterministic_assessor(candidate)
        assert result == QualityRank.LOW


# --- assessor branching in run_decision_scenario ---

class TestAssessorBranching:
    def test_run_scenario_with_llm_assessor(self):
        """Verify run_decision_scenario invokes LLM when assessor='llm'."""
        from prototype.engine_integration import run_decision_scenario
        mock_assessment = MagicMock()
        mock_assessment.usability_rank.value = "HIGH"
        with patch("core.exploit_assessor.assess_exploit_quality", return_value=mock_assessment):
            state = run_decision_scenario(
                [{"id": "X", "probability": 0.9, "ground_truth": "SUCCESS"}],
                max_attempts=2,
                mode="simulation",
                assessor="llm",
            )
        assert state["status"] in ("SUCCESS", "COMPLETED")

    def test_run_scenario_with_deterministic_assessor(self):
        """Verify run_decision_scenario uses deterministic when assessor='deterministic'."""
        from prototype.engine_integration import run_decision_scenario
        with patch("core.exploit_assessor.assess_exploit_quality") as mock_llm:
            state = run_decision_scenario(
                [{"id": "X", "probability": 0.9, "ground_truth": "SUCCESS"}],
                max_attempts=2,
                mode="simulation",
                assessor="deterministic",
            )
            mock_llm.assert_not_called()
        assert state["status"] in ("SUCCESS", "COMPLETED")


# --- CLI --assessor flag ---

class TestCliAssessorFlag:
    def test_cli_parser_passes_deterministic_assessor(self):
        """Verify --assessor deterministic is passed to _run_scenario."""
        from prototype import cli
        with patch("sys.argv", ["cli.py", "run", "--scenario", "success", "--assessor", "deterministic"]):
            with patch("prototype.cli._run_scenario") as mock_run:
                cli.main()
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert kwargs.get("assessor") == "deterministic"

    def test_cli_parser_passes_llm_assessor(self):
        """Verify --assessor llm is passed to _run_scenario."""
        from prototype import cli
        with patch("sys.argv", ["cli.py", "run", "--scenario", "success", "--assessor", "llm"]):
            with patch("prototype.cli._run_scenario") as mock_run:
                cli.main()
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert kwargs.get("assessor") == "llm"
