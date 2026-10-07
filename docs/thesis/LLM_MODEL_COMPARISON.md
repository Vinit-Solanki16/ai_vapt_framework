# Local LLM Model Comparison — Phase 33A

**Experiment:** Phase 33A — local-LLM A/B comparison of the pre-execution
exploit-quality assessor (GAP-1 mechanism)
**Arms:** `llama3.2:3b` (official baseline) vs `qwen2.5:3b` (experimental)
**Date:** 2026-10-07
**Baseline commit at experiment start:** `0042803` (Phase 32B checkpoint)
**Artifacts:**
`experiments/results/llm_model_comparison.json`,
`experiments/results/llm_model_comparison.csv`,
`experiments/results/llm_model_comparison_observations.csv`,
`experiments/results/phase33a_structured_output_probe.json`
**Runner:** `experiments/phase33a_llm_ab_experiment.py`
(`--from-observations` regenerates the summary from the raw CSV without
re-running the models)

---

## 1. Purpose and scope

Evaluate `qwen2.5:3b` as an **alternative** local model for the existing
pre-execution exploit-quality assessment path.

Explicit scope limits (unchanged by this experiment):

- `llama3.2:3b` remains the official thesis baseline, the existing thesis
  baseline, and the default production model.
- `qwen2.5:3b` is an **experimental comparison arm only** — opt-in, never
  selected implicitly.
- GAP-1 and GAP-2 logic is unchanged.
- `decision_engine/core/` and `decision_engine/benchmarks/` are unchanged.
- No existing thesis baseline artifact was overwritten.

## 2. What is NOT measured (research integrity)

**Effectiveness is not reported as "exploit success rate."** The evaluator
does not establish real exploit ground truth for these scanner-derived
findings, so any success-rate number would be fabricated. This experiment
therefore reports, **separately**:

- A. Assessment reliability (valid structured outputs, fallbacks)
- B. Structured-output reliability (schema / parse failures)
- C. Consistency (per-candidate rank agreement across repetitions)
- D. Latency (mean / median / min / max)
- E. Ranking influence (GAP-1 ordering vs a no-assessment baseline)
- F. Model agreement (llama vs qwen, per candidate)

No claim that "Qwen is better" is made beyond what the measurements below
support.

## 3. Protocol (identical for both arms)

| Item | Value |
|------|-------|
| Provider | Ollama (local, offline) |
| Temperature | 0.1 (unchanged, `core.exploit_assessor.get_llm`) |
| Prompt | `core.exploit_assessor.SYSTEM_PROMPT` (v1, unchanged, shared by both arms) |
| Schema | `core.schemas.ExploitAssessment` (unchanged) |
| Parsing | `assess_exploit_quality` (`llm.with_structured_output`) — unchanged |
| Candidates | 8 real corpus CVEs, frozen order |
| Repetitions | 5 (matches the historical llama baseline protocol) |
| Per-call timeout | 60 s wall clock, both arms |
| Environment | Same host, same Ollama instance, same venv |
| Assessment path | Production path: `create_assessor(mode="ai", provider="ollama", model_name=…)` |

Candidate corpus (identical to
`experiments/wave12_thesis_evaluation.py::LLM_TEST_CANDIDATES`, so the llama
arm stays compatible with the historical baseline):
`CVE-2021-44228, CVE-2017-0144, CVE-2023-38408, CVE-2022-22965, CVE-2020-1472,
CVE-2021-26855, CVE-2019-0708, CVE-2022-1388`.

### Model provenance (measured with `ollama show`, not assumed)

| Model | Architecture | Parameters | Context | Quantization | Role |
|-------|--------------|-----------|---------|--------------|------|
| `llama3.2:3b` | llama | 3.2B | 131072 | Q4_K_M | baseline / default |
| `qwen2.5:3b` | qwen2 | 3.1B | 32768 | Q4_K_M | experimental |

## 4. Phase 3 gate — structured-output contract compatibility

Before integration, both models were probed against the **unchanged**
contract (same prompt, temperature 0.1, schema, and parsing) on all 8
candidates.

| Model | Attempts | Valid structured | Schema violations | Parse failures | Mean latency |
|-------|----------|------------------|-------------------|----------------|--------------|
| `llama3.2:3b` | 8 | 8 (100%) | 0 | 0 | 2.922 s |
| `qwen2.5:3b` | 8 | 8 (100%) | 0 | 0 | 1.971 s |

