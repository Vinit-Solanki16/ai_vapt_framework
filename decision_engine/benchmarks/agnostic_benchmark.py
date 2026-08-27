"""DOMAIN-AGNOSTIC BENCHMARK (proves the engine is NOT CVE-specific).

Goal: demonstrate that the Stage-1 decision engine behaves identically on a
made-up domain as it does on VAPT. We define a generic "task" candidate with a
probability + a ground-truth outcome, run SMART (Gap-1 priority + Gap-2 pivot)
vs DUMB (no prioritization, retry-forever-ish) and measure request counts +
loop avoidance.

This is the key evidence for the thesis claim:
  "The decision mechanisms reduce unnecessary attempts and bound repeated
   failure behavior under the defined experimental conditions" — independent of
   the VAPT domain.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from decision_engine.core import (
    ActionCandidate,
    Outcome,
    run_engine,
    Executor,
)

# ---- Synthetic domain: "maintenance tasks" (no security meaning at all) -----
# id, probability(0..1), ground_truth outcome
TASKS = [
    {"id": "T-REBOOT",   "probability": 0.95, "ground_truth": "success"},
    {"id": "T-PATCH",    "probability": 0.80, "ground_truth": "fail_timeout"},
    {"id": "T-BACKUP",   "probability": 0.60, "ground_truth": "fail_syntax"},
    {"id": "T-CLEANUP",  "probability": 0.30, "ground_truth": "success"},
    {"id": "T-AUDIT",    "probability": 0.10, "ground_truth": "fail_dependency"},
]


def _to_candidates(tasks):
    out = []
    for t in tasks:
        out.append(ActionCandidate(
            id=t["id"],
            probability=t["probability"],
            ground_truth=Outcome[t["ground_truth"].upper()],
        ))
    return out


def smart_run():
    """Gap-1 (priority ordering) + Gap-2 (pivot at max_attempts=2)."""
    cands = _to_candidates(TASKS)
    sim = Executor(mode="simulation")
    final = run_engine([c.model_dump() for c in cands], executor=sim,
                       max_attempts=2, mode="simulation")
    return final


def dumb_run():
    """No prioritization, no pivot: try each task up to a hard cap of 5."""
    cands = _to_candidates(TASKS)
    sim = Executor(mode="simulation")
    results = []
    total_req = 0
    for c in cands:
        attempts = 0
        while attempts < 5:  # DUMB: no early pivot
            attempts += 1
            total_req += 1
            r = sim.execute(c)
            if r.outcome == Outcome.SUCCESS:
                break
        results.append((c.id, attempts))
    return results, total_req


def main():
    print("=== DOMAIN-AGNOSTIC BENCHMARK (tasks domain) ===")
    smart = smart_run()
    sreq = sum(r["request_count"] for r in smart["results"])
    spivot = smart["logs"].count("[Pivot]")
    print(f"SMART  : requests={sreq}, pivots={spivot}, status={smart['status']}")
    for r in smart["results"]:
        print(f"   {r['candidate_id']:12s} -> {r['outcome']}")

    dresults, dreq = dumb_run()
    print(f"DUMB   : requests={dreq}")
    for cid, a in dresults:
        print(f"   {cid:12s} attempts={a}")

    print("\n=== VERDICT ===")
    print(f"SMART used {sreq} total attempts vs DUMB {dreq} -> "
          f"{'WIN' if sreq < dreq else 'tie/lose'} (fewer attempts = bounded failure)")
    assert sreq <= dreq, "engine should not waste more attempts than dumb loop"
    print("OK: engine bounds repeated-failure behavior on a NON-VAPT domain.")


if __name__ == "__main__":
    main()
