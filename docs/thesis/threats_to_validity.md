# Threats to Validity — AI-VAPT Research

**Date:** 2026-09-16  
**Commit:** 9952d95 (post-Wave 12)

---

## 1. Internal Validity

### 1.1 Assessment-Ground-Truth Feedback Loop

**Threat:** The deterministic assessor uses ground-truth outcome to assign quality ranks, creating a circular dependency.

**Mitigation:** Real LLM assessment also tested (40 assessments, 0% fallback). LLM produces different rankings than deterministic assessor, confirming framework supports pluggable assessment sources.

**Residual Risk:** Medium — deterministic assessor is circular by design.

### 1.2 Engine Implementation Bugs

**Threat:** Implementation bugs could invalidate experimental results.

**Mitigation:** 
- Fixed GAP-1 bug (commit 252c99a) where assessment did not affect ranking
- 538 tests pass, 0 failures
- All experiments reproducible

**Residual Risk:** Low — comprehensive test suite.

### 1.3 Randomness in LLM

**Threat:** LLM assessment may vary across runs due to sampling randomness.

**Mitigation:** Temperature=0.1 for reproducibility. Deterministic fallback available.

**Residual Risk:** Low — 6/8 candidates perfectly consistent across 5 repetitions.

---

## 2. External Validity

### 2.1 Simulation Mode

**Threat:** All experiments use simulation mode; real execution not validated.

**Mitigation:** Docker path available but not verified due to infrastructure constraints. Simulation mode is clearly labeled.

**Residual Risk:** High — real execution not validated.

### 2.2 Single LLM Model

**Threat:** Only one LLM model (llama3.2:3b) tested.

**Mitigation:** Architecture supports any LLM provider. Different models may produce different rankings.

**Residual Risk:** Medium — single model tested.

### 2.3 Lab-Scale Candidate Sets

**Threat:** Experiments use small candidate sets (3-20 candidates).

**Mitigation:** Architecture scales to larger sets. Mechanistic focus, not statistical significance.

**Residual Risk:** Medium — small-scale experiments.

### 2.4 No Live Targets

**Threat:** No live exploitation validation.

**Mitigation:** Safety design prevents live exploitation. By design.

**Residual Risk:** High — no live validation.

---

## 3. Construct Validity

### 3.1 Priority Score Formula

**Threat:** Priority score formula may not capture all relevant factors.

**Mitigation:** Formula is documented and domain-independent. Same formula used across all experiments.

**Residual Risk:** Low — transparent formula.

### 3.2 Pivot Counting Methodology

**Threat:** Pivot counting may not capture all pivot events.

**Mitigation:** Transparent log analysis (regex on "[Pivot]" AND ("Abandoning" OR "Redirected")). Counting logic is deterministic and reproducible.

**Residual Risk:** Low — transparent methodology.

### 3.3 Boundedness Definition

**Threat:** "Bounded" may be defined too loosely.

**Mitigation:** Strict definition: total attempts ≤ N × max_attempts. Verified mathematically and empirically.

**Residual Risk:** Low — strict definition.

---

## 4. Summary

| Threat | Risk Level | Mitigation |
|--------|------------|------------|
| Assessment-ground-truth loop | Medium | Real LLM also tested |
| Implementation bugs | Low | 538 tests pass |
| LLM randomness | Low | Temperature=0.1, fallback |
| Simulation mode | High | Clearly labeled, Docker available |
| Single LLM model | Medium | Architecture-agnostic |
| Lab-scale sets | Medium | Mechanistic focus |
| No live targets | High | Safety by design |
| Priority formula | Low | Documented, transparent |
| Pivot counting | Low | Transparent methodology |
| Boundedness definition | Low | Strict, verified |

---

## 5. Honest Assessment

### 5.1 What Is Verified

1. GAP-1: Assessment affects ranking (4/10 scenarios)
2. GAP-2: Bounded pivoting (30/30 experiments)
3. Pipeline: Full pipeline produces reproducible results
4. Safety: Allowlist, fail-closed, no external targets
5. Reproducibility: All deterministic experiments repeatable

### 5.2 What Is NOT Verified

1. Real Docker execution (infrastructure unavailable)
2. Live exploit validation (safety design)
3. Production-scale candidate sets (lab-scale only)
4. Multiple LLM models (single model tested)

### 5.3 Research Contribution

Despite limitations, the research contribution is valid:
- Mechanistic validation of assessment-driven ranking
- Bounded failure-driven pivoting with configurable thresholds
- Pluggable assessment sources (deterministic + real LLM)
- Safety-first design with allowlist and fail-closed
