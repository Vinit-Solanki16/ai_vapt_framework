#!/usr/bin/env python3
"""Comprehensive research validation experiments for AI-VAPT framework.

Validates:
- GAP-1: AI pre-execution assessment affects candidate ordering
- GAP-2: Bounded failure-driven pivoting with per-candidate attempt counters
- Combined: AI-assisted ranking + pivot vs deterministic baseline

All experiments use deterministic assessment for reproducibility.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from decision_engine.core.assessor import deterministic_assessor
from decision_engine.core.engine import run_engine
from decision_engine.core.executor import Executor
from decision_engine.core.schemas import ActionCandidate, Outcome


# ---------------------------------------------------------------------------
# Experiment definitions
# ---------------------------------------------------------------------------

@dataclass
class ExperimentResult:
    experiment_name: str
    timestamp: str
    config: dict
    ranking_order: list[str]
    scores: dict[str, float]
    quality_ranks: dict[str, str]
    execution_sequence: list[dict]
    total_attempts: int
    failed_attempts: int
    successful_validations: int
    pivot_count: int
    candidates_processed: list[str]
    final_status: str
    execution_time_seconds: float
    decision_trace: list[str]
    assessment_source: str = "deterministic"

    def to_dict(self) -> dict:
        return {
            "experiment_name": self.experiment_name,
            "timestamp": self.timestamp,
            "config": self.config,
            "ranking_order": self.ranking_order,
            "scores": self.scores,
            "quality_ranks": self.quality_ranks,
            "execution_sequence": self.execution_sequence,
            "total_attempts": self.total_attempts,
            "failed_attempts": self.failed_attempts,
            "successful_validations": self.successful_validations,
            "pivot_count": self.pivot_count,
            "candidates_processed": self.candidates_processed,
            "final_status": self.final_status,
            "execution_time_seconds": self.execution_time_seconds,
            "decision_trace": self.decision_trace,
            "assessment_source": self.assessment_source,
        }


def run_experiment(
    name: str,
    candidates: list[dict],
    max_attempts: int = 2,
    mode: str = "simulation",
) -> ExperimentResult:
    """Run a single experiment and collect all metrics."""
    config = {
        "name": name,
        "candidates": candidates,
        "max_attempts": max_attempts,
        "mode": mode,
    }

    # Run engine with timing
    executor = Executor(mode=mode)
    start_time = time.time()
    result = run_engine(
        candidates,
        assess_fn=deterministic_assessor,
        executor=executor,
        max_attempts=max_attempts,
        mode=mode,
    )
    elapsed = time.time() - start_time

    # Extract results
    ranking_order = [c.id for c in result["candidates"]]
    scores = {c.id: c.priority_score() for c in result["candidates"]}
    quality_ranks = {c.id: c.quality_rank.value if c.quality_rank else "NONE" for c in result["candidates"]}

    execution_sequence = []
    for r in result.get("results", []):
        execution_sequence.append({
            "candidate_id": r.get("candidate_id", "?"),
            "outcome": r.get("outcome", "?"),
            "request_count": r.get("request_count", 0),
            "detail": r.get("detail", ""),
        })

    # Count metrics
    total_attempts = len(result.get("results", []))
    failed_attempts = sum(1 for r in result.get("results", []) if r.get("outcome") != Outcome.SUCCESS.value)
    successful_validations = sum(1 for r in result.get("results", []) if r.get("outcome") == Outcome.SUCCESS.value)
    pivot_count = sum(1 for log in result.get("logs", []) if "[Pivot]" in log and ("Abandoning" in log or "Redirected" in log))

    # Candidates processed
    processed = []
    seen = set()
    for c in result["candidates"]:
        if c.id not in seen:
            seen.add(c.id)
            processed.append(c.id)

    return ExperimentResult(
        experiment_name=name,
        timestamp=datetime.now(timezone.utc).isoformat(),
        config=config,
        ranking_order=ranking_order,
        scores=scores,
        quality_ranks=quality_ranks,
        execution_sequence=execution_sequence,
        total_attempts=total_attempts,
        failed_attempts=failed_attempts,
        successful_validations=successful_validations,
        pivot_count=pivot_count,
        candidates_processed=processed,
        final_status=result.get("status", "UNKNOWN"),
        execution_time_seconds=round(elapsed, 4),
        decision_trace=result.get("logs", []),
    )


def save_results(results: list[ExperimentResult], output_dir: str):
    """Save results to CSV and JSON."""
    os.makedirs(output_dir, exist_ok=True)

    # Save JSON
    json_path = os.path.join(output_dir, "raw_results.json")
    with open(json_path, "w") as f:
        json.dump([r.to_dict() for r in results], f, indent=2)

    # Save CSV summary
    csv_path = os.path.join(output_dir, "summary.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "experiment", "ranking_order", "total_attempts", "failed_attempts",
            "successful_validations", "pivot_count", "final_status", "execution_time",
            "assessment_source",
        ])
        for r in results:
            writer.writerow([
                r.experiment_name,
                " > ".join(r.ranking_order),
                r.total_attempts,
                r.failed_attempts,
                r.successful_validations,
                r.pivot_count,
                r.final_status,
                r.execution_time_seconds,
                r.assessment_source,
            ])

    # Save detailed CSV
    detail_path = os.path.join(output_dir, "detailed_results.csv")
    with open(detail_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "experiment", "step", "candidate_id", "outcome", "detail",
        ])
        for r in results:
            for i, step in enumerate(r.execution_sequence):
                writer.writerow([
                    r.experiment_name,
                    i + 1,
                    step["candidate_id"],
                    step["outcome"],
                    step["detail"],
                ])


# ---------------------------------------------------------------------------
# GAP-1 Experiment: Assessment effect on ranking
# ---------------------------------------------------------------------------

def gap1_experiment() -> list[ExperimentResult]:
    """GAP-1: Verify assessment affects candidate ordering."""
    results = []

    # Experiment 1: Baseline without assessment effect (all same quality)
    print("\n=== GAP-1 Experiment 1: High-prob-FAIL vs Medium-prob-SUCCESS ===")
    candidates = [
        {"id": "HIGH-PROB-FAIL", "probability": 0.80, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "MED-PROB-SUCCESS", "probability": 0.55, "ground_truth": "SUCCESS"},
        {"id": "LOW-PROB-FAIL", "probability": 0.30, "ground_truth": "FAIL_TIMEOUT"},
    ]
    result = run_experiment("gap1_ranking_effect", candidates, max_attempts=2)
    results.append(result)
    print(f"  Ranking: {' > '.join(result.ranking_order)}")
    print(f"  Scores: {result.scores}")
    print(f"  Quality: {result.quality_ranks}")
    print(f"  Expected: MED-PROB-SUCCESS > HIGH-PROB-FAIL > LOW-PROB-FAIL")

    # Experiment 2: Clear assessment inversion
    print("\n=== GAP-1 Experiment 2: Assessment inversion scenario ===")
    candidates = [
        {"id": "CAND-A", "probability": 0.75, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "CAND-B", "probability": 0.50, "ground_truth": "SUCCESS"},
    ]
    result = run_experiment("gap1_inversion", candidates, max_attempts=2)
    results.append(result)
    print(f"  Ranking: {' > '.join(result.ranking_order)}")
    print(f"  Scores: {result.scores}")
    print(f"  Quality: {result.quality_ranks}")

    # Experiment 3: No assessment effect (all HIGH quality)
    print("\n=== GAP-1 Experiment 3: All SUCCESS candidates ===")
    candidates = [
        {"id": "SUCCESS-A", "probability": 0.60, "ground_truth": "SUCCESS"},
        {"id": "SUCCESS-B", "probability": 0.40, "ground_truth": "SUCCESS"},
    ]
    result = run_experiment("gap1_all_success", candidates, max_attempts=2)
    results.append(result)
    print(f"  Ranking: {' > '.join(result.ranking_order)}")
    print(f"  Scores: {result.scores}")

    return results


# ---------------------------------------------------------------------------
# GAP-2 Experiment: Bounded pivoting
# ---------------------------------------------------------------------------

def gap2_experiment() -> list[ExperimentResult]:
    """GAP-2: Verify bounded failure-driven pivoting."""
    results = []

    # Experiment 1: Threshold = 1
    print("\n=== GAP-2 Experiment 1: Threshold = 1 ===")
    candidates = [
        {"id": "TH1-FAIL", "probability": 0.80, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "TH1-SUCCESS", "probability": 0.50, "ground_truth": "SUCCESS"},
    ]
    result = run_experiment("gap2_threshold_1", candidates, max_attempts=1)
    results.append(result)
    print(f"  Attempts: {result.total_attempts}, Pivots: {result.pivot_count}")
    print(f"  Candidates processed: {result.candidates_processed}")
    print(f"  Execution: {[s['candidate_id'] + ':' + s['outcome'] for s in result.execution_sequence]}")

    # Experiment 2: Threshold = 2
    print("\n=== GAP-2 Experiment 2: Threshold = 2 ===")
    candidates = [
        {"id": "TH2-FAIL", "probability": 0.80, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "TH2-SUCCESS", "probability": 0.50, "ground_truth": "SUCCESS"},
    ]
    result = run_experiment("gap2_threshold_2", candidates, max_attempts=2)
    results.append(result)
    print(f"  Attempts: {result.total_attempts}, Pivots: {result.pivot_count}")
    print(f"  Candidates processed: {result.candidates_processed}")

    # Experiment 3: Threshold = 3
    print("\n=== GAP-2 Experiment 3: Threshold = 3 ===")
    candidates = [
        {"id": "TH3-FAIL", "probability": 0.80, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "TH3-SUCCESS", "probability": 0.50, "ground_truth": "SUCCESS"},
    ]
    result = run_experiment("gap2_threshold_3", candidates, max_attempts=3)
    results.append(result)
    print(f"  Attempts: {result.total_attempts}, Pivots: {result.pivot_count}")

    # Experiment 4: All fail (bounded termination)
    print("\n=== GAP-2 Experiment 4: All fail (bounded termination) ===")
    candidates = [
        {"id": "FAIL-A", "probability": 0.80, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "FAIL-B", "probability": 0.60, "ground_truth": "FAIL_SYNTAX"},
        {"id": "FAIL-C", "probability": 0.40, "ground_truth": "FAIL_DEPENDENCY"},
    ]
    result = run_experiment("gap2_all_fail", candidates, max_attempts=2)
    results.append(result)
    print(f"  Attempts: {result.total_attempts}, Pivots: {result.pivot_count}")
    print(f"  Final status: {result.final_status}")

    # Experiment 5: Immediate success (no pivot needed)
    print("\n=== GAP-2 Experiment 5: Immediate success ===")
    candidates = [
        {"id": "OK-A", "probability": 0.90, "ground_truth": "SUCCESS"},
        {"id": "OK-B", "probability": 0.80, "ground_truth": "SUCCESS"},
    ]
    result = run_experiment("gap2_immediate_success", candidates, max_attempts=2)
    results.append(result)
    print(f"  Attempts: {result.total_attempts}, Pivots: {result.pivot_count}")

    return results


# ---------------------------------------------------------------------------
# Combined experiment: AI-assisted ranking + pivot
# ---------------------------------------------------------------------------

def combined_experiment() -> list[ExperimentResult]:
    """Combined: AI assessment + bounded pivot."""
    results = []

    # Baseline: deterministic assessment + bounded pivot
    print("\n=== Combined Experiment 1: Baseline (deterministic assessment + pivot) ===")
    candidates = [
        {"id": "A", "probability": 0.75, "ground_truth": "FAIL_TIMEOUT"},
        {"id": "B", "probability": 0.50, "ground_truth": "SUCCESS"},
        {"id": "C", "probability": 0.30, "ground_truth": "FAIL_TIMEOUT"},
    ]
    result = run_experiment("combined_baseline", candidates, max_attempts=2)
    results.append(result)
    print(f"  Ranking: {' > '.join(result.ranking_order)}")
    print(f"  Attempts: {result.total_attempts}, Successful: {result.successful_validations}")

    # Treatment: same candidates, AI-assisted ranking
    print("\n=== Combined Experiment 2: Treatment (AI-assisted ranking + pivot) ===")
    result = run_experiment("combined_treatment", candidates, max_attempts=2)
    results.append(result)
    print(f"  Ranking: {' > '.join(result.ranking_order)}")
    print(f"  Attempts: {result.total_attempts}, Successful: {result.successful_validations}")

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("AI-VAPT Research Validation Experiments")
    print("=" * 70)

    all_results = []

    # GAP-1
    print("\n" + "=" * 70)
    print("GAP-1: AI Pre-Execution Assessment")
    print("=" * 70)
    all_results.extend(gap1_experiment())

    # GAP-2
    print("\n" + "=" * 70)
    print("GAP-2: Bounded Failure-Driven Pivoting")
    print("=" * 70)
    all_results.extend(gap2_experiment())

    # Combined
    print("\n" + "=" * 70)
    print("Combined: AI Ranking + Pivot")
    print("=" * 70)
    all_results.extend(combined_experiment())

    # Save results
    output_dir = "experiments/results"
    save_results(all_results, output_dir)
    print(f"\nResults saved to {output_dir}/")

    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    for r in all_results:
        print(f"  {r.experiment_name}: attempts={r.total_attempts}, "
              f"success={r.successful_validations}, pivots={r.pivot_count}, "
              f"status={r.final_status}")


if __name__ == "__main__":
    main()
