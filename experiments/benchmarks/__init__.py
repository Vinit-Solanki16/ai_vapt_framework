"""Benchmark scenarios for AI-VAPT research validation.

Each benchmark is a deterministic scenario that validates specific
research claims about the decision engine behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class BenchmarkScenario:
    """A deterministic benchmark scenario."""
    name: str
    description: str
    candidates: list[dict]
    max_attempts: int
    expected_pivots: int
    expected_attempts: int
    expected_final_status: str
    expected_ranking: list[str]  # expected ordering after assessment


# ---------------------------------------------------------------------------
# Threshold benchmarks (GAP-2)
# ---------------------------------------------------------------------------

THRESHOLD_1_SCENARIOS = [
    BenchmarkScenario(
        name="threshold_1_immediate_pivot",
        description="With threshold=1, single failure triggers immediate pivot",
        candidates=[
            {"id": "T1-FAIL", "probability": 0.80, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "T1-SUCCESS", "probability": 0.60, "ground_truth": "SUCCESS"},
        ],
        max_attempts=1,
        expected_pivots=1,
        expected_attempts=2,
        expected_final_status="COMPLETED",
        expected_ranking=["T1-FAIL", "T1-SUCCESS"],
    ),
    BenchmarkScenario(
        name="threshold_1_all_fail",
        description="Threshold=1, all fail: each gets exactly 1 attempt",
        candidates=[
            {"id": "T1-AF-1", "probability": 0.90, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "T1-AF-2", "probability": 0.70, "ground_truth": "FAIL_SYNTAX"},
        ],
        max_attempts=1,
        expected_pivots=2,
        expected_attempts=2,
        expected_final_status="COMPLETED",
        expected_ranking=["T1-AF-1", "T1-AF-2"],
    ),
]


THRESHOLD_2_SCENARIOS = [
    BenchmarkScenario(
        name="threshold_2_two_failures_then_pivot",
        description="Threshold=2: candidate gets 2 attempts before pivot",
        candidates=[
            {"id": "T2-FAIL", "probability": 0.80, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "T2-SUCCESS", "probability": 0.60, "ground_truth": "SUCCESS"},
        ],
        max_attempts=2,
        expected_pivots=1,
        expected_attempts=3,
        expected_final_status="COMPLETED",
        expected_ranking=["T2-FAIL", "T2-SUCCESS"],
    ),
    BenchmarkScenario(
        name="threshold_2_all_fail",
        description="Threshold=2, all fail: each gets exactly 2 attempts",
        candidates=[
            {"id": "T2-AF-1", "probability": 0.90, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "T2-AF-2", "probability": 0.70, "ground_truth": "FAIL_SYNTAX"},
            {"id": "T2-AF-3", "probability": 0.50, "ground_truth": "FAIL_TIMEOUT"},
        ],
        max_attempts=2,
        expected_pivots=3,
        expected_attempts=6,
        expected_final_status="COMPLETED",
        expected_ranking=["T2-AF-1", "T2-AF-2", "T2-AF-3"],
    ),
]


THRESHOLD_3_SCENARIOS = [
    BenchmarkScenario(
        name="threshold_3_three_failures_then_pivot",
        description="Threshold=3: candidate gets 3 attempts before pivot",
        candidates=[
            {"id": "T3-FAIL", "probability": 0.85, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "T3-SUCCESS", "probability": 0.60, "ground_truth": "SUCCESS"},
        ],
        max_attempts=3,
        expected_pivots=1,
        expected_attempts=4,
        expected_final_status="COMPLETED",
        expected_ranking=["T3-FAIL", "T3-SUCCESS"],
    ),
]


# ---------------------------------------------------------------------------
# Combined AI + Pivot benchmarks (GAP-1 + GAP-2)
# ---------------------------------------------------------------------------

COMBINED_SCENARIOS = [
    BenchmarkScenario(
        name="ai_assessment_changes_ranking",
        description="AI assessment boosts high-quality candidate ranking",
        candidates=[
            {"id": "AI-HIGH-FAIL", "probability": 0.95, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "AI-LOW-SUCCESS", "probability": 0.30, "ground_truth": "SUCCESS"},
            {"id": "AI-MID-SUCCESS", "probability": 0.60, "ground_truth": "SUCCESS"},
        ],
        max_attempts=2,
        expected_pivots=2,
        expected_attempts=5,
        expected_final_status="COMPLETED",
        # Deterministic assessor: FAIL->LOW, SUCCESS->HIGH, prob>=0.9->MEDIUM
        # AI-HIGH-FAIL: prob=0.95, quality=MEDIUM -> score = 0.95 * 0.8 = 0.76
        # AI-MID-SUCCESS: prob=0.60, quality=HIGH -> score = 0.60 * 1.0 = 0.60
        # AI-LOW-SUCCESS: prob=0.30, quality=HIGH -> score = 0.30 * 1.0 = 0.30
        expected_ranking=["AI-HIGH-FAIL", "AI-MID-SUCCESS", "AI-LOW-SUCCESS"],
    ),
]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_BENCHMARKS = {
    "threshold_1": THRESHOLD_1_SCENARIOS,
    "threshold_2": THRESHOLD_2_SCENARIOS,
    "threshold_3": THRESHOLD_3_SCENARIOS,
    "combined_ai_pivot": COMBINED_SCENARIOS,
}


def get_all_scenarios() -> list[BenchmarkScenario]:
    """Get all registered benchmark scenarios."""
    scenarios = []
    for group in ALL_BENCHMARKS.values():
        scenarios.extend(group)
    return scenarios


def get_scenarios_by_threshold(n: int) -> list[BenchmarkScenario]:
    """Get benchmark scenarios for a specific threshold."""
    key = f"threshold_{n}"
    return ALL_BENCHMARKS.get(key, [])