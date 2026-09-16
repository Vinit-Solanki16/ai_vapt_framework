# Final Demo Guide — AI-VAPT Framework

**Date:** 2026-09-16  
**Commit:** 9952d95 (post-Wave 12)  
**Version:** 2.0 (Final)

---

## Overview

Two deterministic demonstrations for M.Tech thesis defense:

1. **DEMO A — Research Contribution:** Finding → enrichment → AI assessment → ranking → execution → failure → bounded attempt counter → pivot → alternative candidate → result
2. **DEMO B — Platform:** GUI → Docker lab → assessment → execution → evidence → report

---

## DEMO A — Research Contribution (GAP-1 + GAP-2)

### Objective

Demonstrate the two core research contributions:
- **GAP-1:** AI pre-execution assessment affects candidate ordering
- **GAP-2:** Bounded failure-driven pivoting with per-candidate attempt counters

### Prerequisites

```bash
cd /home/vinit/ai_vapt_framework
python --version  # 3.10.12
```

### Step 1: Run the Research Validation Script

```bash
python experiments/research_validation.py
```

**Expected Output:**
```
======================================================================
AI-VAPT Research Validation Experiments
======================================================================

======================================================================
GAP-1: AI Pre-Execution Assessment
======================================================================

=== GAP-1 Experiment 1: High-prob-FAIL vs Medium-prob-SUCCESS ===
  Ranking: MED-PROB-SUCCESS > HIGH-PROB-FAIL > LOW-PROB-FAIL
  Scores: {'MED-PROB-SUCCESS': 0.55, 'HIGH-PROB-FAIL': 0.52, 'LOW-PROB-FAIL': 0.195}
  Quality: {'MED-PROB-SUCCESS': 'HIGH', 'HIGH-PROB-FAIL': 'LOW', 'LOW-PROB-FAIL': 'LOW'}
  Expected: MED-PROB-SUCCESS > HIGH-PROB-FAIL > LOW-PROB-FAIL

=== GAP-1 Experiment 2: Assessment inversion scenario ===
  Ranking: CAND-B > CAND-A
  Scores: {'CAND-B': 0.50, 'CAND-A': 0.4875}
  Quality: {'CAND-B': 'HIGH', 'CAND-A': 'LOW'}

=== GAP-1 Experiment 3: All SUCCESS candidates ===
  Ranking: SUCCESS-A > SUCCESS-B
  Scores: {'SUCCESS-A': 0.60, 'SUCCESS-B': 0.40}
  Quality: {'SUCCESS-A': 'HIGH', 'SUCCESS-B': 'HIGH'}

======================================================================
GAP-2: Bounded Failure-Driven Pivoting
======================================================================

=== GAP-2 Experiment 1: Threshold = 1 ===
  Attempts: 2, Pivots: 2
  Candidates processed: ['TH1-FAIL', 'TH1-SUCCESS']

=== GAP-2 Experiment 2: Threshold = 2 ===
  Attempts: 5, Pivots: 4
  Candidates processed: ['TH2-FAIL', 'TH2-SUCCESS']

=== GAP-2 Experiment 3: Threshold = 3 ===
  Attempts: 7, Pivots: 4
  Candidates processed: ['TH3-FAIL', 'TH3-SUCCESS']

=== GAP-2 Experiment 4: All fail (bounded termination) ===
  Attempts: 6, Pivots: 5
  Final status: COMPLETED

=== GAP-2 Experiment 5: Immediate success ===
  Attempts: 2, Pivots: 1
  Final status: SUCCESS

======================================================================
Combined: AI Ranking + Pivot
======================================================================

=== Combined Experiment 1: Baseline (deterministic assessment + pivot) ===
  Ranking: B > A > C
  Attempts: 5, Successful: 1

=== Combined Experiment 2: Treatment (AI-assisted ranking + pivot) ===
  Ranking: B > A > C
  Attempts: 5, Successful: 1
```

### Step 2: Run the Wave 12 Thesis Evaluation

```bash
python experiments/wave12_thesis_evaluation.py
```

**Expected Output:**
```
======================================================================
Wave 12 — Thesis-Grade Experimental Evaluation
======================================================================

LLM assessor (Ollama llama3.2:3b): AVAILABLE

======================================================================
Phase 2: GAP-1 Expanded Experiments
======================================================================

GAP-1 Summary: 4/10 scenarios changed ranking

======================================================================
Phase 3: Real LLM Behavior Evaluation
======================================================================

LLM Summary: consistent=False, fallback_rate=0.0, avg_latency=2.8s

======================================================================
Phase 4: GAP-2 Expanded Experiments
======================================================================

GAP-2 Summary: all_bounded=True, 30/30 bounded

======================================================================
Phase 5: Combined Full-Pipeline Experiments
======================================================================

Combined Summary: 4 experiments

======================================================================
Wave 12 Complete
======================================================================
  GAP-1 experiments: 10
  GAP-2 experiments: 30
  Combined experiments: 4
  LLM behavior assessments: 40
  Total experiment runs: 84
  Results saved to: experiments/results/
```

### Step 3: Verify Results

