"""Multi-seed variance benchmark (T-BENCH-VAR, P3).

Runs the EXISTING SMART and DUMB agents (imported unchanged from
tests.evaluate) across N randomized seeds and reports MEAN +/- STD of the
four thesis metrics (requests, validated, completion_%, loop_events) per
agent, so the benchmark can claim statistical defensibility.

What varies between seeds (and why it is safe):
  * Finding ORDER is shuffled every seed (after seeding Python's `random`) to
    stress ranking robustness / order-invariance. The SMART graph re-sorts by
    priority_score and the DUMB loop processes every finding independently, so
    the *aggregated* metrics are expected to be order-invariant -- that
    invariance is asserted explicitly below ("ORDER-INVARIANCE CHECK").
  * A BENIGN parameter of the DUMB baseline -- its retry hard-cap -- is drawn
    from a small range per seed. This is NOT the SMART pivot/threshold logic
    (which stays fixed at threshold=2 and is never touched). It gives the
    variance harness a real, measured spread to report and shows how sensitive
    the naive baseline is to its own retry budget versus the framework.

The SMART loop metric is ALWAYS the MEASURED value from final["loops"] -- it is
never hardcoded. core/*, app.py and tests/evaluate.py are NOT modified.

Usage:
    python tests/benchmark_var.py            # default 5 seeds
    python tests/benchmark_var.py --seeds 5
"""
from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
from pathlib import Path

# Make the repo root importable (mirrors tests/evaluate.py's sys.path trick).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.evaluate import smart_agent, dumb_agent, LABELED_FINDINGS  # noqa: E402
from core.schemas import finding_from_dict, ExecutionOutcome           # noqa: E402

SMART_THRESHOLD = 2          # pivot threshold -- FIXED, never perturbed
OUT_CSV = ROOT / "data" / "benchmark_variance.csv"
CSV_FIELDS = ["seed", "agent", "requests", "validated", "completion_%", "loop_events"]

# Explicit, documented seeds. The DUMB baseline's benign retry cap is derived
# deterministically from the seed so the run is fully reproducible.
DEFAULT_SEEDS = [101, 202, 303, 404, 505]


def _dumb_cap_for_seed(seed: int) -> int:
    """Benign baseline retry cap for a seed (8..12). Not the pivot threshold."""
    return 8 + (seed % 5)


def _build_findings(seed: int):
    """Fresh Finding objects from LABELED_FINDINGS, order shuffled for this seed."""
    random.seed(seed)
    findings = [finding_from_dict(dict(d)) for d in LABELED_FINDINGS]
    random.shuffle(findings)
    return findings


def _capture_agent(agent, name, results, loops, n_findings):
    reqs = sum(r.get("request_count", 0) for r in results)
    validated = sum(1 for r in results if r["outcome"] == ExecutionOutcome.SUCCESS.value)
    comp = round(100.0 * validated / n_findings, 1)
    return {
        "agent": name,
        "requests": reqs,
        "validated": validated,
        "completion_%": comp,
        "loop_events": loops,
    }


def run_one_seed(seed: int):
    """Run SMART + DUMB for one seed. Returns (rows, status)."""
    n = len(LABELED_FINDINGS)
    findings = _build_findings(seed)

    # SMART -- pivot threshold fixed; loop metric taken from final["loops"].
    smart = smart_agent(findings, threshold=SMART_THRESHOLD)
    s_row = _capture_agent(
        "smart", "SMART (framework)", smart["results"], smart["loops"], n
    )

    # DUMB -- benign retry cap derived from the seed (baseline only).
    dumb_cap = _dumb_cap_for_seed(seed)
    dumb = dumb_agent(findings, hard_cap=dumb_cap)
    d_row = _capture_agent(
        "dumb", "DUMB (baseline)", dumb["results"], dumb["loops"], n
    )
    d_row["_dumb_cap"] = dumb_cap  # internal: documented benign perturbation

    s_row["seed"] = seed
    d_row["seed"] = seed
    return [s_row, d_row], "OK"


def summarize(rows):
    """Print per-agent MEAN +/- STD for each metric."""
    agents = ["SMART (framework)", "DUMB (baseline)"]
    metrics = ["requests", "validated", "completion_%", "loop_events"]
    print("\n=== PER-AGENT MEAN +/- STD ACROSS SEEDS ===")
    header = f"{'agent':18} " + "  ".join(f"{m:>12}" for m in metrics)
    print(header)
    for agent in agents:
        series = {m: [r[m] for r in rows if r["agent"] == agent] for m in metrics}
        parts = []
        for m in metrics:
            vals = series[m]
            mean = statistics.fmean(vals)
            std = statistics.stdev(vals) if len(vals) > 1 else 0.0
            parts.append(f"{mean:>7.2f}+/-{std:<4.2f}")
        print(f"{agent:18} " + "  ".join(parts))
    print("\n(note: 'completion_%' shown as percentage points; std uses sample stdev)")


