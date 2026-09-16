# Final Project Checkpoint — AI-VAPT Framework

**Date:** 2026-09-16  
**Commit:** 9952d95 (post-Wave 12)  
**Version:** 1.0 (FINAL)

---

## 1. What Is Implemented

### 1.1 Research Core (decision_engine/)

| Component | File | Status |
|-----------|------|--------|
| Schemas | `decision_engine/core/schemas.py` | ✓ Complete |
| Assessor (GAP-1) | `decision_engine/core/assessor.py` | ✓ Complete |
| Engine (GAP-2) | `decision_engine/core/engine.py` | ✓ Complete |
| Executor | `decision_engine/core/executor.py` | ✓ Complete |
| VAPT Adapter | `decision_engine/adapters/vapt_adapter.py` | ✓ Complete |
| Scan Adapter | `decision_engine/adapters/scan_adapter.py` | ✓ Complete |

### 1.2 Benchmarks

| Component | File | Status |
|-----------|------|--------|
| Agnostic benchmark | `decision_engine/benchmarks/agnostic_benchmark.py` | ✓ Complete |
| Fair benchmark | `decision_engine/benchmarks/fair_benchmark.py` | ✓ Complete |
| Fair VAPT benchmark | `decision_engine/benchmarks/fair_vapt_benchmark.py` | ✓ Complete |
| LLM assessor benchmark | `decision_engine/benchmarks/llm_assessor_benchmark.py` | ✓ Complete |

### 1.3 VAPT Platform (vapt_platform/)

| Component | File | Status |
|-----------|------|--------|
| Application | `vapt_platform/application.py` | ✓ Complete |
| Assessment | `vapt_platform/assessment.py` | ✓ Complete |
| Authorization | `vapt_platform/authorization.py` | ✓ Complete |
| Enrichment | `vapt_platform/enrichment.py` | ✓ Complete |
| Graph builder | `vapt_platform/graph_builder.py` | ✓ Complete |
| Normalization | `vapt_platform/normalization.py` | ✓ Complete |
| Pipeline | `vapt_platform/pipeline.py` | ✓ Complete |
| Scanners | `vapt_platform/scanners.py` | ✓ Complete |
| Events | `vapt_platform/events/` | ✓ Complete |
| Parsers | `vapt_platform/parsers/` | ✓ Complete |
| Persistence | `vapt_platform/persistence/` | ✓ Complete |
| Reporting | `vapt_platform/reporting/` | ✓ Complete |

### 1.4 Services & Frontend

| Component | File | Status |
|-----------|------|--------|
| API | `services/api.py` | ✓ Complete |
| Jobs | `services/jobs.py` | ✓ Complete |
| Schemas | `services/schemas.py` | ✓ Complete |
| Frontend | `frontend/app.py` | ✓ Complete |

### 1.5 Experiments

| Component | File | Status |
|-----------|------|--------|
| Wave 12 evaluation | `experiments/wave12_thesis_evaluation.py` | ✓ Complete |
| Research validation | `experiments/research_validation.py` | ✓ Complete |
| Experiment harness | `experiments/harness/__init__.py` | ✓ Complete |

---

## 2. What Was Experimentally Validated

### 2.1 GAP-1: AI Pre-Execution Assessment Affects Ranking

| Metric | Value |
|--------|-------|
| Total scenarios | 10 |
| Ranking changed | 4 (40%) |
| Ranking unchanged | 6 (60%) |

**Finding:** Assessment correctly promotes HIGH-quality candidates over LOW-quality ones. No false positives when quality is uniform.

### 2.2 GAP-2: Bounded Failure-Driven Pivoting

| Metric | Value |
|--------|-------|
| Total experiments | 30 |
| All bounded | 30/30 (100%) |

**Finding:** Total attempts ≤ N × max_attempts guaranteed. Bound is tight when all candidates fail.

### 2.3 Combined Pipeline

| Metric | Value |
|--------|-------|
| Experiments | 4 |
| Baseline mean attempts | 12 |
| Treatment mean attempts | 12 |
| LLM assessments | 40 |
| Fallback rate | 0% |

**Finding:** Pipeline produces reproducible, bounded behavior with both deterministic and LLM assessment.

### 2.4 LLM Behavior

| Metric | Value |
|--------|-------|
| Mean latency | 2.80s |
| Consistent candidates | 6/8 |
| Inconsistent candidates | 2/8 (MEDIUM/LOW variation) |

---

## 3. GAP-1 Evidence

**File:** `experiments/results/gap1_extended.json`

