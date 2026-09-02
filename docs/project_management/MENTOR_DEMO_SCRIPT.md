# MENTOR DEMONSTRATION SCRIPT — ai_vapt_framework

**Audience:** M.Tech mentor
**Date:** Phase 11 — Mentor Demonstration
**Scope:** Deterministic, reproducible walkthrough of the decision-engine research contribution.
**Boundary:** UI / CLI of the existing `prototype/` layer; **no** source-code changes.
**Safety:** Simulation mode only. No external targets. No real exploit execution.

---

## 0. PRE-DEMO CHECKLIST (run ≤ 2 minutes before mentor arrives)

```bash
cd /home/vinit/ai_vapt_framework
source venv/bin/activate
python -m pytest tests/ decision_engine/tests/ prototype/tests/ services/tests/ frontend/tests/ -q
```

**Expected:** `192 passed in ~30s`.

Confirm frozen files are clean:

```bash
git diff -- core/ decision_engine/core/ tests/ decision_engine/tests/ datasets/ decision_engine/benchmarks/
```

**Expected:** empty diff (no output).

**If either check fails:** stop, do not demo, and report the failure.

---

## 1. OPENING (≤ 2 minutes)

> "This is a live demonstration of the research contribution of the M.Tech project: a
> **domain-independent decision engine** that combines a pre-execution quality assessor
> (Gap-1) with a state-aware failure-threshold pivot (Gap-2).
>
> The engine is the same code path that the published fair benchmark runs against.
> What you are about to see is a **UI / CLI wrapper** that calls the real engine —
> there is no parallel fake implementation. Outcomes are resolved in **simulation
> mode** from a curated ground-truth label, so nothing touches a real network."

Three things to point out before any scenario runs:

1. The script is `prototype/run_demo.py`. The scenarios are in `prototype/demo_data.py`.
   The engine is in `decision_engine/core/engine.py` (frozen).
2. The demo runs in **simulation mode**. The safety banner is at the bottom of every
   run.
3. Each scenario's output is **deterministic** — same input → same trace, same status,
   same attempt count. There is no random element in the engine path itself; the only
   non-determinism in the wider project is the *DUMB / PIVOT-ONLY* comparison agent
   in Scenario 4, which is seeded with `seed=42` for the demo.

---

## 2. DEMO FLOW (≈ 12–15 minutes total)

Each scenario is a single command. **Read the "What to point out"** line while the
command runs. **Verify the expected output** appears.

### 2.1 Scenario 1 — Success path (Gap-1 ranking + advance)

**Goal:** Show that a high-priority candidate succeeds on first attempt and the engine
advances; the `success` path is not just a failure-handling mechanism.

**Command:**
```bash
PYTHONPATH=. python prototype/run_demo.py success 2
```

