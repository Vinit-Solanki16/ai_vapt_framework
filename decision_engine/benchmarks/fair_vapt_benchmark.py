"""FAIR VAPT BENCHMARK: 4-agent ablation on the FULL VAPT corpus.

Re-runs the same 4-agent fair protocol from fair_benchmark.py on the complete
data/poc_corpus/labels.json (all 12 CVEs) instead of the curated n=3 in
tests/evaluate.py (TRACK0 frozen).  Uses live EPSS from
datasets/epss_corpus_enrichment.json for probability.

Cap-asymmetry bias (B2) is fixed: all 4 agents run under IDENTICAL cap T.
Gap-1 (priority) vs Gap-2 (pivot) are decomposed via the 4-agent ablation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from decision_engine.adapters.vapt_adapter import (
    vapt_candidates_from_corpus,
    CORPUS_DIR,
    LABELS,
    EPSS_ENRICH,
)
from decision_engine.benchmarks.fair_benchmark import (
    simulate_agent,
    _priority_order,
    _ci95,
    make_ranker,
    priority_score_from,
    _true_quality_rank,
    _QUALITY_NUMERIC,
    _spearman,
)
from decision_engine.core.schemas import Outcome, QualityRank


# ---------------------------------------------------------------------------
# Corpus loader (with fallback for missing files)
# ---------------------------------------------------------------------------

def load_corpus() -> list:
    """Load full VAPT corpus candidates, or return minimal fallback."""
    try:
        cands = vapt_candidates_from_corpus()
    except Exception:
        # Fallback: construct from labels directly
        import json, os
        labels_path = Path(__file__).resolve().parent.parent.parent / "data" / "poc_corpus" / "labels.json"
        epss_path = Path(__file__).resolve().parent.parent.parent / "datasets" / "epss_corpus_enrichment.json"

        labels = {}
        epss = {}
        if labels_path.exists():
            labels = json.loads(labels_path.read_text())
        if epss_path.exists():
            epss = json.loads(epss_path.read_text())

        _OUTCOME_MAP = {
            "success": Outcome.SUCCESS,
            "fail_timeout": Outcome.FAIL_TIMEOUT,
            "fail_syntax": Outcome.FAIL_SYNTAX,
            "fail_dependency": Outcome.FAIL_DEPENDENCY,
        }

        from decision_engine.core.schemas import ActionCandidate
        cands = []
        for cve, meta in labels.items():
            o = _OUTCOME_MAP.get(str(meta.get("outcome", "")).lower(), Outcome.FAIL_TIMEOUT)
            cands.append(ActionCandidate(
                id=cve,
                probability=float(epss.get(cve, 0.0)),
                ground_truth=o,
            ))

    return cands


# ---------------------------------------------------------------------------
# Ranker for VAPT (same as fair_benchmark)
# ---------------------------------------------------------------------------

ranker = make_ranker("perfect")
_cands = None   # cached corpus candidates


def _get_corpus():
    global _cands
    if _cands is None:
        _cands = load_corpus()
    return _cands


# ---------------------------------------------------------------------------
# Run 4-agent fair protocol
# ---------------------------------------------------------------------------

CAPS = [1, 2, 3, 5]
N_SEEDS = 30
MAX_TOTAL_MULT = 4   # mirror fair_benchmark


def run_agent_on_corpus(agent_name: str, cap_T: int, seed: int, candidates: list) -> dict:
    """Run one agent on the VAPT corpus."""
    import random

    if agent_name == "DUMB":
        order_fn = lambda cs: _shuffled(cs, seed)
        abandon = False
    elif agent_name == "PIVOT-ONLY":
        order_fn = lambda cs: _shuffled(cs, seed)
        abandon = True
    elif agent_name == "PRIORITY-ONLY":
        order_fn = lambda cs: _priority_order(cs)
        abandon = False
    elif agent_name == "SMART":
        order_fn = lambda cs: _priority_order(cs)
        abandon = True
    else:
        raise ValueError(f"Unknown agent: {agent_name}")

    rng = random.Random(seed)
    max_total = len(candidates) * cap_T * MAX_TOTAL_MULT
    metrics = simulate_agent(
        candidates, order_fn, abandon, cap_T,
        max_total, ranker, rng,
    )
    return metrics


def _shuffled(candidates: list, seed: int):
    """Return a deterministically shuffled copy."""
    import random
    rng = random.Random(seed)
    copy = list(candidates)
    rng.shuffle(copy)
    return copy


def run_vapt_benchmark(
    caps: list = CAPS,
    n_seeds: int = N_SEEDS,
    output_jsonl: str = None,
    verbose: bool = True,
):
    """Run fair benchmark on the full VAPT corpus."""
    candidates = _get_corpus()
    n_cands = len(candidates)
    true_successes = sum(1 for c in candidates if c.ground_truth == Outcome.SUCCESS)

    if verbose:
        print("FAIR VAPT BENCHMARK — full corpus")
        print(f"  Corpus       : {n_cands} CVEs")
        print(f"  True success : {true_successes} ({true_successes/n_cands*100:.1f}%)")
        print(f"  Caps T       : {caps}")
        print(f"  Seeds        : {n_seeds}")
        print()

    raw_rows = []
    for seed in range(n_seeds):
        for cap_T in caps:
            for agent in ["DUMB", "PIVOT-ONLY", "PRIORITY-ONLY", "SMART"]:
                m = run_agent_on_corpus(agent, cap_T, seed, candidates)
                rho = _spearman_corpus(candidates, ranker)
                row = {
                    "corpus": "vapt_full",
                    "n_candidates": n_cands,
                    "true_successes": true_successes,
                    "seed": seed,
                    "cap_T": cap_T,
                    "agent": agent,
                    "requests": m["requests"],
                    "wasted_requests": m["wasted_requests"],
                    "found_success_pct": m["found_success_pct"],
                    "loop_events": m["loop_events"],
                    "spearman_rho": rho,
                }
                raw_rows.append(row)

    if output_jsonl:
        with open(output_jsonl, "w") as fh:
            for row in raw_rows:
                fh.write(json.dumps(row) + "\n")
        if verbose:
            print(f"JSONL → {output_jsonl} ({len(raw_rows)} rows)")

    # Aggregate
    from collections import defaultdict
    groups = defaultdict(lambda: defaultdict(list))
    for row in raw_rows:
        g = f"{row['cap_T']}|{row['agent']}"
        groups[g]["requests"].append(row["requests"])
        groups[g]["wasted_requests"].append(row["wasted_requests"])
        groups[g]["found_success_pct"].append(row["found_success_pct"])
        groups[g]["loop_events"].append(row["loop_events"])

    agg = {}
    for gkey, metrics in groups.items():
        cap_T_s, agent = gkey.split("|")
        cap_T = int(cap_T_s)
        agg[(cap_T, agent)] = {k: _ci95(v) for k, v in metrics.items()}

    if verbose:
        print_table(agg, candidates, true_successes)

    return {"raw": raw_rows, "aggregated": agg, "n_rows": len(raw_rows)}


def _spearman_corpus(candidates: list, ranker_fn) -> float:
    """Spearman rho between assigned priority and true quality on corpus."""
    true_vals = [_QUALITY_NUMERIC[_true_quality_rank(c)] for c in candidates]
    assigned_vals = [priority_score_from(c, ranker_fn) for c in candidates]
    return _spearman(assigned_vals, true_vals)


def print_table(agg: dict, candidates: list, true_successes: int):
    """Print summary table."""
    caps = sorted(set(k[0] for k in agg))
    n = len(candidates)

    print(f"{'='*75}")
    print(f"  VAPT Full Corpus — {n} CVEs, {true_successes} true successes")
    print(f"{'='*75}")
    print(f"\n  {'Cap':>4} {'Agent':<14} {'Requests':>10} {'Wasted':>8} "
          f"{'Succ%':>7} {'Loops':>6} {'Rho':>6}")
    print(f"  {'-'*58}")
    for cap_T in caps:
        for agent in ["DUMB", "PIVOT-ONLY", "PRIORITY-ONLY", "SMART"]:
            key = (cap_T, agent)
            d = agg.get(key)
            if d is None:
                continue
            req_m = d["requests"][0]
            was_m = d["wasted_requests"][0]
            suc_m = d["found_success_pct"][0]
            loop_m = d["loop_events"][0]
            print(f"  {cap_T:>4} {agent:<14} {req_m:>10.1f} {was_m:>8.1f} "
                  f"{suc_m:>6.1f}% {loop_m:>6.1f}")

    print(f"\n  Decomposition (identical cap T):")
    print(f"  {'T':>4} {'priority=DUMB-PRIORITY':>22} "
          f"{'pivot=PRIORITY-SMART':>20} {'total':>8}")
    print(f"  {'-'*58}")
    for cap_T in caps:
        decomp = _decompose_vapt(agg, cap_T)
        pc = decomp.get("priority_component")
        pic = decomp.get("pivot_component")
        tg = decomp.get("total_gain")
        pc_s = f"{pc:+.1f}" if pc is not None else "N/A"
        pic_s = f"{pic:+.1f}" if pic is not None else "N/A"
        tg_s = f"{tg:+.1f}" if tg is not None else "N/A"
        print(f"  {cap_T:>4} {pc_s:>22} {pic_s:>20} {tg_s:>8}")


def _decompose_vapt(agg: dict, cap_T: int) -> dict:
    dumb = agg.get((cap_T, "DUMB"))
    prio_only = agg.get((cap_T, "PRIORITY-ONLY"))
    smart = agg.get((cap_T, "SMART"))

    prio_comp = None
    pivot_comp = None
    total_gain = None

    if dumb and prio_only:
        prio_comp = dumb["requests"][0] - prio_only["requests"][0]
    if prio_only and smart:
        pivot_comp = prio_only["requests"][0] - smart["requests"][0]
    if prio_comp is not None and pivot_comp is not None:
        total_gain = prio_comp + pivot_comp

    return {
        "priority_component": prio_comp,
        "pivot_component": pivot_comp,
        "total_gain": total_gain,
        "dumb_requests": dumb["requests"][0] if dumb else None,
        "prio_only_requests": prio_only["requests"][0] if prio_only else None,
        "smart_requests": smart["requests"][0] if smart else None,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="FAIR VAPT benchmark on full corpus")
    parser.add_argument("--seeds", type=int, default=N_SEEDS, help=f"seeds per condition (≥{N_SEEDS})")
    parser.add_argument("--caps", nargs="+", type=int, default=CAPS, help="cap T values")
    parser.add_argument("--jsonl", type=str, default=None, help="write results to JSONL file")
    parser.add_argument("--quiet", action="store_true", help="suppress table output")
    args = parser.parse_args()

    result = run_vapt_benchmark(
        caps=args.caps,
        n_seeds=args.seeds,
        output_jsonl=args.jsonl,
        verbose=not args.quiet,
    )
    print(f"\nDone. {result['n_rows']} raw rows.")


if __name__ == "__main__":
    main()
