"""Experiment harness for AI-VAPT research validation.

Provides reproducible benchmark scenarios for:
- GAP-1: AI pre-execution assessment effect on candidate ordering
- GAP-2: Bounded failure-driven pivoting with per-candidate attempt counters
- Combined: AI-assisted ranking + pivot vs deterministic baseline

All experiments use deterministic assessment to ensure reproducibility
without external LLM dependencies. Results are saved to experiments/results/.
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from decision_engine.core.assessor import deterministic_assessor
from decision_engine.core.engine import rank_candidates, run_engine
from decision_engine.core.executor import Executor
from decision_engine.core.schemas import (
    ActionCandidate,
    Outcome,
    QualityRank,
    candidate_from_dict,
)


# ---------------------------------------------------------------------------
# Experiment configuration
# ---------------------------------------------------------------------------

@dataclass
class ExperimentConfig:
    """Configuration for a single experiment run."""
    name: str
    description: str
    candidates: list[dict]
    max_attempts: int = 2
    mode: str = "simulation"
    assessor_mode: str = "deterministic"  # "deterministic" or "ai"
    repetitions: int = 1  # for variance measurement
    seed: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "candidate_count": len(self.candidates),
            "max_attempts": self.max_attempts,
            "mode": self.mode,
            "assessor_mode": self.assessor_mode,
            "repetitions": self.repetitions,
        }


@dataclass
class ExperimentResult:
    """Result of a single experiment run."""
    config_name: str
    run_index: int
    final_status: str
    total_attempts: int
    pivot_count: int
    candidates_processed: list[str]
    ranking_order: list[str]
    execution_sequence: list[dict]
    decision_trace: list[str]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "config_name": self.config_name,
            "run_index": self.run_index,
            "final_status": self.final_status,
            "total_attempts": self.total_attempts,
            "pivot_count": self.pivot_count,
            "candidates_processed": self.candidates_processed,
            "ranking_order": self.ranking_order,
            "execution_sequence": self.execution_sequence,
            "decision_trace": self.decision_trace,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Benchmark scenarios (deterministic, reproducible)
# ---------------------------------------------------------------------------

def scenario_threshold_1() -> list[dict]:
    """Threshold=1: immediate pivot after first failure."""
    return [
        {"id": "TH1-FAIL-A", "probability": 0.80, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "TH1-SUCCESS", "probability": 0.60, "ground_truth": "SUCCESS"},
    ]


def scenario_threshold_2() -> list[dict]:
    """Threshold=2: two attempts before pivot."""
    return [
        {"id": "TH2-FAIL-A", "probability": 0.80, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "TH2-SUCCESS", "probability": 0.60, "ground_truth": "SUCCESS"},
        {"id": "TH2-FAIL-B", "probability": 0.40, "ground_truth": "FAIL_SYNTAX"},
    ]


def scenario_threshold_3() -> list[dict]:
    """Threshold=3: three attempts before pivot."""
    return [
        {"id": "TH3-FAIL-A", "probability": 0.90, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "TH3-FAIL-B", "probability": 0.70, "ground_truth": "FAIL_SYNTAX"},
        {"id": "TH3-SUCCESS", "probability": 0.50, "ground_truth": "SUCCESS"},
    ]


def scenario_all_fail() -> list[dict]:
    """All candidates fail — bounded termination."""
    return [
        {"id": "AF-1", "probability": 0.90, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "AF-2", "probability": 0.70, "ground_truth": "FAIL_SYNTAX"},
        {"id": "AF-3", "probability": 0.50, "ground_truth": "FAIL_TIMEOUT"},
    ]


def scenario_immediate_success() -> list[dict]:
    """First candidate succeeds immediately."""
    return [
        {"id": "IS-1", "probability": 0.95, "ground_truth": "SUCCESS"},
        {"id": "IS-2", "probability": 0.80, "ground_truth": "SUCCESS"},
    ]


def scenario_ai_informed_ranking() -> list[dict]:
    """Scenario where AI assessment changes ordering vs probability-only.

    Without assessment, AF-1 (prob=0.9) ranks first.
    With assessment (deterministic: HIGH for SUCCESS, LOW for FAIL),
    AF-1 gets LOW quality -> score = 0.9 * (0.5 + 0.5*0.3) = 0.585
    AF-2 gets HIGH quality -> score = 0.5 * (0.5 + 0.5*1.0) = 0.5
    So AF-1 still ranks first but the gap narrows. With a stronger
    AI signal, AF-2 could overtake AF-1.

    To demonstrate AI-inverted ordering, use:
    - AF-1: prob=0.95, ground_truth=FAIL -> LOW quality -> score=0.6175
    - AF-2: prob=0.40, ground_truth=SUCCESS -> HIGH quality -> score=0.40
    Here probability dominates. But with multiple failures and a
    high-quality late candidate, the ranking effect is visible.
    """
    return [
        {"id": "AI-RANK-FAIL-1", "probability": 0.95, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "AI-RANK-FAIL-2", "probability": 0.85, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "AI-RANK-SUCCESS", "probability": 0.40, "ground_truth": "SUCCESS"},
    ]


# ---------------------------------------------------------------------------
# Experiment runner
# ---------------------------------------------------------------------------

def run_single_experiment(
    config: ExperimentConfig,
    run_index: int = 0,
) -> ExperimentResult:
    """Run a single experiment and collect results."""
    # Build executor
    executor = Executor(mode="simulation")

    # Run engine
    final_state = run_engine(
        config.candidates,
        assess_fn=deterministic_assessor,
        executor=executor,
        max_attempts=config.max_attempts,
        mode=config.mode,
    )

    # Extract ranking order (from initial state after ranking)
    candidates = final_state.get("candidates", [])
    ranking_order = [c.id for c in candidates]

    # Extract execution sequence
    execution_sequence = []
    for r in final_state.get("results", []):
        execution_sequence.append({
            "candidate_id": r.get("candidate_id", "?"),
            "outcome": r.get("outcome", "?"),
            "detail": r.get("detail", ""),
        })

    # Count pivots
    pivot_count = sum(
        1 for log in final_state.get("logs", [])
        if "[Pivot]" in log and ("Abandoning" in log or "Redirected" in log)
    )

    # Candidates processed
    processed = []
    seen = set()
    for c in candidates:
        if c.id not in seen:
            seen.add(c.id)
            processed.append(c.id)

    return ExperimentResult(
        config_name=config.name,
        run_index=run_index,
        final_status=final_state.get("status", "UNKNOWN"),
        total_attempts=len(final_state.get("results", [])),
        pivot_count=pivot_count,
        candidates_processed=processed,
        ranking_order=ranking_order,
        execution_sequence=execution_sequence,
        decision_trace=final_state.get("logs", []),
    )


def run_experiment_batch(
    config: ExperimentConfig,
) -> list[ExperimentResult]:
    """Run an experiment configuration N times."""
    results = []
    for i in range(config.repetitions):
        result = run_single_experiment(config, run_index=i)
        results.append(result)
    return results


def save_results_csv(results: list[ExperimentResult], path: str) -> None:
    """Save experiment results to CSV."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "config_name", "run_index", "final_status", "total_attempts",
            "pivot_count", "ranking_order", "candidates_processed",
            "timestamp",
        ])
        for r in results:
            writer.writerow([
                r.config_name,
                r.run_index,
                r.final_status,
                r.total_attempts,
                r.pivot_count,
                "|".join(r.ranking_order),
                "|".join(r.candidates_processed),
                r.timestamp,
            ])


