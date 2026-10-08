# GAP-1 Operational Effectiveness (Phase 33C)

## Research question

"When candidate quality differences are meaningful, does AI-assisted
pre-execution assessment improve the order in which useful candidates are
selected compared with a probability/severity-only baseline?"

## Design (four arms, all else identical)

| Arm | Ranking signal |
|-----|----------------|
| A. Baseline (probability-only) | No assessment; probability order |
| B. Deterministic | Existing deterministic quality assessor |
| C. Llama (`llama3.2:3b`, authoritative baseline config) | LLM quality grades |
| D. Qwen (`qwen2.5:3b`, experimental arm only) | LLM quality grades |

Identical across arms: synthetic corpus (6 candidates, `SYN-OE-*`), candidate
order, probabilities, static ground-truth usefulness, attempt budget (3),
ranking procedure (`rank_candidates`, read-only), stopping rule (stop at first
useful success or budget exhaustion, one attempt per candidate), prompts,
temperature (0.1), schema, repetitions (5).

Corpus construction: code quality is tiered (HIGH/MEDIUM/LOW intended tiers)
while probabilities are anti-aligned with quality (LOW-quality candidates
carry the highest probabilities, 0.80–0.88; HIGH-quality carry 0.55–0.62).
Ground-truth usefulness was fixed statically before any assessment ran
(HIGH-tier = useful/SUCCESS; MEDIUM/LOW-tier = non-useful/FAIL_*) and was
never derived from, copied from, or conditioned on any assessor output.
Outcomes were resolved from that static ground truth via the existing
simulation `Executor` — nothing was executed, no network, no targets.

## Results (final artifacts, run 2 of 2; run 1 reproduced the pattern)

| Arm | Top-1 useful | 1st-attempt success | Success in budget (3) | Mean total / wasted | Mean rank displacement |
|-----|------|------|------|------|------|
| A. Baseline | 0.00 (0/5) | 0.00 | 0.00 (0/5) | 3.0 / 3.0 | 0.00 |
| B. Deterministic | 1.00 (5/5) | 1.00 | 1.00 (5/5) | 1.0 / 0.0 | 2.33 |
| C. Llama | 0.00 (0/5) | 0.00 | 0.00 (0/5) | 3.0 / 3.0 | 0.93 |
| D. Qwen | 0.00 (0/5) | 0.00 | 0.00 (0/5) | 3.0 / 3.0 | 0.00 |

Attempts until useful success (uncapped position): baseline 5, deterministic
1, llama 4–5 (first useful candidate ranked 4th–5th), qwen 5. Baseline first
attempts resolved as FAIL_DEPENDENCY / FAIL_SYNTAX / FAIL_TIMEOUT in order.

Secondary metrics: structured-output validity 100% both LLM arms (0 fallbacks);
assessor consistency (modal agreement) deterministic 1.00, qwen 1.00
(uniform LOW every rep), llama 0.83; latency mean llama ~6.0 s, qwen ~2.5 s
per assessment; llama–qwen paired rank agreement 0.50 (mode agreement 1/6
candidates in run 2).

## Interpretation: mechanism validity vs operational effectiveness

1. **Mechanism validity (does assessment change ranking?).**
   Yes for deterministic (change rate 1.00) and llama (change rate 1.00,
   mean displacement ~0.9–1.1). No for qwen (uniform LOW in all 30
   assessments across both runs; displacement 0.00). Qwen's null result is a
   valid finding: a uniform-LOW assessor cannot move the ranking.

2. **Operational effectiveness (do ranking changes improve outcomes?).**
   Only the deterministic arm improved outcomes (top-1 useful 5/5, success on
   attempt 1, zero wasted attempts). Llama changed the ranking on every rep
   yet selected a non-useful top-1 (usually `SYN-OE-MED-02`) and succeeded
   within budget 0/5 — ranking movement without operational benefit.
   Qwen matched the baseline exactly (0/5). Neither LLM arm reduced wasted
   attempts relative to baseline (3.0 vs 3.0).

## Claims explicitly NOT made

- No claim of improved VAPT effectiveness, superior AI VAPT, universal
  improvement, or real-world exploitation effectiveness. The corpus is
  synthetic, the outcomes are simulated from static labels, and n = 5
  reps/arm supports descriptive statistics only (no CIs, no significance
  tests — none are reported).
- The deterministic arm's perfect score is NOT evidence of predictive power:
  the existing deterministic assessor reads the candidate's ground-truth
  label by construction (`SUCCESS` → HIGH), so it acts as an
  oracle-contaminated ceiling reference, not a fair predictor. Its value in
  this design is to confirm the operational model is sensitive (budget,
  stopping rule, and metrics *can* register an improvement when ranking is
  informative) — which makes the LLM arms' zero benefit interpretable
  rather than attributable to a broken harness.

## Limitations

- n = 5 repetitions per arm; descriptive only.
- Single 6-candidate corpus with deliberately anti-aligned
  probability/quality; results do not generalize beyond this controlled
  regime.
- Single attempt per candidate; no partial-credit or retry dynamics.
- LLM fallback path (deterministic LOW without ground truth) was never
  triggered (0 fallbacks); fallback behavior under failure is untested here.
- Llama shows run-to-run rank jitter (mean displacement 1.07 vs 0.93);
  operational metrics were identical across runs.

## Reproducibility

- Script: `experiments/gap1_operational_effectiveness_experiment.py`
- Raw results: `experiments/results/gap1_operational_effectiveness.json`
- Per-rep summary: `experiments/results/gap1_operational_effectiveness.csv`
- Frozen core (`decision_engine/core/`, `decision_engine/benchmarks/`)
  verified unmodified; all historical result files checksum-verified
  unchanged; full pytest suite: 687 passed.
- Key metrics were independently recomputed from the recorded raw rep
  records (orders + static ground truth) and match exactly.