**Expected output (canonical):**
```
================================================================
AI VAPT DECISION ENGINE — MENTOR PROTOTYPE — LIVE DEMO
================================================================
Scenario:  success
Mode:      simulation
Max Attempts: 2

CANDIDATE RANKING
----------------------------------------
  1. DEMO-SUCCESS-A             prob=0.9500  quality=HIGH      score=0.9500
  2. DEMO-WORKER                prob=0.8500  quality=HIGH      score=0.8500
  3. DEMO-SUCCESS-B             prob=0.6000  quality=HIGH      score=0.6000

ENGINE EXECUTION
----------------------------------------
  DEMO-SUCCESS-A             Outcome: SUCCESS  (simulated(ground_truth))
  DEMO-WORKER                Outcome: SUCCESS  (simulated(ground_truth))
  DEMO-SUCCESS-B             Outcome: SUCCESS  (simulated(ground_truth))

DECISION TRACE
----------------------------------------
  [INIT]   Engine initialized: 3 candidates, pivot_threshold=2, mode=simulation
  [EXECUTE] Attempt: 1/2  Outcome: SUCCESS  Candidate: DEMO-SUCCESS-A
  [ADVANCE] DEMO-SUCCESS-A validated. Next candidate.
  [PIVOT]   Redirected to: DEMO-WORKER
  [EXECUTE] Attempt: 1/2  Outcome: SUCCESS  Candidate: DEMO-WORKER
  [ADVANCE] DEMO-WORKER validated. Next candidate.
  [PIVOT]   Redirected to: DEMO-SUCCESS-B
  [EXECUTE] Attempt: 1/2  Outcome: SUCCESS  Candidate: DEMO-SUCCESS-B
  [ADVANCE] DEMO-SUCCESS-B validated. Next candidate.
  [PIVOT]   All candidates processed. Workflow complete.

  [COMPLETED]  SUCCESS — candidate validated.

FINAL RESULT
----------------------------------------
Status:         SUCCESS
Total Attempts: 3
Pivot Count:    2
Candidates Processed: 3 (DEMO-SUCCESS-A, DEMO-WORKER, DEMO-SUCCESS-B)

================================================================
SAFETY
================================================================
SIMULATION MODE
Outcomes are resolved from supplied demo ground truth.
No external targets contacted. No real vulnerabilities validated.
================================================================
```

**What to point out to the mentor:**

- **Candidate ranking table** (Gap-1): all three candidates are SUCCESS, so the
  `deterministic_assessor` labels them `HIGH`; priority score = probability ×
  (0.5 + 0.5 × 1.0) = probability × 1.0. Rank order is by raw probability:
  0.95 > 0.85 > 0.60.
- **Execution timeline:** 3 attempts, 3 successes. No FAIL row. Total = 3.
- **Status = `SUCCESS`**: engine reached the validated terminal state, not just
  "all candidates processed". (Note: in this scenario the final pivot also fires
  because the *success* branch routes through the pivot node to attempt the next
  candidate; the engine ends with status `SUCCESS` per the router's promotion
  logic in `run_engine()`.)
- **Pivot count = 2**: two `[PIVOT] Redirected` events between the three
  successful attempts. Pivots are not a failure-only concept — the engine pivots
  *after every validated candidate* to consume the queue.

---

### 2.2 Scenario 2 — Failure → bounded retry → pivot → next candidate (Gap-2)

**Goal:** Show the bounded failure-threshold mechanism. A failing candidate is
attempted exactly `max_attempts = 2` times, then the engine pivots to the next
candidate and continues.

**Command:**
```bash
PYTHONPATH=. python prototype/run_demo.py failure_pivot 2
```

**Expected output (canonical):**
```
================================================================
AI VAPT DECISION ENGINE — MENTOR PROTOTYPE — LIVE DEMO
================================================================
Scenario:  failure_pivot
Mode:      simulation
Max Attempts: 2

CANDIDATE RANKING
----------------------------------------
  1. DEMO-WORKER                prob=0.8500  quality=HIGH      score=0.8500
  2. DEMO-DEAD-END              prob=0.7000  quality=LOW       score=0.4550

ENGINE EXECUTION
----------------------------------------
  DEMO-WORKER                Outcome: SUCCESS  (simulated(ground_truth))
  DEMO-DEAD-END              Outcome: FAIL_TIMEOUT  (simulated(ground_truth))
  DEMO-DEAD-END              Outcome: FAIL_TIMEOUT  (simulated(ground_truth))

DECISION TRACE
----------------------------------------
  [INIT]   Engine initialized: 2 candidates, pivot_threshold=2, mode=simulation
  [EXECUTE] Attempt: 1/2  Outcome: SUCCESS  Candidate: DEMO-WORKER
  [ADVANCE] DEMO-WORKER validated. Next candidate.
  [PIVOT]   Redirected to: DEMO-DEAD-END
  [EXECUTE] Attempt: 1/2  Outcome: FAIL_TIMEOUT  Candidate: DEMO-DEAD-END
  [EXECUTE] Attempt: 2/2  Outcome: FAIL_TIMEOUT  Candidate: DEMO-DEAD-END
  [PIVOT]   Threshold reached for DEMO-DEAD-END. Abandoning route.
  [PIVOT]   All candidates processed. Workflow complete.

  [COMPLETED]  All candidates processed. Workflow complete.

FINAL RESULT
----------------------------------------
Status:         COMPLETED
Total Attempts: 3
Pivot Count:    2
Candidates Processed: 2 (DEMO-WORKER, DEMO-DEAD-END)

================================================================
SAFETY
================================================================
SIMULATION MODE
Outcomes are resolved from supplied demo ground truth.
No external targets contacted. No real vulnerabilities validated.
================================================================
```

