"""Tests for the experiment harness and benchmarks."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments.harness import (
    ExperimentConfig,
    run_single_experiment,
    run_experiment_batch,
    scenario_threshold_1,
    scenario_threshold_2,
    scenario_threshold_3,
    scenario_all_fail,
    scenario_immediate_success,
)
from experiments.benchmarks import get_all_scenarios, get_scenarios_by_threshold


class TestExperimentHarness:
    """Test the experiment harness produces valid results.

    Engine behavior: EXHAUSTIVE processing — all candidates are visited.
    After success on a candidate, the engine advances to the next one.
    After max_attempts failures, the engine pivots to the next candidate.
    """

    def test_threshold_1_scenario(self):
        """Threshold=1: each candidate gets exactly 1 attempt.
        Engine is exhaustive: processes all candidates.
        Order: TH1-SUCCESS (HIGH quality) > TH1-FAIL-A (LOW quality).
        Last result is FAIL from TH1-FAIL-A, so status = COMPLETED."""
        config = ExperimentConfig(
            name="test_t1",
            description="test",
            candidates=scenario_threshold_1(),
            max_attempts=1,
            repetitions=1,
        )
        results = run_experiment_batch(config)
        assert len(results) == 1
        r = results[0]
        # TH1-SUCCESS gets 1 attempt (success, advance), TH1-FAIL-A gets 1 attempt (fail, abandon)
        assert r.final_status == "COMPLETED"
        assert r.total_attempts == 2
        assert r.pivot_count == 2  # Advance from TH1-SUCCESS + Abandon TH1-FAIL-A

    def test_threshold_2_scenario(self):
        """Threshold=2: candidates get up to 2 attempts."""
        config = ExperimentConfig(
            name="test_t2",
            description="test",
            candidates=scenario_threshold_2(),
            max_attempts=2,
            repetitions=1,
        )
        results = run_experiment_batch(config)
        r = results[0]
        assert r.final_status == "COMPLETED"
        # TH2-FAIL-A: 2 fails, pivot to TH2-SUCCESS
        # TH2-SUCCESS: 1 success, advance to TH2-FAIL-B
        # TH2-FAIL-B: 2 fails, complete
        assert r.total_attempts == 5

    def test_threshold_3_scenario(self):
        """Threshold=3: candidates get up to 3 attempts.
        Engine is exhaustive: processes all candidates.
        Order: TH3-FAIL-A (HIGH/0.9) > TH3-FAIL-B (LOW/0.7) > TH3-SUCCESS (HIGH/0.5).
        All are visited; last result is TH3-FAIL-B failing, so status = COMPLETED."""
        config = ExperimentConfig(
            name="test_t3",
            description="test",
            candidates=scenario_threshold_3(),
            max_attempts=3,
            repetitions=1,
        )
        results = run_experiment_batch(config)
        r = results[0]
        assert r.final_status == "COMPLETED"
        # TH3-FAIL-A: 3 fails, pivot to TH3-SUCCESS
        # TH3-SUCCESS: 1 success, advance to TH3-FAIL-B
        # TH3-FAIL-B: 3 fails, complete
        assert r.total_attempts == 7

    def test_all_fail(self):
        """All candidates fail: each gets max_attempts tries."""
        config = ExperimentConfig(
            name="test_af",
            description="test",
            candidates=scenario_all_fail(),
            max_attempts=2,
            repetitions=1,
        )
        results = run_experiment_batch(config)
        r = results[0]
        assert r.final_status == "COMPLETED"
        assert r.total_attempts == 6  # 3 candidates * 2 attempts each
        # 3 "Abandoning" + 2 "Redirected" = 5 pivot log entries
        assert r.pivot_count == 5

    def test_immediate_success(self):
        """Both candidates succeed: engine processes all candidates."""
        config = ExperimentConfig(
            name="test_is",
            description="test",
            candidates=scenario_immediate_success(),
            max_attempts=2,
            repetitions=1,
        )
        results = run_experiment_batch(config)
        r = results[0]
        assert r.final_status == "SUCCESS"
        # IS-1: 1 success, advance to IS-2
        # IS-2: 1 success, complete
        assert r.total_attempts == 2
        assert r.pivot_count == 1  # Advance from IS-1 to IS-2

    def test_reproducibility(self):
        """Same config + deterministic assessor = identical results."""
        config = ExperimentConfig(
            name="test_repro",
            description="test",
            candidates=scenario_threshold_1(),
            max_attempts=1,
            repetitions=3,
        )
        results = run_experiment_batch(config)
        # All runs should be identical (deterministic)
        for r in results[1:]:
            assert r.total_attempts == results[0].total_attempts
            assert r.pivot_count == results[0].pivot_count
            assert r.ranking_order == results[0].ranking_order

    def test_ranking_reflects_assessment(self):
        """Verify that ranking uses priority_score (prob * quality)."""
        from decision_engine.core.engine import rank_candidates
        from decision_engine.core.assessor import deterministic_assessor
        from decision_engine.core.schemas import candidate_from_dict

        candidates = [
            candidate_from_dict({"id": "HIGH-P-FAIL", "probability": 0.95, "ground_truth": "FAIL_TIMEOUT"}),
            candidate_from_dict({"id": "LOW-P-SUCCESS", "probability": 0.30, "ground_truth": "SUCCESS"}),
        ]
        # Apply assessment
        for c in candidates:
            c.quality_rank = deterministic_assessor(c)

        ranked = rank_candidates(candidates)
        ids = [c.id for c in ranked]
        # HIGH-P-FAIL gets MEDIUM (prob>=0.9), LOW-P-SUCCESS gets HIGH
        # HIGH-P-FAIL: score = 0.95 * (0.5 + 0.5*0.6) = 0.95 * 0.8 = 0.76
        # LOW-P-SUCCESS: score = 0.30 * (0.5 + 0.5*1.0) = 0.30 * 1.0 = 0.30
        assert ids == ["HIGH-P-FAIL", "LOW-P-SUCCESS"]


class TestBenchmarks:
    """Test all benchmark scenarios."""

    def test_all_benchmarks_run(self):
        scenarios = get_all_scenarios()
        assert len(scenarios) > 0
        for sc in scenarios:
            config = ExperimentConfig(
                name=sc.name,
                description=sc.description,
                candidates=sc.candidates,
                max_attempts=sc.max_attempts,
                repetitions=1,
            )
            results = run_experiment_batch(config)
            assert len(results) == 1
            r = results[0]
            assert r.final_status is not None

    def test_threshold_benchmarks_exist(self):
        for n in [1, 2, 3]:
            scenarios = get_scenarios_by_threshold(n)
            assert len(scenarios) > 0, f"No threshold={n} benchmarks"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])