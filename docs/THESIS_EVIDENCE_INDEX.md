# Thesis Evidence Index — AI-VAPT Framework

**Date:** 2026-09-16  
**Commit:** 9952d95 (post-Wave 12)

---

## 1. Overview

This document indexes all evidence files for the M.Tech thesis. Every numerical claim traces back to a result file.

---

## 2. Research Claims and Evidence

### 2.1 GAP-1: AI Pre-Execution Assessment Affects Ranking

| Claim | Evidence File | Key Metric |
|-------|---------------|------------|
| 4/10 scenarios changed ranking | `experiments/results/gap1_extended.json` | `ranking_changed` field |
| Assessment can invert probability order | `experiments/results/gap1_extended.json` | `mixed_population` scenario |
| Graceful fallback (equal quality) | `experiments/results/gap1_extended.json` | 6/10 scenarios unchanged |
| Large sets show ranking changes | `experiments/results/gap1_extended.json` | `large_set_10/15/20` scenarios |

### 2.2 GAP-2: Bounded Failure-Driven Pivoting

| Claim | Evidence File | Key Metric |
|-------|---------------|------------|
| 30/30 experiments bounded | `experiments/results/gap2_extended.json` | `bounded` field |
| Per-candidate attempt counters | `experiments/results/gap2_extended.json` | `candidate_attempt_counters` field |
| Configurable threshold (1-5) | `experiments/results/gap2_extended.json` | `threshold` field |
| Tight bound (all fail) | `experiments/results/gap2_extended.json` | Attempts = N × max_attempts |

### 2.3 Combined Pipeline

| Claim | Evidence File | Key Metric |
|-------|---------------|------------|
| Baseline = Treatment attempts | `experiments/results/combined_results.json` | `total_attempts` field |
| Pipeline reproducibility | `experiments/results/combined_results.json` | All 4 experiments complete |
| LLM assessment works | `experiments/results/llm_behavior.json` | 40 assessments, 0% fallback |

### 2.4 LLM Behavior

| Claim | Evidence File | Key Metric |
|-------|---------------|------------|
| Mean latency ~2.8s | `experiments/results/llm_behavior.json` | `overall_latency.mean` |
| 6/8 candidates consistent | `experiments/results/llm_behavior.json` | `consistency_per_candidate` |
| 0% fallback rate | `experiments/results/llm_behavior.json` | `fallback_rate` |

---

## 3. File Locations

### 3.1 Primary Evidence

| File | Description | Size |
|------|-------------|------|
| `experiments/results/gap1_extended.json` | GAP-1 full data (10 scenarios) | ~10KB |
| `experiments/results/gap1_extended.csv` | GAP-1 summary table | ~2KB |
| `experiments/results/gap2_extended.json` | GAP-2 full data (30 experiments) | ~15KB |
| `experiments/results/gap2_extended.csv` | GAP-2 summary table | ~3KB |
| `experiments/results/combined_results.json` | Combined pipeline data | ~5KB |
| `experiments/results/combined_results.csv` | Combined summary table | ~1KB |
| `experiments/results/llm_behavior.json` | LLM behavior data (40 assessments) | ~10KB |
| `experiments/results/statistical_summary.json` | Aggregated statistics | ~5KB |

### 3.2 Secondary Evidence

| File | Description |
|------|-------------|
| `experiments/results/gap1_ai_informed_ranking.json` | GAP-1 AI-informed ranking |
| `experiments/results/raw_results.json` | Raw experiment results |
| `experiments/results/summary.csv` | Summary CSV |
| `experiments/results/detailed_results.csv` | Detailed CSV |
| `experiments/results/experiment_metadata.json` | Experiment metadata |

### 3.3 Docker Evidence (if available)

| File | Description |
|------|-------------|
| `data/experiment_runs/*/metadata.json` | Docker experiment metadata |
| `data/experiment_runs/*/framework_logs_*.txt` | Framework logs |
| `data/experiment_runs/*/emulator_access_*.log` | Emulator access logs |

---

## 4. Numerical Claims Traceability

### 4.1 GAP-1 Claims

| Claim | Value | Source File | Field |
|-------|-------|-------------|-------|
| Total scenarios | 10 | `gap1_extended.json` | `len(data)` |
| Ranking changed | 4 | `gap1_extended.json` | `ranking_changed=True` |
| Ranking unchanged | 6 | `gap1_extended.json` | `ranking_changed=False` |
| Mean attempts | 11.6 | `statistical_summary.json` | `gap1.attempts.mean` |
| Mean success | 2.6 | `statistical_summary.json` | `gap1.successful_validations.mean` |

### 4.2 GAP-2 Claims

| Claim | Value | Source File | Field |
|-------|-------|-------------|-------|
| Total experiments | 30 | `gap2_extended.json` | `len(data)` |
| All bounded | True | `gap2_extended.json` | `bounded=True` |
| Mean attempts | 11.67 | `statistical_summary.json` | `gap2.attempts.mean` |
| Max attempts | 46 | `gap2_extended.json` | `total_attempts` max |

### 4.3 LLM Claims

| Claim | Value | Source File | Field |
|-------|-------|-------------|-------|
| Total assessments | 40 | `llm_behavior.json` | `summary.total_assessments` |
| LLM assessments | 40 | `llm_behavior.json` | `summary.llm_count` |
| Fallback rate | 0.0 | `llm_behavior.json` | `summary.fallback_rate` |
| Mean latency | 2.80s | `llm_behavior.json` | `summary.overall_latency.mean` |

---

## 5. Verification Commands

```bash
# Verify all JSON files are valid
for f in experiments/results/*.json; do
    python -c "import json; json.load(open('$f')); print('OK: $f')"
done

# Verify all CSV files are valid
for f in experiments/results/*.csv; do
    python -c "import csv; list(csv.reader(open('$f'))); print('OK: $f')"
done

# Verify statistical summary
python -c "
import json
with open('experiments/results/statistical_summary.json') as f:
    ss = json.load(f)
assert ss['gap1']['total_experiments'] == 10
assert ss['gap1']['ranking_changed_count'] == 4
assert ss['gap2']['total_experiments'] == 30
assert ss['gap2']['all_bounded'] == True
assert ss['llm_behavior']['available'] == True
print('All assertions pass')
"
```

---

## 6. Documentation Index

### 6.1 Thesis Documents

| Document | Purpose |
|----------|---------|
| `docs/thesis/final_research_methodology.md` | Research methodology |
| `docs/thesis/gap1_evaluation.md` | GAP-1 evaluation |
| `docs/thesis/gap2_evaluation.md` | GAP-2 evaluation |
| `docs/thesis/combined_evaluation.md` | Combined evaluation |
| `docs/thesis/statistical_analysis.md` | Statistical analysis |
| `docs/thesis/threats_to_validity.md` | Threats to validity |
| `docs/thesis/reproducibility.md` | Reproducibility guide |
| `docs/thesis/safety_ethics.md` | Safety & ethics |
| `docs/thesis/implementation_architecture.md` | Implementation architecture |

### 6.2 Project Documents

| Document | Purpose |
|----------|---------|
| `docs/FINAL_PROJECT_CHECKPOINT.md` | Final checkpoint |
| `docs/FINAL_VALIDATION_REPORT.md` | Validation report |
| `docs/REPRODUCTION_GUIDE.md` | Reproduction guide |
| `docs/THESIS_EVIDENCE_INDEX.md` | This document |
| `docs/project_management/FINAL_DEMO_GUIDE.md` | Demo guide |

---

## 7. Summary

All numerical claims in the thesis trace back to result files. All result files are JSON/CSV text files that can be independently verified. No fabricated results.
