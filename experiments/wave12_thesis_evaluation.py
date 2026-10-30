#!/usr/bin/env python3
"""Wave 12 — Thesis-Grade Experimental Evaluation.

Comprehensive experiment suite covering:
  Phase 2: GAP-1 expanded (larger candidate sets, 10 controlled scenarios)
  Phase 3: Real LLM behavior evaluation (Ollama llama3.2:3b, 5 repetitions)
  Phase 4: GAP-2 expanded (thresholds 1-5, 6 scenarios = 30 experiments)
  Phase 5: Combined full-pipeline experiments (baseline vs treatment)
  Phase 6: Statistical analysis

GAP-1 experiments use deterministic assessor with synthetic candidate IDs
(LLM assessor requires real CVE IDs from the corpus).
LLM experiments use real CVE IDs from the VAPT corpus.

All experiments are deterministic reproducible; LLM experiments track
latency, source, and fallback provenance.
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
# Result types
# ---------------------------------------------------------------------------

@dataclass
class Gap1Result:
    scenario_name: str
    candidate_count: int
    scenario_type: str
    baseline_order: list[str]
    treatment_order: list[str]
    ranking_changed: bool
    assessment_source: str
    scores: dict[str, float]
    quality_ranks: dict[str, str]
    execution_sequence: list[dict]
    total_attempts: int
    failed_attempts: int
    successful_validations: int
    pivot_count: int
    final_status: str
    execution_time_seconds: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class LlmBehaviorResult:
    candidate_id: str
    run_index: int
    quality_rank: str
    latency_seconds: float
    source: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class Gap2Result:
    scenario_name: str
    threshold: int
    candidate_count: int
    scenario_type: str
    total_attempts: int
    expected_max_attempts: int
    bounded: bool
    pivot_count: int
    candidate_attempt_counters: dict[str, int]
    final_status: str
    execution_sequence: list[dict]
    execution_time_seconds: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class CombinedResult:
    scenario_name: str
    mode: str
    candidate_count: int
    assessment_source: str
    ranking_order: list[str]
    total_attempts: int
    failed_attempts: int
    successful_validations: int
    pivot_count: int
    final_status: str
    assessment_latency_seconds: float
    total_latency_seconds: float
    execution_sequence: list[dict]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_pivots(logs: list[str]) -> int:
    return sum(1 for log in logs if "[Pivot]" in log and ("Abandoning" in log or "Redirected" in log))


def _baseline_order(candidates: list[dict]) -> list[str]:
    """Probability-only ranking (no assessment)."""
    cands = [candidate_from_dict(d) for d in candidates]
    ranked = sorted(cands, key=lambda c: c.probability, reverse=True)
    return [c.id for c in ranked]


def _treatment_order(candidates: list[dict], assess_fn) -> tuple[list[str], dict, dict]:
    """Assessment-aware ranking."""
    cands = [candidate_from_dict(d) for d in candidates]
    for c in cands:
        if not c.assessed:
            c.quality_rank = assess_fn(c)
            c.assessed = True
    ranked = rank_candidates(cands)
    order = [c.id for c in ranked]
    scores = {c.id: c.priority_score() for c in ranked}
    qualities = {c.id: c.quality_rank.value if c.quality_rank else "NONE" for c in ranked}
    return order, scores, qualities


def _get_llm_assess_fn():
    """Try to get a real LLM assessor; return None if unavailable."""
    try:
        from decision_engine.adapters.vapt_adapter import vapt_assess_fn
        fn = vapt_assess_fn(use_llm=True, provider="ollama")
        test_cand = ActionCandidate(id="CVE-2021-44228", probability=0.95)
        result = fn(test_cand)
        if result in (QualityRank.HIGH, QualityRank.MEDIUM, QualityRank.LOW):
            return fn
    except Exception as e:
        print(f"  LLM assessor test failed: {e}")
    return None


def _assess_with_provenance(candidate: ActionCandidate, llm_fn) -> tuple[QualityRank, str, float]:
    """Assess a candidate, returning (rank, source, latency)."""
    if llm_fn is not None:
        start = time.time()
        try:
            rank = llm_fn(candidate)
            latency = time.time() - start
            return rank, "llm", latency
        except Exception:
            latency = time.time() - start
            return deterministic_assessor(candidate), "fallback", latency
    return deterministic_assessor(candidate), "deterministic", 0.0


# ---------------------------------------------------------------------------
# GAP-1 Scenarios (deterministic assessor, synthetic IDs)
# ---------------------------------------------------------------------------

GAP1_SCENARIOS = {
    "assessment_changes_ranking": {
        "type": "assessment_changes_ranking",
        "candidates": [
            {"id": "HIGH-PROB-FAIL", "probability": 0.90, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "MED-PROB-SUCCESS", "probability": 0.55, "ground_truth": "SUCCESS"},
            {"id": "LOW-PROB-FAIL", "probability": 0.30, "ground_truth": "FAIL_TIMEOUT"},
        ],
    },
    "assessment_no_change": {
        "type": "no_change",
        "candidates": [
            {"id": "ALL-SUCCESS-A", "probability": 0.80, "ground_truth": "SUCCESS"},
            {"id": "ALL-SUCCESS-B", "probability": 0.60, "ground_truth": "SUCCESS"},
            {"id": "ALL-SUCCESS-C", "probability": 0.40, "ground_truth": "SUCCESS"},
        ],
    },
    "high_prob_poor_quality": {
        "type": "high_prob_poor_quality",
        "candidates": [
            {"id": "HP-POOR", "probability": 0.95, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "LP-GOOD", "probability": 0.45, "ground_truth": "SUCCESS"},
            {"id": "LP-MED", "probability": 0.35, "ground_truth": "SUCCESS"},
        ],
    },
    "lower_prob_high_quality": {
        "type": "lower_prob_high_quality",
        "candidates": [
            {"id": "LP-HIGH-1", "probability": 0.40, "ground_truth": "SUCCESS"},
            {"id": "LP-HIGH-2", "probability": 0.35, "ground_truth": "SUCCESS"},
            {"id": "HP-LOW", "probability": 0.85, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "HP-MED", "probability": 0.75, "ground_truth": "FAIL_TIMEOUT"},
        ],
    },
    "mixed_population": {
        "type": "mixed_population",
        "candidates": [
            {"id": "MIX-A", "probability": 0.90, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "MIX-B", "probability": 0.70, "ground_truth": "SUCCESS"},
            {"id": "MIX-C", "probability": 0.50, "ground_truth": "FAIL_SYNTAX"},
            {"id": "MIX-D", "probability": 0.40, "ground_truth": "SUCCESS"},
            {"id": "MIX-E", "probability": 0.20, "ground_truth": "FAIL_DEPENDENCY"},
        ],
    },
    "all_high_quality": {
        "type": "all_high_quality",
        "candidates": [
            {"id": "HQ-1", "probability": 0.85, "ground_truth": "SUCCESS"},
            {"id": "HQ-2", "probability": 0.65, "ground_truth": "SUCCESS"},
            {"id": "HQ-3", "probability": 0.45, "ground_truth": "SUCCESS"},
            {"id": "HQ-4", "probability": 0.25, "ground_truth": "SUCCESS"},
        ],
    },
    "all_low_quality": {
        "type": "all_low_quality",
        "candidates": [
            {"id": "LQ-1", "probability": 0.90, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "LQ-2", "probability": 0.70, "ground_truth": "FAIL_SYNTAX"},
            {"id": "LQ-3", "probability": 0.50, "ground_truth": "FAIL_DEPENDENCY"},
            {"id": "LQ-4", "probability": 0.30, "ground_truth": "FAIL_TIMEOUT"},
        ],
    },
    "large_set_10": {
        "type": "large_set_10",
        "candidates": [
            {"id": f"C{i:02d}", "probability": round(0.95 - i * 0.08, 2),
             "ground_truth": "SUCCESS" if i % 3 == 0 else "FAIL_TIMEOUT"}
            for i in range(10)
        ],
    },
    "large_set_15": {
        "type": "large_set_15",
        "candidates": [
            {"id": f"X{i:02d}", "probability": round(0.95 - i * 0.06, 2),
             "ground_truth": "SUCCESS" if i % 4 == 0 else "FAIL_TIMEOUT"}
            for i in range(15)
        ],
    },
    "large_set_20": {
        "type": "large_set_20",
        "candidates": [
            {"id": f"Z{i:02d}", "probability": round(0.95 - i * 0.045, 2),
             "ground_truth": "SUCCESS" if i % 5 == 0 else "FAIL_TIMEOUT"}
            for i in range(20)
        ],
    },
}


def run_gap1_experiments() -> list[Gap1Result]:
    """Run all GAP-1 experiments with deterministic assessor."""
    results = []
    assess_fn = deterministic_assessor
    source = "deterministic"

    for name, scenario in GAP1_SCENARIOS.items():
        candidates = scenario["candidates"]
        print(f"\n  GAP-1: {name} ({len(candidates)} candidates, {scenario['type']})")

        baseline_ids = _baseline_order(candidates)
        treatment_ids, scores, qualities = _treatment_order(candidates, assess_fn)

        ranking_changed = baseline_ids != treatment_ids

        executor = Executor(mode="simulation")
        start_time = time.time()
        engine_result = run_engine(
            candidates,
            assess_fn=assess_fn,
            executor=executor,
            max_attempts=2,
            mode="simulation",
        )
        elapsed = time.time() - start_time

        exec_seq = [
            {"candidate_id": r.get("candidate_id", "?"),
             "outcome": r.get("outcome", "?"),
             "detail": r.get("detail", "")}
            for r in engine_result.get("results", [])
        ]
        total_attempts = len(engine_result.get("results", []))
        failed = sum(1 for r in engine_result.get("results", []) if r.get("outcome") != Outcome.SUCCESS.value)
        success = sum(1 for r in engine_result.get("results", []) if r.get("outcome") == Outcome.SUCCESS.value)
        pivots = _count_pivots(engine_result.get("logs", []))

        result = Gap1Result(
            scenario_name=name,
            candidate_count=len(candidates),
            scenario_type=scenario["type"],
            baseline_order=baseline_ids,
            treatment_order=treatment_ids,
            ranking_changed=ranking_changed,
            assessment_source=source,
            scores=scores,
            quality_ranks=qualities,
            execution_sequence=exec_seq,
            total_attempts=total_attempts,
            failed_attempts=failed,
            successful_validations=success,
            pivot_count=pivots,
            final_status=engine_result.get("status", "UNKNOWN"),
            execution_time_seconds=round(elapsed, 4),
        )
        results.append(result)
        print(f"    Baseline:  {' > '.join(baseline_ids[:5])}{'...' if len(baseline_ids) > 5 else ''}")
        print(f"    Treatment: {' > '.join(treatment_ids[:5])}{'...' if len(treatment_ids) > 5 else ''}")
        print(f"    Changed: {ranking_changed}, Attempts: {total_attempts}, Success: {success}")

    return results


# ---------------------------------------------------------------------------
# Phase 3: Real LLM Behavior (using real CVE IDs from corpus)
# ---------------------------------------------------------------------------

LLM_TEST_CANDIDATES = [
    {"id": "CVE-2021-44228", "probability": 0.95, "ground_truth": "SUCCESS"},
    {"id": "CVE-2017-0144", "probability": 0.55, "ground_truth": "SUCCESS"},
    {"id": "CVE-2023-38408", "probability": 0.30, "ground_truth": "FAIL_TIMEOUT"},
    {"id": "CVE-2022-22965", "probability": 0.45, "ground_truth": "FAIL_SYNTAX"},
    {"id": "CVE-2020-1472", "probability": 0.70, "ground_truth": "SUCCESS"},
    {"id": "CVE-2021-26855", "probability": 0.65, "ground_truth": "SUCCESS"},
    {"id": "CVE-2019-0708", "probability": 0.50, "ground_truth": "FAIL_TIMEOUT"},
    {"id": "CVE-2022-1388", "probability": 0.75, "ground_truth": "SUCCESS"},
]


def run_llm_behavior_experiments(repetitions: int = 5) -> dict:
    """Run LLM assessment multiple times to measure consistency and latency."""
    llm_fn = _get_llm_assess_fn()

    if llm_fn is None:
        print("\n  LLM assessor not available — skipping LLM behavior experiments")
        return {"available": False, "results": [], "summary": {}}

    print(f"\n  LLM assessor available (Ollama llama3.2:3b)")
    print(f"  Running {repetitions} repetitions on {len(LLM_TEST_CANDIDATES)} candidates...")

    all_results: list[LlmBehaviorResult] = []
    rank_per_run: dict[str, list[str]] = {}
    latency_per_candidate: dict[str, list[float]] = {}

    for rep in range(repetitions):
        print(f"    Repetition {rep + 1}/{repetitions}...")
        for cand_dict in LLM_TEST_CANDIDATES:
            cand = ActionCandidate(
                id=cand_dict["id"],
                probability=cand_dict["probability"],
                ground_truth=Outcome(cand_dict["ground_truth"]),
            )
            rank, source, latency = _assess_with_provenance(cand, llm_fn)

            result = LlmBehaviorResult(
                candidate_id=cand_dict["id"],
                run_index=rep,
                quality_rank=rank.value,
                latency_seconds=round(latency, 4),
                source=source,
            )
            all_results.append(result)

            rank_per_run.setdefault(cand_dict["id"], []).append(rank.value)
            latency_per_candidate.setdefault(cand_dict["id"], []).append(latency)

    # Compute consistency stats
    consistency = {}
    for cand_id, ranks in rank_per_run.items():
        unique_ranks = set(ranks)
        consistency[cand_id] = {
            "ranks": ranks,
            "unique_ranks": list(unique_ranks),
            "consistent": len(unique_ranks) == 1,
            "mode": statistics.mode(ranks) if ranks else None,
        }

    latency_stats = {}
    for cand_id, lats in latency_per_candidate.items():
        latency_stats[cand_id] = {
            "mean": round(statistics.mean(lats), 4),
            "median": round(statistics.median(lats), 4),
            "stdev": round(statistics.stdev(lats), 4) if len(lats) > 1 else 0.0,
            "min": round(min(lats), 4),
            "max": round(max(lats), 4),
            "all": [round(l, 4) for l in lats],
        }

    all_latencies = [r.latency_seconds for r in all_results if r.source == "llm"]
    fallback_count = sum(1 for r in all_results if r.source == "fallback")
    llm_count = sum(1 for r in all_results if r.source == "llm")

    summary = {
        "available": True,
        "repetitions": repetitions,
        "total_assessments": len(all_results),
        "llm_count": llm_count,
        "fallback_count": fallback_count,
        "fallback_rate": round(fallback_count / len(all_results), 4) if all_results else 0,
        "all_consistent": all(c["consistent"] for c in consistency.values()),
        "consistency_per_candidate": consistency,
        "latency_stats": latency_stats,
        "overall_latency": {
            "mean": round(statistics.mean(all_latencies), 4) if all_latencies else 0,
            "median": round(statistics.median(all_latencies), 4) if all_latencies else 0,
            "stdev": round(statistics.stdev(all_latencies), 4) if len(all_latencies) > 1 else 0,
            "min": round(min(all_latencies), 4) if all_latencies else 0,
            "max": round(max(all_latencies), 4) if all_latencies else 0,
        },
    }

    print(f"    All consistent: {summary['all_consistent']}")
    print(f"    Fallback rate: {summary['fallback_rate']}")
    print(f"    Avg latency: {summary['overall_latency']['mean']}s")

    return {"available": True, "results": [r.to_dict() for r in all_results], "summary": summary}


# ---------------------------------------------------------------------------
# Phase 4: GAP-2 Expanded Experiments
# ---------------------------------------------------------------------------

GAP2_SCENARIOS = {
    "immediate_success": {
        "type": "immediate_success",
        "candidates": [
            {"id": "IS-1", "probability": 0.95, "ground_truth": "SUCCESS"},
            {"id": "IS-2", "probability": 0.80, "ground_truth": "SUCCESS"},
            {"id": "IS-3", "probability": 0.60, "ground_truth": "SUCCESS"},
        ],
    },
    "one_fail_then_success": {
        "type": "one_fail_then_success",
        "candidates": [
            {"id": "OFS-FAIL", "probability": 0.85, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "OFS-SUCCESS", "probability": 0.55, "ground_truth": "SUCCESS"},
            {"id": "OFS-FAIL2", "probability": 0.30, "ground_truth": "FAIL_SYNTAX"},
        ],
    },
    "repeated_failure_pivot": {
        "type": "repeated_failure_pivot",
        "candidates": [
            {"id": "RFP-FAIL1", "probability": 0.90, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "RFP-FAIL2", "probability": 0.75, "ground_truth": "FAIL_SYNTAX"},
            {"id": "RFP-SUCCESS", "probability": 0.50, "ground_truth": "SUCCESS"},
            {"id": "RFP-FAIL3", "probability": 0.35, "ground_truth": "FAIL_DEPENDENCY"},
        ],
    },
    "multiple_candidates_failing": {
        "type": "multiple_fail",
        "candidates": [
            {"id": "MF-1", "probability": 0.90, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "MF-2", "probability": 0.80, "ground_truth": "FAIL_SYNTAX"},
            {"id": "MF-3", "probability": 0.60, "ground_truth": "FAIL_DEPENDENCY"},
            {"id": "MF-OK", "probability": 0.45, "ground_truth": "SUCCESS"},
        ],
    },
    "all_candidates_failing": {
        "type": "all_fail",
        "candidates": [
            {"id": "AF-1", "probability": 0.90, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "AF-2", "probability": 0.75, "ground_truth": "FAIL_SYNTAX"},
            {"id": "AF-3", "probability": 0.55, "ground_truth": "FAIL_DEPENDENCY"},
            {"id": "AF-4", "probability": 0.35, "ground_truth": "FAIL_TIMEOUT"},
        ],
    },
    "large_set_bounded": {
        "type": "large_set_bounded",
        "candidates": [
            {"id": f"LB-{i}", "probability": round(0.9 - i * 0.08, 2),
             "ground_truth": "SUCCESS" if i == 7 else "FAIL_TIMEOUT"}
            for i in range(10)
        ],
    },
}


def run_gap2_experiments() -> list[Gap2Result]:
    """Run GAP-2 experiments at thresholds 1-5 across all scenarios."""
    results = []

    for name, scenario in GAP2_SCENARIOS.items():
        candidates = scenario["candidates"]
        for threshold in [1, 2, 3, 4, 5]:
            print(f"\n  GAP-2: {name} (threshold={threshold}, {len(candidates)} candidates)")

            executor = Executor(mode="simulation")
            start_time = time.time()
            engine_result = run_engine(
                candidates,
                assess_fn=deterministic_assessor,
                executor=executor,
                max_attempts=threshold,
                mode="simulation",
            )
            elapsed = time.time() - start_time

            results_list = engine_result.get("results", [])
            total_attempts = len(results_list)
            expected_max = len(candidates) * threshold
            bounded = total_attempts <= expected_max

            cand_attempts: dict[str, int] = {}
            for r in results_list:
                cid = r.get("candidate_id", "?")
                cand_attempts[cid] = cand_attempts.get(cid, 0) + 1

            exec_seq = [
                {"candidate_id": r.get("candidate_id", "?"),
                 "outcome": r.get("outcome", "?")}
                for r in results_list
            ]

            pivots = _count_pivots(engine_result.get("logs", []))

            result = Gap2Result(
                scenario_name=name,
                threshold=threshold,
                candidate_count=len(candidates),
                scenario_type=scenario["type"],
                total_attempts=total_attempts,
                expected_max_attempts=expected_max,
                bounded=bounded,
                pivot_count=pivots,
                candidate_attempt_counters=cand_attempts,
                final_status=engine_result.get("status", "UNKNOWN"),
                execution_sequence=exec_seq,
                execution_time_seconds=round(elapsed, 4),
            )
            results.append(result)
            print(f"    Attempts: {total_attempts}/{expected_max} (bounded={bounded}), Pivots: {pivots}")

    return results


# ---------------------------------------------------------------------------
# Phase 5: Combined Experiments
# ---------------------------------------------------------------------------

COMBINED_SCENARIOS = {
    "combined_mixed": {
        "candidates": [
            {"id": "CMB-A", "probability": 0.90, "ground_truth": "FAIL_TIMEOUT"},
            {"id": "CMB-B", "probability": 0.65, "ground_truth": "SUCCESS"},
            {"id": "CMB-C", "probability": 0.45, "ground_truth": "FAIL_SYNTAX"},
            {"id": "CMB-D", "probability": 0.30, "ground_truth": "SUCCESS"},
        ],
    },
    "combined_large": {
        "candidates": [
            {"id": f"CL-{i}", "probability": round(0.9 - i * 0.07, 2),
             "ground_truth": "SUCCESS" if i in (3, 7) else "FAIL_TIMEOUT"}
            for i in range(10)
        ],
    },
}


def run_combined_experiments(llm_fn=None) -> list[CombinedResult]:
    """Run full pipeline experiments in baseline and treatment modes."""
    results = []

    for name, scenario in COMBINED_SCENARIOS.items():
        candidates = scenario["candidates"]

        for mode, assess_fn, source in [
            ("baseline", deterministic_assessor, "deterministic"),
            ("treatment", llm_fn if llm_fn else deterministic_assessor,
             "llm" if llm_fn else "deterministic"),
        ]:
            print(f"\n  Combined: {name} ({mode}, {len(candidates)} candidates)")

            executor = Executor(mode="simulation")
            assess_start = time.time()
            for c in [candidate_from_dict(d) for d in candidates]:
                assess_fn(c)
            assess_latency = time.time() - assess_start

            start_time = time.time()
            engine_result = run_engine(
                candidates,
                assess_fn=assess_fn,
                executor=executor,
                max_attempts=2,
                mode="simulation",
            )
            total_latency = time.time() - start_time

            ranking_order = [c.id for c in engine_result.get("candidates", [])]
            results_list = engine_result.get("results", [])
            total_attempts = len(results_list)
            failed = sum(1 for r in results_list if r.get("outcome") != Outcome.SUCCESS.value)
            success = sum(1 for r in results_list if r.get("outcome") == Outcome.SUCCESS.value)
            pivots = _count_pivots(engine_result.get("logs", []))

            exec_seq = [
                {"candidate_id": r.get("candidate_id", "?"),
                 "outcome": r.get("outcome", "?")}
                for r in results_list
            ]

            result = CombinedResult(
                scenario_name=name,
                mode=mode,
                candidate_count=len(candidates),
                assessment_source=source,
                ranking_order=ranking_order,
                total_attempts=total_attempts,
                failed_attempts=failed,
                successful_validations=success,
                pivot_count=pivots,
                final_status=engine_result.get("status", "UNKNOWN"),
                assessment_latency_seconds=round(assess_latency, 4),
                total_latency_seconds=round(total_latency, 4),
                execution_sequence=exec_seq,
            )
            results.append(result)
            print(f"    Ranking: {' > '.join(ranking_order[:5])}")
            print(f"    Attempts: {total_attempts}, Success: {success}, Pivots: {pivots}")

    return results


# ---------------------------------------------------------------------------
# Phase 6: Statistical Analysis
# ---------------------------------------------------------------------------

def compute_gap1_stats(results: list[Gap1Result]) -> dict:
    if not results:
        return {}
    changed_count = sum(1 for r in results if r.ranking_changed)
    total = len(results)
    attempt_counts = [r.total_attempts for r in results]
    success_counts = [r.successful_validations for r in results]
    pivot_counts = [r.pivot_count for r in results]
    times = [r.execution_time_seconds for r in results]

    groups: dict[str, list[Gap1Result]] = {}
    for r in results:
        groups.setdefault(r.scenario_type, []).append(r)

    return {
        "total_experiments": total,
        "ranking_changed_count": changed_count,
        "ranking_changed_rate": round(changed_count / total, 4) if total else 0,
        "ranking_unchanged_count": total - changed_count,
        "attempts": _compute_basic_stats(attempt_counts),
        "successful_validations": _compute_basic_stats(success_counts),
        "pivots": _compute_basic_stats(pivot_counts),
        "execution_time": _compute_basic_stats(times),
        "by_scenario_type": {
            t: {
                "count": len(rs),
                "ranking_changed": sum(1 for r in rs if r.ranking_changed),
                "mean_attempts": round(statistics.mean([r.total_attempts for r in rs]), 4),
                "mean_success": round(statistics.mean([r.successful_validations for r in rs]), 4),
            }
            for t, rs in groups.items()
        },
    }


def _compute_basic_stats(values: list) -> dict:
    if not values:
        return {"mean": 0, "median": 0, "stdev": 0, "min": 0, "max": 0}
    return {
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "stdev": round(statistics.stdev(values), 4) if len(values) > 1 else 0,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def compute_gap2_stats(results: list[Gap2Result]) -> dict:
    if not results:
        return {}
    bounded_count = sum(1 for r in results if r.bounded)
    total = len(results)
    attempt_counts = [r.total_attempts for r in results]
    pivot_counts = [r.pivot_count for r in results]

    by_threshold = {}
    for t in [1, 2, 3, 4, 5]:
        t_results = [r for r in results if r.threshold == t]
        if t_results:
            by_threshold[str(t)] = {
                "count": len(t_results),
                "all_bounded": all(r.bounded for r in t_results),
                "mean_attempts": round(statistics.mean([r.total_attempts for r in t_results]), 4),
                "mean_pivots": round(statistics.mean([r.pivot_count for r in t_results]), 4),
                "max_attempts": max(r.total_attempts for r in t_results),
            }

    return {
        "total_experiments": total,
        "all_bounded": bounded_count == total,
        "bounded_count": bounded_count,
        "attempts": _compute_basic_stats(attempt_counts),
        "pivots": _compute_basic_stats(pivot_counts),
        "by_threshold": by_threshold,
    }


def compute_combined_stats(results: list[CombinedResult]) -> dict:
    if not results:
        return {}
    baseline = [r for r in results if r.mode == "baseline"]
    treatment = [r for r in results if r.mode == "treatment"]

    def _mode_stats(rs):
        if not rs:
            return {}
        return {
            "mean_attempts": round(statistics.mean([r.total_attempts for r in rs]), 4),
            "mean_success": round(statistics.mean([r.successful_validations for r in rs]), 4),
            "mean_pivots": round(statistics.mean([r.pivot_count for r in rs]), 4),
        }

    return {
        "total_experiments": len(results),
        "baseline_count": len(baseline),
        "treatment_count": len(treatment),
        "baseline": _mode_stats(baseline),
        "treatment": {
            **_mode_stats(treatment),
            "mean_assess_latency": round(statistics.mean([r.assessment_latency_seconds for r in treatment]), 4) if treatment else 0,
        },
    }


# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------

def save_gap1_results(results: list[Gap1Result], output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "gap1_extended.json"), "w") as f:
        json.dump([r.to_dict() for r in results], f, indent=2)
    with open(os.path.join(output_dir, "gap1_extended.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "scenario_name", "candidate_count", "scenario_type",
            "baseline_order", "treatment_order", "ranking_changed",
            "assessment_source", "total_attempts", "failed_attempts",
            "successful_validations", "pivot_count", "final_status",
            "execution_time_seconds",
        ])
        for r in results:
            writer.writerow([
                r.scenario_name, r.candidate_count, r.scenario_type,
                "|".join(r.baseline_order), "|".join(r.treatment_order),
                r.ranking_changed, r.assessment_source, r.total_attempts,
                r.failed_attempts, r.successful_validations, r.pivot_count,
                r.final_status, r.execution_time_seconds,
            ])


def save_gap2_results(results: list[Gap2Result], output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "gap2_extended.json"), "w") as f:
        json.dump([r.to_dict() for r in results], f, indent=2)
    with open(os.path.join(output_dir, "gap2_extended.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "scenario_name", "threshold", "candidate_count", "scenario_type",
            "total_attempts", "expected_max_attempts", "bounded",
            "pivot_count", "candidate_attempt_counters", "final_status",
            "execution_time_seconds",
        ])
        for r in results:
            writer.writerow([
                r.scenario_name, r.threshold, r.candidate_count, r.scenario_type,
                r.total_attempts, r.expected_max_attempts, r.bounded,
                r.pivot_count, json.dumps(r.candidate_attempt_counters),
                r.final_status, r.execution_time_seconds,
            ])


def save_llm_results(results: dict, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "llm_behavior.json"), "w") as f:
        json.dump(results, f, indent=2)


def save_combined_results(results: list[CombinedResult], output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "combined_results.json"), "w") as f:
        json.dump([r.to_dict() for r in results], f, indent=2)
    with open(os.path.join(output_dir, "combined_results.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "scenario_name", "mode", "candidate_count", "assessment_source",
            "ranking_order", "total_attempts", "failed_attempts",
            "successful_validations", "pivot_count", "final_status",
            "assessment_latency_seconds", "total_latency_seconds",
        ])
        for r in results:
            writer.writerow([
                r.scenario_name, r.mode, r.candidate_count, r.assessment_source,
                "|".join(r.ranking_order), r.total_attempts, r.failed_attempts,
                r.successful_validations, r.pivot_count, r.final_status,
                r.assessment_latency_seconds, r.total_latency_seconds,
            ])


def save_statistical_summary(gap1_stats, gap2_stats, llm_stats, combined_stats, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gap1": gap1_stats,
        "gap2": gap2_stats,
        "llm_behavior": llm_stats,
        "combined": combined_stats,
    }
    with open(os.path.join(output_dir, "statistical_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("Wave 12 — Thesis-Grade Experimental Evaluation")
    print("=" * 70)

    output_dir = "experiments/results"
    os.makedirs(output_dir, exist_ok=True)

    # Check LLM availability
    llm_fn = _get_llm_assess_fn()
    llm_available = llm_fn is not None
    print(f"\nLLM assessor (Ollama llama3.2:3b): {'AVAILABLE' if llm_available else 'NOT AVAILABLE'}")

    # Phase 2: GAP-1 Expanded
    print("\n" + "=" * 70)
    print("Phase 2: GAP-1 Expanded Experiments")
    print("=" * 70)
    gap1_results = run_gap1_experiments()
    save_gap1_results(gap1_results, output_dir)
    gap1_stats = compute_gap1_stats(gap1_results)
    print(f"\nGAP-1 Summary: {gap1_stats['ranking_changed_count']}/{gap1_stats['total_experiments']} scenarios changed ranking")

    # Phase 3: LLM Behavior
    print("\n" + "=" * 70)
    print("Phase 3: Real LLM Behavior Evaluation")
    print("=" * 70)
    llm_results = run_llm_behavior_experiments(repetitions=5)
    save_llm_results(llm_results, output_dir)
    llm_stats = llm_results.get("summary", {})
    if llm_results["available"]:
        print(f"\nLLM Summary: consistent={llm_stats.get('all_consistent')}, "
              f"fallback_rate={llm_stats.get('fallback_rate')}, "
              f"avg_latency={llm_stats.get('overall_latency', {}).get('mean')}s")

    # Phase 4: GAP-2 Expanded
    print("\n" + "=" * 70)
    print("Phase 4: GAP-2 Expanded Experiments")
    print("=" * 70)
    gap2_results = run_gap2_experiments()
    save_gap2_results(gap2_results, output_dir)
    gap2_stats = compute_gap2_stats(gap2_results)
    print(f"\nGAP-2 Summary: all_bounded={gap2_stats['all_bounded']}, "
          f"{gap2_stats['bounded_count']}/{gap2_stats['total_experiments']} bounded")

    # Phase 5: Combined
    print("\n" + "=" * 70)
    print("Phase 5: Combined Full-Pipeline Experiments")
    print("=" * 70)
    combined_results = run_combined_experiments(llm_fn=llm_fn)
    save_combined_results(combined_results, output_dir)
    combined_stats = compute_combined_stats(combined_results)
    print(f"\nCombined Summary: {combined_stats['total_experiments']} experiments")

    # Phase 6: Statistical Summary
    print("\n" + "=" * 70)
    print("Phase 6: Statistical Analysis")
    print("=" * 70)
    save_statistical_summary(gap1_stats, gap2_stats, llm_stats, combined_stats, output_dir)
    print(f"\nStatistical summary saved to {output_dir}/statistical_summary.json")

    total_experiments = len(gap1_results) + len(gap2_results) + len(combined_results)
    if llm_results["available"]:
        total_experiments += llm_stats.get("total_assessments", 0)

    print("\n" + "=" * 70)
    print("Wave 12 Complete")
    print("=" * 70)
    print(f"  GAP-1 experiments: {len(gap1_results)}")
    print(f"  GAP-2 experiments: {len(gap2_results)}")
    print(f"  Combined experiments: {len(combined_results)}")
    print(f"  LLM behavior assessments: {llm_stats.get('total_assessments', 0) if llm_results['available'] else 'N/A'}")
    print(f"  Total experiment runs: {total_experiments}")
    print(f"  Results saved to: {output_dir}/")


if __name__ == "__main__":
    main()