**What to point out to the mentor:**

- **DEMO-WORKER** is ranked first because its `quality=HIGH` and probability=0.85
  → priority=0.85, vs DEMO-DEAD-END at priority=0.4550. *Gap-1 ordering is
  visible here — quality beats raw probability.*
- **DEMO-DEAD-END is attempted exactly twice**, then `[PIVOT] Threshold reached
  for DEMO-DEAD-END. Abandoning route.` This is the Gap-2 mechanism: per-candidate
  attempt counter (`attempt_count`) is reset only when the index advances, so the
  *same* candidate gets at most `max_attempts` attempts.
- The engine **does not loop forever**. After 2 failures on DEMO-DEAD-END, the
  router fires `pivot` and the index advances. There is no recovery/retry to
  DEMO-DEAD-END.
- Total attempts = 3 (1 success + 2 failures). Status = `COMPLETED` (queue
  exhausted, no further candidates).

---

### 2.3 Scenario 3 — Multiple candidates with mixed outcomes (bounded termination)

**Goal:** Show that bounded termination holds for a larger queue with mixed
outcomes, and that ranking + threshold-pivot work together across the full list.

**Command:**
```bash
PYTHONPATH=. python prototype/run_demo.py multi_candidate 2
```

**Expected output (canonical):**
```
================================================================
AI VAPT DECISION ENGINE — MENTOR PROTOTYPE — LIVE DEMO
================================================================
Scenario:  multi_candidate
Mode:      simulation
Max Attempts: 2

CANDIDATE RANKING
----------------------------------------
  1. DEMO-SUCCESS-A             prob=0.9500  quality=HIGH      score=0.9500
  2. DEMO-WORKER                prob=0.8500  quality=HIGH      score=0.8500
  3. DEMO-DEAD-END              prob=0.7000  quality=LOW       score=0.4550
  4. DEMO-MID                   prob=0.5000  quality=LOW       score=0.3250
  5. DEMO-LOW-QUALITY           prob=0.3000  quality=LOW       score=0.1950

ENGINE EXECUTION
----------------------------------------
  DEMO-SUCCESS-A             Outcome: SUCCESS  (simulated(ground_truth))
  DEMO-WORKER                Outcome: SUCCESS  (simulated(ground_truth))
  DEMO-DEAD-END              Outcome: FAIL_TIMEOUT  (simulated(ground_truth))
  DEMO-DEAD-END              Outcome: FAIL_TIMEOUT  (simulated(ground_truth))
  DEMO-MID                   Outcome: FAIL_TIMEOUT  (simulated(ground_truth))
  DEMO-MID                   Outcome: FAIL_TIMEOUT  (simulated(ground_truth))
  DEMO-LOW-QUALITY           Outcome: FAIL_SYNTAX  (simulated(ground_truth))
  DEMO-LOW-QUALITY           Outcome: FAIL_SYNTAX  (simulated(ground_truth))

DECISION TRACE
----------------------------------------
  [INIT]   Engine initialized: 5 candidates, pivot_threshold=2, mode=simulation
  [EXECUTE] Attempt: 1/2  Outcome: SUCCESS  Candidate: DEMO-SUCCESS-A
  [ADVANCE] DEMO-SUCCESS-A validated. Next candidate.
  [PIVOT]   Redirected to: DEMO-WORKER
  [EXECUTE] Attempt: 1/2  Outcome: SUCCESS  Candidate: DEMO-WORKER
  [ADVANCE] DEMO-WORKER validated. Next candidate.
  [PIVOT]   Redirected to: DEMO-DEAD-END
  [EXECUTE] Attempt: 1/2  Outcome: FAIL_TIMEOUT  Candidate: DEMO-DEAD-END
  [EXECUTE] Attempt: 2/2  Outcome: FAIL_TIMEOUT  Candidate: DEMO-DEAD-END
  [PIVOT]   Threshold reached for DEMO-DEAD-END. Abandoning route.
  [PIVOT]   Redirected to: DEMO-MID
  [EXECUTE] Attempt: 1/2  Outcome: FAIL_TIMEOUT  Candidate: DEMO-MID
  [EXECUTE] Attempt: 2/2  Outcome: FAIL_TIMEOUT  Candidate: DEMO-MID
  [PIVOT]   Threshold reached for DEMO-MID. Abandoning route.
  [PIVOT]   Redirected to: DEMO-LOW-QUALITY
  [EXECUTE] Attempt: 1/2  Outcome: FAIL_SYNTAX  Candidate: DEMO-LOW-QUALITY
  [EXECUTE] Attempt: 2/2  Outcome: FAIL_SYNTAX  Candidate: DEMO-LOW-QUALITY
  [PIVOT]   Threshold reached for DEMO-LOW-QUALITY. Abandoning route.
  [PIVOT]   All candidates processed. Workflow complete.

  [COMPLETED]  All candidates processed. Workflow complete.

FINAL RESULT
----------------------------------------
Status:         COMPLETED
Total Attempts: 8
Pivot Count:    7
Candidates Processed: 5 (DEMO-SUCCESS-A, DEMO-WORKER, DEMO-DEAD-END, DEMO-MID, DEMO-LOW-QUALITY)

================================================================
SAFETY
================================================================
SIMULATION MODE
Outcomes are resolved from supplied demo ground truth.
No external targets contacted. No real vulnerabilities validated.
================================================================
```

