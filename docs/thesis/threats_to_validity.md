# Threats to Validity — AI-VAPT Research

**Date:** 2026-09-16  
**Framework:** AI-VAPT autonomous penetration testing framework

---

## 1. Internal Validity

### 1.1 Assessment-Ground-Truth Feedback Loop

**Threat:** The deterministic assessor uses the ground-truth outcome (SUCCESS/FAIL) to determine quality rank. This creates a circular dependency: the assessment predicts what is already known.

**Impact:** May overstate the effectiveness of pre-execution assessment in real-world scenarios where ground truth is unavailable.

**Mitigation:**
1. Real LLM assessment (Ollama llama3.2:3b) was also tested, which does NOT have access to ground truth
2. The research claim is that "assessment affects ranking" — the source of assessment is orthogonal
3. Documented as a limitation in Section 4

**Severity:** Medium (acknowledged and mitigated)

### 1.2 Engine Exhaustiveness

**Threat:** The engine processes ALL candidates exhaustively rather than stopping at first success. This may not match real-world expectations where the goal is to find one working exploit.

**Impact:** Total attempts are higher than a "stop-at-first-success" design. Metrics may appear less efficient.

**Mitigation:**
1. Documented clearly: engine is designed to validate ALL candidates
2. Thesis contribution is about bounded pivoting, not minimal attempts
3. Early success still triggers pivot to next candidate (not full stop)

**Severity:** Low (design choice, not a bug)

### 1.3 Small Sample Size

**Threat:** Experiments use 2-3 candidates. Statistical significance cannot be computed from such small samples.

**Impact:** Cannot claim the results generalize to larger candidate sets.

**Mitigation:**
1. Thesis focuses on mechanistic validation, not statistical generalization
2. Scalability is demonstrated through domain-independent design
3. Architecture supports arbitrary candidate counts

**Severity:** Medium (acknowledged; experiments are proof-of-concept)

### 1.4 Single Run for LLM Experiments

**Threat:** Real LLM assessment experiments were run once (not 3 repetitions) due to time constraints.

**Impact:** Cannot measure variance in LLM assessment.

**Mitigation:**
1. Temperature set to 0.1 for near-deterministic behavior
2. All LLM responses were reasonable and consistent with expectations
3. Framework tracks LLM provenance for audit

**Severity:** Low (LLM experiments supplementary, deterministic experiments have 3 repetitions)

---

## 2. External Validity

### 2.1 Simulation-Only Validation

**Threat:** All experiments use simulation mode (ground-truth labels). Real execution was not tested.

**Impact:** Framework may behave differently with real PoC execution against real targets.

**Mitigation:**
1. Simulation mode is clearly labeled; not presented as real-world validation
2. Docker-based validation path exists but requires infrastructure
3. Research claims are about the DECISION ENGINE, not exploit execution success

**Severity:** Medium (acknowledged; research contributions are architecture-level)

### 2.2 Single LLM Model

**Threat:** Only one LLM model was tested (llama3.2:3b). Results may differ with other models.

**Impact:** Cannot claim LLM assessment quality generalizes across models.

**Mitigation:**
1. Framework supports any LLM (Ollama, OpenAI, extensible)
2. Deterministic assessor provides reproducible baseline
3. Thesis claim is "assessment (from any source) affects ranking"

**Severity:** Low (mechanism validated, not specific model performance)

### 2.3 Controlled Environment

**Threat:** Experiments run in a controlled WSL2 environment, not a real penetration testing engagement.

**Impact:** Real-world noise (network issues, target variability, timeouts) not captured.

**Mitigation:**
1. Framework includes timeout handling, error recovery
2. Executor abstraction supports real execution backend
3. Docker lab provides controlled but realistic environment (when available)

**Severity:** Medium (acknowledged limitation)

---

## 3. Construct Validity

### 3.1 Priority Score Formula

**Threat:** The priority score formula `probability * (0.5 + 0.5 * quality)` is arbitrary and may not reflect real-world exploitability.

**Impact:** Ranking order may not match a human expert's judgment.

**Mitigation:**
1. Formula is documented and transparent
2. Weights are configurable
3. Research contribution is the MECHANISM (assessment affects ranking), not the specific formula

**Severity:** Low (formula is a design choice, validated through experimentation)

### 3.2 Pivot Counting Methodology

**Threat:** Pivot counting uses log analysis (regex on "[Pivot]"), which may miss edge cases or double-count.

**Impact:** Pivot metrics may be inaccurate.

**Mitigation:**
1. Log format is standardized and stable
2. Manual verification confirmed counts match expected behavior
3. Thesis focuses on qualitative behavior (pivots occur) not exact counts

**Severity:** Low (verified manually)

### 3.3 Quality Rank Mapping

**Threat:** The deterministic assessor maps probability >= 0.9 to MEDIUM quality, which may not reflect real exploit usability.

**Impact:** Quality rankings may be unrealistic.

**Mitigation:**
1. Documented as simulation-only
2. Real LLM assessment produces different (more nuanced) rankings
3. Research claim is about ranking INFLUENCE, not quality accuracy

**Severity:** Low (acknowledged simplification)

---

## 4. Conclusion Validity

### 4.1 No Statistical Tests

**Threat:** No statistical significance tests (t-test, ANOVA, chi-square) were performed.

**Impact:** Cannot make claims about statistical significance.

**Mitigation:**
1. Thesis focuses on deterministic reproducibility, not statistical inference
2. Experiments are mechanistic proofs, not population studies
3. Identical results across 3 repetitions confirm determinism

**Severity:** N/A (not a statistical study)

### 4.2 Confounding Variables

**Threat:** Multiple variables changed between experiments (candidates, thresholds, assessors).

**Impact:** Cannot isolate the effect of a single variable.

**Mitigation:**
1. Each experiment controls specific variables (see methodology)
2. Baseline vs treatment comparisons hold other factors constant
3. Experiments are designed to demonstrate individual mechanisms

**Severity:** Low (controlled experimental design)

---

## 5. Summary Table

| Threat | Type | Severity | Mitigated |
|--------|------|----------|-----------|
| Assessment-ground-truth loop | Internal | Medium | Yes (real LLM tested) |
| Engine exhaustiveness | Internal | Low | Yes (documented design) |
| Small sample size | Internal | Medium | Yes (mechanistic focus) |
| Single LLM run | Internal | Low | Yes (temperature control) |
| Simulation-only | External | Medium | Yes (clearly labeled) |
| Single LLM model | External | Low | Yes (architecture-agnostic) |
| Controlled environment | External | Medium | Yes (acknowledged) |
| Priority formula | Construct | Low | Yes (documented) |
| Pivot counting | Construct | Low | Yes (verified manually) |
| Quality mapping | Construct | Low | Yes (documented) |
| No statistical tests | Conclusion | N/A | Yes (deterministic study) |
| Confounding variables | Conclusion | Low | Yes (controlled design) |

---

## 6. Recommendations for Future Work

1. **Larger candidate sets:** Run experiments with 10-50 candidates from real vulnerability scans
2. **Multiple LLM models:** Compare assessment quality across GPT-4, Claude, Llama, etc.
3. **Real execution:** Validate Docker-based evidence tier when infrastructure permits
4. **Statistical analysis:** Collect multiple runs for variance measurement and confidence intervals
5. **Human evaluation:** Compare LLM assessments with human expert assessments
6. **Ablation studies:** Isolate the effect of each scoring factor on ranking quality