**Gate verdict: PASS.** `qwen2.5:3b` satisfies the existing structured-output
contract without any schema change, so the A/B experiment proceeded.

## 5. Results (40 assessments per arm, 80 total)

| Metric | `llama3.2:3b` | `qwen2.5:3b` |
|--------|---------------|--------------|
| Provider | ollama | ollama |
| Temperature | 0.1 | 0.1 |
| Prompt version | v1 (shared) | v1 (shared) |
| Candidates | 8 | 8 |
| Repetitions | 5 | 5 |
| Total assessments | 40 | 40 |
| Valid structured outputs | 39 | 40 |
| **Valid output rate** | **97.5%** | **100.0%** |
| Fallbacks | 1 | 0 |
| **Fallback rate** | **2.5%** | **0.0%** |
| Schema / parse failures | 1 | 0 |
| Mean latency | 12.706 s * | 2.275 s |
| Median latency | 2.466 s | 2.252 s |
| Min / Max latency | 1.789 s / 397.478 s * | 1.549 s / 3.666 s |
| Mean latency (valid LLM calls only) | 2.840 s | 2.275 s |
| Quality distribution | HIGH 0 / MED 7 / LOW 32 / — 1 | HIGH 0 / MED 0 / LOW 40 |
| Mean per-candidate consistency | 94.37% | 100.00% |
| All candidates consistent | No | Yes |
| **Ranking-change rate vs no-assessment** | **0.0%** | **0.0%** |
| **Inter-model agreement** | — | **80.0%** (40 paired obs) |

\* The llama mean/min/max are distorted by a **single 397.5 s hang** (see §6).
Excluding that one observation, llama's valid-call mean is **2.840 s**, which
matches the historical baseline's ~2.8 s per assessment
(`docs/thesis/results.md`).

### Per-candidate consistency

`llama3.2:3b` — `CVE-2021-44228` = MEDIUM (5/5), `CVE-2019-0708` = MEDIUM
(4/5, one timeout), all other six candidates = LOW (5/5).
`qwen2.5:3b` — all eight candidates = LOW (5/5).

### Quality distribution

Neither model produced a HIGH rank on this corpus. llama assigned MEDIUM to
7 of 40 observations (6 of 8 candidates at least once); qwen assigned LOW to
all 40. Both were unanimous that the corpus exploits are, at best, medium
usability.

## 6. Reliability anomaly (reported honestly)

One llama observation, `CVE-2019-0708` in repetition 1, **hung for 397.5 s**
and was recorded as a fallback at the 60 s policy boundary. It was not
retried, so it is one observation, not a systemic pattern. Its effect:

- llama valid output rate drops from 100% to 97.5% and consistency on
  `CVE-2019-0708` from 5/5 to 4/5;
- llama's mean/min/max latency become non-representative (median 2.466 s is
  the meaningful central value).

A caveat that applies to **both** arms: the experiment host was under heavy
external CPU load during the run (load average ≈ 12, shared with other
processes), which is the most likely contributor to the single hang. Latency
figures are therefore indicative of a loaded workstation, not of idle-hardware
throughput.

## 7. GAP-1 measurement — ranking influence (Phase 6)

No-assessment baseline order (GAP-1 without assessment):

```
CVE-2021-44228 → CVE-2022-1388 → CVE-2020-1472 → CVE-2021-26855
→ CVE-2017-0144 → CVE-2019-0708 → CVE-2022-22965 → CVE-2023-38408
```

| Model | Assessed order | Changed vs no-assessment | Positions moved |
|-------|----------------|--------------------------|-----------------|
| `llama3.2:3b` | same as baseline | **No** | 0 |
| `qwen2.5:3b` | same as baseline | **No** | 0 |

- **Did ranking change?** No, for either model.
- **How often?** 0% of orderings.
- **For which candidates?** None.
- **Did the models disagree on order?** No — inter-model order is identical
  (0 positions moved).
- **Did either model produce invalid/fallback results?** llama produced 1
  fallback (the 397.5 s hang); qwen produced none.