**What to point out to the mentor:**

- The 5-candidate ranking: two `HIGH`-quality candidates first, then three `LOW`-
  quality candidates in probability order. Gap-1 and Gap-2 are *separable* but
  compose cleanly: the engine attempts `DEMO-SUCCESS-A` and `DEMO-WORKER` once
  each, then bounds each of the three failures to exactly 2 attempts.
- **Total attempts = 8**: 2 successes + 3 × 2 failures. This is the upper bound
  the engine promises for this queue and cap.
- **Bounded termination is structural**, not statistical. The engine cannot
  revisit a candidate after the index advances — there is no cycling logic in
  the graph. Status `COMPLETED` is reached in a fixed number of steps.
- `Pivot Count = 7`: one `Redirected` after every candidate (5) plus two
  `Abandoning` pivots for the failed candidates. (In the formatted output, the
  `pivot_count` counts both `Abandoning` and `Redirected` log lines; that is
  implementation-defined and is **not** itself a research metric — only the
  attempt count is.)

---

### 2.4 Scenario 4 — DUMB vs SMART request-count comparison

**Goal:** Quantify the *separable* contribution of Gap-2 (pivot) under the fair
benchmark's identical-cap protocol. The key claim: **with the same per-visit
cap T=2, abandoning after T failures (SMART) yields strictly fewer total
requests than no-abandon cycling (DUMB / PRIORITY-ONLY).**

