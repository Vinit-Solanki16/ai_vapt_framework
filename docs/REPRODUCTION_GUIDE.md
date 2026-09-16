# Reproduction Guide — AI-VAPT Framework

**Date:** 2026-09-16  
**Commit:** 9952d95 (post-Wave 12)

---

## 1. Quick Start

```bash
# Clone the repository
cd /home/vinit/ai_vapt_framework

# Activate virtual environment
source venv/bin/activate

# Run all tests
pytest -q
# Expected: 538 passed, 7 skipped, 0 failed

# Run research validation
python experiments/research_validation.py

# Run Wave 12 thesis evaluation
python experiments/wave12_thesis_evaluation.py

# View results
cat experiments/results/statistical_summary.json
```

---

## 2. Environment

| Component | Version |
|-----------|---------|
| OS | WSL2 (Ubuntu) |
| Python | 3.10.12 |
| Git | 2.x |
| LLM (optional) | Ollama llama3.2:3b |

---

## 3. Running Experiments

### 3.1 Deterministic Experiments (No LLM Required)

```bash
# GAP-1 experiments
python -c "
from experiments.research_validation import gap1_experiment
results = gap1_experiment()
print(f'GAP-1: {len(results)} experiments')
for r in results:
    print(f'  {r.experiment_name}: attempts={r.total_attempts}, success={r.successful_validations}')
"

# GAP-2 experiments
python -c "
from experiments.research_validation import gap2_experiment
results = gap2_experiment()
print(f'GAP-2: {len(results)} experiments')
for r in results:
    print(f'  {r.experiment_name}: attempts={r.total_attempts}, pivots={r.pivot_count}')
"

# Combined experiments
python -c "
from experiments.research_validation import combined_experiment
results = combined_experiment()
print(f'Combined: {len(results)} experiments')
for r in results:
    print(f'  {r.experiment_name}: attempts={r.total_attempts}, success={r.successful_validations}')
"
```

### 3.2 LLM Experiments (Ollama Required)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull llama3.2:3b
ollama pull llama3.2:3b

# Run LLM behavior experiments
python -c "
from experiments.wave12_thesis_evaluation import run_llm_behavior_experiments
results = run_llm_behavior_experiments(repetitions=5)
print(f'LLM available: {results["available"]}')
print(f'Total assessments: {results["summary"]["total_assessments"]}')
print(f'All consistent: {results["summary"]["all_consistent"]}')
"
```

### 3.3 Benchmarks

```bash
# Domain-agnostic benchmark
python -m decision_engine.benchmarks.agnostic_benchmark

# Fair benchmark (4-agent ablation)
python -m decision_engine.benchmarks.fair_benchmark --seeds 30

# VAPT benchmark
python -m decision_engine.benchmarks.fair_vapt_benchmark --seeds 30

# LLM assessor benchmark
python -m decision_engine.benchmarks.llm_assessor_benchmark
```

---

## 4. Verifying Results

### 4.1 Test Suite

```bash
pytest -q --tb=short
# Expected: 538 passed, 7 skipped, 0 failed
```

### 4.2 Statistical Summary

```bash
python -c "
import json
with open('experiments/results/statistical_summary.json') as f:
    ss = json.load(f)
print(f'GAP-1: {ss["gap1"]["ranking_changed_count"]}/{ss["gap1"]["total_experiments"]} changed')
print(f'GAP-2: {ss["gap2"]["bounded_count"]}/{ss["gap2"]["total_experiments"]} bounded')
print(f'LLM available: {ss["llm_behavior"]["available"]}')
print(f'LLM consistent: {ss["llm_behavior"].get("all_consistent", "N/A")}')
"
```

### 4.3 Individual Result Files

```bash
# GAP-1
cat experiments/results/gap1_extended.csv

# GAP-2
cat experiments/results/gap2_extended.csv

# Combined
cat experiments/results/combined_results.csv

# LLM behavior
cat experiments/results/llm_behavior.json | python -m json.tool

# Statistical summary
cat experiments/results/statistical_summary.json | python -m json.tool
```

---

## 5. API Verification

```bash
# Start API server
python -m uvicorn services.api:app --host 0.0.0.0 --port 8000 &

# Health check
curl http://localhost:8000/health

# Create a run
curl -X POST http://localhost:8000/runs   -H "Content-Type: application/json"   -d '{"target":"demo","mode":"simulation"}'

# Get run details (replace {run_id})
curl http://localhost:8000/runs/{run_id}
curl http://localhost:8000/runs/{run_id}/events
curl http://localhost:8000/runs/{run_id}/evidence
curl http://localhost:8000/runs/{run_id}/report

# Stop server
kill %1
```

---

## 6. Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | `source venv/bin/activate` |
| LLM not available | Install Ollama: `curl -fsSL https://ollama.ai/install.sh \| sh` |
| Docker not available | Enable Docker Desktop WSL2 integration |
| Test failures | Run `pytest -q --tb=long` for details |
| Missing results | Run `python experiments/wave12_thesis_evaluation.py` |

---

## 7. Data Integrity

All raw data files are JSON/CSV text files. They can be independently verified:

```bash
# Verify JSON is valid
python -c "import json; json.load(open('experiments/results/statistical_summary.json')); print('OK')"

# Verify CSV is valid
python -c "import csv; list(csv.reader(open('experiments/results/gap1_extended.csv'))); print('OK')"
```

---

## 8. Re-running from Scratch

```bash
# Clean results
rm -rf experiments/results/*

# Re-run all experiments
python experiments/wave12_thesis_evaluation.py
python experiments/research_validation.py

# Re-run all tests
pytest -q

# Verify
python -c "
import json
with open('experiments/results/statistical_summary.json') as f:
    ss = json.load(f)
assert ss['gap1']['ranking_changed_count'] == 4
assert ss['gap2']['all_bounded'] == True
assert ss['llm_behavior']['available'] == True
print('All checks pass')
"
```
