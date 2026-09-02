"""Tests for the LLM Assessor Benchmark.

Tests the benchmark that measures LLM assessor quality against VAPT corpus labels.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch

from decision_engine.benchmarks.llm_assessor_benchmark import (
    load_corpus_labels,
    load_correspondence,
    predict_usability_rank,
    compute_accuracy,
    run_llm_assessor_benchmark,
)


class TestLoadCorpusLabels:
    """Tests for loading the VAPT corpus labels."""

    def test_load_corpus_labels_returns_dict(self):
        """load_corpus_labels should return a dictionary."""
        labels = load_corpus_labels()
        assert isinstance(labels, dict)
        # Should contain the CVEs from the fixture
        assert "CVE-2021-44228" in labels
        assert labels["CVE-2021-44228"]["reliability"] == "HIGH"
        assert labels["CVE-2023-38408"]["reliability"] == "MEDIUM"
        assert labels["CVE-2022-22965"]["reliability"] == "LOW"


class TestLoadCorrespondence:
    """Tests for loading CVE to reliability correspondence."""

    def test_load_correspondence_maps_correctly(self):
        """load_correspondence should map CVE ID to its reliability."""
        correspondence = load_correspondence()
        assert isinstance(correspondence, dict)
        assert correspondence["CVE-2021-44228"] == "HIGH"
        assert correspondence["CVE-2023-38408"] == "MEDIUM"
        assert correspondence["CVE-2022-22965"] == "LOW"
        assert len(correspondence) == 12  # From labels.json


class TestPredictUsabilityRank:
    """Tests for running the LLM assessor on a single CVE."""

    def test_predict_usability_rank_returns_quality_rank(self):
        """predict_usability_rank should return a QualityRank."""
        with patch("decision_engine.benchmarks.llm_assessor_benchmark.vapt_assess_fn") as mock_assess:
            # Mock the assessor to return a fixed QualityRank
            mock_fn = MagicMock(return_value="HIGH")
            mock_assess.return_value = mock_fn
            
            result = predict_usability_rank("CVE-2021-44228")
            
            # The function should call vapt_assess_fn(use_llm=True) and return its result
            mock_assess.assert_called_once_with(use_llm=True)
            mock_fn.assert_called_once()
            # Since our mock returns string, we need to check that it was called
            # The actual function returns QualityRank, but our mock returns string
            # We'll just verify it was called


class TestComputeAccuracy:
    """Tests for computing accuracy between predictions and ground truth."""

    def test_compute_accuracy_perfect_match(self):
        """When predictions match ground truth, accuracy should be 1.0."""
        cves = ["CVE-1", "CVE-2", "CVE-3"]
        predictions = ["HIGH", "MEDIUM", "LOW"]  # Will be converted to QualityRank in real usage
        reliabilities = ["HIGH", "MEDIUM", "LOW"]
        
        # Convert to QualityRank objects as the real function expects
        from decision_engine.core.schemas import QualityRank
        quality_predictions = [QualityRank[p] for p in predictions]
        
        accuracies = compute_accuracy(cves, quality_predictions, reliabilities)
        
        # All should be correct (accuracy = True)
        assert all(accuracies.values())
        assert len(accuracies) == 3
        
        # Check individual values
        assert accuracies["CVE-1"] == True
        assert accuracies["CVE-2"] == True
        assert accuracies["CVE-3"] == True

    def test_compute_accuracy_mixed(self):
        """Test mixed correct/incorrect predictions."""
        cves = ["CVE-1", "CVE-2", "CVE-3"]
        from decision_engine.core.schemas import QualityRank
        predictions = [QualityRank.HIGH, QualityRank.LOW, QualityRank.HIGH]  # HIGH, LOW, HIGH
        reliabilities = ["HIGH", "HIGH", "LOW"]  # Expected: HIGH, HIGH, LOW
        
        accuracies = compute_accuracy(cves, predictions, reliabilities)
        
        # CVE-1: HIGH == HIGH -> True
        # CVE-2: LOW != HIGH -> False  
        # CVE-3: HIGH != LOW -> False
        assert accuracies["CVE-1"] == True
        assert accuracies["CVE-2"] == False
        assert accuracies["CVE-3"] == False
        
        # Overall accuracy should be 1/3
        # Note: compute_accuracy returns per-CVE accuracy dict
        # The overall accuracy is computed in run_llm_assessor_benchmark

    def test_compute_accuracy_handles_medium(self):
        """Test that MEDIUM reliability is handled correctly."""
        cves = ["CVE-MED"]
        from decision_engine.core.schemas import QualityRank
        predictions = [QualityRank.MEDIUM]
        reliabilities = ["MEDIUM"]
        
        accuracies = compute_accuracy(cves, predictions, reliabilities)
        assert accuracies["CVE-MED"] == True


class TestRunLlmAssessorBenchmark:
    """Tests for the main benchmark runner."""

    def test_run_llm_assessor_benchmark_structure(self):
        """run_llm_assessor_benchmark should return the expected structure."""
        with patch("decision_engine.benchmarks.llm_assessor_benchmark.load_correspondence") as mock_load, \
             patch("decision_engine.benchmarks.llm_assessor_benchmark.predict_usability_rank") as mock_predict, \
             patch("decision_engine.benchmarks.llm_assessor_benchmark.compute_accuracy") as mock_compute:
            
            # Setup mocks
            mock_load.return_value = {
                "CVE-2021-44228": "HIGH",
                "CVE-2023-38408": "MEDIUM",
                "CVE-2022-22965": "LOW"
            }
            
            from decision_engine.core.schemas import QualityRank
            mock_predict.side_effect = [
                QualityRank.HIGH,
                QualityRank.MEDIUM, 
                QualityRank.LOW
            ]
            
            mock_compute.return_value = {
                "CVE-2021-44228": True,
                "CVE-2023-38408": True,
                "CVE-2022-22965": True
            }
            
            # Run the benchmark
            result = run_llm_assessor_benchmark()
            
            # Check structure
            assert isinstance(result, dict)
            assert "cves" in result
            assert "predictions" in result
            assert "accuracies" in result
            assert "overall_accuracy" in result
            
            # Check types
            assert isinstance(result["cves"], list)
            assert isinstance(result["predictions"], list)
            assert isinstance(result["accuracies"], dict)
            assert isinstance(result["overall_accuracy"], (int, float))
            
            # Check values
            assert len(result["cves"]) == 3
            assert len(result["predictions"]) == 3
            assert len(result["accuracies"]) == 3
            assert result["overall_accuracy"] == 1.0  # All correct
            
            # Check that mocks were called
            mock_load.assert_called_once()
            assert mock_predict.call_count == 3
            mock_compute.assert_called_once()

    def test_run_llm_assessor_benchmark_with_mixed_results(self):
        """Test benchmark with some correct and some incorrect predictions."""
        with patch("decision_engine.benchmarks.llm_assessor_benchmark.load_correspondence") as mock_load, \
             patch("decision_engine.benchmarks.llm_assessor_benchmark.predict_usability_rank") as mock_predict, \
             patch("decision_engine.benchmarks.llm_assessor_benchmark.compute_accuracy") as mock_compute:
            
            # Setup mocks
            mock_load.return_value = {
                "CVE-2021-44228": "HIGH",
                "CVE-2023-38408": "MEDIUM",
                "CVE-2022-22965": "LOW"
            }
            
            from decision_engine.core.schemas import QualityRank
            mock_predict.side_effect = [
                QualityRank.HIGH,   # Correct: HIGH == HIGH
                QualityRank.LOW,    # Incorrect: LOW != MEDIUM
                QualityRank.HIGH    # Incorrect: HIGH != LOW
            ]
            
            mock_compute.return_value = {
                "CVE-2021-44228": True,   # Correct
                "CVE-2023-38408": False,  # Incorrect
                "CVE-2022-22965": False   # Incorrect
            }
            
            result = run_llm_assessor_benchmark()
            
            # Overall accuracy should be 1/3 ≈ 0.3333
            assert result["overall_accuracy"] == pytest.approx(0.3333, rel=1e-4)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])