```bash
# Check statistical summary
cat experiments/results/statistical_summary.json | python -m json.tool | head -30

# Check GAP-1 CSV
cat experiments/results/gap1_extended.csv

# Check GAP-2 CSV
cat experiments/results/gap2_extended.csv

# Check combined results
cat experiments/results/combined_results.csv

# Check LLM behavior
cat experiments/results/llm_behavior.json | python -m json.tool | head -30
```

### Step 4: Run Domain-Agnostic Benchmark

```bash
python -m decision_engine.benchmarks.agnostic_benchmark
```

**Expected Output:**
```
=== DOMAIN-AGNOSTIC BENCHMARK (tasks domain) ===
SMART  : requests=4, pivots=4, status=SUCCESS
   T-REBOOT     -> SUCCESS
   T-PATCH      -> FAIL_TIMEOUT
   T-CLEANUP    -> SUCCESS
DUMB   : requests=10
   T-REBOOT     attempts=1
   T-PATCH      attempts=5
   T-BACKUP     attempts=5
   T-CLEANUP    attempts=5
   T-AUDIT      attempts=5

=== VERDICT ===
SMART used 4 total attempts vs DUMB 10 -> WIN (fewer attempts = bounded failure)
OK: engine bounds repeated-failure behavior on a NON-VAPT domain.
```

### Step 5: Run Fair Benchmark (4-Agent Ablation)

```bash
python -m decision_engine.benchmarks.fair_benchmark --seeds 30 --caps 1 2 3 5
```

**Expected Output:**
```
FAIR BENCHMARK — Gap-1 (priority) vs Gap-2 (pivot) ablation
  Families : ['many_success', 'sparse_success', 'all_fail', 'long_tail', 'correlated', 'anticorrelated']
  Caps T    : [1, 2, 3, 5]
  Seeds     : 30 per condition
  N/cand    : 50

...
```

### Evidence Produced

| Evidence | File |
|----------|------|
| GAP-1 ranking changes | `experiments/results/gap1_extended.json` |
| GAP-2 boundedness | `experiments/results/gap2_extended.json` |
| LLM behavior | `experiments/results/llm_behavior.json` |
| Combined pipeline | `experiments/results/combined_results.json` |
| Statistical summary | `experiments/results/statistical_summary.json` |

### Safety Constraints

- All experiments use simulation mode (no live execution)
- No external targets
- No real vulnerabilities exploited
- Deterministic results (reproducible)

---

## DEMO B — Platform (GUI → Docker Lab → Assessment → Execution → Evidence → Report)

### Objective

Demonstrate the full VAPT platform workflow:
1. Start the API server
2. Create a run via API
3. View run progress
4. Generate report
5. View evidence

### Prerequisites

```bash
cd /home/vinit/ai_vapt_framework

# Install dependencies
pip install -r requirements.txt
```

### Step 1: Run the Full Test Suite

```bash
pytest -q --tb=short
```

**Expected Output:**
```
538 passed, 7 skipped, 2 warnings in ~63s
```

### Step 2: Verify API Endpoints

```bash
# Start the API server (background)
python -m uvicorn services.api:app --host 0.0.0.0 --port 8000 &

# Health check
curl http://localhost:8000/health
# Expected: {"status":"ok"}

# Create a run
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"target":"demo","mode":"simulation"}'
# Expected: {"id":"...", "status":"created", ...}

# Get run details
curl http://localhost:8000/runs/{run_id}

# Get run events
curl http://localhost:8000/runs/{run_id}/events

# Get run evidence
curl http://localhost:8000/runs/{run_id}/evidence

# Get run report
curl http://localhost:8000/runs/{run_id}/report

# Stop the server
kill %1
```

### Step 3: Run Integration Tests

```bash
pytest services/tests/test_api.py -v
pytest services/tests/test_safety.py -v
```

### Step 4: Run Frontend Tests

```bash
pytest frontend/tests/test_frontend_smoke.py -v
```

### Step 5: Run Docker Lab Tests (if Docker available)

```bash
pytest tests/test_docker_lab.py -v
```

**Note:** Docker tests require Docker Desktop WSL2 integration. If unavailable, tests will skip or fail with clear error.

### Step 6: Run Docker Lab Scenarios (if Docker available)

```bash
# Run docker_vuln scenario
python tests/run_tdocker_scenarios.py

# Or run individual scenarios
pytest tests/test_docker_lab.py::test_docker_vuln -v
pytest tests/test_docker_lab.py::test_docker_fail -v
pytest tests/test_docker_lab.py::test_docker_pivot -v
```

### Evidence Produced

| Evidence | Location |
|----------|----------|
| API responses | Terminal output |
| Test results | pytest output |
| Run data | `data/experiment_runs/` |
| Reports | `data/reports/` |

### Safety Constraints

- All execution uses simulation mode
- Docker lab is isolated (no external targets)
- Allowlist enforced
- Fail-closed on errors

---

## Summary

| Demo | Type | Duration | Evidence |
|------|------|----------|----------|
| A | Research (GAP-1 + GAP-2) | ~2 minutes | 84 experiment runs |
| B | Platform (API + Tests) | ~1 minute | 538 tests pass |

Both demos are deterministic, reproducible, and safe (simulation-only).