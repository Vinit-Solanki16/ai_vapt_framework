# Experimental Methodology — AI-VAPT Research Validation

**Date:** 2026-09-16  
**Version:** 2.0 (Wave 12 — Thesis-Grade)  
**Commit:** bb82bae

---

## 1. Research Questions

**RQ1 (GAP-1):** Does AI pre-execution assessment influence candidate ordering in the autonomous decision engine?

**RQ2 (GAP-2):** Does bounded failure-driven pivoting terminate correctly after a configurable number of failed attempts?

**RQ3 (Combined):** Does the full pipeline (assessment → ranking → execution → pivot) produce reproducible, bounded behavior?

**RQ4 (LLM Behavior):** Does real LLM assessment produce consistent, low-latency quality rankings across repeated evaluations?

---

## 2. Experimental Design

### 2.1 Independent Variables

| Variable | Levels | Description |
|----------|--------|-------------|
| Assessment mode | deterministic, llm (llama3.2:3b) | Source of quality ranking |
| Pivot threshold | 1, 2, 3, 4, 5 | Max attempts per candidate before pivot |
| Candidate set | 3–20 candidates per scenario | Varying probability/quality combinations |
| Repetitions | 5× (LLM), 1× (deterministic) | Variance measurement |

### 2.2 Dependent Variables

| Variable | Measurement |
|----------|-------------|
| Ranking order | Ordered list of candidate IDs after assessment |
| Ranking changed | Boolean: baseline order ≠ treatment order |
| Total attempts | Count of execution attempts across all candidates |
| Pivots | Count of pivot events (abandon + redirect) |
| Successful validations | Count of SUCCESS outcomes |
| Final status | COMPLETED or SUCCESS |
| Execution time | Wall-clock seconds |
| LLM latency | Seconds per LLM assessment call |
| LLM consistency | Whether repeated assessments agree |

### 2.3 Controlled Variables

- **Execution mode:** simulation (ground-truth outcomes)
- **Assessment temperature:** 0.1 (for reproducibility)
- **Repetitions:** 5× for LLM experiments, 1× for deterministic (identical by design)
- **Priority formula:** `probability * (0.5 + 0.5 * quality_weight)`

---

## 3. Experiment Scenarios

### 3.1 GAP-1 Scenarios (10 total)

| # | Scenario | Candidates | Type | Expected |
|---|----------|-----------|------|----------|
| 1 | assessment_changes_ranking | 3 | Classic inversion | Ranking changes |
| 2 | assessment_no_change | 3 | All SUCCESS | No change |
| 3 | high_prob_poor_quality | 3 | 1 FAIL + 2 SUCCESS | Ranking changes |
| 4 | lower_prob_high_quality | 4 | 2 FAIL + 2 SUCCESS | Ranking changes |
| 5 | mixed_population | 5 | Mixed | Ranking changes |
| 6 | all_high_quality | 4 | All SUCCESS | No change |
| 7 | all_low_quality | 4 | All FAIL | No change |
| 8 | large_set_10 | 10 | Periodic SUCCESS | Ranking changes |
| 9 | large_set_15 | 15 | Periodic SUCCESS | Ranking changes |
| 10 | large_set_20 | 20 | Periodic SUCCESS | Ranking changes |

### 3.2 GAP-2 Scenarios (6 scenarios × 5 thresholds = 30 experiments)

| # | Scenario | Candidates | Type |
|---|----------|-----------|------|
| 1 | immediate_success | 3 | First candidate succeeds immediately |
| 2 | one_fail_then_success | 3 | One failure, then success |
| 3 | repeated_failure_pivot | 4 | Multiple failures before success |
| 4 | multiple_candidates_failing | 4 | Three fail, one succeeds |
| 5 | all_candidates_failing | 4 | All candidates fail (bounded termination) |
| 6 | large_set_bounded | 10 | Large set with late success |

Each scenario tested at thresholds 1, 2, 3, 4, 5.

### 3.3 LLM Behavior Experiments

| # | CVE | Ground Truth | Purpose |
|---|-----|-------------|---------|
| 1 | CVE-2021-44228 | SUCCESS | HIGH reliability CVE |
| 2 | CVE-2017-0144 | SUCCESS | HIGH reliability CVE |
| 3 | CVE-2023-38408 | FAIL_TIMEOUT | MEDIUM reliability |
| 4 | CVE-2022-22965 | FAIL_SYNTAX | LOW reliability |
| 5 | CVE-2020-1472 | SUCCESS | HIGH reliability |
| 6 | CVE-2021-26855 | SUCCESS | MEDIUM reliability |
| 7 | CVE-2019-0708 | FAIL_TIMEOUT | MEDIUM reliability |
| 8 | CVE-2022-1388 | SUCCESS | HIGH reliability |

