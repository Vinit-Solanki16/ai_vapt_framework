# GAP-1 Effectiveness Evaluation — Quality-Discriminating Corpus (Phase 33B)

## 0. Status and scope

RESEARCH EXPERIMENT. Controlled synthetic corpus (`SYN-QD-*`). Nothing here is
real-world exploit evidence; no candidate was executed. This document evaluates
the GAP-1 decision mechanism (does assessed quality enter and move ranking?),
NOT operational VAPT effectiveness (no validation outcome was measured).

Historical artifacts untouched: `llm_behavior.json`, `llm_model_comparison.json`,
`results.md`, and all prior numbers are unchanged. New additive artifacts only:

- `experiments/gap1_quality_discriminating_experiment.py` (harness)
- `experiments/results/gap1_quality_discriminating.json` (full record)
- `experiments/results/gap1_quality_discriminating.csv` (per-assessment rows)
- this document

## 1. Motivation

Phase 33A found 0% ranking change for both llama3.2:3b and qwen2.5:3b on the
8-CVE model-comparison corpus. Documented cause: insufficient ranking leverage
(few probability tiers; near-uniform quality ranks), so the ranking function
`priority = probability * (0.5 + 0.5 * quality)` had little opportunity to
reorder. A null ranking result under a null-leverage corpus says nothing about
the mechanism. This phase supplies leverage deliberately.

## 2. Corpus design (why it provides ranking leverage)

Six synthetic candidates, IDs `SYN-QD-*`, with probabilities in a tight band
(0.55–0.88) so that quality — not probability — decides order:

| id | prob | ground_truth (det. arm) | intended tier | code features |
|----|------|-------------------------|---------------|---------------|
| SYN-QD-HIGH-01 | 0.55 | SUCCESS | HIGH | valid syntax, stdlib only, complete, user privs |
| SYN-QD-HIGH-02 | 0.62 | SUCCESS | HIGH | valid, one common dep, error handling, complete |
| SYN-QD-MED-01 | 0.68 | FAIL_TIMEOUT | MEDIUM | valid but incomplete (NotImplementedError TODO), extra dep |
| SYN-QD-MED-02 | 0.74 | FAIL_TIMEOUT | MEDIUM | valid flow, requires root + noisy threaded design |
| SYN-QD-LOW-01 | 0.80 | FAIL_SYNTAX | LOW | syntax error, placeholder body, unrealistic kernel-module dep |
| SYN-QD-LOW-02 | 0.88 | FAIL_DEPENDENCY | LOW | malformed/pseudocode, undefined names, contradictory prereqs |

Baseline (no-assessment) order is pure probability:
`LOW-02 > LOW-01 > MED-02 > MED-01 > HIGH-02 > HIGH-01`.

A priori leverage (design rationale, not a result): if an assessor assigns the
intended tiers, scores are HIGH-02 0.62, MED-02 0.592, LOW-02 0.572, HIGH-01
0.55, MED-01 0.544, LOW-01 0.52 — the assessed order differs from baseline
including top-1. The deterministic assessor (HIGH on SUCCESS, else LOW here
since all non-SUCCESS probs < 0.9) likewise must reorder. Any arm returning
uniform ranks mathematically cannot reorder (priority monotonic in
probability) — that outcome is mechanism-consistent, not a mechanism failure.

## 3. Protocol (identical conditions, all arms)

- Same corpus, candidate order, probabilities (above).
- Same prompt (`core/exploit_assessor.py` SYSTEM_PROMPT + human template),
  same schema (`ExploitAssessment`), same temperature (0.1), same ranking
  formula and `rank_candidates` import (read-only; core/benchmarks unmodified).
- Explicit `code_sample` per candidate; `use_online=False` (fully local, no
  network); synthetic IDs hit no corpus label (`corpus_label` returns None).
- Arms: A no-assessment baseline; B deterministic (5 reps, pure function);
  C llama3.2:3b via Ollama (5 reps x 6 = 30 assessments);
  D qwen2.5:3b via Ollama (5 reps x 6 = 30 assessments).
- Per-assessment exceptions would count as invalid output with deterministic
  fallback (none occurred: 60/60 valid, 0 fallbacks).
- Metrics per rep: assessed order, order-changed, top-1/top-3-changed,
  per-candidate displacement, mean/total displacement, quality distribution.
- Statistics are descriptive only (n = 5 reps/arm). No inferential tests, no
  confidence intervals, no significance claims — the sample is too small.

## 4. Results

### Arm B — Deterministic
- Ranking-change rate **1.0** (5/5), top-1 **1.0**, top-3 **1.0**.
- Mean rank displacement 2.3333 (median 2.3333, sd 0, min = max = 2.3333).
- Assessed order every rep:
  `HIGH-02 > LOW-02 > HIGH-01 > LOW-01 > MED-02 > MED-01`.
- Quality distribution: HIGH 10, LOW 20. Consistency 1.0. Latency ~0.

