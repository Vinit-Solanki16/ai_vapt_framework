# GAP-2 Evaluation: Bounded Failure-Driven Pivoting

**Date:** 2026-09-16  
**Commit:** 9952d95 (post-Wave 12)  
**Status:** CONFIRMED — 30/30 experiments bounded (100%)

---

## 1. Research Question

**RQ2:** Does bounded failure-driven pivoting terminate correctly after a configurable number of failed attempts?

**Hypothesis:** The engine bounds total attempts to N × max_attempts where N = number of candidates.

---

## 2. Experimental Design

### 2.1 Pivot Mechanism

The engine tracks per-candidate attempt counts. When `attempt_count >= max_attempts`, the engine pivots to the next candidate. The per-candidate counter resets on pivot.

### 2.2 Scenarios

| # | Scenario | Candidates | Type |
|---|----------|-----------|------|
| 1 | immediate_success | 3 | First candidate succeeds immediately |
| 2 | one_fail_then_success | 3 | One failure, then success |
| 3 | repeated_failure_pivot | 4 | Multiple failures before success |
| 4 | multiple_candidates_failing | 4 | Three fail, one succeeds |
| 5 | all_candidates_failing | 4 | All candidates fail (bounded termination) |
| 6 | large_set_bounded | 10 | Large set with late success |

Each scenario tested at thresholds 1, 2, 3, 4, 5 = 30 experiments.

---

## 3. Results

### 3.1 Summary

| Metric | Value |
|--------|-------|
| Total experiments | 30 |
| All bounded | **30/30 (100%)** |
| Mean attempts | 11.67 |
| Mean pivots | 7.17 |
| Max attempts observed | 46 (threshold=5, large_set) |

### 3.2 Boundedness by Threshold

| Threshold | Experiments | All Bounded | Mean Attempts | Max Attempts |
|-----------|-------------|-------------|---------------|--------------|
| 1 | 6 | ✓ | 4.67 | 10 |
| 2 | 6 | ✓ | 8.17 | 19 |
| 3 | 6 | ✓ | 11.67 | 28 |
| 4 | 6 | ✓ | 15.17 | 37 |
| 5 | 6 | ✓ | 18.67 | 46 |

### 3.3 All Candidates Fail (Tight Bound)

| Threshold | Attempts | Expected Max | Bounded |
|-----------|----------|--------------|---------|
| 1 | 4 | 4 | ✓ |
| 2 | 8 | 8 | ✓ |
| 3 | 12 | 12 | ✓ |
| 4 | 16 | 16 | ✓ |
| 5 | 20 | 20 | ✓ |

**Key finding:** When all candidates fail, the engine makes exactly N × max_attempts attempts, confirming the bound is tight.

---

## 4. Key Findings

### 4.1 Boundedness Guaranteed

Total attempts ≤ N × max_attempts for all 30 experiments. This is guaranteed by:
1. Per-candidate attempt counter
2. Counter reset on pivot
3. max_attempts check before each re-execution

### 4.2 Threshold Behavior

As threshold increases, total attempts increase linearly (as expected). The bound scales correctly.

### 4.3 Pivot Counting

Pivots are counted as log entries containing "[Pivot]" AND ("Abandoning" OR "Redirected"). Each pivot either:
- **Abandons** a failing candidate (threshold reached)
- **Redirects** to the next candidate

---

## 5. Statistical Analysis

| Metric | Mean | Median | Stdev | Min | Max |
|--------|------|--------|-------|-----|-----|
| Attempts | 11.67 | 9.5 | 10.23 | 3 | 46 |
| Pivots | 7.17 | 6.0 | 5.20 | 2 | 18 |

---

## 6. Validity Assessment

| Claim | Status | Evidence |
|-------|--------|----------|
| GAP-2 bounded pivoting | **SUPPORTED** | 30/30 experiments bounded |
| Per-candidate attempt counters | **SUPPORTED** | Counters reset on pivot |
| Configurable threshold (1-5) | **SUPPORTED** | All thresholds verified |
| Bounded termination (all fail) | **SUPPORTED** | N × max_attempts confirmed |

---

## 7. Raw Data

- `experiments/results/gap2_extended.json` — Full data (30 experiments)
- `experiments/results/gap2_extended.csv` — Summary table
- `experiments/results/statistical_summary.json` — Aggregated statistics
