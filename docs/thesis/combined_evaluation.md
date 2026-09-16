# Combined Evaluation: Full Pipeline (Assessment → Ranking → Execution → Pivot)

**Date:** 2026-09-16  
**Commit:** 9952d95 (post-Wave 12)  
**Status:** CONFIRMED — 4 experiments, baseline vs treatment

---

## 1. Research Question

**RQ3:** Does the full pipeline (assessment → ranking → execution → pivot) produce reproducible, bounded behavior?

---

## 2. Experimental Design

### 2.1 Modes

| Mode | Assessment | Purpose |
|------|------------|---------|
| Baseline | Deterministic assessor | Reproducible offline |
| Treatment | Real LLM (Ollama llama3.2:3b) | Real-world signal |

### 2.2 Scenarios

| Scenario | Candidates | Description |
|----------|-----------|-------------|
| combined_mixed | 4 | Mixed success/failure |
| combined_large | 10 | Large set with periodic success |

---

## 3. Results

### 3.1 Summary

| Metric | Baseline (Deterministic) | Treatment (LLM) |
|--------|--------------------------|---------------------|
| Experiments | 2 | 2 |
| Mean attempts | 12 | 12 |
| Mean success | 2 | 2 |
| Mean pivots | 11 | 11 |
| Mean assess latency | ~0s | 12.0s |

### 3.2 combined_mixed (4 candidates)

| Mode | Ranking | Attempts | Success | Pivots |
|------|---------|----------|---------|--------|
| Baseline | CMB-A > CMB-B > CMB-D > CMB-C | 6 | 2 | 5 |
| Treatment | CMB-A > CMB-B > CMB-C > CMB-D | 6 | 2 | 5 |

**Ranking difference:** CMB-D and CMB-C swap positions because the LLM assessor evaluates them differently than the deterministic assessor.

### 3.3 combined_large (10 candidates)

| Mode | Ranking (first 5) | Attempts | Success | Pivots |
|------|-------------------|----------|---------|--------|
| Baseline | CL-0 > CL-3 > CL-1 > CL-2 > CL-7 | 18 | 2 | 17 |
| Treatment | CL-0 > CL-1 > CL-2 > CL-3 > CL-4 | 18 | 2 | 17 |

**Key finding:** The LLM assessor produces a more "conservative" ranking (closer to probability order) compared to the deterministic assessor which strongly promotes SUCCESS candidates.

---

## 4. Key Findings

### 4.1 Pipeline Integrity

Both baseline and treatment produce identical attempt counts and success counts, confirming:
1. Deterministic assessor correctly simulates a "good" assessor
2. Real LLM assessor produces consistent results
3. Framework degrades gracefully between assessment sources

### 4.2 Ranking Differences

Ranking differences between baseline and treatment are expected because:
- **Deterministic:** Uses ground-truth outcome (knows if candidate will succeed)
- **LLM:** Assesses based on CVE characteristics (complexity, prerequisites, exploitability)

This validates that the framework supports **pluggable assessment sources**.

---

## 5. Raw Data

- `experiments/results/combined_results.json` — Full data
- `experiments/results/combined_results.csv` — Summary table
