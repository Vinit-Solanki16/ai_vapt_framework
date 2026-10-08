# GAP-2 Failure-Pivot Effectiveness (Phase 34)

## Research question

"Does state-aware failure-threshold pivoting reduce repeated wasted attempts
and improve useful-candidate discovery compared with retrying the same
candidate?"

## Design (four arms, all else identical)

| Arm | Policy |
|-----|--------|
| A. No-pivot retry baseline | Retry the first-ranked candidate until SUCCESS or budget exhaustion; never pivots |
| B1. Threshold pivot T=1 | Abandon a candidate after 1 failure, try the next ranked candidate |
| B2. Threshold pivot T=2 | Abandon after 2 consecutive failures |
| B3. Threshold pivot T=3 | Abandon after 3 consecutive failures |

Identical across arms per scenario: synthetic corpus and listed order,
static per-(candidate, attempt) outcome scripts, ranking procedure
(assess-all `deterministic_assessor` + `rank_candidates`, frozen read-only),
overall attempt budget, stopping rule (stop at first SUCCESS or budget
exhaustion). Outcomes were fixed before any run and verified per attempt
against the static tables (`no_fabricated_outcomes` passes on all 96 runs);
nothing was executed — a playback stub replays scripted Outcomes with no
targets and no network. The corpus carries no ground-truth labels, so no
assessor label leakage can affect ranking.

Eight scenarios (S0 control + the seven required): immediate success;
fail-then-success; flaky-then-success (fails twice, succeeds on 3rd);
early recovery (fails once, succeeds on 2nd); multi-fail; all-fail;
late success on third candidate; tight-budget interaction. Three
deterministic repetitions per scenario x arm (96 runs); descriptive
statistics only.

Mechanism fidelity: for every scenario x threshold, the frozen `run_engine`
LangGraph path was executed with a fresh stub; all 24 walk sequences equal
the engine's trace prefix and all rankings match — the measured pivot
behavior is the real GAP-2 mechanism plus an operational budget cap and
stop-on-success, not a reimplementation.

## Results

Per-scenario means over reps (total attempts / success-in-budget /
repeated attempts / pivots):

| Scenario | No-pivot | T=1 | T=2 | T=3 |
|----------|----------|-----|-----|-----|
| S0 immediate success | 1 / 1.0 / 0 / 0 | 1 / 1.0 / 0 / 0 | 1 / 1.0 / 0 / 0 | 1 / 1.0 / 0 / 0 |
| S1 fail-then-success | 6 / 0.0 / 5 / 0 | 2 / 1.0 / 0 / 1 | 3 / 1.0 / 1 / 1 | 4 / 1.0 / 2 / 1 |
| S2 flaky-then-success | 3 / 1.0 / 2 / 0 | 2 / 1.0 / 0 / 1 | 3 / 1.0 / 1 / 1 | 3 / 1.0 / 2 / 0 |
| S3 early recovery | 2 / 1.0 / 1 / 0 | 2 / 1.0 / 0 / 1 | 2 / 1.0 / 1 / 0 | 2 / 1.0 / 1 / 0 |
| S4 multi-fail | 9 / 0.0 / 8 / 0 | 3 / 1.0 / 0 / 2 | 5 / 1.0 / 2 / 2 | 7 / 1.0 / 4 / 2 |
| S5 all fail | 12 / 0.0 / 11 / 0 | 3 / 0.0 / 0 / 2 | 6 / 0.0 / 3 / 2 | 9 / 0.0 / 6 / 2 |
| S6 late success | 12 / 0.0 / 11 / 0 | 3 / 1.0 / 0 / 2 | 5 / 1.0 / 2 / 2 | 7 / 1.0 / 4 / 2 |
| S7 tight budget (4) | 4 / 0.0 / 3 / 0 | 3 / 1.0 / 0 / 2 | 4 / 0.0 / 2 / 2 | 4 / 0.0 / 2 / 1 |

State-correctness: all checks pass on all 96 runs — counters increment
1,2,3… per candidate with no cross-candidate leak and reset on pivot; every
abandonment consumed exactly T attempts; every pivot targeted the next
ranked candidate; no run exceeded its budget; all runs terminated
(bounded: threshold totals <= N x T, no-pivot totals <= budget).

## Interpretation

1. **State/mechanism validity.** The GAP-2 mechanism works exactly as
   specified: per-candidate counters, exact threshold triggering, correct
   next-candidate pivots, counter reset without leakage, and bounded
   termination under both all-fail (totals exactly N x T) and budget-capped
   conditions. Fidelity cross-validation ties the measured behavior to the
   frozen engine implementation.

2. **Operational effect of pivoting.** Threshold pivoting sharply reduces
   repeated wasted attempts whenever the first-ranked candidate cannot
   succeed (S1: 5 -> 0 repeated with T=1; S4/S6: 8–11 -> 0–4; S5: 11 -> 0–6)
   and discovers useful candidates the retry baseline never reaches
   (no-pivot success rate 0.0 vs pivot 1.0 in S1, S4, S6). Lower thresholds
   find success sooner when failures are persistent (T=1 first in S1, S4,
   S6), at the cost of abandoning recoverable candidates (S3: T=1 pivots
   away from a candidate that would have succeeded on its next attempt,
   though totals tie at 2).

## Honestly recorded non-improvements

- S0: all arms identical (1 attempt, success) — pivoting adds nothing when
  the first candidate succeeds.
- S2: retrying pays off — the no-pivot arm succeeds on attempt 3 via the
  flaky candidate's recovery, matching T=3; T=1/T=2 succeed only via the
  second candidate after abandoning a recoverable one.
- S3: all arms succeed in 2 attempts; T=1's pivot is pure mechanism
  overhead with zero operational gain.
- S5: no arm succeeds (nothing to discover); pivoting only bounds the loss
  (3–9 vs 12 attempts).
- S7: under a tight budget, T=2, T=3, and no-pivot ALL fail while only T=1
  reaches success — higher thresholds can miss success that a lower
  threshold finds. Threshold choice interacts with budget; no threshold is
  universally best.

## Claims explicitly NOT made

No claim of universal improvement, real-world VAPT effectiveness, or
optimal thresholds beyond these controlled scenarios. Outcomes are scripted
synthetic tables, success means a scripted SUCCESS token, and statistics
are descriptive only (deterministic reps; no CIs, no significance tests).

## Reproducibility

- Script: `experiments/gap2_failure_pivot_effectiveness_experiment.py`
- Raw results: `experiments/results/gap2_failure_pivot_effectiveness.json`
- Per-rep summary: `experiments/results/gap2_failure_pivot_effectiveness.csv`
- Repeat run reproduced the first run exactly (modulo timestamps).
- Key metrics independently recomputed from raw records (sequences vs
  static tables, counter/threshold/budget checks, summary rates): all pass.
- Frozen core (`decision_engine/core/`, `decision_engine/benchmarks/`)
  verified unmodified; all 34 historical result files checksum-verified
  unchanged; full pytest suite: 687 passed.