5 repetitions per candidate = 40 total assessments.

### 3.4 Combined Experiments (4 runs)

| Scenario | Baseline | Treatment |
|----------|----------|-----------|
| combined_mixed | Deterministic assessor | LLM assessor (llama3.2:3b) |
| combined_large | Deterministic assessor | LLM assessor (llama3.2:3b) |

---

## 4. Assessment Methods

### 4.1 Deterministic Assessor (Offline)

```python
def deterministic_assessor(candidate: ActionCandidate) -> QualityRank:
    if candidate.ground_truth == Outcome.SUCCESS:
        return QualityRank.HIGH
    if candidate.probability >= 0.9:
        return QualityRank.MEDIUM
    return QualityRank.LOW
```

**Properties:**
- Reproducible across runs
- Simulates a "perfect" assessor (knows ground truth)
- Used for baseline experiments

### 4.2 Real LLM Assessor (Online)

**Provider:** Ollama  
**Model:** llama3.2:3b (Q4_K_M, 3.2B parameters)  
**Temperature:** 0.1  
**Latency:** ~2.8s per assessment call  
**Fallback:** Deterministic assessor on LLM failure

**Properties:**
- Real-world assessment signal (no ground-truth knowledge)
- Tracks source (llm/fallback) and latency
- Falls back to deterministic on failure (0% fallback rate observed)

---

## 5. Data Collection

### 5.1 Metrics

| Metric | Source | Type |
|--------|--------|------|
| Ranking order | Engine state after assessment | List[str] |
| Ranking changed | Baseline vs treatment comparison | Boolean |
| Scores | priority_score() per candidate | Dict[str, float] |
| Quality ranks | Assessor output | Dict[str, QualityRank] |
| Execution sequence | Engine results | List[ExecutionResult] |
| Total attempts | len(results) | int |
| Pivots | Log analysis (regex on "[Pivot]") | int |
| Successful validations | Count of SUCCESS outcomes | int |
| Execution time | time.time() delta | float |
| LLM latency | Per-call timing | float |
| LLM source | llm vs fallback | str |

### 5.2 Storage

- **JSON:** Full experiment state (reproducible)
- **CSV:** Summary tables (publication-ready)
- **Statistical summary:** Aggregated metrics with mean/median/stdev

---

## 6. Validity Threats

### 6.1 Internal Validity

| Threat | Mitigation |
|--------|------------|
| Assessment-ground-truth feedback loop | Documented; real LLM assessment also tested |
| Engine implementation bugs | Fixed GAP-1 bug; all 538 tests pass |
| Randomness in LLM | Temperature=0.1; deterministic fallback available |

### 6.2 External Validity

| Threat | Mitigation |
|--------|------------|
| Simulation mode | Clearly labeled; Docker path available but not verified |
| Single LLM model | Documented; architecture supports any LLM |
| Lab-scale candidate sets | Up to 20 candidates tested; architecture scales |

### 6.3 Construct Validity

| Threat | Mitigation |
|--------|------------|
| Priority score formula | Documented; domain-independent |
| Pivot counting methodology | Transparent log analysis |

---

## 7. Reproducibility

### 7.1 Commands

```bash
# Full test suite
pytest -q

# Wave 12 thesis evaluation
python experiments/wave12_thesis_evaluation.py

# View results
cat experiments/results/statistical_summary.json
cat experiments/results/gap1_extended.csv
cat experiments/results/gap2_extended.csv
cat experiments/results/combined_results.csv
cat experiments/results/llm_behavior.json
```

### 7.2 Environment

- **Python:** 3.10.12
- **LLM:** Ollama llama3.2:3b (Q4_K_M)
- **OS:** WSL2 (Ubuntu)
- **Dependencies:** requirements.txt (pinned)

---

## 8. Ethical Considerations

- **No live exploitation:** All experiments use simulation
- **Safety boundaries:** Allowlist, fail-closed, no external targets
- **Responsible disclosure:** No real vulnerabilities exploited
- **IRB:** Not applicable (simulation-only research)

---

## 9. Summary of Experiments

| Phase | Experiments | Runs | Assessment |
|-------|-------------|------|------------|
| GAP-1 (ranking) | 10 scenarios | 10 | Deterministic |
| LLM behavior | 8 candidates × 5 reps | 40 | Ollama llama3.2:3b |
| GAP-2 (pivoting) | 6 scenarios × 5 thresholds | 30 | Deterministic |
| Combined | 2 scenarios × 2 modes | 4 | Deterministic + LLM |
| **Total** | | **84** | |