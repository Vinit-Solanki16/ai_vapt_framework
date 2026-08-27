# T-DE-BENCH — Benchmark Fairness / Reproducibility / Structural-Bias Review

**Reviewer:** independent review agent (READ-ONLY + experiment design only)
**Date:** 2026-08-27
**Scope reviewed:** `decision_engine/benchmarks/agnostic_benchmark.py` (TRACK1), `tests/evaluate.py` (TRACK0 VAPT sim), `tests/test_ttests_gaps.py`, `decision_engine/core/*.py`.
**No files modified; no commit made.** This is a critique + a concrete (not implemented) experiment design for Hermes to enact later.

---

## 1. Current RQ coverage (from authority review)

| RQ | Question | Agnostic bench | VAPT `evaluate.py` | Status |
|----|----------|----------------|--------------------|--------|
| RQ1 | Scoring-information value (does quality ranking *help*?) | Not isolated | Not isolated | **Unmet** |
| RQ2 | Sensitivity to scoring errors (perfect/noisy/random/heuristic/LLM) | None (deterministic only) | None (ollama sim only) | **Unmet** |
| RQ3 | Pivot-policy comparison (thresholds, adaptive) | None (2 vs ∞) | None (2 vs 10) | **Unmet** |
| RQ4 | Domain-structure generalization | 1 family, n=5 | 1 target, n=3 | **Weak** |

Both benchmarks currently demonstrate *mechanism existence*, not *validated advantage*.

---

## 2. Concrete bias findings (>=3 required; 11 listed)

**B1 — Asymmetric retry cap (agnostic).** `agnostic_benchmark.py:54` SMART uses `max_attempts=2`; `agnostic_benchmark.py:67` DUMB uses `while attempts < 5`. The request-count win (8 vs 17) is entirely the 2-vs-5 cap difference. With a *fair* DUMB cap of 2, DUMB also scores 8 — identical to SMART. (See T-DE-BOUNDARY Q5.)

**B2 — Asymmetric retry cap (VAPT).** `tests/evaluate.py:53` SMART `threshold=2`; `tests/evaluate.py:95,109` DUMB `hard_cap=10`. Reported "5 req vs 21 req" is again cap-driven: 1 (success) + 2 + 2 = 5 vs 1 + 10 + 10 = 21. A fair DUMB cap of 2 yields 5 = SMART. Same defect as B1.

**B3 — Gap-1 priority never isolated.** In both benchmarks every *successful* candidate succeeds on attempt 1 in *any* order, and *failing* candidates fail in any order. There is no attempt budget that would make "try high-value first" change the outcome. So neither benchmark can attribute any win to priority ordering — only to the pivot cap. (RQ1 unmet.)

**B4 — Deterministic assessor keys off ground truth.** `decision_engine/core/assessor.py:21` maps `ground_truth == SUCCESS → HIGH`. The scorer never errs, so **scoring-information value is never exercised**: the engine's priority is *correct by construction*. RQ2 (noisy/random/LLM) is completely absent.

**B5 — "Completion %" is identical across agents (VAPT).** `tests/evaluate.py:121-131` both SMART and DUMB find the single labelled success → completion 33% both. The only differentiator is requests/loops, which (B2) is cap-driven. The benchmark therefore does **not** show SMART finds more vulns; it only shows fewer wasted requests on *known-failing* labels — a legitimate but narrower claim than the headline implies.

**B6 — No ablation to separate Gap-1 vs Gap-2.** Both "SMART" agents bundle priority + pivot. There is no PRIORITY-ONLY (no pivot) or PIVOT-ONLY (no priority) condition, so their individual contributions cannot be estimated (RQ1/RQ3).

**B7 — Single pivot threshold, no policy sweep (RQ3).** Only `threshold=2` vs "no pivot." No comparison across T ∈ {1,2,3,5} or adaptive policies. The choice T=2 is arbitrary and unaudited.

**B8 — Tiny, non-varied samples.** Agnostic: 5 tasks, 2 successes (`agnostic_benchmark.py:30-36`). VAPT: 3 findings, 1 success (`tests/evaluate.py:35-42`). No domain-structure variation (RQ4): no many-success, sparse-success, all-fail, long-tail, or correlated-quality regimes.

**B9 — Not reproducible / not aggregated.** Both report a single run, no seeds, no std/CIs. `evaluate.py` even times wall-clock (`tests/evaluate.py:118-120`) which is meaningless in simulation mode (no real I/O) and adds noise to the "time saved" delta.

**B10 — VAPT benchmark tied to one provider/path.** `PROVIDER="ollama"` (`tests/evaluate.py:43`); the LLM assessor path is never actually exercised in benchmarking (simulation resolves outcomes from labels). So "LLM sensitivity" (RQ2) is doubly absent.