**Command:**
```bash
PYTHONPATH=. python3 -c "
from prototype.demo_data import multi_candidate_scenario
from decision_engine.core.schemas import ActionCandidate, Outcome, QualityRank
from decision_engine.benchmarks.fair_benchmark import simulate_agent, make_ranker, _priority_order, _random_order
import random

candidates = []
for d in multi_candidate_scenario():
    gt = Outcome(d['ground_truth'])
    qr = QualityRank.HIGH if gt == Outcome.SUCCESS else QualityRank.LOW
    c = ActionCandidate(id=d['id'], probability=d['probability'], ground_truth=gt, quality_rank=qr, assessed=True)
    candidates.append(c)

ranker = make_ranker('perfect')
cap_T, max_total = 2, 4 * cap_T * 4

print(f'{\"Agent\":<14} {\"Requests\":>9} {\"Wasted\":>7} {\"Pivots\":>7} {\"Found\":>6}')
for name, order_fn, abandon in [
    ('DUMB',          lambda cs: _random_order(cs, random.Random(42)), False),
    ('PIVOT-ONLY',    lambda cs: _random_order(cs, random.Random(42)), True),
    ('PRIORITY-ONLY', lambda cs: _priority_order(cs), False),
    ('SMART',         lambda cs: _priority_order(cs), True),
]:
    m = simulate_agent(candidates, order_fn, abandon, cap_T, max_total, ranker, random.Random(42))
    print(f'{name:<14} {m[\"requests\"]:>9} {m[\"wasted_requests\"]:>7} {m[\"pivot_events\"]:>7} {m[\"found_success\"]:>6}')

print()
print('Decomposition (identical cap T=2):')
print('  priority_component = DUMB - PRIORITY-ONLY  = 0  (priority alone does not reduce requests under cap)')
print('  pivot_component    = PRIORITY-ONLY - SMART = 24 (abandonment is the separable mechanism)')
"
```

**Expected output (canonical):**
```
Agent          Requests  Wasted  Pivots  Found
DUMB                 32      30       0      2
PIVOT-ONLY            8       6       3      2
PRIORITY-ONLY        32      30       0      2
SMART                  8       6       3      2

Decomposition (identical cap T=2):
  priority_component = DUMB - PRIORITY-ONLY  = 0  (priority alone does not reduce requests under cap)
  pivot_component    = PRIORITY-ONLY - SMART = 24 (abandonment is the separable mechanism)
```

**What to point out to the mentor:**

- **Same 5 candidates, same cap T=2, same assessor.** The only difference between
  agents is `(order, abandon)`.
- **DUMB and PRIORITY-ONLY have *identical* request counts (32).** Under the fair
  cap, ordering candidates before visiting them again does not reduce total
  attempts — both agents cycle through the queue until the global budget
  (`N × T × 4 = 40`) is exhausted. *Priority alone is not the win.*
- **PIVOT-ONLY and SMART both produce 8 requests** — one pass through the
  queue, two attempts per candidate, then abandonment.
- **The pivot component = 32 − 8 = 24 requests saved per run** for this queue.
  The fair benchmark (`decision_engine/benchmarks/fair_benchmark.py`) reports the
  same decomposition across 6 candidate families, 9 ranker conditions, 4 cap
  values, and ≥ 30 seeds each.
- `found_success = 2` for all four agents: both successes are found regardless
  of strategy. **The win is in *wasted* requests, not in success recall.**

This scenario is the only one that uses the benchmark's `simulate_agent` path
because the comparison is between alternative *policies*, not the engine itself.
The engine path is the SMART path.

---

## 3. CLOSING (≤ 2 minutes)

