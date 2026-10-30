"""PHASE 34 — GAP-2 operational effectiveness and failure-aware pivoting.

RESEARCH-ONLY, ADDITIVE script. Does NOT modify:
  decision_engine/core/, decision_engine/benchmarks/,
  GAP-1, GAP-2, or any historical results.

RESEARCH QUESTION
"Does state-aware failure-threshold pivoting reduce repeated wasted attempts
and improve useful-candidate discovery compared with retrying the same
candidate?"

DESIGN
Controlled synthetic execution corpus with INDEPENDENTLY SPECIFIED candidate
outcomes. Outcomes are static per-(candidate, attempt-index) playback tables
defined below BEFORE any run, and are NEVER derived from the decision
engine, the assessor, or the pivot logic. The scripted playback stub only
replays those tables; every recorded outcome is verified against them
(no-fabrication check).

Arms (same corpus, outcome tables, ranking procedure, budget per scenario):
  A. NO-PIVOT / RETRY BASELINE — keep retrying the first-ranked candidate
     until SUCCESS or the overall attempt budget is exhausted. Never pivots.
  B. THRESHOLD PIVOT T=1 / T=2 / T=3 — explicit per-candidate attempt
     counters; abandon a candidate after T consecutive failures and move to
     the next ranked candidate; stop at first SUCCESS or budget exhaustion.

The threshold arms are implemented as an explicit budget-capped walk that
reuses the frozen interfaces read-only (deterministic_assessor,
rank_candidates, Executor). Mechanism fidelity is cross-validated: for every
scenario x threshold, the frozen run_engine (LangGraph GAP-2 path,
uncapped) is executed with a fresh playback stub and its attempt-sequence
prefix must equal the walk's recorded sequence. Any mismatch is recorded.

Ranking (identical for every arm): assess-all with deterministic_assessor +
rank_candidates (frozen, read-only). The corpus carries NO ground-truth
labels, so no GAP-1 label leakage can influence ordering; probabilities are
strictly descending in listed order and the recorded ranking order is
verified to equal the listed order.

PRIMARY METRICS (per scenario x arm x rep): total attempts, failed attempts,
repeated attempts on same candidate, wasted attempts, unique candidates
attempted, attempts until useful success, useful success within budget,
pivot count, abandonment-at-threshold records, bounded-termination flags.

STATE-CORRECTNESS CHECKS (verified per run, recorded): counter increments,
per-candidate counters, exact threshold trigger, next-valid pivot target,
no counter leak/reset on pivot, budget never exceeded, termination (no
infinite loop), no fabricated outcomes.

STATISTICS: mechanism is fully deterministic (REPS=3 identical runs);
descriptive statistics only. No significance claims.

SAFETY: synthetic controlled validation only. No targets, no network, no
real-world execution. Playback stub returns scripted Outcomes; nothing runs.
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

from decision_engine.core.assessor import deterministic_assessor
from decision_engine.core.engine import rank_candidates, run_engine
from decision_engine.core.executor import Executor
from decision_engine.core.schemas import (
    ExecutionResult,
    Outcome,
    candidate_from_dict,
)

# ---------------------------------------------------------------------------
# Controlled synthetic scenarios.
# candidates: (id, probability, outcome_script)
#   outcome_script: static list of Outcome names indexed by 1-based attempt
#     number on that candidate; entries beyond the list repeat the last one.
#   Fixed outcomes use a single-element script. Flaky (recovering)
#   candidates use multi-element scripts, e.g. ["FAIL_TIMEOUT", "SUCCESS"]
#   succeeds on its 2nd attempt. All scripts are INPUT DATA, fixed here
#   before any assessment/execution/pivot logic runs.
# ---------------------------------------------------------------------------
SCENARIOS = {
    "S0_immediate_success": {
        "description": "control: first candidate succeeds at once; no pivot needed",
        "budget": 4,
        "candidates": [
            ("S0-A", 0.85, ["SUCCESS"]),
            ("S0-B", 0.60, ["FAIL_TIMEOUT"]),
        ],
    },
    "S1_fail_then_success": {
        "description": "first candidate repeatedly fails, second succeeds",
        "budget": 6,
        "candidates": [
            ("S1-A", 0.90, ["FAIL_TIMEOUT"]),
            ("S1-B", 0.65, ["SUCCESS"]),
        ],
    },
    "S2_flaky_then_success": {
        "description": "first fails twice then succeeds on 3rd attempt; second succeeds",
        "budget": 8,
        "candidates": [
            ("S2-A", 0.90, ["FAIL_TIMEOUT", "FAIL_TIMEOUT", "SUCCESS"]),
            ("S2-B", 0.65, ["SUCCESS"]),
        ],
    },
    "S3_early_recovery": {
        "description": "first fails once then succeeds on 2nd attempt; second succeeds",
        "budget": 6,
        "candidates": [
            ("S3-A", 0.90, ["FAIL_TIMEOUT", "SUCCESS"]),
            ("S3-B", 0.65, ["SUCCESS"]),
        ],
    },
    "S4_multi_fail": {
        "description": "two candidates fail with different modes, third succeeds",
        "budget": 9,
        "candidates": [
            ("S4-A", 0.90, ["FAIL_TIMEOUT"]),
            ("S4-B", 0.75, ["FAIL_SYNTAX"]),
            ("S4-C", 0.60, ["SUCCESS"]),
        ],
    },
    "S5_all_fail": {
        "description": "all candidates fail; bounded termination expected",
        "budget": 12,
        "candidates": [
            ("S5-A", 0.90, ["FAIL_TIMEOUT"]),
            ("S5-B", 0.75, ["FAIL_SYNTAX"]),
            ("S5-C", 0.60, ["FAIL_DEPENDENCY"]),
        ],
    },
    "S6_late_success": {
        "description": "success arrives on third candidate after two failures",
        "budget": 12,
        "candidates": [
            ("S6-A", 0.90, ["FAIL_TIMEOUT"]),
            ("S6-B", 0.75, ["FAIL_DEPENDENCY"]),
            ("S6-C", 0.60, ["SUCCESS"]),
            ("S6-D", 0.45, ["SUCCESS"]),
        ],
    },
    "S7_budget_interaction": {
        "description": "tight budget: only a low threshold can still reach success",
        "budget": 4,
        "candidates": [
            ("S7-A", 0.90, ["FAIL_TIMEOUT"]),
            ("S7-B", 0.75, ["FAIL_SYNTAX"]),
            ("S7-C", 0.60, ["SUCCESS"]),
        ],
    },
}

ARMS = ["no_pivot_retry", "threshold_T1", "threshold_T2", "threshold_T3"]
THRESHOLD_OF = {"threshold_T1": 1, "threshold_T2": 2, "threshold_T3": 3}
REPS = 3
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


# ---------------------------------------------------------------------------
# Scripted playback executor (synthetic stub, not a real action runner).
# ---------------------------------------------------------------------------
class PlaybackStub:
    """Replays static per-(candidate, attempt) outcome tables.

    Independent of engine/assessor/pivot logic: tables are fixed scenario
    input. Tracks per-candidate attempt indices for counter verification.
    """

    def __init__(self, scripts: dict[str, list[str]]):
        self.scripts = {k: list(v) for k, v in scripts.items()}
        self.next_index: dict[str, int] = {k: 1 for k in scripts}

    def __call__(self, candidate):
        cid = candidate.id
        idx = self.next_index.get(cid, 1)
        script = self.scripts[cid]
        outcome_name = script[min(idx, len(script)) - 1]
        self.next_index[cid] = idx + 1
        candidate.attempted = True
        return ExecutionResult(
            candidate_id=cid,
            outcome=Outcome(outcome_name),
            request_count=1,
            detail="scripted-playback(synthetic)",
        )


def scenario_scripts(name: str) -> dict[str, list[str]]:
    return {cid: list(script)
            for cid, _p, script in SCENARIOS[name]["candidates"]}


def expected_outcome(name: str, cid: str, attempt_idx: int) -> str:
    script = scenario_scripts(name)[cid]
    return script[min(attempt_idx, len(script)) - 1]


def ranked_order(name: str) -> list[str]:
    """Identical ranking procedure for every arm (frozen, read-only)."""
    cands = [candidate_from_dict({"id": cid, "probability": p})
             for cid, p, _s in SCENARIOS[name]["candidates"]]
    for c in cands:  # assess-all, mirroring engine.initial_state
        c.quality_rank = deterministic_assessor(c)
        c.assessed = True
    return [c.id for c in rank_candidates(cands)]


def compute_metrics(attempts: list[dict], budget: int) -> dict:
    """Primary operational metrics from a recorded attempt sequence."""
    total = len(attempts)
    failed = sum(1 for a in attempts if a["outcome"] != "SUCCESS")
    per_cand: dict[str, int] = {}
    for a in attempts:
        per_cand[a["candidate_id"]] = per_cand.get(a["candidate_id"], 0) + 1
    repeated = sum(n - 1 for n in per_cand.values())
    # repeated_failed: failed attempts beyond the first attempt per candidate.
    repeated_failed = 0
    seen: dict[str, int] = {}
    for a in attempts:
        seen[a["candidate_id"]] = seen.get(a["candidate_id"], 0) + 1
        if seen[a["candidate_id"]] > 1 and a["outcome"] != "SUCCESS":
            repeated_failed += 1
    success_pos = next(
        (i + 1 for i, a in enumerate(attempts) if a["outcome"] == "SUCCESS"),
        None,
    )
    success = success_pos is not None
    return {
        "total_attempts": total,
        "failed_attempts": failed,
        "repeated_attempts": repeated,
        "repeated_failed_attempts": repeated_failed,
        # Under stop-on-first-success, every non-success attempt is wasted;
        # the equivalence is structural, not a reporting shortcut.
        "wasted_attempts": total - (1 if success else 0),
        "unique_candidates_attempted": len(per_cand),
        "per_candidate_counts": per_cand,
        "attempts_until_useful_success": success_pos,
        "useful_success_within_budget": success,
    }


def verify_state(name: str, arm: str, order: list[str], attempts: list[dict],
                 abandonments: list[dict], pivots: list[dict],
                 budget: int) -> dict[str, bool]:
    """State-correctness checks of a recorded run against static tables."""
    scripts = scenario_scripts(name)
    # 1+2. counters increment 1,2,3... per candidate, maintained per candidate
    idx_by_cand: dict[str, list[int]] = {}
    for a in attempts:
        idx_by_cand.setdefault(a["candidate_id"], []).append(
            a["attempt_index"])
    counters_ok = all(
        idxs == list(range(1, len(idxs) + 1)) for idxs in idx_by_cand.values()
    )
    # 9. no fabricated outcomes: every record matches the static table
    no_fabrication = all(
        a["outcome"] == expected_outcome(name, a["candidate_id"],
                                         a["attempt_index"])
        for a in attempts
    )
    checks: dict[str, bool] = {
        "counter_increments_correctly": counters_ok,
        "counter_maintained_per_candidate": counters_ok,
        "no_fabricated_outcomes": no_fabrication,
        # 7+8. budget respected and run terminated (loop is budget-capped
        # with a hard iteration guard; reaching here means termination).
        "attempt_budget_never_exceeded": len(attempts) <= budget,
        "terminated_no_infinite_loop": True,
    }
    if arm.startswith("threshold_"):
        t = THRESHOLD_OF[arm]
        # 3. abandonment happens after exactly T failures, never more
        checks["threshold_triggers_exactly"] = (
            all(ab["attempts_at_abandon"] == t for ab in abandonments)
            and all(n <= t for n in
                    compute_metrics(attempts, budget)["per_candidate_counts"].values())
        )
        # 4. pivot target is the next valid (unprocessed) candidate in order
        pos = {cid: i for i, cid in enumerate(order)}
        checks["pivot_selects_next_valid_candidate"] = all(
            p["to"] == order[pos[p["from"]] + 1]
            and pos[p["to"]] == pos[p["from"]] + 1
            for p in pivots
        )
        # 5+6. first attempt on a pivoted-to candidate starts at index 1
        first_idx = {}
        for a in attempts:
            first_idx.setdefault(a["candidate_id"], a["attempt_index"])
        checks["counter_reset_after_pivot_no_leak"] = all(v == 1 for v in
                                                          first_idx.values())
        checks["abandoned_after_threshold"] = all(
            ab["abandoned_at_threshold"] for ab in abandonments)
    else:
        # No-pivot arm: exactly one candidate ever attempted, zero pivots.
        checks["threshold_triggers_exactly"] = True
        checks["pivot_selects_next_valid_candidate"] = True
        checks["counter_reset_after_pivot_no_leak"] = True
        checks["abandoned_after_threshold"] = True
        checks["single_candidate_never_pivots"] = (
            len(idx_by_cand) <= 1 and not pivots and not abandonments
        )
    return checks


def run_threshold_walk(name: str, arm: str, rep: int) -> dict:
    """Explicit budget-capped threshold-pivot walk (operational arm)."""
    t = THRESHOLD_OF[arm]
    budget = SCENARIOS[name]["budget"]
    order = ranked_order(name)
    stub = PlaybackStub(scenario_scripts(name))
    executor = Executor(mode="real", execute_fn=stub)
    listed_ids = [c[0] for c in SCENARIOS[name]["candidates"]]

    attempts, abandonments, pivots = [], [], []
    counters: dict[str, int] = {}
    pos, total = 0, 0
    guard = 0
    outcome_reached: str | None = None  # success | budget | exhausted
    while guard < budget + 5:
        guard += 1
        if pos >= len(order):
            outcome_reached = "exhausted"
            break
        if total >= budget:
            outcome_reached = "budget"
            break
        cid = order[pos]
        counters[cid] = counters.get(cid, 0) + 1
        cand = candidate_from_dict({"id": cid, "probability": 0.0})
        result = executor.execute(cand)
        total += 1
        attempts.append({"seq": total, "candidate_id": cid,
                         "attempt_index": counters[cid],
                         "outcome": result.outcome.value})
        if result.outcome == Outcome.SUCCESS:
            outcome_reached = "success"
            break
        if counters[cid] >= t:  # failure threshold reached -> abandon + pivot
            abandonments.append({"candidate": cid,
                                 "attempts_at_abandon": counters[cid],
                                 "abandoned_at_threshold": counters[cid] == t})
            if pos + 1 < len(order):
                pivots.append({"from": cid, "to": order[pos + 1],
                               "reason": "threshold_reached"})
            pos += 1
    metrics = compute_metrics(attempts, budget)
    checks = verify_state(name, arm, order, attempts, abandonments, pivots,
                          budget)
    return {"scenario": name, "arm": arm, "rep": rep, "threshold": t,
            "budget": budget, "ranking_order": order,
            "listed_order": listed_ids,
            "ranking_matches_listed": order == listed_ids,
            "attempts": attempts, "abandonments": abandonments,
            "pivots": pivots, "pivot_count": len(pivots),
            "stop_reason": outcome_reached, "metrics": metrics,
            "state_checks": checks,
            "all_state_checks_pass": all(checks.values())}


def run_nopivot_walk(name: str, rep: int) -> dict:
    """Arm A: retry the first-ranked candidate until success or budget."""
    budget = SCENARIOS[name]["budget"]
    order = ranked_order(name)
    target = order[0]
    stub = PlaybackStub(scenario_scripts(name))
    executor = Executor(mode="real", execute_fn=stub)
    listed_ids = [c[0] for c in SCENARIOS[name]["candidates"]]

    attempts = []
    total, guard = 0, 0
    outcome_reached: str | None = None
    while guard < budget + 5:
        guard += 1
        if total >= budget:
            outcome_reached = "budget"
            break
        cand = candidate_from_dict({"id": target, "probability": 0.0})
        result = executor.execute(cand)
        total += 1
        attempts.append({"seq": total, "candidate_id": target,
                         "attempt_index": total,
                         "outcome": result.outcome.value})
        if result.outcome == Outcome.SUCCESS:
            outcome_reached = "success"
            break
    metrics = compute_metrics(attempts, budget)
    checks = verify_state(name, "no_pivot_retry", order, attempts, [], [],
                          budget)
    return {"scenario": name, "arm": "no_pivot_retry", "rep": rep,
            "threshold": None, "budget": budget, "ranking_order": order,
            "listed_order": listed_ids,
            "ranking_matches_listed": order == listed_ids,
            "retry_target": target, "attempts": attempts,
            "abandonments": [], "pivots": [], "pivot_count": 0,
            "stop_reason": outcome_reached, "metrics": metrics,
            "state_checks": checks,
            "all_state_checks_pass": all(checks.values())}


def fidelity_check(name: str, arm: str) -> dict:
    """Cross-validate the walk against the frozen GAP-2 run_engine path.

    Fresh stub + frozen engine (max_attempts=T, uncapped). The walk's
    recorded attempt sequence must equal the engine trace prefix of the
    same length (engine continues past first success by design, so only
    the prefix is comparable).
    """
    from decision_engine.core.engine import run_engine as frozen_run

    t = THRESHOLD_OF[arm]
    order = ranked_order(name)
    stub = PlaybackStub(scenario_scripts(name))
    executor = Executor(mode="real", execute_fn=stub)
    candidates = [{"id": cid, "probability": p}
                  for cid, p, _s in SCENARIOS[name]["candidates"]]
    final = frozen_run(candidates, assess_fn=deterministic_assessor,
                       executor=executor, max_attempts=t, mode="simulation")
    engine_seq = [(r.get("candidate_id"), r.get("outcome"))
                  for r in final.get("results", [])]
    engine_order = [c.id for c in final.get("candidates", [])]
    walk = run_threshold_walk(name, arm, rep=-1)  # deterministic; rep unused
    walk_seq = [(a["candidate_id"], a["outcome"]) for a in walk["attempts"]]
    prefix = engine_seq[:len(walk_seq)]
    return {"scenario": name, "arm": arm, "threshold": t,
            "engine_total_attempts": len(engine_seq),
            "engine_final_status": final.get("status"),
            "engine_ranking_order": engine_order,
            "ranking_matches_walk": engine_order == order,
            "walk_length": len(walk_seq),
            "prefix_matches_walk": prefix == walk_seq,
            "engine_prefix": prefix, "walk_sequence": walk_seq}


def summarize(scenario: str, arm: str, reps: list[dict]) -> dict:
    n = len(reps)
    m = [r["metrics"] for r in reps]
    tot = [x["total_attempts"] for x in m]
    fail = [x["failed_attempts"] for x in m]
    rep_ = [x["repeated_attempts"] for x in m]
    wast = [x["wasted_attempts"] for x in m]
    uniq = [x["unique_candidates_attempted"] for x in m]
    until = [x["attempts_until_useful_success"] for x in m]
    until_ok = [u for u in until if u is not None]
    within = [x["useful_success_within_budget"] for x in m]
    piv = [r["pivot_count"] for r in reps]
    aband = [len(r["abandonments"]) for r in reps]
    return {
        "scenario": scenario, "arm": arm, "reps": n,
        "budget": SCENARIOS[scenario]["budget"],
        "threshold": THRESHOLD_OF.get(arm),
        "total_attempts": {"per_rep": tot,
                           "mean": round(statistics.mean(tot), 4)},
        "failed_attempts": {"per_rep": fail,
                            "mean": round(statistics.mean(fail), 4)},
        "repeated_attempts": {"per_rep": rep_,
                              "mean": round(statistics.mean(rep_), 4)},
        "wasted_attempts": {"per_rep": wast,
                            "mean": round(statistics.mean(wast), 4)},
        "unique_candidates_attempted": {"per_rep": uniq,
                                       "mean": round(statistics.mean(uniq), 4)},
        "attempts_until_useful_success": {
            "per_rep": until, "n_successful_reps": len(until_ok),
            "mean": (round(statistics.mean(until_ok), 4)
                     if until_ok else None)},
        "useful_success_within_budget_rate": round(sum(within) / n, 4),
        "pivot_count": {"per_rep": piv,
                        "mean": round(statistics.mean(piv), 4)},
        "abandonment_count": {"per_rep": aband,
                              "mean": round(statistics.mean(aband), 4)},
        "all_abandoned_at_threshold": all(
            ab["abandoned_at_threshold"]
            for r in reps for ab in r["abandonments"]),
        "bounded_termination": all(
            r["metrics"]["total_attempts"] <= r["budget"] for r in reps),
        "all_state_checks_pass": all(r["all_state_checks_pass"]
                                     for r in reps),
    }


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    records: dict[str, dict[str, list[dict]]] = {}
    for sname in SCENARIOS:
        records[sname] = {}
        order = ranked_order(sname)
        print(f"{sname}: order={order} "
              f"budget={SCENARIOS[sname]['budget']}", flush=True)
        records[sname]["no_pivot_retry"] = [
            run_nopivot_walk(sname, rep) for rep in range(REPS)]
        for arm in ("threshold_T1", "threshold_T2", "threshold_T3"):
            records[sname][arm] = [
                run_threshold_walk(sname, arm, rep) for rep in range(REPS)]

    fidelity = [fidelity_check(s, a) for s in SCENARIOS
                for a in ("threshold_T1", "threshold_T2", "threshold_T3")]
    fidelity_ok = all(f["prefix_matches_walk"] and f["ranking_matches_walk"]
                      for f in fidelity)

    summaries = {s: {a: summarize(s, a, records[s][a]) for a in ARMS}
                 for s in SCENARIOS}

    payload = {
        "experiment": "gap2_failure_pivot_effectiveness",
        "phase": "34",
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "research_integrity_note": (
            "Controlled synthetic outcome scripts (fixed before any run). "
            "NOT real-world exploit evidence. Nothing executed: a scripted "
            "playback stub replays static tables; no targets, no network. "
            "Outcomes never derived from engine/assessor/pivot logic "
            "(verified per run by no_fabricated_outcomes). Ranking, GAP-1, "
            "GAP-2, prompts, schema unchanged; decision_engine/core and "
            "decision_engine/benchmarks unmodified. Corpus carries no "
            "ground-truth labels, so no assessor label leakage into ranking. "
            "Statistics are descriptive only; no significance claimed."
        ),
        "protocol": {
            "arms": ARMS,
            "thresholds": [1, 2, 3],
            "repetitions": REPS,
            "ranking": ("assess-all deterministic_assessor + "
                        "rank_candidates (frozen, read-only); no "
                        "ground-truth labels in corpus"),
            "stopping_rule": ("stop at first SUCCESS or budget exhaustion; "
                              "threshold arms abandon after T failures; "
                              "no-pivot arm retries first-ranked candidate"),
            "scenarios": {
                s: {"description": v["description"], "budget": v["budget"],
                    "candidates": [
                        {"id": cid, "probability": p, "outcome_script": sc}
                        for cid, p, sc in v["candidates"]]}
                for s, v in SCENARIOS.items()},
        },
        "summaries": summaries,
        "records": records,
        "fidelity_vs_frozen_engine": {
            "all_prefixes_match": fidelity_ok,
            "checks": fidelity,
        },
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    json_path = os.path.join(
        RESULTS_DIR, "gap2_failure_pivot_effectiveness.json")
    csv_path = os.path.join(
        RESULTS_DIR, "gap2_failure_pivot_effectiveness.csv")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    write_csv(payload, csv_path)
    print(f"Wrote {json_path}", flush=True)
    print(f"Wrote {csv_path}", flush=True)
    print(f"FIDELITY_ALL_PREFIXES_MATCH: {fidelity_ok}", flush=True)
    for s in SCENARIOS:
        row = " | ".join(
            f"{a}: tot={summaries[s][a]['total_attempts']['mean']} "
            f"succ={summaries[s][a]['useful_success_within_budget_rate']} "
            f"rep={summaries[s][a]['repeated_attempts']['mean']} "
            f"piv={summaries[s][a]['pivot_count']['mean']}"
            for a in ARMS)
        print(f"{s}: {row}", flush=True)


def write_csv(payload: dict, csv_path: str) -> None:
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "arm", "rep", "threshold", "budget",
                    "ranking_order", "attempt_sequence",
                    "total_attempts", "failed_attempts", "repeated_attempts",
                    "repeated_failed_attempts", "wasted_attempts",
                    "unique_candidates_attempted",
                    "attempts_until_useful_success",
                    "useful_success_within_budget", "pivot_count",
                    "abandonments", "stop_reason", "all_state_checks_pass"])
        for sname, arms in payload["records"].items():
            for arm_name, reps in arms.items():
                for r in reps:
                    seq = "|".join(
                        f"{a['candidate_id']}#{a['attempt_index']}:"
                        f"{a['outcome']}" for a in r["attempts"])
                    aband = "|".join(
                        f"{ab['candidate']}:{ab['attempts_at_abandon']}"
                        for ab in r["abandonments"]) or ""
                    w.writerow([
                        sname, arm_name, r["rep"], r["threshold"], r["budget"],
                        "|".join(r["ranking_order"]), seq,
                        r["metrics"]["total_attempts"],
                        r["metrics"]["failed_attempts"],
                        r["metrics"]["repeated_attempts"],
                        r["metrics"]["repeated_failed_attempts"],
                        r["metrics"]["wasted_attempts"],
                        r["metrics"]["unique_candidates_attempted"],
                        r["metrics"]["attempts_until_useful_success"],
                        r["metrics"]["useful_success_within_budget"],
                        r["pivot_count"], aband, r["stop_reason"],
                        r["all_state_checks_pass"]])


if __name__ == "__main__":
    main()
