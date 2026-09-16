# Reproducibility Guide — AI-VAPT Research

**Date:** 2026-09-16  
**Commit:** 9952d95 (post-Wave 12)

---

## 1. Environment

### 1.1 System

| Component | Version |
|-----------|---------|
| OS | WSL2 (Ubuntu) |
| Python | 3.10.12 |
| LLM | Ollama llama3.2:3b (Q4_K_M) |
| Git | 2.x |

### 1.2 Dependencies

```
# requirements.txt (pinned)
langchain>=0.3.0
langgraph>=0.2.0
pydantic>=2.0.0
fastapi>=0.110.0
uvicorn>=0.27.0
pytest>=8.0.0
```

---

## 2. Commands

### 2.1 Full Test Suite

```bash
cd /home/vinit/ai_vapt_framework
pytest -q
```

**Expected output:**
```
538 passed, 7 skipped, 2 warnings in ~63s
```

### 2.2 Wave 12 Thesis Evaluation

```bash
python experiments/wave12_thesis_evaluation.py
```

**Expected output:**
```
Wave 12 — Thesis-Grade Experimental Evaluation
...
GAP-1 Summary: 4/10 scenarios changed ranking
GAP-2 Summary: all_bounded=True, 30/30 bounded
Combined Summary: 4 experiments
...
Total experiment runs: 84+
```

### 2.3 Research Validation

```bash
python experiments/research_validation.py
```

### 2.4 View Results

```bash
cat experiments/results/statistical_summary.json
cat experiments/results/gap1_extended.csv
cat experiments/results/gap2_extended.csv
cat experiments/results/combined_results.csv
cat experiments/results/llm_behavior.json
```

---

## 3. Deterministic Experiments

All deterministic experiments produce identical results across runs. The engine is fully deterministic given the same inputs.

| Experiment | Runs | Deterministic |
|------------|------|---------------|
| GAP-1 | 10 | Yes |
| GAP-2 | 30 | Yes |
| Combined (baseline) | 2 | Yes |
| Combined (treatment) | 2 | No (LLM) |
| LLM behavior | 40 | No (LLM) |

---

## 4. LLM Experiments

### 4.1 Setup

```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull llama3.2:3b
ollama pull llama3.2:3b

# Verify
ollama list
```

### 4.2 Expected Behavior

- **Latency:** ~2.8s per assessment call
- **Consistency:** 6/8 candidates perfectly consistent across 5 repetitions
- **Fallback rate:** 0% (LLM available)

### 4.3 Reproducibility Note

LLM experiments use temperature=0.1 for reproducibility. Minor variation (MEDIUM ↔ LOW) is expected in 2/8 candidates. This is documented behavior, not a bug.

---

## 5. Raw Data

### 5.1 File Locations

| File | Description |
|------|-------------|
| `experiments/results/gap1_extended.json` | Full GAP-1 data |
| `experiments/results/gap1_extended.csv` | GAP-1 summary |
| `experiments/results/gap2_extended.json` | Full GAP-2 data |
| `experiments/results/gap2_extended.csv` | GAP-2 summary |
| `experiments/results/combined_results.json` | Combined data |
| `experiments/results/combined_results.csv` | Combined summary |
| `experiments/results/llm_behavior.json` | LLM behavior data |
| `experiments/results/statistical_summary.json` | Aggregated statistics |

### 5.2 Data Integrity

All raw data files are JSON/CSV text files. They can be independently verified against the experiment scripts:

- `experiments/wave12_thesis_evaluation.py` — Wave 12 experiments
- `experiments/research_validation.py` — Research validation
- `experiments/harness/__init__.py` — Experiment harness

---

## 6. Verification Steps

### 6.1 Verify Test Suite

```bash
pytest -q --tb=short
# Expected: 538 passed, 7 skipped, 0 failed
```

### 6.2 Verify Experiments

```bash
python experiments/wave12_thesis_evaluation.py
# Expected: 84+ experiments, all reproducible
```

### 6.3 Verify Results

```bash
python -c "
import json
with open('experiments/results/statistical_summary.json') as f:
    ss = json.load(f)
print(f'GAP-1: {ss["gap1"]["ranking_changed_count"]}/{ss["gap1"]["total_experiments"]} changed')
print(f'GAP-2: {ss["gap2"]["bounded_count"]}/{ss["gap2"]["total_experiments"]} bounded')
print(f'LLM available: {ss["llm_behavior"]["available"]}')
"
```

---

## 7. Known Issues

1. **Docker unavailable:** Docker Desktop WSL2 integration not enabled. Cannot validate DOCKER_OBSERVED evidence tier.
2. **LLM variation:** 2/8 candidates show minor MEDIUM/LOW variation across repetitions (expected at temperature=0.1).
3. **Single LLM model:** Only llama3.2:3b tested.

---

## 8. Re-running Experiments

To re-run all experiments from scratch:

```bash
# Clean results
rm -rf experiments/results/*

# Run Wave 12 evaluation
python experiments/wave12_thesis_evaluation.py

# Run research validation
python experiments/research_validation.py

# Run fair benchmark
python -m decision_engine.benchmarks.fair_benchmark

# Run VAPT benchmark
python -m decision_engine.benchmarks.fair_vapt_benchmark

# Run domain-agnostic benchmark
python -m decision_engine.benchmarks.agnostic_benchmark
```