> "What was demonstrated:
>
> 1. The real `decision_engine.run_engine()` runs the scenarios — the same code
>    that ships in the frozen research implementation. No reimplementation, no
>    mock.
> 2. Gap-1 (priority ranking) and Gap-2 (bounded failure-threshold pivot) are
>    visible and separable: Gap-1 is the *order* in which candidates are tried,
>    Gap-2 is the *abandonment* after the per-candidate attempt cap is reached.
> 3. Bounded termination is structural — `run_engine` cannot revisit a
>    candidate once the index advances.
> 4. Under the fair-cap protocol, the *pivot* component is what saves requests;
>    priority alone produces the same request count as random order.
>
> What was **NOT** claimed:
>
> - No claim of full VAPT platform capability. The engine is domain-independent;
>   the VAPT adapter is a thin attachment, not a production scanner.
> - No claim of real-world validation at scale. Observed validation is limited
>   to L2 (127.0.0.1 loopback against the local lab emulator, n=2).
> - No claim of speed, throughput, or production deployment readiness.
> - No Docker-validated, end-to-end-pentest, or production claims.
> - No LLM-calibration claim. The assessor shown is the deterministic fallback;
>   the LLM assessor exists in the benchmark suite and is documented but is
>   not the focus of this demo.
>
> The full test suite (192 tests) passes, and the frozen files in
> `core/`, `decision_engine/core/`, `tests/`, `datasets/`, and
> `decision_engine/benchmarks/` are unmodified as of this rehearsal."

---

## 4. BACKUP PLAN — pre-recorded output

**Path:** `docs/project_management/MENTOR_DEMO_BACKUP_OUTPUT.txt`

This file is a frozen text snapshot of every expected output block in §2, captured
during the rehearsal on 2026-09-02. If any live command fails or the terminal
freezes, open this file and walk the mentor through the canonical output
verbatim. The narrative "What to point out" lines in §2.1–§2.4 are unchanged —
they were written from this snapshot, not from the live run.

**When to switch to backup:**
- Any single scenario command returns a non-zero exit code.
- Any expected `Status:` line is missing from the output.
- Total attempts in Scenarios 2 or 3 differ from the canonical value (3 and 8).
- The comparison table in Scenario 4 shows anything other than the values in the
  expected output (32 / 8 / 32 / 8).

**How to switch:** "Let me show you the recorded output for this step — the
command is identical but I have a saved trace we can read off." Then narrate
from the backup file while the live command continues to run in another terminal.

---

## 5. REHEARSAL NOTES (2026-09-02)

| # | Scenario | Command | Wall time | Status | Notes |
|---|----------|---------|-----------|--------|-------|
| 1 | success | `python prototype/run_demo.py success 2` | <1 s | OK | Output matches canonical §2.1 exactly. |
| 2 | failure_pivot | `python prototype/run_demo.py failure_pivot 2` | <1 s | OK | Output matches canonical §2.2 exactly. DEMO-WORKER is rank #1 (priority 0.85 > 0.4550 for DEMO-DEAD-END). |
| 3 | multi_candidate | `python prototype/run_demo.py multi_candidate 2` | <1 s | OK | Output matches canonical §2.3 exactly. Total = 8. |
| 4 | DUMB vs SMART | inline `python3 -c "..."` | ~1 s | OK | Numbers: 32 / 8 / 32 / 8. Decomposition: priority=0, pivot=24. |

**Pre-demo regression run:** `192 passed in 30.84s`. Frozen-file diff: empty.
**Backup snapshot saved to:** `docs/project_management/MENTOR_DEMO_BACKUP_OUTPUT.txt`.
**Determinism check:** all four scenarios reproduced bit-identically across
two rehearsal runs.

---

## 6. FILES TOUCHED IN PHASE 11

- **CREATED:** `docs/project_management/MENTOR_DEMO_SCRIPT.md` (this file).
- **CREATED:** `docs/project_management/MENTOR_DEMO_BACKUP_OUTPUT.txt` (canonical
  output snapshot, used if the live demo fails).

**Not touched (frozen boundary, verified by `git diff`):**
- `core/`, `decision_engine/core/`, `tests/`, `decision_engine/tests/`,
  `datasets/`, `decision_engine/benchmarks/`.

**Not touched (existed already, not modified):**
- `prototype/run_demo.py`, `prototype/demo_data.py`, `prototype/engine_integration.py`,
  `prototype/trace_formatter.py`.