def save_results_json(results: list[ExperimentResult], path: str) -> None:
    """Save experiment results to JSON."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump([r.to_dict() for r in results], f, indent=2)


# ---------------------------------------------------------------------------
# Pre-defined experiment suite
# ---------------------------------------------------------------------------

EXPERIMENT_SUITE: list[ExperimentConfig] = [
    ExperimentConfig(
        name="gap2_threshold_1",
        description="GAP-2: pivot threshold = 1 (immediate pivot after first failure)",
        candidates=scenario_threshold_1(),
        max_attempts=1,
        repetitions=3,
    ),
    ExperimentConfig(
        name="gap2_threshold_2",
        description="GAP-2: pivot threshold = 2 (two attempts before pivot)",
        candidates=scenario_threshold_2(),
        max_attempts=2,
        repetitions=3,
    ),
    ExperimentConfig(
        name="gap2_threshold_3",
        description="GAP-2: pivot threshold = 3 (three attempts before pivot)",
        candidates=scenario_threshold_3(),
        max_attempts=3,
        repetitions=3,
    ),
    ExperimentConfig(
        name="gap2_all_fail",
        description="GAP-2: all candidates fail (bounded termination)",
        candidates=scenario_all_fail(),
        max_attempts=2,
        repetitions=3,
    ),
    ExperimentConfig(
        name="gap2_immediate_success",
        description="GAP-2: first candidate succeeds (no pivot needed)",
        candidates=scenario_immediate_success(),
        max_attempts=2,
        repetitions=3,
    ),
    ExperimentConfig(
        name="gap1_ai_informed_ranking",
        description="GAP-1: AI assessment effect on candidate ordering",
        candidates=scenario_ai_informed_ranking(),
        max_attempts=2,
        repetitions=3,
    ),
]


def run_full_suite(output_dir: str = "experiments/results") -> dict[str, list[ExperimentResult]]:
    """Run the complete experiment suite."""
    os.makedirs(output_dir, exist_ok=True)
    all_results: dict[str, list[ExperimentResult]] = {}

    for config in EXPERIMENT_SUITE:
        print(f"Running: {config.name}...")
        results = run_experiment_batch(config)
        all_results[config.name] = results

        # Save individual results
        csv_path = os.path.join(output_dir, f"{config.name}.csv")
        json_path = os.path.join(output_dir, f"{config.name}.json")
        save_results_csv(results, csv_path)
        save_results_json(results, json_path)

        # Print summary
        for r in results:
            print(f"  run {r.run_index}: status={r.final_status}, "
                  f"attempts={r.total_attempts}, pivots={r.pivot_count}, "
                  f"ranking={r.ranking_order}")

    # Save combined results
    combined_csv = os.path.join(output_dir, "all_experiments.csv")
    with open(combined_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "config_name", "run_index", "final_status", "total_attempts",
            "pivot_count", "ranking_order", "candidates_processed",
        ])
        for results in all_results.values():
            for r in results:
                writer.writerow([
                    r.config_name, r.run_index, r.final_status,
                    r.total_attempts, r.pivot_count,
                    "|".join(r.ranking_order),
                    "|".join(r.candidates_processed),
                ])

    return all_results


if __name__ == "__main__":
    results = run_full_suite()
    print(f"\nCompleted {len(results)} experiments.")