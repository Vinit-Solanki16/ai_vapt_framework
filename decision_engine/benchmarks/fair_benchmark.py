"""FAIR BENCHMARK: decomposed Gap-1 (priority) vs Gap-2 (pivot) ablation.

Implements the experiment design from docs/roadmap/external_reviews/T-DE-BENCH_REVIEW.md §3.
Every metric is computed under an IDENTICAL per-candidate cap T — the cap-asymmetry
biases (B1/B2) found by T-DE-BENCH are eliminated.

Four agents, all with the same cap T ∈ {1, 2, 3, 5}:

  DUMB          : random order, no scoring, no abandonment, cap T per visit
  PIVOT-ONLY    : random order, abandon after T failures, cap T per visit
  PRIORITY-ONLY : priority order, no abandonment, cap T per visit
  SMART         : priority order, abandon after T failures, cap T per visit

Decomposition:
  priority_component = DUMB − PRIORITY-ONLY   (ordering value, both revisit)
  pivot_component    = PRIORITY-ONLY − SMART   (abandonment value, both priority order)

No wall-clock timing; reproducible seeds; >=30 seeds per condition; mean ± 95% CI;
JSONL dump.  Fixes B1–B9 (cap asymmetry, no ablation, tiny samples, no seeds/CIs).
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from decision_engine.core.schemas import ActionCandidate, Outcome, QualityRank


# ---------------------------------------------------------------------------
# Synthetic family generator
# ---------------------------------------------------------------------------

def make_family(kind: str, N: int, seed: int) -> List[ActionCandidate]:
    """Generate N ActionCandidates for regime `kind` (seeded, N >= 50).

    Regimes:
      many_success   : ~80% true SUCCESS
      sparse_success : ~10% true SUCCESS
      all_fail       : 0% SUCCESS
      long_tail      : power-law probabilities; ~20% SUCCESS
      correlated     : high prob ↔ high quality ↔ SUCCESS
      anticorrelated : high prob ↔ LOW quality ↔ FAIL
    """
    rng = random.Random(seed)
    cands: List[ActionCandidate] = []
    probs = _make_probabilities(kind, N, rng)

    for i in range(N):
        cid = f"F-{kind}-{i:03d}"
        p = probs[i]

        # Ground truth: correlate with probability for correlated/anticorrelated
        gt, true_qrank = _ground_truth_for(kind, i, N, rng, p)

        cands.append(ActionCandidate(
            id=cid,
            probability=p,
            quality_rank=true_qrank,   # assessable quality signal
            ground_truth=gt,
        ))

    return cands


def _make_probabilities(kind: str, N: int, rng: random.Random) -> List[float]:
    if kind == "long_tail":
        # Zipf-like: 1/rank^alpha
        probs = [1.0 / ((i + 1) ** 1.2) for i in range(N)]
        s = sum(probs)
        return [p / s * 0.95 for p in probs]  # normalise to [0, 0.95]
    # uniform random for the rest
    return [rng.uniform(0.1, 0.99) for _ in range(N)]


def _ground_truth_for(
    kind: str, idx: int, N: int, rng: random.Random, prob: float
) -> Tuple[Outcome, QualityRank]:
    """Return (ground_truth, true_quality_rank) for this candidate."""
    if kind == "many_success":
        success = rng.random() < 0.80
    elif kind == "sparse_success":
        success = rng.random() < 0.10
    elif kind == "all_fail":
        success = False
    elif kind == "long_tail":
        success = rng.random() < 0.20
    elif kind == "correlated":
        # high probability → success
        success = rng.random() < prob
    elif kind == "anticorrelated":
        # low probability → success, high prob → fail
        success = rng.random() < (1.0 - prob)
    else:
        success = rng.random() < 0.3

    gt = Outcome.SUCCESS if success else Outcome.FAIL_TIMEOUT
    # True quality rank correlates with ground truth for oracle assessor
    true_qrank = QualityRank.HIGH if success else QualityRank.LOW
    return gt, true_qrank


# ---------------------------------------------------------------------------
# Rankers (scoring / assessor functions)
# ---------------------------------------------------------------------------

# Map quality to numeric for Spearman correlation
_QUALITY_NUMERIC = {QualityRank.HIGH: 2, QualityRank.MEDIUM: 1, QualityRank.LOW: 0}


def _spearman(vals_a: List[float], vals_b: List[float]) -> float:
    """Pearson r on ranks ≈ Spearman rho (ties averaged)."""
    n = len(vals_a)
    if n < 2:
        return 1.0
    ranks_a = _rank_data(vals_a)
    ranks_b = _rank_data(vals_b)
    mean_a = sum(ranks_a) / n
    mean_b = sum(ranks_b) / n
    cov = sum((ra - mean_a) * (rb - mean_b) for ra, rb in zip(ranks_a, ranks_b))
    std_a = math.sqrt(sum((r - mean_a) ** 2 for r in ranks_a))
    std_b = math.sqrt(sum((r - mean_b) ** 2 for r in ranks_b))
    if std_a == 0 or std_b == 0:
        return 0.0
    return cov / (std_a * std_b)


def _rank_data(vals: List[float]) -> List[float]:
    """Average-rank transform (handles ties)."""
    sorted_vals = sorted(enumerate(vals), key=lambda x: x[1])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(sorted_vals):
        j = i
        while j < len(sorted_vals) - 1 and sorted_vals[j + 1][1] == sorted_vals[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[sorted_vals[k][0]] = avg_rank
        i = j + 1
    return ranks


def _true_quality_rank(c: ActionCandidate) -> QualityRank:
    """Oracle: best guess at true quality from ground truth."""
    if c.ground_truth == Outcome.SUCCESS:
        return QualityRank.HIGH
    return QualityRank.LOW


def make_ranker(
    kind: str,
    error_rate: float = 0.0,
    llm_accuracy: float = 0.8,
) -> Callable[[ActionCandidate], QualityRank]:
    """Return a scorer (Gap-1 assessor function) of type ActionCandidate → QualityRank.

    Kinds:
      perfect   : ground-truth oracle (deterministic_assessor logic)
      noisy     : flips to random rank with probability `error_rate` (0.0–1.0)
      heuristic : probability-only (quality always MEDIUM)
      llm_stub  : correct with probability `llm_accuracy`, else random
    """
    rng = random.Random(42)   # deterministic ranker behaviour (independent of sim rng)

    if kind == "perfect":
        def _rank(c: ActionCandidate) -> QualityRank:
            return _true_quality_rank(c)
        return _rank

    if kind == "heuristic":
        def _rank(c: ActionCandidate) -> QualityRank:
            # pure probability signal, no quality
            return QualityRank.MEDIUM
        return _rank

    if kind == "noisy":
        all_ranks = [QualityRank.HIGH, QualityRank.MEDIUM, QualityRank.LOW]

        def _rank(c: ActionCandidate) -> QualityRank:
            if rng.random() < error_rate:
                return rng.choice(all_ranks)
            return _true_quality_rank(c)
        return _rank

    if kind == "llm_stub":
        all_ranks = [QualityRank.HIGH, QualityRank.MEDIUM, QualityRank.LOW]

        def _rank(c: ActionCandidate) -> QualityRank:
            if rng.random() < llm_accuracy:
                return _true_quality_rank(c)
            return rng.choice(all_ranks)
        return _rank

    raise ValueError(f"Unknown ranker kind: {kind!r}")


def priority_score_from(c: ActionCandidate, ranker: Callable) -> float:
    """Compute priority_score as the engine does (prob * quality factor)."""
    q = ranker(c)
    u = _QUALITY_NUMERIC.get(q, 0) / 2.0   # 0→0, 1→0.5, 2→1.0
    return round(c.probability * (0.5 + 0.5 * u), 4)


# ---------------------------------------------------------------------------
# Agent simulations (mirrors engine behaviour, parameterized by order + abandon)
# ---------------------------------------------------------------------------

def _exec_attempt(c: ActionCandidate) -> Outcome:
    """Simulate one attempt on a candidate (ground-truth resolution)."""
    return c.ground_truth or Outcome.FAIL_TIMEOUT


def simulate_agent(
    candidates: List[ActionCandidate],
    order_fn: Callable[[List[ActionCandidate]], List[ActionCandidate]],
    abandon: bool,
    cap_T: int,
    max_total: int,
    ranker: Callable[[ActionCandidate], QualityRank],
    rng: random.Random,
) -> dict:
    """Run one agent simulation.

    Parameters
    ----------
    candidates  : list of ActionCandidate with ground_truth set
    order_fn    : function returning ordered list (priority or shuffled)
    abandon      : if True, abandon a candidate after cap_T failures and never
                   revisit it; if False, revisit failed candidates (bounded by
                   max_total)
    cap_T        : per-candidate per-visit attempt cap
    max_total    : global attempt budget (for no-abandon agents)
    ranker       : Gap-1 scoring function
    rng          : seeded RNG for reproducibility

    Returns metrics dict.

    Fair-cap protocol:
    - DUMB / PRIORITY-ONLY (no abandon): per-VISIT cap T. After T failures on
      a candidate, move to next; revisit on next pass. Each pass costs up to
      N*T attempts. Global budget max_total = N*T*K (K passes).
    - PIVOT-ONLY / SMART (abandon): per-candidate TOTAL cap T. After T failures
      on a candidate, abandon it forever. Single pass, at most N*T attempts.
    This makes "abandon" the only variable between DUMB and SMART.
    """
    # Work on a deep-ish copy so we can safely assign ranker-derived quality
    # ranks without mutating caller's objects.
    cands_copy: List[ActionCandidate] = []
    for c in candidates:
        nc = ActionCandidate(
            id=c.id, probability=c.probability,
            quality_rank=None, assessed=False, attempted=False,
            execution_outcome=None, ground_truth=c.ground_truth,
        )
        cands_copy.append(nc)
    # Ranker assigns priority signal (Gap-1) before ordering.
    for c in cands_copy:
        c.quality_rank = ranker(c)
        c.assessed = True

    # Order candidates
    ordered = order_fn(cands_copy)
    ordered = [c for c in ordered]   # copy to avoid mutating originals

    total_requests = 0
    total_wasted = 0
    found_successes = 0
    true_successes = sum(1 for c in candidates if c.ground_truth == Outcome.SUCCESS)
    loop_events = 0   # excess beyond N * cap_T (for no-abandon agents)
    pivot_events = 0  # explicit abandon pivots

    succeeded: set[str] = set()
    failed_once: set[str] = set()   # candidates abandoned (for abandon agents)
    # Per-visit attempt counter (reset on each visit; for no-abandon agents).
    # For abandon agents, this is the total-allowed counter.
    visit_attempts: dict[str, int] = {c.id: 0 for c in candidates}
    total_attempts: dict[str, int] = {c.id: 0 for c in candidates}

    visit_idx = 0
    # Non-abandon agents cycle through the list (revisiting failed ones)
    # Abandon agents do a single forward pass.

    while total_requests < max_total:
        # Termination guard: if no candidate can be attempted in the next
        # visit slot, stop. For abandon agents: candidates not yet succeeded
        # and not yet abandoned. For non-abandon: not yet succeeded and
        # per-visit cap not yet reached.
        if abandon:
            remaining = sum(1 for c in ordered
                            if c.id not in succeeded and c.id not in failed_once)
        else:
            # For non-abandon, also exclude already-succeeded ones from the
            # remaining count (they're "done" — no need to revisit).
            remaining = sum(1 for c in ordered
                            if c.id not in succeeded)
        if remaining == 0:
            break

        if abandon:
            # Single forward pass — once we pass the last candidate, done.
            if visit_idx >= len(ordered):
                break
        else:
            # DUMB / PRIORITY-ONLY (no abandon): cycle back through ALL candidates
            # (including already-failed ones) until the global budget is exhausted.
            # This is the defining "dumb" behaviour — it keeps retrying dead-ends.
            if visit_idx >= len(ordered):
                visit_idx = 0
                # Reset per-visit counters for new pass (each pass is a fresh
                # attempt budget per candidate).
                for c in ordered:
                    visit_attempts[c.id] = 0

        c = ordered[visit_idx]

        if c.id in succeeded:
            visit_idx += 1
            continue

        if abandon and c.id in failed_once:
            visit_idx += 1
            continue

        # For non-abandon agents, if this visit already has cap_T attempts, skip.
        if not abandon and visit_attempts[c.id] >= cap_T:
            visit_idx += 1
            continue

        # Attempt
        total_requests += 1
        visit_attempts[c.id] += 1
        total_attempts[c.id] += 1
        result = _exec_attempt(c)

        if result == Outcome.SUCCESS:
            succeeded.add(c.id)
            found_successes += 1
            visit_idx += 1
        else:
            total_wasted += 1
            if abandon and total_attempts[c.id] >= cap_T:
                failed_once.add(c.id)
                pivot_events += 1
                visit_idx += 1
            elif not abandon and visit_attempts[c.id] >= cap_T:
                # Reached per-visit cap — move to next candidate. Will revisit
                # on next pass.
                visit_idx += 1
            else:
                # Stay on same candidate (retry within cap)
                pass

    # loop_events = excess attempts beyond N * cap_T for no-abandon agents
    # (measures how much the agent revisits beyond a single fair pass)
    if not abandon:
        loop_events = max(0, total_requests - len(candidates) * cap_T)

    return {
        "requests": total_requests,
        "wasted_requests": total_wasted,
        "found_success": found_successes,
        "found_success_pct": (found_successes / true_successes * 100) if true_successes else 100.0,
        "loop_events": loop_events,
        "pivot_events": pivot_events,
        "attempts_per_candidate": total_attempts,
    }


def _priority_order(candidates: List[ActionCandidate]) -> List[ActionCandidate]:
    """Sort by priority_score (deterministic — ranker is the experiment variable)."""
    return sorted(candidates, key=lambda c: c.priority_score(), reverse=True)


def _random_order(candidates: List[ActionCandidate], rng: random.Random) -> List[ActionCandidate]:
    """Shuffle a copy deterministically (seeded by rng)."""
    ordered = list(candidates)
    rng.shuffle(ordered)
    return ordered


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

DEFAULT_FAMILIES = [
    "many_success", "sparse_success", "all_fail",
    "long_tail", "correlated", "anticorrelated",
]
DEFAULT_NOISE_MODES = [
    ("perfect", {"error_rate": 0.0}),
    ("noisy", {"error_rate": 0.1}),
    ("noisy", {"error_rate": 0.25}),
    ("noisy", {"error_rate": 0.5}),
    ("noisy", {"error_rate": 1.0}),
]
DEFAULT_LLM_STUBS = [
    ("llm_stub", {"llm_accuracy": 0.6}),
    ("llm_stub", {"llm_accuracy": 0.8}),
    ("llm_stub", {"llm_accuracy": 0.95}),
]
DEFAULT_HEURISTIC = [("heuristic", {})]
DEFAULT_CAPS = [1, 2, 3, 5]
MIN_SEEDS = 30
N_PER_FAMILY = 50
MAX_TOTAL_MULT = 4   # for no-abandon agents: max_total = N * cap_T * MULT


def _ci95(values: List[float]) -> Tuple[float, float, float]:
    """Return (mean, lower_ci, upper_ci)."""
    if not values:
        return 0.0, 0.0, 0.0
    mean = statistics.mean(values)
    n = len(values)
    if n < 2:
        return mean, mean, mean
    std = statistics.stdev(values)
    sem = std / math.sqrt(n)
    # t critical for 95%, df=n-1 (Clopper-Pearson approx; normal approx for n>=30)
    # n>=30 → normal z=1.96 is fine
    if n >= 30:
        margin = 1.96 * sem
    else:
        margin = 2.045 * sem   # approximate t0.025 for df=29
    return mean, mean - margin, mean + margin


def _spearman_from_ranker(
    candidates: List[ActionCandidate],
    ranker: Callable,
) -> float:
    """Spearman rank correlation between assigned priority scores and ground truth."""
    true_vals = [_QUALITY_NUMERIC[_true_quality_rank(c)] for c in candidates]
    assigned_vals = [priority_score_from(c, ranker) for c in candidates]
    return _spearman(assigned_vals, true_vals)


def run_fair_benchmark(
    families: List[str] = DEFAULT_FAMILIES,
    noise_modes: List[Tuple[str, dict]] = None,
    llm_stubs: List[Tuple[str, dict]] = None,
    heuristic_modes: List[Tuple[str, dict]] = None,
    caps: List[int] = DEFAULT_CAPS,
    n_seeds: int = MIN_SEEDS,
    n_per_family: int = N_PER_FAMILY,
    output_jsonl: str = None,
    verbose: bool = True,
) -> dict:
    """Run the full fair benchmark suite and return structured results.

    Parameters
    ----------
    families        : list of family kinds to evaluate
    noise_modes      : list of (ranker_kind, kwargs) for noisy rankers
    llm_stubs        : list of (ranker_kind, kwargs) for llm_stub rankers
    heuristic_modes  : list of (ranker_kind, kwargs) for heuristic rankers
    caps             : per-candidate cap T values
    n_seeds          : number of random seeds per condition (>=30)
    n_per_family     : candidates per family (>=50)
    output_jsonl     : path to write JSONL results
    verbose          : print mean±CI tables

    Returns dict of results keyed by (family, ranker_label, cap, seed).
    """
    noise_modes = noise_modes or DEFAULT_NOISE_MODES
    llm_stubs = llm_stubs or DEFAULT_LLM_STUBS
    heuristic_modes = heuristic_modes or DEFAULT_HEURISTIC
    all_rankers = (
        [("perfect", {"error_rate": 0.0})]
        + list(noise_modes)
        + list(heuristic_modes)
        + list(llm_stubs)
    )

    results: Dict[tuple, dict] = {}
    jsonl_rows: List[dict] = []

    for family in families:
        for seed in range(n_seeds):
            candidates = make_family(family, n_per_family, seed)

            for ranker_kind, rkwargs in all_rankers:
                ranker = make_ranker(ranker_kind, **rkwargs)
                rank_label = _ranker_label(ranker_kind, rkwargs)
                rho = _spearman_from_ranker(candidates, ranker)

                for cap_T in caps:
                    max_total = n_per_family * cap_T * MAX_TOTAL_MULT

                    for agent_name, order_fn, abandon in [
                        ("DUMB",          lambda cs: _random_order(cs, random.Random(seed)), False),
                        ("PIVOT-ONLY",    lambda cs: _random_order(cs, random.Random(seed)), True),
                        ("PRIORITY-ONLY", lambda cs: _priority_order(cs),           False),
                        ("SMART",         lambda cs: _priority_order(cs),           True),
                    ]:
                        rng = random.Random(seed)
                        metrics = simulate_agent(
                            candidates, order_fn, abandon, cap_T,
                            max_total, ranker, rng,
                        )
                        key = (family, rank_label, cap_T, seed, agent_name)
                        row = {
                            "family": family,
                            "ranker": rank_label,
                            "cap_T": cap_T,
                            "seed": seed,
                            "agent": agent_name,
                            "requests": metrics["requests"],
                            "wasted_requests": metrics["wasted_requests"],
                            "found_success_pct": metrics["found_success_pct"],
                            "loop_events": metrics["loop_events"],
                            "pivot_events": metrics["pivot_events"],
                            "spearman_rho": rho,
                            "n_candidates": n_per_family,
                            "true_successes": sum(1 for c in candidates
                                                if c.ground_truth == Outcome.SUCCESS),
                        }
                        results[key] = row
                        jsonl_rows.append(row)

    if output_jsonl:
        with open(output_jsonl, "w") as fh:
            for row in jsonl_rows:
                fh.write(json.dumps(row) + "\n")
        if verbose:
            print(f"JSONL → {output_jsonl} ({len(jsonl_rows)} rows)")

    # Aggregate
    aggregated = _aggregate(results, caps)
    if verbose:
        _print_tables(aggregated, families, all_rankers, caps)

    return {"raw": results, "aggregated": aggregated, "n_jsonl_rows": len(jsonl_rows)}


def _ranker_label(kind: str, kwargs: dict) -> str:
    if kind == "perfect":
        return "perfect"
    if kind == "heuristic":
        return "heuristic"
    if kind == "noisy":
        return f"noisy_p{kwargs.get('error_rate', 0)}"
    if kind == "llm_stub":
        return f"llm_acc{kwargs.get('llm_accuracy', 0.8)}"
    return kind


def _aggregate(results: Dict[tuple, dict], caps: List[int]) -> dict:
    """Aggregate raw results into mean ± 95% CI per (family, ranker, cap, agent)."""
    from collections import defaultdict

    groups: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    for key, row in results.items():
        family, ranker, cap_T, seed, agent = key
        g = f"{family}|{ranker}|{cap_T}|{agent}"
        groups[g]["requests"].append(row["requests"])
        groups[g]["wasted_requests"].append(row["wasted_requests"])
        groups[g]["found_success_pct"].append(row["found_success_pct"])
        groups[g]["loop_events"].append(row["loop_events"])
        groups[g]["spearman_rho"].append(row["spearman_rho"])

    agg = {}
    for gkey, metrics in groups.items():
        parts = gkey.split("|")
        family, ranker, cap_T_s, agent = parts
        cap_T = int(cap_T_s)
        agg[(family, ranker, cap_T, agent)] = {
            metric: _ci95(vals)
            for metric, vals in metrics.items()
        }

    return agg


def _decompose(agg: dict, family: str, ranker: str, cap_T: int) -> dict:
    """Decompose ordering_gain into priority + pivot components."""
    dumb = agg.get((family, ranker, cap_T, "DUMB"))
    pivot_only = agg.get((family, ranker, cap_T, "PIVOT-ONLY"))
    prio_only = agg.get((family, ranker, cap_T, "PRIORITY-ONLY"))
    smart = agg.get((family, ranker, cap_T, "SMART"))

    def _mean(d, metric):
        return d[metric][0] if d else None

    total_gain = None
    prio_comp = None
    pivot_comp = None
    pivot_control = None  # PIVOT-ONLY − DUMB (should ≈ 0 if pivot alone ≠ much)

    if dumb and prio_only:
        prio_comp = dumb["requests"][0] - prio_only["requests"][0]
    if prio_only and smart:
        pivot_comp = prio_only["requests"][0] - smart["requests"][0]
    if dumb and pivot_only:
        pivot_control = pivot_only["requests"][0] - dumb["requests"][0]
    if prio_comp is not None and pivot_comp is not None:
        total_gain = prio_comp + pivot_comp

    return {
        "total_gain": total_gain,
        "priority_component": prio_comp,
        "pivot_component": pivot_comp,
        "pivot_control": pivot_control,
        "dumb_requests": _mean(dumb, "requests"),
        "pivot_only_requests": _mean(pivot_only, "requests"),
        "prio_only_requests": _mean(prio_only, "requests"),
        "smart_requests": _mean(smart, "requests"),
        "dumb_wasted": _mean(dumb, "wasted_requests"),
        "smart_wasted": _mean(smart, "wasted_requests"),
        "dumb_loop": _mean(dumb, "loop_events"),
        "smart_loop": _mean(smart, "loop_events"),
    }


def _print_tables(agg: dict, families: List[str], rankers: List[Tuple], caps: List[int]):
    """Print human-readable summary tables."""
    for family in families:
        print(f"\n{'='*70}")
        print(f"  Family: {family}   (N=50, seeds={MIN_SEEDS})")
        print(f"{'='*70}")

        for ranker_kind, rkwargs in rankers:
            rank_label = _ranker_label(ranker_kind, rkwargs)
            print(f"\n  Ranker: {rank_label}")
            print(f"  {'Cap':>4} {'Agent':<14} {'Requests':>12} {'Wasted':>8} "
                  f"{'Succ%':>7} {'Loops':>6} {'Rho':>6}")
            print(f"  {'-'*60}")

            row_data = {}
            for cap_T in caps:
                for agent in ["DUMB", "PIVOT-ONLY", "PRIORITY-ONLY", "SMART"]:
                    key = (family, rank_label, cap_T, agent)
                    d = agg.get(key)
                    if d is None:
                        continue
                    req_m, req_lo, req_hi = d["requests"]
                    was_m = d["wasted_requests"][0]
                    suc_m = d["found_success_pct"][0]
                    loop_m = d["loop_events"][0]
                    rho_m = d["spearman_rho"][0]
                    print(f"  {cap_T:>4} {agent:<14} {req_m:>11.1f} {was_m:>8.1f} "
                          f"{suc_m:>6.1f}% {loop_m:>6.1f} {rho_m:>6.3f}")
                    row_data[(cap_T, agent)] = d

            # Decomposition table
            if row_data:
                print(f"\n  Decomposition (identical cap T):")
                print(f"  {'T':>4} {'priority=DUMB-PRIORITY':>22} "
                      f"{'pivot=PRIORITY-SMART':>20} {'total':>8}")
                print(f"  {'-'*60}")
                for cap_T in caps:
                    decomp = _decompose(agg, family, rank_label, cap_T)
                    pc = decomp.get("priority_component")
                    pic = decomp.get("pivot_component")
                    tg = decomp.get("total_gain")
                    pc_s = f"{pc:+.1f}" if pc is not None else "N/A"
                    pic_s = f"{pic:+.1f}" if pic is not None else "N/A"
                    tg_s = f"{tg:+.1f}" if tg is not None else "N/A"
                    print(f"  {cap_T:>4} {pc_s:>22} {pic_s:>20} {tg_s:>8}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="FAIR benchmark: Gap-1 vs Gap-2 ablation")
    parser.add_argument("--seeds", type=int, default=MIN_SEEDS, help=f"seeds per condition (≥{MIN_SEEDS})")
    parser.add_argument("--n", type=int, default=N_PER_FAMILY, help=f"candidates per family (≥50)")
    parser.add_argument("--families", nargs="+", default=DEFAULT_FAMILIES, help="family kinds")
    parser.add_argument("--caps", nargs="+", type=int, default=DEFAULT_CAPS, help="cap T values")
    parser.add_argument("--jsonl", type=str, default=None, help="write results to JSONL file")
    parser.add_argument("--quiet", action="store_true", help="suppress table output")
    args = parser.parse_args()

    print("FAIR BENCHMARK — Gap-1 (priority) vs Gap-2 (pivot) ablation")
    print(f"  Families : {args.families}")
    print(f"  Caps T    : {args.caps}")
    print(f"  Seeds     : {args.seeds} per condition")
    print(f"  N/cand    : {args.n}")
    print()

    result = run_fair_benchmark(
        families=args.families,
        caps=args.caps,
        n_seeds=args.seeds,
        n_per_family=args.n,
        output_jsonl=args.jsonl,
        verbose=not args.quiet,
    )

    n_rows = result["n_jsonl_rows"]
    print(f"\nDone. {n_rows} raw rows written.")


if __name__ == "__main__":
    main()
