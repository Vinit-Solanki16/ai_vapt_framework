#!/usr/bin/env python3
"""Phase 33A — controlled local-LLM A/B experiment (llama3.2:3b vs qwen2.5:3b).

Compares two local Ollama models as the PRE-EXECUTION exploit-quality assessor
(GAP-1) behind the existing production assessor path.

Controlled variables (identical for both arms — no per-model prompts):
  - candidate corpus (8 real CVEs, same order, same probabilities)
  - system + human prompt  (core.exploit_assessor, unchanged)
  - temperature 0.1        (core.exploit_assessor.get_llm, unchanged)
  - Pydantic schema        (core.schemas.ExploitAssessment, unchanged)
  - parsing path           (assess_exploit_quality, unchanged)
  - repetitions            (5, matching the historical llama baseline)
  - timeout policy         (60s wall clock per call, both arms)
  - environment            (same host, same Ollama, same venv)

Measures (reported SEPARATELY, never conflated):
  A. Assessment reliability  - valid structured outputs / fallbacks
  B. Structured-output reliability - schema/parse failures
  C. Consistency             - per-candidate rank agreement across reps
  D. Latency                 - mean/median/min/max
  E. Ranking influence       - GAP-1 order change vs no-assessment baseline
  F. Model agreement         - llama vs qwen per candidate

Does NOT measure "exploit success rate": the evaluator has no real exploit
ground truth for these scanner-derived findings. No such claim is made.

Read-only w.r.t. decision_engine/core/ and decision_engine/benchmarks/.
Never overwrites an existing thesis baseline artifact.
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decision_engine.core.engine import rank_candidates
from decision_engine.core.schemas import ActionCandidate, Outcome
from vapt_platform.assessment import create_assessor

# --- Frozen experiment configuration ---------------------------------------
MODELS = ["llama3.2:3b", "qwen2.5:3b"]
REPETITIONS = 5
PER_CALL_TIMEOUT_S = 60.0

# Identical to experiments/wave12_thesis_evaluation.py::LLM_TEST_CANDIDATES so
# the llama arm stays compatible with the historical baseline.
CANDIDATES = [
    {"id": "CVE-2021-44228", "probability": 0.95, "ground_truth": "SUCCESS"},
    {"id": "CVE-2017-0144", "probability": 0.55, "ground_truth": "SUCCESS"},
    {"id": "CVE-2023-38408", "probability": 0.30, "ground_truth": "FAIL_TIMEOUT"},
    {"id": "CVE-2022-22965", "probability": 0.45, "ground_truth": "FAIL_SYNTAX"},
    {"id": "CVE-2020-1472", "probability": 0.70, "ground_truth": "SUCCESS"},
    {"id": "CVE-2021-26855", "probability": 0.65, "ground_truth": "SUCCESS"},
    {"id": "CVE-2019-0708", "probability": 0.50, "ground_truth": "FAIL_TIMEOUT"},
    {"id": "CVE-2022-1388", "probability": 0.75, "ground_truth": "SUCCESS"},
]

PROMPT_VERSION = "core.exploit_assessor.SYSTEM_PROMPT (v1, unchanged)"
TEMPERATURE = 0.1

# Measured from `ollama show <model>` on the experiment host (not assumed).
MODEL_PROVENANCE = {
    "llama3.2:3b": {
        "architecture": "llama", "parameters": "3.2B",
        "context_length": 131072, "quantization": "Q4_K_M",
        "role": "official thesis baseline / production default",
    },
    "qwen2.5:3b": {
        "architecture": "qwen2", "parameters": "3.1B",
        "context_length": 32768, "quantization": "Q4_K_M",
        "role": "experimental comparison arm (opt-in only)",
    },
}

OBSERVATIONS_CSV = "experiments/results/llm_model_comparison_observations.csv"


def _make_candidate(d: dict) -> ActionCandidate:
    return ActionCandidate(
        id=d["id"],
        probability=d["probability"],
        ground_truth=Outcome(d["ground_truth"]),
    )


def _no_assessment_order() -> list[str]:
    """GAP-1 baseline: rank with NO assessment (quality None for all)."""
    cands = [_make_candidate(d) for d in CANDIDATES]
    return [c.id for c in rank_candidates(cands)]


def _assessed_order(ranks: dict[str, str]) -> list[str]:
    """GAP-1 treatment: rank AFTER assessment (assessment precedes ranking)."""
    cands = []
    for d in CANDIDATES:
        c = _make_candidate(d)
        r = ranks.get(d["id"])
        if r:
            from decision_engine.core.schemas import QualityRank

            c.quality_rank = QualityRank(r)
            c.assessed = True
        cands.append(c)
    return [c.id for c in rank_candidates(cands)]


def run_arm(model_name: str) -> dict:
    print(f"\n{'=' * 72}\nARM: {model_name}\n{'=' * 72}", flush=True)
    assessor = create_assessor(mode="ai", provider="ollama", model_name=model_name)

    records: list[dict] = []
    per_rep_ranks: list[dict[str, str]] = []

    for rep in range(REPETITIONS):
        print(f"  repetition {rep + 1}/{REPETITIONS}", flush=True)
        rep_ranks: dict[str, str] = {}
        for d in CANDIDATES:
            cand = _make_candidate(d)
            t0 = time.perf_counter()
            try:
                res = assessor(cand)
                dt = time.perf_counter() - t0
                if dt > PER_CALL_TIMEOUT_S:
                    raise TimeoutError(f"exceeded {PER_CALL_TIMEOUT_S}s")
                rep_ranks[d["id"]] = res.quality_rank.value
                records.append({
                    "model": model_name,
                    "repetition": rep,
                    "candidate_id": d["id"],
                    "probability": d["probability"],
                    "ground_truth": d["ground_truth"],
                    "quality_rank": res.quality_rank.value,
                    "source": res.source,
                    "provider": res.provider,
                    "reported_model": res.model,
                    "fallback": res.fallback,
                    "latency_s": round(dt, 4),
                    "valid_structured": (res.source == "llm"),
                    "error": res.error,
                    "reasoning_len": len(res.reasoning or ""),
                })
            except Exception as e:  # noqa: BLE001
                dt = time.perf_counter() - t0
                records.append({
                    "model": model_name,
                    "repetition": rep,
                    "candidate_id": d["id"],
                    "probability": d["probability"],
                    "ground_truth": d["ground_truth"],
                    "quality_rank": None,
                    "source": "error",
                    "provider": "ollama",
                    "reported_model": model_name,
                    "fallback": True,
                    "latency_s": round(dt, 4),
                    "valid_structured": False,
                    "error": f"{type(e).__name__}: {e}"[:200],
                    "reasoning_len": 0,
                })
        per_rep_ranks.append(rep_ranks)
        print(f"    ranks: {json.dumps(rep_ranks)}", flush=True)

    return {"model": model_name, "records": records, "per_rep_ranks": per_rep_ranks}


def load_arm_from_observations(model_name: str) -> dict:
    """Rebuild an arm from the saved per-observation CSV (no re-inference).

    Lets the summary/metadata be regenerated deterministically without
    re-running the models, so artifacts are never hand-edited.
    """
    records: list[dict] = []
    with open(OBSERVATIONS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if row["model"] != model_name:
                continue
            row["repetition"] = int(row["repetition"])
            row["probability"] = float(row["probability"])
            row["latency_s"] = float(row["latency_s"])
            row["reasoning_len"] = int(row["reasoning_len"])
            row["fallback"] = str(row["fallback"]) == "True"
            row["valid_structured"] = str(row["valid_structured"]) == "True"
            row["quality_rank"] = row["quality_rank"] or None
            records.append(row)
    reps = sorted({r["repetition"] for r in records})
    per_rep_ranks = [
        {r["candidate_id"]: r["quality_rank"] for r in records if r["repetition"] == rep}
        for rep in reps
    ]
    return {"model": model_name, "records": records, "per_rep_ranks": per_rep_ranks}


def summarise(arm: dict) -> dict:
    model = arm["model"]
    records = arm["records"]
    n = len(records)

    valid = sum(1 for r in records if r["valid_structured"])
    fallback = sum(1 for r in records if r["fallback"])
    schema_parse_fail = sum(
        1 for r in records
        if not r["valid_structured"] and r["source"] == "error"
    )
    lat = [r["latency_s"] for r in records]
    llm_lat = [r["latency_s"] for r in records if r["valid_structured"]]

    # Quality distribution
    dist = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NONE": 0}
    for r in records:
        dist[r["quality_rank"] or "NONE"] += 1

    # Per-candidate consistency across repetitions
    consistency = {}
    for d in CANDIDATES:
        ranks = [r["quality_rank"] for r in records
                 if r["candidate_id"] == d["id"] and r["quality_rank"]]
        if not ranks:
            consistency[d["id"]] = {
                "ranks": [], "mode": None, "consistent": False,
                "agreement": 0.0,
            }
            continue
        mode = statistics.mode(ranks)
        agree = sum(1 for x in ranks if x == mode) / len(ranks)
        consistency[d["id"]] = {
            "ranks": ranks,
            "mode": mode,
            "consistent": len(set(ranks)) == 1,
            "agreement": round(agree, 4),
        }

    # GAP-1 ordering: majority rank per candidate -> assessed order
    majority = {cid: c["mode"] for cid, c in consistency.items() if c["mode"]}
    assessed_order = _assessed_order(majority)

    return {
        "model": model,
        "provider": "ollama",
        "temperature": TEMPERATURE,
        "prompt_version": PROMPT_VERSION,
        "candidates": len(CANDIDATES),
        "repetitions": REPETITIONS,
        "total_assessments": n,
        "valid_structured": valid,
        "valid_output_rate": round(valid / n, 4) if n else 0.0,
        "fallback_count": fallback,
        "fallback_rate": round(fallback / n, 4) if n else 0.0,
        "schema_or_parse_failures": schema_parse_fail,
        "latency": {
            "mean": round(statistics.mean(lat), 4) if lat else 0.0,
            "median": round(statistics.median(lat), 4) if lat else 0.0,
            "min": round(min(lat), 4) if lat else 0.0,
            "max": round(max(lat), 4) if lat else 0.0,
            "mean_llm_only": round(statistics.mean(llm_lat), 4) if llm_lat else 0.0,
        },
        "quality_distribution": dist,
        "consistency_per_candidate": consistency,
        "all_candidates_consistent": all(
            c["consistent"] for c in consistency.values()
        ),
        "mean_consistency_agreement": round(
            statistics.mean(c["agreement"] for c in consistency.values()), 4
        ) if consistency else 0.0,
        "majority_ranks": majority,
        "assessed_order": assessed_order,
    }


def main() -> int:
    os.makedirs("experiments/results", exist_ok=True)
    from_obs = "--from-observations" in sys.argv
    print("Phase 33A A/B experiment")
    print(f"models={MODELS} reps={REPETITIONS} candidates={len(CANDIDATES)}")
    print(f"timeout={PER_CALL_TIMEOUT_S}s  temperature={TEMPERATURE}")

    baseline_order = _no_assessment_order()
    print(f"\nNo-assessment GAP-1 order (baseline): {baseline_order}")

    if from_obs:
        print("(reusing saved observations — no new inference)")
        arms = [load_arm_from_observations(m) for m in MODELS]
    else:
        arms = [run_arm(m) for m in MODELS]
    summaries = [summarise(a) for a in arms]
    by_model = {s["model"]: s for s in summaries}

    # --- Inter-model agreement (per candidate, over paired reps) ------------
    agreement = {}
    pair_total = 0
    pair_match = 0
    for d in CANDIDATES:
        cid = d["id"]
        a_ranks = [r["quality_rank"] for r in arms[0]["records"] if r["candidate_id"] == cid]
        b_ranks = [r["quality_rank"] for r in arms[1]["records"] if r["candidate_id"] == cid]
        pairs = list(zip(a_ranks, b_ranks))
        matches = sum(1 for x, y in pairs if x == y)
        pair_total += len(pairs)
        pair_match += matches
        agreement[cid] = {
            "llama": a_ranks,
            "qwen": b_ranks,
            "matches": matches,
            "pairs": len(pairs),
            "agreement": round(matches / len(pairs), 4) if pairs else 0.0,
        }
    overall_agreement = round(pair_match / pair_total, 4) if pair_total else 0.0

    # --- Ranking influence --------------------------------------------------
    ranking = {}
    for s in summaries:
        order = s["assessed_order"]
        changed = order != baseline_order
        moved = sum(
            1 for i, cid in enumerate(order)
            if i >= len(baseline_order) or baseline_order[i] != cid
        )
        ranking[s["model"]] = {
            "assessed_order": order,
            "baseline_order": baseline_order,
            "order_changed_vs_no_assessment": changed,
            "positions_moved": moved,
        }
    llama_order = by_model[MODELS[0]]["assessed_order"]
    qwen_order = by_model[MODELS[1]]["assessed_order"]
    ranking["inter_model_order_identical"] = llama_order == qwen_order
    ranking["inter_model_positions_moved"] = sum(
        1 for i, cid in enumerate(llama_order)
        if i >= len(qwen_order) or qwen_order[i] != cid
    )

    result = {
        "experiment": "phase33a_llm_model_comparison",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "models": MODELS,
            "baseline_model": MODELS[0],
            "experimental_model": MODELS[1],
            "model_provenance": MODEL_PROVENANCE,
            "provider": "ollama",
            "temperature": TEMPERATURE,
            "prompt_version": PROMPT_VERSION,
            "schema": "core.schemas.ExploitAssessment",
            "candidates": [d["id"] for d in CANDIDATES],
            "repetitions": REPETITIONS,
            "per_call_timeout_s": PER_CALL_TIMEOUT_S,
            "candidate_order": "frozen (identical for both arms)",
            "observations_source": (
                "experiments/results/llm_model_comparison_observations.csv"
            ),
            "effectiveness_metric": (
                "NOT measured: no real exploit ground truth exists for these "
                "scanner-derived findings. Reported separately as reliability, "
                "structured-output reliability, consistency, latency, ranking "
                "influence, and model agreement."
            ),
        },
        "summaries": summaries,
        "inter_model_agreement": {
            "per_candidate": agreement,
            "overall_agreement": overall_agreement,
            "paired_observations": pair_total,
        },
        "ranking_influence": ranking,
    }

    with open("experiments/results/llm_model_comparison.json", "w") as f:
        json.dump(result, f, indent=2)

    # --- CSV: one row per model summary + per-observation rows ---------------
    with open("experiments/results/llm_model_comparison.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "model", "provider", "temperature", "prompt_version", "candidates",
            "repetitions", "total_assessments", "valid_output_rate",
            "fallback_rate", "schema_or_parse_failures", "mean_latency_s",
            "median_latency_s", "min_latency_s", "max_latency_s",
            "mean_consistency_agreement", "all_candidates_consistent",
            "assessed_order", "order_changed_vs_no_assessment",
            "inter_model_overall_agreement",
        ])
        for s in summaries:
            w.writerow([
                s["model"], s["provider"], s["temperature"], s["prompt_version"],
                s["candidates"], s["repetitions"], s["total_assessments"],
                s["valid_output_rate"], s["fallback_rate"],
                s["schema_or_parse_failures"], s["latency"]["mean"],
                s["latency"]["median"], s["latency"]["min"], s["latency"]["max"],
                s["mean_consistency_agreement"], s["all_candidates_consistent"],
                "|".join(s["assessed_order"]),
                ranking[s["model"]]["order_changed_vs_no_assessment"],
                overall_agreement,
            ])

    # --- Per-observation CSV -------------------------------------------------
    with open("experiments/results/llm_model_comparison_observations.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(arms[0]["records"][0].keys()))
        w.writeheader()
        for a in arms:
            for r in a["records"]:
                w.writerow(r)

    print("\n" + "=" * 72)
    print("RESULTS")
    print("=" * 72)
    for s in summaries:
        print(f"\n{s['model']}")
        print(f"  valid output rate        : {s['valid_output_rate']:.2%}")
        print(f"  fallback rate            : {s['fallback_rate']:.2%}")
        print(f"  schema/parse failures    : {s['schema_or_parse_failures']}")
        print(f"  latency mean/median      : {s['latency']['mean']:.3f}s / {s['latency']['median']:.3f}s")
        print(f"  latency min/max          : {s['latency']['min']:.3f}s / {s['latency']['max']:.3f}s")
        print(f"  quality distribution     : {json.dumps(s['quality_distribution'])}")
        print(f"  consistency agreement    : {s['mean_consistency_agreement']:.2%}")
        print(f"  assessed order           : {s['assessed_order']}")
    print(f"\ninter-model agreement      : {overall_agreement:.2%} over {pair_total} paired obs")
    print(f"inter-model order identical: {ranking['inter_model_order_identical']}")
    print(f"llama order                : {llama_order}")
    print(f"qwen  order                : {qwen_order}")
    print("\nwrote experiments/results/llm_model_comparison.{csv,json}")
    print("wrote experiments/results/llm_model_comparison_observations.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
