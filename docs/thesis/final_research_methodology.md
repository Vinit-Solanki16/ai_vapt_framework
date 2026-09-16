# Final Research Methodology — AI-VAPT Framework

**Date:** 2026-09-16  
**Commit:** 9952d95 (post-Wave 12)  
**Version:** 3.0 (Final)

---

## 1. Research Questions

| RQ | Question | Status |
|----|----------|--------|
| RQ1 | Does AI pre-execution assessment influence candidate ordering? | **CONFIRMED** |
| RQ2 | Does bounded failure-driven pivoting terminate correctly? | **CONFIRMED** |
| RQ3 | Does the full pipeline produce reproducible, bounded behavior? | **CONFIRMED** |
| RQ4 | Does real LLM assessment produce consistent, low-latency rankings? | **CONFIRMED** |

---

## 2. Experimental Design

### 2.1 Independent Variables

| Variable | Levels | Description |
|----------|--------|-------------|
| Assessment mode | deterministic, llm | Source of quality ranking |
| Pivot threshold | 1, 2, 3, 4, 5 | Max attempts per candidate |
| Candidate set | 3–20 candidates | Varying probability/quality |
| Repetitions | 5× (LLM), 1× (deterministic) | Variance measurement |

### 2.2 Dependent Variables

| Variable | Measurement |
|----------|-------------|
| Ranking order | Ordered list of candidate IDs |
| Ranking changed | Boolean: baseline ≠ treatment |
| Total attempts | Count of execution attempts |
| Pivots | Count of pivot events |
| Successful validations | Count of SUCCESS outcomes |
| Final status | COMPLETED or SUCCESS |
| Execution time | Wall-clock seconds |
| LLM latency | Seconds per assessment |
| LLM consistency | Whether repeated assessments agree |

### 2.3 Controlled Variables

- **Execution mode:** simulation (ground-truth outcomes)
- **Assessment temperature:** 0.1
- **Priority formula:** `probability * (0.5 + 0.5 * quality_weight)`

---

## 3. Assessment Methods

### 3.1 Deterministic Assessor (Offline)

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
- Simulates a "perfect" assessor
- Used for baseline experiments

### 3.2 Real LLM Assessor (Online)

**Provider:** Ollama  
**Model:** llama3.2:3b (Q4_K_M, 3.2B parameters)  
**Temperature:** 0.1  
**Latency:** ~2.8s per assessment call  
**Fallback:** Deterministic assessor on LLM failure

**Properties:**
- Real-world assessment signal
- Tracks source (llm/fallback) and latency
- Falls back to deterministic on failure

---

## 4. Experiment Scenarios

### 4.1 GAP-1 Scenarios (10 total)

| # | Scenario | Candidates | Type |
|---|----------|-----------|------|
| 1 | assessment_changes_ranking | 3 | Classic inversion |
| 2 | assessment_no_change | 3 | All SUCCESS |
| 3 | high_prob_poor_quality | 3 | 1 FAIL + 2 SUCCESS |
| 4 | lower_prob_high_quality | 4 | 2 FAIL + 2 SUCCESS |
| 5 | mixed_population | 5 | Mixed |
| 6 | all_high_quality | 4 | All SUCCESS |
| 7 | all_low_quality | 4 | All FAIL |
| 8 | large_set_10 | 10 | Periodic SUCCESS |
| 9 | large_set_15 | 15 | Periodic SUCCESS |
| 10 | large_set_20 | 20 | Periodic SUCCESS |

### 4.2 GAP-2 Scenarios (6 × 5 thresholds = 30 experiments)

| # | Scenario | Candidates | Type |
|---|----------|-----------|------|
| 1 | immediate_success | 3 | First candidate succeeds |
| 2 | one_fail_then_success | 3 | One failure, then success |
| 3 | repeated_failure_pivot | 4 | Multiple failures before success |
| 4 | multiple_candidates_failing | 4 | Three fail, one succeeds |
| 5 | all_candidates_failing | 4 | All fail (bounded termination) |
| 6 | large_set_bounded | 10 | Large set with late success |

### 4.3 LLM Behavior Experiments

8 candidates × 5 repetitions = 40 total assessments.

### 4.4 Combined Experiments

2 scenarios × 2 modes (baseline/treatment) = 4 experiments.

---

## 5. Data Collection

### 5.1 Metrics

| Metric | Source | Type |
|--------|--------|------|
| Ranking order | Engine state | List[str] |
| Ranking changed | Baseline vs treatment | Boolean |
| Scores | priority_score() | Dict[str, float] |
| Quality ranks | Assessor output | Dict[str, QualityRank] |
| Execution sequence | Engine results | List[ExecutionResult] |
| Total attempts | len(results) | int |
| Pivots | Log analysis | int |
| Successful validations | Count of SUCCESS | int |
| Execution time | time.time() delta | float |
| LLM latency | Per-call timing | float |
| LLM source | llm vs fallback | str |

### 5.2 Storage

- **JSON:** Full experiment state
- **CSV:** Summary tables
- **Statistical summary:** Aggregated metrics

---

## 6. Validity Threats

### 6.1 Internal Validity

| Threat | Mitigation |
|--------|------------|
| Assessment-ground-truth loop | Real LLM also tested |
| Implementation bugs | 538 tests pass |
| LLM randomness | Temperature=0.1 |

### 6.2 External Validity

| Threat | Mitigation |
|--------|------------|
| Simulation mode | Clearly labeled |
| Single LLM model | Architecture-agnostic |
| Lab-scale sets | Mechanistic focus |

### 6.3 Construct Validity

| Threat | Mitigation |
|--------|------------|
| Priority formula | Documented |
| Pivot counting | Transparent log analysis |

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
```

### 7.2 Environment

- **Python:** 3.10.12
- **LLM:** Ollama llama3.2:3b (Q4_K_M)
- **OS:** WSL2 (Ubuntu)

---

## 8. Ethical Considerations

- **No live exploitation:** All experiments use simulation
- **Safety boundaries:** Allowlist, fail-closed, no external targets
- **Responsible disclosure:** No real vulnerabilities exploited
- **IRB:** Not applicable (simulation-only research)

---

## 9. Summary

| Phase | Experiments | Runs | Assessment |
|-------|-------------|------|------------|
| GAP-1 | 10 scenarios | 10 | Deterministic |
| LLM behavior | 8 candidates × 5 reps | 40 | Ollama llama3.2:3b |
| GAP-2 | 6 scenarios × 5 thresholds | 30 | Deterministic |
| Combined | 2 scenarios × 2 modes | 4 | Deterministic + LLM |
| **Total** | | **84** | |