### Arm C — llama3.2:3b
- Ranking-change rate **1.0** (5/5), top-1 **1.0**, top-3 **1.0**.
- Mean displacement: mean 0.9333, median 1.0, sd 0.1333, min 0.6667, max 1.0.
- Assessed order reps 0–3:
  `MED-02 > LOW-02 > LOW-01 > HIGH-02 > MED-01 > HIGH-01`;
  rep 4 swaps HIGH-02/MED-01 (single MEDIUM→LOW flip on HIGH-02).
- Quality distribution: LOW 21, MEDIUM 9, HIGH 0. Valid-output rate 1.0,
  fallback rate 0.0.
- Consistency overall 0.9667 (5/6 candidates 1.0; HIGH-02 0.8: MEDIUM x4, LOW x1).
- Latency (n=30): median 2.28s, min 1.79s, max **407.46s** (one rep-3 stall on
  HIGH-02 that still returned valid MEDIUM output), mean 15.91s skewed by that
  outlier (mean of remaining 29 ≈ 2.41s). Central tendency: median 2.28s.

### Arm D — qwen2.5:3b
- Ranking-change rate **0.0** (0/5), top-1 0.0, top-3 0.0, displacement 0.
- Quality distribution: **LOW 30/30**. Valid-output rate 1.0, fallback 0.0.
- Consistency 1.0 (all candidates, all reps).
- Latency (n=30): mean 2.30s, median 2.13s, sd 0.65s, min 1.73s, max 5.43s.

### Model comparison
| metric | llama3.2:3b | qwen2.5:3b |
|---|---|---|
| valid-output rate | 1.0 | 1.0 |
| fallback rate | 0.0 | 0.0 |
| consistency (overall agreement) | 0.9667 | 1.0 |
| latency median (mean) | 2.28s (15.91s w/ 1 stall) | 2.13s (2.30s) |
| quality distribution | LOW 21 / MED 9 | LOW 30 |
| ranking-change rate | 1.0 | 0.0 |
| mean rank displacement | 0.9333 | 0.0 |
| top-1 change rate | 1.0 | 0.0 |
| inter-model agreement (mode ranks) | 4/6 = 0.6667 (differ: HIGH-02, MED-02) | — |

## 5. Effectiveness interpretation (kept separate)

A. **Mechanism validity — CONFIRMED.** Assessment enters ranking:
deterministic 5/5 and llama 5/5 reps changed order; qwen 0/5 is exactly what
the formula predicts for uniform ranks (priority monotonic in probability).
The assess-before-rank path works.

B. **Ranking influence — CONDITIONAL.** Influence requires quality VARIANCE
from the assessor, not just corpus variance. Deterministic (HIGH vs LOW) moved
ranks by 2.33 positions/candidate; llama (MEDIUM vs LOW) by 0.93; qwen (all
LOW) by 0. Influence magnitude scales with the spread the assessor emits.

C. **Reliability — HIGH for both.** 60/60 valid structured outputs, zero
fallbacks, zero transport errors (one latency stall still returned valid JSON).

D. **Consistency — HIGH for both.** qwen 1.0; llama 0.9667 (one candidate
flipped once in five reps). No wild oscillation.

E. **Latency — COMPARABLE, one tail event.** Medians 2.28s vs 2.13s; llama had
a single 407s stall (cause undetermined — recorded, not excluded).

F. **Generalization — NOT established.** Synthetic non-exploit code; intended
tiers were NOT reproduced (both models graded the "HIGH" check-scripts LOW —
plausibly correct strictness toward benign scripts with no exploit logic, but
that reading is interpretive, not measured). Real-CVE behavior, other
temperatures/prompts/models, and any link from ranking movement to validation
success remain unproven.

## 6. Research conclusion (conservative)

1. **Does pre-execution quality assessment affect ranking under a
   quality-discriminating corpus?** Yes for assessors that emit spread:
   deterministic 5/5 reps, llama 5/5 reps changed order including top-1.
2. **How often?** Deterministic 100%, llama 100%, qwen 0% (5 reps each).
3. **How much?** Mean displacement 2.33 (deterministic) / 0.93 (llama) / 0.0
   (qwen) positions per candidate; top-1 changed in all deterministic and
   llama reps.
4. **Do llama and qwen differ?** Yes: qwen is uniformly strict (all LOW,
   faster, perfectly consistent); llama discriminates MEDIUM vs LOW
   (96.7% consistent); mode-rank agreement 4/6.
5. **Sufficient to claim improved VAPT effectiveness?** NO. No execution, no
   validation outcome, synthetic corpus, n = 6 candidates x 5 reps. The
   mechanism works; improved operational outcome is unmeasured.
6. **What remains unproven?** Everything in F above, plus statistical
   significance (sample too small by design for this probe).

## 7. Limitations

- n = 6 synthetic candidates, 5 reps/arm: descriptive statistics only.
- Intended quality tiers were not reproduced by either model (no HIGH grades
  from either LLM); corpus "discrimination" was partial and model-defined.
- Single temperature (0.1), single prompt, single schema; no prompt-robustness
  sweep.
- One unexplained 407s Ollama latency stall (valid output regardless).
- No execution backend: ranking movement is not validation improvement.
- qwen result (0% change) must not be misread as "qwen is worse" — under a
  corpus it grades uniformly, ANY ranker of this form must preserve order;
  strictness vs discrimination is a separate question from correctness.