**B11 — DUMB "loop_events" metric is by construction.** `tests/evaluate.py:110` DUMB increments `loops` whenever it hits `hard_cap` without success — guaranteed for every failing target. It measures "DUMB never self-terminates," not a tunable property; using it as the headline "loops avoided" overstates SMART's distinctive value vs. a *pivoting* baseline.

---

## 3. Experiment design proposal (raise proof-of-mechanism → validated)

**Goal:** isolate Gap-1 (priority) and Gap-2 (pivot) contributions, measure robustness to scoring error, and generalize across domain structures — under a *fair* protocol.

### 3.1 Synthetic, parameterized task-family generator (RQ4)
A single generator `make_family(kind, N, seed)` emitting `ActionCandidate(id, probability, quality_rank, ground_truth)` over these regimes:
- `many_success` (≈80% true success)
- `sparse_success` (≈10%)
- `all_fail` (0%)
- `long_tail` (power-law probabilities)
- `correlated` (high prob ⇒ high quality ⇒ high success)
- `anticorrelated` (high prob ⇒ low quality)
N ≥ 50 candidates per family; ≥ 30 random seeds per condition for CIs.

### 3.2 Scoring-noise sweeps (RQ2)
Replace the deterministic assessor with a *noisy ranker* injecting error at rates
`p ∈ {0.0 (perfect), 0.1, 0.25, 0.5, 1.0 (random)}`, plus a `heuristic` ranker
(probability-only, no quality) and an `llm_stub` ranker with controllable accuracy
(0.6 / 0.8 / 0.95) to emulate LLM assessor quality. Measure rank correlation
(Spearman) between assigned priority and true value, and the downstream metrics.

### 3.3 Pivot-policy baselines (RQ3) — the key ablation
Compare four agents **all under the SAME per-candidate attempt cap T** (removes B1/B2):
- **DUMB**: no scoring, no pivot, cap T (lower bound)
- **PIVOT-ONLY**: random order, pivot at T (isolates Gap-2)
- **PRIORITY-ONLY**: priority order, **no** pivot, cap T (isolates Gap-1)
- **SMART**: priority + pivot at T (full)
Sweep T ∈ {1, 2, 3, 5}. This decomposes the total request saving into a
priority component (DUMB − PRIORITY-ONLY) and a pivot component (PRIORITY-ONLY − SMART).

### 3.4 Metrics (per family × noise × policy × seed)
- `requests` (total attempts)
- `wasted_requests` (attempts on true-fail candidates)
- `found_success` (completion % over true successes)
- `loop_events` (executions over cap T)
- `ordering_gain` = requests(DUMB) − requests(SMART), decomposed via the ablation
- `rank_corr` (Spearman) for RQ2
Report **mean ± 95% CI** over seeds; dump JSONL for reproducibility. Drop wall-clock
from simulation metrics (B9).

### 3.5 Fair-cap protocol (fixes B1/B2/B5/B11)
Request-count comparisons use identical cap T across all agents; the pivot benefit
is measured as `wasted_requests(PIVOT-ONLY) − wasted_requests(SMART)` and the
priority benefit as `requests(DUMB) − requests(PIVOT-ONLY)`, both on identical caps.
Only then does "SMART beats baseline" become a valid claim.

### 3.6 VAPT generalization (RQ4 extension)
Re-run the same 4-agent protocol on the **full** `data/poc_corpus/labels.json`
(`tests/test_ttests_gaps.py:187` already iterates all labels) instead of the 3-entry
hand-picked `LABELED_FINDINGS` (`tests/evaluate.py:35-42`), so results generalize
beyond a curated n=3.

---

## 4. Verdict

- **Biases found:** 11 (B1–B11), all concrete and file:line-anchored. Required ≥3 — **met**.
- **Experiment design:** §3 provides families (3.1), noise levels (3.2), baselines (3.3), and metrics (3.4) for Hermes to enact. Required ≥1 — **met**.
- **Headline correction for Hermes:** the "8 vs 17" (agnostic) and "5 vs 21" (VAPT) figures are **cap-asymmetry artefacts**, not evidence of intelligent prioritization. They remain valid only as *loop-bound* demonstrations (proof-of-mechanism). Under the §3.5 fair-cap protocol, SMART's genuine, separable advantage is the pivot component on wasting attempts; the priority component is currently **unproven** and must be established by the ablation in §3.3 before any thesis claim of "SMART beats DUMB due to scoring" is allowed (ties to R3 claim register gate).
- **Recommended claim retiering:** downgrade "Engine bounds repeated failure on a NON-VAPT domain" from "PARTIAL — initial cross-domain proof-of-mechanism" to "PARTIAL — loop-bound demo only; priority (Gap-1) benefit unisolated; baseline unfair" until §3 is enacted.