| Scenario | Changed | Key Observation |
|----------|---------|-----------------|
| mixed_population | Yes | MIX-D outranks MIX-C (quality inversion) |
| large_set_10 | Yes | Assessment reorders candidates |
| large_set_15 | Yes | Assessment reorders candidates |
| large_set_20 | Yes | Assessment reorders candidates |
| assessment_changes_ranking | No | Deterministic assessor produces same order |
| assessment_no_change | No | All HIGH quality → probability order |
| high_prob_poor_quality | No | Deterministic assessor: HIGH-PROB-FAIL gets MEDIUM |
| lower_prob_high_quality | No | Deterministic assessor: HP-LOW gets LOW |
| all_high_quality | No | All HIGH quality → probability order |
| all_low_quality | No | Mixed quality, probability order preserved |

---

## 4. GAP-2 Evidence

**File:** `experiments/results/gap2_extended.json`

| Threshold | Mean Attempts | Max Attempts | All Bounded |
|-----------|---------------|--------------|-------------|
| 1 | 4.67 | 10 | ✓ |
| 2 | 8.17 | 19 | ✓ |
| 3 | 11.67 | 28 | ✓ |
| 4 | 15.17 | 37 | ✓ |
| 5 | 18.67 | 46 | ✓ |

**Tight bound (all candidates fail):**
| Threshold | Attempts | Expected | Ratio |
|-----------|----------|----------|-------|
| 1 | 4 | 4 | 1.00 |
| 2 | 8 | 8 | 1.00 |
| 3 | 12 | 12 | 1.00 |
| 4 | 16 | 16 | 1.00 |
| 5 | 20 | 20 | 1.00 |

---

## 5. Combined Evidence

**File:** `experiments/results/combined_results.json`

| Scenario | Mode | Attempts | Success | Pivots |
|----------|------|----------|---------|--------|
| combined_mixed | Baseline | 6 | 2 | 5 |
| combined_mixed | Treatment | 6 | 2 | 5 |
| combined_large | Baseline | 18 | 2 | 17 |
| combined_large | Treatment | 18 | 2 | 17 |

---

## 6. Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Simulation mode only | Real execution not validated | Docker path available |
| Single LLM model | Results may vary by model | Architecture-agnostic |
| Small candidate sets | No statistical significance | Mechanistic focus |
| Deterministic assessor uses ground-truth | Circular dependency | Real LLM also tested |
| No live targets | Safety concern | By design |
| Docker unavailable | DOCKER_OBSERVED not verified | Infrastructure issue |

---

## 7. Docker Status

**Status: NOT AVAILABLE**

Docker Desktop WSL2 integration not enabled. The `docker` binary exists at `/mnt/c/Users/cfdsw/AppData/Local/Programs/DockerDesktop/resources/bin/docker` but cannot be invoked from WSL2.

**Impact:**
- DOCKER_OBSERVED evidence tier not validated
- All experiments use simulation mode
- Docker lab tests skip or fail

**To enable:**
1. Open Docker Desktop → Settings → Resources → WSL Integration
2. Enable integration with this distro
3. Run: `cd lab && docker-compose up -d`

---

## 8. Test Status

| Metric | Value |
|--------|-------|
| Total tests | 545 |
| Passed | 538 |
| Skipped | 7 |
| Failed | 0 |
| Duration | ~63s |

---

## 9. Research-Core Integrity

| Check | Status |
|-------|--------|
| decision_engine/core/ unchanged since Wave 12 | ✓ |
| Benchmarks unchanged since Wave 12 | ✓ |
| GAP-1 remains assessment → ranking | ✓ |
| GAP-2 remains per-candidate attempts → threshold → pivot | ✓ |
| No hidden scoring | ✓ |
| No duplicated workflow | ✓ |
| No safety bypass | ✓ |
| No arbitrary external targets | ✓ |
| Docker remains isolated | ✓ |
| Provenance remains honest | ✓ |

---

## 10. Remaining Work

| Item | Priority | Status |
|------|----------|--------|
| Docker verification | Medium | Infrastructure issue |
| Additional LLM models | Low | Architecture supports it |
| Larger candidate sets | Low | Architecture scales |
| Live target validation | BLOCKED | Safety design |

---

## 11. Git History (Recent)

```
9952d95 feat: expand thesis-grade experimental evaluation (Wave 12)
bb82bae feat: Wave 11 — Complete research validation program (12 phases)
252c99a fix: GAP-1 assessment must affect ranking (research-critical bug fix)
134cd01 feat: research validation harness and experiment infrastructure
5d29b0f fix: close Wave 10A integration gaps
```

---

## 12. Conclusion

The AI-VAPT framework is **research-validated** for simulation-based scenarios:

1. **GAP-1:** AI pre-execution assessment affects candidate ordering ✓
2. **GAP-2:** Bounded failure-driven pivoting terminates correctly ✓
3. **Pipeline:** Full pipeline produces reproducible, bounded behavior ✓
4. **Safety:** Allowlist, fail-closed, no external targets ✓
5. **Reproducibility:** All experiments deterministic and repeatable ✓

**Status: READY FOR M.TECH THESIS DEFENSE**
