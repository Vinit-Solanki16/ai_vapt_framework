# T-DE-BOUNDARY — Independent Read-Only Architecture / Domain-Leakage Review

**Reviewer:** independent review agent (READ-ONLY)
**Date:** 2026-08-27
**Scope:** `decision_engine/core/*.py`, `decision_engine/adapters/vapt_adapter.py`, `decision_engine/benchmarks/agnostic_benchmark.py`
**Gates:** T-DE-TESTS passed (12/12 engine tests; TRACK0 39/39 frozen). No files modified; no commit made.

Verified boundary claim first (reproducible):
```
grep -rn "from core import|core\.|poc_corpus|labels\.json|exploit_assessor" decision_engine/core/
  -> only decision_engine.core.* imports; 0 VAPT code imports
```
The `.pyc` matches are compiled bytecode; every text match is `decision_engine.core.*` (the internal package), not the VAPT `core`. ✅ Confirmed.

---

## Findings (PASS / FAIL per challenge question)

### Q1. Do any VAPT/CVE/exploit assumptions hide in engine *logic* (not docstrings)? — **PASS**

Engine logic is generic:
- `engine.py` loop (`_assess_node`→`_execute_node`→`_evaluate`→`_pivot_node`): operates on `current_index`, `attempt_count`, `max_attempts`, `status`, `Outcome`. No CVE/exploit references in logic.
- `schemas.py:83-84` `priority_score() = probability * (0.5 + 0.5*quality)` — purely numeric; `id`/`probability`/`quality_rank`/`ground_truth` are domain-agnostic.
- `assessor.py:19-25` `deterministic_assessor` keys off `ground_truth == SUCCESS` / `probability` — no VAPT semantics.
- `Outcome` enum (`schemas.py:37-46`) carries VAPT-flavoured labels (`FAIL_NO_TARGET`, `FAIL_SYNTAX`) but these are **semantically generic failure buckets**, not CVE logic. Minor cosmetic caveat only — does not bind behaviour to VAPT.

**Verdict: PASS.** VAPT appears only in explanatory docstrings (explicitly disclosed in §A). No leakage into executable logic.

### Q2. Is the maintenance example structurally independent, or does it reuse VAPT data shapes by accident? — **PASS (with note)**

`agnostic_benchmark.py:30-47` defines tasks with `{id, probability, ground_truth}` — identical *interface* to `ActionCandidate`. This is **by design**, not accidental: the engine is domain-agnostic precisely because every domain is mapped to `ActionCandidate`. The *semantics* are genuinely different (T-REBOOT/T-PATCH vs CVE-xxxx), and the engine never reads task meaning — only `probability` and `ground_truth`.

**Caveat:** "Same data shape" is expected and correct, not a leak. Independence holds at the semantic level. PASS.

### Q3. Is the generic Executor truly generic (any execute_fn) or VAPT-shaped? — **PASS**

`executor.py:40-53`: in `real` mode it calls `self.execute_fn(candidate)` and only requires the return to be an `ExecutionResult`. The engine (`engine.py:69-87`) consumes solely `result.outcome` (`Outcome`). Nothing assumes a PoC/exploit. `simulation` mode reads `ground_truth` purely as a label.

**Verdict: PASS.** `execute_fn` is genuinely pluggable; the engine is blind to domain action content.

### Q4. Does checkpoint state encode domain assumptions? — **PASS**

`engine.py:163-190` `save/load_checkpoint` serialise `EngineState` (`candidates`, `current_index`, `current_id`, `quality_rank`, `attempt_count`, `max_attempts`, `status`, `mode`, `logs`, `results`). All fields are generic engine state; `logs` use only `[Pivot]`/`[Advance]`/`[Executor]` tokens. No VAPT-specific field is persisted. (T-DE-TESTS `test_de09` confirms round-trip reproducibility.)

**Verdict: PASS.**

### Q5. Is the benchmark circular / structurally biased toward SMART? — **FAIL (structurally biased; headline misleading)**

This is the one genuine problem. Analysis of `agnostic_benchmark.py`:

- **Asymmetric retry caps by construction.** SMART uses `max_attempts=2` (`agnostic_benchmark.py:54`); DUMB uses `while attempts < 5` (`agnostic_benchmark.py:67`). The total-attempt metric is therefore guaranteed to favour SMART *regardless of any intelligence*, purely because the cap is lower (2 vs 5).
- **The 8-vs-17 gap is entirely the cap difference, not Gap-1 priority.** Recomputing with a *fair* DUMB baseline (same cap 2): DUMB = 1 (T-REBOOT) + 2 (T-PATCH) + 2 (T-BACKUP) + 1 (T-CLEANUP) + 2 (T-AUDIT) = **8** — identical to SMART. SMART's priority ordering contributes **zero** attempt-count reduction here.
- **Gap-1 (priority) is never isolated.** Both successful tasks succeed on attempt 1 in any order; failing tasks fail in any order. Ordering only changes *which* task fails first, not the count — and there is no budget cap that would make "do useful work early" matter. The benchmark cannot demonstrate Gap-1 value at all; it only demonstrates the pivot *loop bound*.
- **Deterministic assessor** (`assessor.py:21`, keys off `ground_truth`) means Gap-1 *scoring quality* is not exercised either.

So the benchmark proves only: *"the engine runs and bounds a retry loop on a non-VAPT domain"* — a real but narrow proof-of-mechanism. It does **not** validly show "SMART beats DUMB because of intelligent prioritization," yet the docstring (`agnostic_benchmark.py:9-12`) and VERDICT (`agnostic_benchmark.py:92-95`) claim exactly that, and §B of the authority doc repeats "8 vs 17." This is a **circular/biased comparison** and an overclaim.

**Verdict: FAIL** on the specific question "is the benchmark circular/biased toward SMART?" — Yes, it is. The headline metric is an artefact of an unequal retry cap. This must be flagged to Hermes (do NOT silently "fix" the benchmark here; this is a read-only review). Recommended corrections for T-DE-BENCH: (a) give DUMB the *same* `max_attempts` cap and measure only the *priority-ordering* benefit under a shared attempt budget; (b) add a budget-at-N scenario where ordering actually changes outcomes; (c) rename the metric to "loop-bound demonstration," not "SMART beats DUMB."

---

## Summary

| # | Question | Verdict |
|---|----------|---------|
| 1 | VAPT assumptions in engine *logic* | **PASS** |
| 2 | Maintenance example independent | **PASS** (shape shared by design) |
| 3 | Executor truly generic | **PASS** |
| 4 | Checkpoint encodes domain assumptions | **PASS** |
| 5 | Benchmark circular/biased toward SMART | **FAIL** (cap-asymmetric; Gap-1 never isolated) |

The architecture is **genuinely domain-independent** (Q1–Q4 PASS). The generalized engine legitimately separates VAPT into `adapters/vapt_adapter.py` and keeps logic generic. However, the cross-domain *evidence* (Q5) is **weak and biased**: the agnostic benchmark's 8-vs-17 "win" is an artefact of comparing a 2-attempt pivot cap against a 5-attempt dumb loop, not of intelligent prioritization. The engine's domain independence is an architectural fact; the *claim that it demonstrably beats a fair baseline on a non-VAPT domain* is not yet supported by this benchmark.

**Recommendation to Hermes:** downgrade the §B "Engine bounds repeated failure on a NON-VAPT domain" row from "PARTIAL — initial cross-domain proof-of-mechanism" to "PARTIAL — loop-bound demo only; baseline unfair; Gap-1 unisolated," and route Q5's fix through T-DE-BENCH. Do not use the 8-vs-17 figure as evidence of SMART superiority in any thesis text.