def order_invariance_check():
    """Confirm aggregated metrics are invariant to finding ORDER (cap fixed).

    Runs both agents with the default (unshuffled) order and with a shuffled
    order; the measured metrics must match. This isolates the ORDER effect from
    the benign cap perturbation used for the variance spread.
    """
    n = len(LABELED_FINDINGS)
    findings_default = [finding_from_dict(dict(d)) for d in LABELED_FINDINGS]
    random.seed(999)
    findings_shuffled = [finding_from_dict(dict(d)) for d in LABELED_FINDINGS]
    random.shuffle(findings_shuffled)

    cap = 10
    s_def_full = smart_agent(findings_default, threshold=SMART_THRESHOLD)
    s_def = _capture_agent("smart", "SMART (framework)",
                           s_def_full["results"], s_def_full["loops"], n)
    s_shu_full = smart_agent(findings_shuffled, threshold=SMART_THRESHOLD)
    s_shu = _capture_agent("smart", "SMART (framework)",
                           s_shu_full["results"], s_shu_full["loops"], n)
    d_def_full = dumb_agent(findings_default, hard_cap=cap)
    d_def = _capture_agent("dumb", "DUMB (baseline)",
                           d_def_full["results"], d_def_full["loops"], n)
    d_shu_full = dumb_agent(findings_shuffled, hard_cap=cap)
    d_shu = _capture_agent("dumb", "DUMB (baseline)",
                           d_shu_full["results"], d_shu_full["loops"], n)

    ok = all(s_def[m] == s_shu[m] and d_def[m] == d_shu[m]
             for m in ["requests", "validated", "completion_%", "loop_events"])
    print("\n=== ORDER-INVARIANCE CHECK (default vs shuffled, cap fixed) ===")
    print(f"  SMART  default={s_def}  shuffled={s_shu}")
    print(f"  DUMB   default={d_def}  shuffled={d_shu}")
    print(f"  RESULT: {'PASS (metrics invariant to finding order)' if ok else 'FAIL'}")
    return ok


def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in CSV_FIELDS})
    print(f"\nWrote {len(rows)} rows -> {path}")


def main():
    ap = argparse.ArgumentParser(description="T-BENCH-VAR multi-seed variance benchmark")
    ap.add_argument("--seeds", type=int, default=len(DEFAULT_SEEDS),
                    help="number of seeds (uses first N of the documented seed list)")
    args = ap.parse_args()
    seeds = DEFAULT_SEEDS[: max(1, args.seeds)]

    print(f"T-BENCH-VAR: running {len(seeds)} seeds {seeds}")
    print(f"SMART pivot threshold = {SMART_THRESHOLD} (fixed); "
          f"DUMB benign retry cap = 8..12 per seed\n")

    all_rows = []
    per_seed_status = []
    for seed in seeds:
        try:
            rows, status = run_one_seed(seed)
            all_rows.extend(rows)
            per_seed_status.append((seed, status, rows[1].get("_dumb_cap")))
            s, d = rows[0], rows[1]
            print(f"seed {seed:>3} [cap={rows[1]['_dumb_cap']}] "
                  f"SMART(reqs={s['requests']},val={s['validated']},"
                  f"comp={s['completion_%']},loops={s['loop_events']}) "
                  f"DUMB(reqs={d['requests']},val={d['validated']},"
                  f"comp={d['completion_%']},loops={d['loop_events']})")
        except Exception as exc:  # one seed failure must not abort all
            per_seed_status.append((seed, f"FAILED: {exc!r}", None))
            print(f"seed {seed:>3} FAILED: {exc!r}")

    summarize(all_rows)
    write_csv(all_rows, OUT_CSV)

    print("\n=== PER-SEED STATUS ===")
    for seed, status, cap in per_seed_status:
        print(f"  seed {seed:>3}: {status}" + (f" (dumb_cap={cap})" if cap else ""))

    try:
        order_invariance_check()
    except Exception as exc:
        print(f"  ORDER-INVARIANCE CHECK ERROR: {exc!r}")

    ok_seeds = sum(1 for _, st, _ in per_seed_status if st == "OK")
    print(f"\nDONE: {ok_seeds}/{len(seeds)} seeds succeeded.")


if __name__ == "__main__":
    main()
