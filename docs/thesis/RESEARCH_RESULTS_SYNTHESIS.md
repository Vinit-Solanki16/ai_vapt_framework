# Research Results Synthesis (Phase 35)

> **Document type:** Consolidative synthesis - additive thesis artifact.
> **Scope:** GAP-1 (Phase 33A/33B/33C) and GAP-2 (Phase 34) evidence.
> **Status:** All experiments completed; frozen core verified unmodified;
> pytest suite 687 passed; historical artifacts checksum-verified unchanged.
> **Date:** 2026-10-07

---

## Table of Contents

1. [Research Integrity](#1-research-integrity)
2. [GAP-1: Pre-Execution Quality Assessment](#2-gap-1-pre-execution-quality-assessment)
3. [GAP-2: Failure-Aware Threshold Pivoting](#3-gap-2-failure-aware-threshold-pivoting)
4. [Cross-GAP Synthesis](#4-cross-gap-synthesis)
5. [Limitations](#5-limitations)
6. [Artifact Inventory](#6-artifact-inventory)
7. [Reproducibility](#7-reproducibility)

---

## 1. Research Integrity

All experiments are **controlled research validation** only.
No real targets, no network, no exploit execution.
Outcomes from static ground truth (GAP-1) or scripted playback tables (GAP-2),
independent of any assessor or pivot logic.

| Check | Result |
|-------|--------|
| decision_engine/core/ diff | Empty (zero changes) |
| decision_engine/benchmarks/ diff | Empty (zero changes) |
| Historical result files (Sep 16) | Unchanged timestamps, unchanged content |
| pytest suite | **687 passed**, 3 pre-existing warnings |
| Ground-truth independence (GAP-1) | Statically defined before assessment; never derived from assessor |
| No-fabrication check (GAP-2) | All 96 runs verified against static tables |
| Fidelity cross-validation (GAP-2) | All 24 walk-engine prefixes match frozen run_engine path |

---

## 2. GAP-1: Pre-Execution Quality Assessment

### 2.1 Research Question

"When candidate quality differences are meaningful, does AI-assisted
pre-execution assessment improve the order in which useful candidates are
selected compared with a probability/severity-only baseline?"

### 2.2 Phase 33A: LLM Structured-Output Probe (8 CVEs)

**Purpose:** Validate that local LLMs produce structured outputs through the
existing assessor path and measure reliability, consistency, and ranking
influence on the historical 8-CVE corpus (same as the Wave-12 baseline).

**Design:** A/B comparison of llama3.2:3b vs qwen2.5:3b, 5 repetitions each,
8 candidates, same prompt/temperature/schema. Measured: validity, fallback
rate, latency, consistency, inter-model agreement, and ranking influence
vs no-assessment baseline.

**Results:**

| Metric | llama3.2:3b | qwen2.5:3b |
|--------|-------------|------------|
| Valid structured output | 97.5% (39/40) | 100% (40/40) |
| Fallback rate | 2.5% (1/40) | 0.0% |
| Schema/parse failures | 1 | 0 |
| Quality distribution | 0H / 7M / 32L / 1N | 0H / 0M / 40L / 0N |
| Mean consistency agreement | 94.4% | 100% |
| All candidates consistent | No | Yes |
| Mean latency (s) | 12.7 (median 2.5) | 2.3 (median 2.3) |
| Ranking changed vs baseline | No (0 positions moved) | No (0 positions moved) |
| Inter-model order identical | Yes (both arms produced same order) |

**Key observation:** Despite different quality distributions (llama: 7M/32L;
qwen: 40L), both models produced **identical assessed order** and neither
changed ranking vs the no-assessment baseline. This corpus had insufficient
quality differentiation for ranking influence.

### 2.3 Phase 33B: Quality-Discriminating Ranking (SYN-QD-*)

**Purpose:** Test ranking influence when candidate population is deliberately
quality-discriminating (HIGH/MEDIUM/LOW tiers with clear syntactic, dependency,
privilege, and complexity differences). Probabilities anti-aligned with quality
to test whether assessment can overcome probability bias.

**Design:** 6 synthetic candidates (SYN-QD-*), 4 arms (no-assessment baseline,
deterministic, llama3.2:3b, qwen2.5:3b), 5 reps each. Same prompt/temperature/
schema. Rankings computed via frozen `rank_candidates`.

**Results:**

| Arm | Ranking change | Top-1 change | Mean displacement | Quality distribution |
|-----|---------------|-------------|-------------------|---------------------|
| Baseline | 0.0 (0/5) | 0.0 | 0.00 | N/A (unassessed) |
| Deterministic | 1.0 (5/5) | 1.0 | 2.33 | 10 HIGH, 20 LOW |
| llama3.2:3b | 1.0 (5/5) | 1.0 | 0.93 | 9 MEDIUM, 21 LOW |
| qwen2.5:3b | 0.0 (0/5) | 0.0 | 0.00 | 30 LOW (uniform) |

**Key observations:**
- Deterministic arm produces maximal displacement (2.33) by perfectly separating
  HIGH-tier (2 candidates rated HIGH) from all others (4 rated LOW).
- Llama changes ranking (displacement 0.93) but its top-1 is SYN-QD-MED-02
  (MEDIUM tier, probability 0.74), not a HIGH-tier candidate. Llama assigned
  MEDIUM to HIGH-02 and MED-01/MED-02 but LOW to HIGH-01.
- Qwen produces **uniform LOW** across all 30 assessments (every candidate,
  every repetition). Zero ranking change. This is a **valid null result**:
  a uniform-LOW assessor cannot influence ranking.
- Llama consistency: 96.7% modal agreement. Qwen: 100% (because uniform).
- Inter-model paired rank agreement (from Phase 33C, same models/corpus): 50%.

### 2.4 Phase 33C: Operational Effectiveness (SYN-OE-*)

**Purpose:** Test whether ranking changes translate into operational effectiveness
(better candidate selection within a fixed attempt budget).

**Design:** 6 synthetic candidates (SYN-OE-*), 4 arms (no-assessment baseline,
deterministic, llama3.2:3b, qwen2.5:3b), 5 reps each, attempt budget = 3,
stop at first useful success. Ground truth statically defined (HIGH-tier = useful,
MEDIUM/LOW-tier = non-useful). Probabilities anti-aligned with quality.

**Results:**

| Arm | Top-1 useful | 1st-attempt success | Success in budget (3) | Mean total/wasted | Mean displacement |
|-----|-------------|-------------------|----------------------|-------------------|------------------|
| A. Baseline | 0.00 (0/5) | 0.00 | 0.00 (0/5) | 3.0 / 3.0 | 0.00 |
| B. Deterministic | 1.00 (5/5) | 1.00 | 1.00 (5/5) | 1.0 / 0.0 | 2.33 |
| C. Llama | 0.00 (0/5) | 0.00 | 0.00 (0/5) | 3.0 / 3.0 | 0.93 |
| D. Qwen | 0.00 (0/5) | 0.00 | 0.00 (0/5) | 3.0 / 3.0 | 0.00 |

Attempts until useful success (uncapped position):
- Baseline: 5 (all reps)
- Deterministic: 1 (all reps)
- Llama: 4-5 (first useful candidate ranked 4th-5th)
- Qwen: 5 (all reps)

**Secondary metrics:**
- Structured-output validity: 100% both LLM arms (0 fallbacks)
- Consistency (modal agreement): deterministic 1.00, qwen 1.00 (uniform LOW),
  llama 0.83
- Latency mean (per assessment): llama ~41.1 s, qwen ~2.3 s
- Llama-qwen paired rank agreement: 0.50 (mode agreement 1/6 candidates)

### 2.5 GAP-1 Mechanism-Validity Conclusion

| Assessor | Changes ranking? | Mechanism valid? |
|----------|---------------|-----------------|
| Deterministic | Yes (displacement 2.33) | Yes |
| Llama 3.2 3B | Yes (displacement 0.93) | Yes |
| Qwen 2.5 3B | No (displacement 0.00) | No (uniform LOW) |

The ranking mechanism (probability * quality-weight) works as designed: when
quality signal varies (deterministic: HIGH vs LOW; llama: MEDIUM vs LOW),
ranking changes. When quality signal is uniform (qwen: all LOW), ranking does
not change. This confirms the mechanism is sensitive to quality input.

### 2.6 GAP-1 Operational-Effectiveness Conclusion

| Assessor | Improves outcomes vs baseline? |
|----------|------------------------------|
| Deterministic | Yes (perfect: top-1 useful 5/5, success on attempt 1, zero waste) |
| Llama 3.2 3B | **No** (identical to baseline: 0/5 success, 3.0 wasted) |
| Qwen 2.5 3B | **No** (identical to baseline: 0/5 success, 3.0 wasted) |

**Neither LLM arm improved operational outcomes.** Llama changed the ranking
but selected a non-useful top-1 (usually SYN-OE-MED-02) and succeeded within
budget 0/5. Qwen matched baseline exactly (uniform LOW, zero displacement).
Neither reduced wasted attempts relative to baseline (3.0 vs 3.0).

**CRITICAL INTERPRETATION:**
- The deterministic Phase-33C arm's perfect score is an **oracle-contaminated
  ceiling/reference, NOT predictive evidence**. The existing deterministic
  assessor reads the candidate's ground-truth label by construction
  (SUCCESS maps to HIGH), so it acts as a sensitivity control, not a fair
  predictor. Its value is to confirm the operational model CAN register
  improvement when ranking is informative -- which makes the LLM arms'
  zero benefit interpretable rather than attributable to a broken harness.
- Llama changed ranking but did not improve operational outcomes.
- Qwen produced a valid null result due to uniform LOW assessments.

### 2.7 GAP-1 Limitations

- n = 5 repetitions per arm; descriptive statistics only, no significance tests.
- Single 6-candidate corpus with deliberately anti-aligned probability/quality.
  Results do not generalize beyond this controlled regime.
- Single attempt per candidate; no partial-credit or retry dynamics.
- LLM fallback path was never triggered (0 fallbacks); fallback behavior
  under failure is untested here.
- Llama shows run-to-run rank jitter (mean displacement 1.07 vs 0.93);
  operational metrics were identical across runs.
- Models tested: only llama3.2:3b and qwen2.5:3b via Ollama.
  Results do not imply behavior of larger or different models.

### 2.8 GAP-1 Supported Claims

- The ranking mechanism (probability * quality-weight) is sensitive to quality
  input: non-uniform quality changes ranking; uniform quality does not.
- llama3.2:3b produces differentiated quality ranks (MEDIUM/LOW) and changes
  ranking on controlled synthetic corpora with meaningful quality differences.
- qwen2.5:3b produces uniform LOW on the tested synthetic corpora and does
  not change ranking.
- On the tested controlled corpus, LLM assessment did not improve candidate
  selection outcomes vs the probability-only baseline.
- The deterministic assessor acts as a valid oracle-contaminated ceiling
  reference for sensitivity validation.

### 2.9 GAP-1 Unsupported Claims (explicitly NOT made)

- Universal AI superiority in VAPT or exploit ranking.
- Improved VAPT effectiveness in general.
- Real-world exploitation effectiveness (corpus is synthetic, outcomes simulated).
- Predictive power of LLM quality assessment for actual exploit success.
- Any claim that LLM assessment is universally better or worse than baselines.
- Statistical significance (n = 5 reps/arm supports descriptive only).

---

## 3. GAP-2: Failure-Aware Threshold Pivoting

### 3.1 Research Question

"Do state-aware failure-threshold pivoting reduce repeated wasted attempts
and improve useful-candidate discovery compared with retrying the same
candidate?"

### 3.2 Phase 34: Failure-Pivot Effectiveness

**Purpose:** Evaluate whether failure counters and threshold-based pivoting
reduce repeated wasted attempts and discover useful candidates that a
no-pivot retry baseline misses.

**Design:** 8 controlled synthetic scenarios with independently specified
per-(candidate, attempt) outcome scripts. 4 arms per scenario:
no-pivot retry baseline, threshold T=1, T=2, T=3. 3 deterministic reps
each (96 total runs). Budget-capped stop-on-success. Outcomes fixed before
any run; verified per attempt against static tables (no-fabrication check).

**Mechanism fidelity:** For every scenario x threshold, the frozen
run_engine (LangGraph GAP-2 path, uncapped) was executed with a fresh
playback stub. All 24 walk sequences equal the engine trace prefix and
all rankings match -- the measured pivot behavior IS the real GAP-2
mechanism plus an operational budget cap and stop-on-success.

**Results (per-scenario means over reps):**

| Scenario | No-pivot | T=1 | T=2 | T=3 |
|----------|----------|-----|-----|-----|
| S0 immediate success | 1 att / 1.0 suc / 0 rep / 0 piv | 1 / 1.0 / 0 / 0 | 1 / 1.0 / 0 / 0 | 1 / 1.0 / 0 / 0 |
| S1 fail-then-success | 6 att / 0.0 suc / 5 rep / 0 piv | 2 / 1.0 / 0 / 1 | 3 / 1.0 / 1 / 1 | 4 / 1.0 / 2 / 1 |
| S2 flaky-then-success | 3 att / 1.0 suc / 2 rep / 0 piv | 2 / 1.0 / 0 / 1 | 3 / 1.0 / 1 / 1 | 3 / 1.0 / 2 / 0 |
| S3 early recovery | 2 att / 1.0 suc / 1 rep / 0 piv | 2 / 1.0 / 0 / 1 | 2 / 1.0 / 1 / 0 | 2 / 1.0 / 1 / 0 |
| S4 multi-fail | 9 att / 0.0 suc / 8 rep / 0 piv | 3 / 1.0 / 0 / 2 | 5 / 1.0 / 2 / 2 | 7 / 1.0 / 4 / 2 |
| S5 all fail | 12 att / 0.0 suc / 11 rep / 0 piv | 3 / 0.0 / 0 / 2 | 6 / 0.0 / 3 / 2 | 9 / 0.0 / 6 / 2 |
| S6 late success | 12 att / 0.0 suc / 11 rep / 0 piv | 3 / 1.0 / 0 / 2 | 5 / 1.0 / 2 / 2 | 7 / 1.0 / 4 / 2 |
| S7 tight budget (4) | 4 att / 0.0 suc / 3 rep / 0 piv | 3 / 1.0 / 0 / 2 | 4 / 0.0 / 2 / 2 | 4 / 0.0 / 2 / 1 |

Legend: att = total attempts, suc = success-in-budget rate,
rep = repeated attempts, piv = pivot count.

**State-correctness:** All checks pass on all 96 runs -- counters increment
1,2,3... per candidate with no cross-candidate leak and reset on pivot; every
abandonment consumed exactly T attempts; every pivot targeted the next ranked
candidate; no run exceeded its budget; all runs terminated.

### 3.3 GAP-2 State/Mechanism-Validity Conclusion

The GAP-2 mechanism works exactly as specified:
- Per-candidate failure counters increment correctly and reset on pivot.
- Exact threshold triggering (abandon after exactly T consecutive failures).
- Correct next-candidate pivots (always the next ranked candidate).
- No counter leakage across candidates.
- Bounded termination under all-fail and budget-capped conditions.
- Fidelity cross-validation ties measured behavior to frozen engine implementation.

### 3.4 GAP-2 Operational-Effectiveness Conclusion

Threshold pivoting reduces repeated wasted attempts in appropriate scenarios
and discovers useful candidates the retry baseline never reaches:

- **S1 (fail-then-success):** Pivoting finds success the retry baseline misses.
  No-pivot: 6 attempts, 0% success. T=1: 2 attempts, 100%. T=2: 3 att. T=3: 4 att.
  Lower thresholds find success sooner when failures are persistent.
- **S4 (multi-fail):** No-pivot exhausts budget on one candidate (0% success).
  All pivot arms reach the 3rd candidate (100% success).
  T=1: 3 att, T=2: 5 att, T=3: 7 att.
- **S6 (late success):** Same pattern. No-pivot: 12 att, 0%.
  T=1: 3 att, 100%. T=2: 5 att. T=3: 7 att.
- **S5 (all fail):** No arm succeeds (nothing to discover).
  Pivoting only bounds the loss: T=1: 3 att, T=2: 6 att, T=3: 9 att vs 12.

**Honestly recorded non-improvements:**
- **S0:** All arms identical (1 attempt, success). Pivoting adds nothing when
  the first candidate succeeds immediately.
- **S2 (flaky-then-success):** Retrying pays off -- no-pivot succeeds on attempt
  3 via the flaky candidate recovery, matching T=3. T=1/T=2 succeed via the
  second candidate after abandoning a recoverable one. This shows retrying
  CAN be beneficial for recoverable/flaky candidates.
- **S3 (early recovery):** All arms succeed in 2 attempts; T=1 pivot is
  pure mechanism overhead with zero operational gain.
- **S7 (tight budget, 4):** Only T=1 reaches success (3 att, 100%).
  T=2, T=3, and no-pivot ALL fail (4 att, 0%). Higher thresholds can
  pivot too late under budget constraints.

### 3.5 GAP-2 Threshold Trade-offs

No threshold was universally best:
- **T=1** is most efficient at eliminating repeated waste and finding success
  sooner when failures are persistent (S1: 2 att, S4: 3 att, S6: 3 att,
  S7: 3 att). But it pivots too early for recoverable/flaky candidates
  (S2/S3), abandoning candidates that would have succeeded on retry.
- **T=2** is a compromise: fewer repeated attempts than T=3 but more than T=1.
  Misses success in tight-budget S7.
- **T=3** allows more retries before pivoting (beneficial for flaky candidates)
  but wastes more attempts on truly failing ones (S1: 4 att vs T=1: 2 att).
- **Threshold choice interacts with budget:** under tight budgets, only low
  thresholds can still reach success; no single threshold is optimal.

**Key finding:** Failure counters and threshold pivoting were correctly
implemented. Pivoting reduced repeated waste in appropriate scenarios.
Retrying can be beneficial for recoverable/flaky candidates.
Aggressive thresholds can pivot too early. No threshold was universally best.

### 3.6 GAP-2 Limitations

- 8 controlled scenarios with scripted outcomes; not real exploit execution.
- Deterministic repetitions (3 reps, identical); no stochastic variation.
- Outcomes are scripted SUCCESS/FAIL tokens; not actual exploit results.
- Descriptive statistics only; no significance tests.
- Thresholds tested: T=1, 2, 3 only; no continuous optimization.
- Budget sizes are scenario-specific; budget-threshold interaction
  requires per-deployment tuning.
- No evaluation of adaptive or dynamic threshold strategies.
- Candidate ranking uses deterministic assessor (oracle-influenced);
  real-world ranking noise not modeled.

### 3.7 GAP-2 Supported Claims

- Failure counters and threshold pivoting are correctly implemented
  (state-correctness verified on all 96 runs).
- Pivoting reduces repeated wasted attempts when the first-ranked
  candidate cannot succeed.
- Pivoting discovers useful candidates the retry baseline never reaches
  (no-pivot success rate 0.0 vs pivot 1.0 in S1, S4, S6).
- Retrying can be beneficial for recoverable/flaky candidates (S2, S3).
- Aggressive thresholds can pivot too early, abandoning candidates that
  would have succeeded on retry.
- Threshold choice interacts with available budget; no single threshold
  is optimal across all scenarios.

### 3.8 GAP-2 Unsupported Claims (explicitly NOT made)

- Universally optimal pivot threshold.
- Universal improvement of pivoting over retrying (S2/S3 show cases
  where retrying performs equally well or is necessary).
- Real-world VAPT effectiveness (outcomes are scripted synthetic tables).
- Real-world exploitation effectiveness.
- Statistical significance (deterministic reps; no CIs, no significance tests).

---

## 4. Cross-GAP Synthesis

### 4.1 Relationship Between GAP-1 and GAP-2

GAP-1 (pre-execution quality assessment) and GAP-2 (failure-aware pivoting)
address **complementary but distinct problems**:

- **GAP-1** tries to improve the initial ranking so the engine picks better
  candidates first. Results: ranking mechanism works, but tested LLMs did not
  produce quality assessments that improved outcomes on the controlled corpus.

- **GAP-2** handles what happens when candidates fail: should the engine retry
  the same candidate or pivot to the next? Results: pivoting is effective
  for persistent failures but retrying is sometimes beneficial for flaky ones.

Together they form a two-layer strategy: assessment to guide initial selection
(GAP-1) and stateful pivot logic to handle execution failure (GAP-2).

### 4.2 What This Research Package Establishes

| Question | Answer |
|----------|--------|
| Does quality-assessment change ranking? | Yes when quality signal varies (deterministic, llama). No when uniform (qwen). |
| Does LLM quality assessment improve outcomes on tested corpus? | No (both LLM arms: 0/5 success within budget, identical to baseline). |
| Are failure counters and threshold pivoting correctly implemented? | Yes (all 96 state-correctness checks pass). |
| Does pivoting reduce repeated wasted attempts? | Yes, when failures are persistent (S1, S4, S5, S6, S7). |
| Is retrying sometimes better? | Yes, for recoverable/flaky candidates (S2, S3). |
| Is there a universally optimal pivot threshold? | No (threshold choice depends on scenario and budget). |

---

## 5. Limitations (Global)

1. **All experiments are controlled research validation.** No real targets,
   no network execution, no actual exploit success rates.
2. **GAP-1 corpus is synthetic** with deliberately anti-aligned
   probability/quality. Results do not generalize beyond this regime.
3. **GAP-2 outcomes are scripted tables** -- SUCCESS means a scripted token,
   not real exploit success.
4. **Small sample sizes:** GAP-1 n=5 reps/arm (descriptive only),
   GAP-2 n=3 deterministic reps (descriptive only).
5. **No significance tests** claimed or reported anywhere.
6. **Two LLM models tested** (llama3.2:3b, qwen2.5:3b) via Ollama only.
   Results do not imply behavior of larger or different models.
7. **Single prompt and schema** used throughout; no prompt optimization
   or schema variation tested.
8. **Deterministic assessor is oracle-contaminated** (reads ground truth
   by construction); its perfect score is a ceiling reference, not
   predictive evidence.
9. **No real-world exploitation effectiveness** is claimed or implied.

---

## 6. Artifact Inventory

### Experiment Scripts
| File | Phase | Description |
|------|-------|-------------|
| experiments/phase33a_llm_ab_experiment.py | 33A | LLM A/B comparison (llama vs qwen, 8 CVEs) |
| experiments/phase33a_probe_structured_output.py | 33A | Structured output probe |
| experiments/gap1_quality_discriminating_experiment.py | 33B | Quality-discriminating ranking (SYN-QD-*) |
| experiments/gap1_operational_effectiveness_experiment.py | 33C | Operational effectiveness (SYN-OE-*) |
| experiments/gap2_failure_pivot_effectiveness_experiment.py | 34 | Failure-pivot effectiveness (8 scenarios) |

### Result Files (JSON)
| File | Phase | Size |
|------|-------|------|
| experiments/results/llm_model_comparison.json | 33A | 12 KB |
| experiments/results/phase33a_structured_output_probe.json | 33A | 7 KB |
| experiments/results/gap1_quality_discriminating.json | 33B | 38 KB |
| experiments/results/gap1_operational_effectiveness.json | 33C | 62 KB |
| experiments/results/gap2_failure_pivot_effectiveness.json | 34 | 323 KB |

### Result Files (CSV)
| File | Phase |
|------|-------|
| experiments/results/llm_model_comparison.csv | 33A |
| experiments/results/llm_model_comparison_observations.csv | 33A |
| experiments/results/gap1_quality_discriminating.csv | 33B |
| experiments/results/gap1_operational_effectiveness.csv | 33C |
| experiments/results/gap2_failure_pivot_effectiveness.csv | 34 |

### Thesis Documentation
| File | Description |
|------|-------------|
| docs/thesis/RESEARCH_RESULTS_SYNTHESIS.md | This document (Phase 35) |
| docs/thesis/GAP1_OPERATIONAL_EFFECTIVENESS.md | Phase 33C individual report |
| docs/thesis/GAP2_FAILURE_PIVOT_EFFECTIVENESS.md | Phase 34 individual report |
| docs/thesis/GAP1_EFFECTIVENESS_EVALUATION.md | Phase 33B individual report |
| docs/thesis/LLM_MODEL_COMPARISON.md | Phase 33A individual report |

---

## 7. Reproducibility

### GAP-1 Reproduction
- Phase 33A: `python experiments/phase33a_llm_ab_experiment.py`
  (requires Ollama with llama3.2:3b and qwen2.5:3b; or
  `--from-observations` to regenerate summary without re-inference)
- Phase 33B: `python experiments/gap1_quality_discriminating_experiment.py`
  (requires Ollama)
- Phase 33C: `python experiments/gap1_operational_effectiveness_experiment.py`
  (requires Ollama)

### GAP-2 Reproduction
- Phase 34: `python experiments/gap2_failure_pivot_effectiveness_experiment.py`
  (fully deterministic; no LLM required; synthetic playback only)

### Verification
- Full test suite: `python -m pytest` (687 tests, all pass)
- Research core integrity: `git diff HEAD -- decision_engine/` (must be empty)
- Historical artifacts: timestamps from Sep 16 must be unchanged

### Validation Results (Phase 35)
- pytest: 687 passed, 3 warnings (pre-existing Pydantic serialization)
- Research core diff: empty
- Historical artifacts: unchanged
- All new artifacts are additive (untracked or new files only)

---

*End of Phase 35: Final Research Synthesis.*