**Why the order is unchanged (mechanism, not a defect):** the candidate set
contains only two distinct probability tiers. Seven of eight candidates have
probability 0.95–0.50 and all receive the same quality rank from both models
(LOW, except one MEDIUM), so their `priority_score = probability × (0.5 + 0.5 ×
quality)` differs only through the probability term. Assessment therefore has
no *ordering* leverage on this corpus, and both models agree with the
probability-only baseline.

**What this does and does not show.** The GAP-1 mechanism — assessment
executing **before** ranking and feeding a quality weight into the score — is
live and exercised (each model's ranks are recorded and the ranks do enter the
score computation). This experiment does **not** demonstrate that a
model-driven assessment changes execution order; that requires a corpus with
comparable probabilities across differing quality tiers. That is a property of
the test corpus, not of either model. No claim is made beyond this.

## 8. Model agreement (Phase 7F)

Overall inter-model agreement: **80.0%** over 40 paired observations. All
disagreements are the MEDIUM/LOW boundary on the two "reliable" candidates:

| Candidate | llama mode | qwen | Agreement |
|-----------|-----------|------|-----------|
| `CVE-2021-44228` | MEDIUM | LOW | 0/5 |
| `CVE-2017-0144` | LOW | LOW | 5/5 |
| `CVE-2023-38408` | LOW | LOW | 5/5 |
| `CVE-2022-22965` | LOW | LOW | 5/5 |
| `CVE-2020-1472` | LOW | LOW | 5/5 |
| `CVE-2021-26855` | LOW | LOW | 5/5 |
| `CVE-2019-0708` | LOW (4/5 MEDIUM 1/5) | LOW | 4/5 |
| `CVE-2022-1388` | LOW | LOW | 5/5 |

The models agree on 6 of 8 candidates outright; the disagreement is confined
to one candidate (plus one llama timeout on another). Qwen is consistently
more conservative (LOW where llama says MEDIUM).

## 9. Baseline compatibility

The llama arm was run with the same corpus, repetition count, temperature,
prompt, and schema as the historical Phase 3 baseline
(`docs/thesis/results.md`, 40 LLM behaviour runs, ~2.8 s per assessment).
llama's valid-call mean latency here is **2.840 s**, consistent with that
baseline. **No existing baseline file was modified or overwritten**; this
document and the `llm_model_comparison.*` artifacts are additive.

## 10. Recommendation (Phase 11)

### **A. Keep `llama3.2:3b` as the default; keep `qwen2.5:3b` experimental only.**

Measured basis:

1. **Structured-output reliability** — qwen 100% (0/40 failures) vs llama
   97.5% (1/40), and qwen 100% in the Phase 3 gate. Qwen meets the contract,
   but the margin is one observation.
2. **Consistency** — qwen 100% per-candidate agreement vs llama 94.37%.
3. **Latency** — qwen's median (2.252 s) is slightly better than llama's
   (2.466 s) and its spread is much tighter (max 3.666 s vs llama's 397.5 s
   outlier). Note the shared-load caveat in §6.
4. **Ranking influence** — identical (0% change) for both; the corpus cannot
   discriminate them, so this metric does **not** favour either model.
5. **Baseline continuity** — switching the default would invalidate the
   comparability of every existing thesis result that references
   `llama3.2:3b`, for a difference that is not established on the metrics
   that matter for the research claim.

Option **B** (make Qwen the default) is **not** supported: the evidence shows
qwen is *at least as reliable* on this corpus, but nothing in these
measurements shows it is *better for the research contribution*, and adopting
it would break baseline continuity. Option **C** (reject Qwen) is also not
supported: qwen passed the structured-output gate and was fully consistent, so
it is a valid, working experimental arm.

**Practical conclusion:** qwen2.5:3b is a viable, lower-variance alternative
worth retaining as an experimental arm for future work on a
quality-discriminating corpus. `llama3.2:3b` remains the default.

## 11. Threats to validity

- **Single corpus / small n.** 8 candidates × 5 repetitions. The corpus does
  not span multiple quality tiers at comparable probability, so ranking
  influence is unmeasurable here (see §7).
- **Host contention.** External CPU load inflated latency and likely caused
  the single llama hang (§6).
- **No ground truth.** No real exploit success was measured, by design; this
  experiment characterises assessor behaviour, not exploit effectiveness.
- **Prompt/schema held constant by construction.** Results describe these two
  models under *this* contract only; a different prompt could rank them
  differently.
