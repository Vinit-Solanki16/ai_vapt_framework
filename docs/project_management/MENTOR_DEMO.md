# Mentor Demonstration Guide

**Date:** 2026-09-21
**Branch:** `prototype-development`
**Status:** READY

---

## Overview

This guide provides a step-by-step demonstration of the AI-VAPT framework
for mentors and evaluators. The demo showcases the two validated research
contributions:

1. **GAP-1:** AI/LLM assessment of exploit quality BEFORE candidate ranking
2. **GAP-2:** Dynamic pivoting after configurable failure threshold

---

## Prerequisites

```bash
# Activate environment
source venv/bin/activate

# Verify Ollama is running (optional — deterministic fallback works without it)
ollama serve &

# Verify installation
python -m pytest tests/ -q  # Should show 545 passed
```

---

## Demo 1: Simulation Mode (Deterministic)

### 1.1 Run the Failure-Pivot Scenario

```bash
python -m prototype.cli run \
  --scenario failure_pivot \
  --mode simulation \
  --max-attempts 2 \
  --assessor deterministic
```

### Expected Output

```
CANDIDATE RANKING
----------------------------------------
  1. DEMO-WORKER                prob=0.8500  quality=HIGH     score=0.8500
  2. DEMO-DEAD-END              prob=0.7000  quality=LOW      score=0.3500

ENGINE EXECUTION
----------------------------------------
  DEMO-WORKER                Outcome: SUCCESS  (simulated(ground_truth))
  DEMO-DEAD-END              Outcome: FAIL_TIMEOUT  (simulated(ground_truth))
  DEMO-DEAD-END              Outcome: FAIL_TIMEOUT  (simulated(ground_truth))

DECISION TRACE
----------------------------------------
  [INIT]   Engine initialized: 2 candidates, pivot_threshold=2, mode=simulation
  [EXECUTE] Attempt: 1/?  Outcome: SUCCESS  Candidate: DEMO-WORKER
  [ADVANCE] DEMO-WORKER validated. Next candidate.
  [PIVOT]   Redirected to: DEMO-DEAD-END
  [EXECUTE] Attempt: 1/2  Outcome: FAIL_TIMEOUT  Candidate: DEMO-DEAD-END
  [EXECUTE] Attempt: 2/2  Outcome: FAIL_TIMEOUT  Candidate: DEMO-DEAD-END
  [PIVOT]   Threshold reached for DEMO-DEAD-END. Abandoning route.
  [PIVOT]   All candidates processed. Workflow complete.

FINAL RESULT
----------------------------------------
Status:         COMPLETED
Total Attempts: 3
Pivot Count:    2
Candidates Processed: 2 (DEMO-WORKER, DEMO-DEAD-END)
```

### Key Observations

1. **GAP-1 in action:** DEMO-WORKER (quality=HIGH, score=0.85) is ranked first
   despite DEMO-DEAD-END having probability 0.70. The AI assessment
   (deterministic fallback here) correctly identified DEMO-WORKER as higher
   quality, so it was attempted first.

2. **GAP-2 in action:** DEMO-DEAD-END fails twice (threshold=2), then the
   engine pivots. The per-candidate attempt counter resets after pivot.

3. **Bounded termination:** The engine stops after all candidates are
   processed — no infinite loops.

---

## Demo 2: AI Assessment Mode (Ollama)

### 2.1 Run with AI Assessor

```bash
python -m prototype.cli run \
  --scenario failure_pivot \
  --mode simulation \
  --max-attempts 2 \
  --assessor llm
```

### Expected Behavior

- The system calls local Ollama (`llama3.2:3b`) to assess each candidate
- Assessment includes: syntax validity, complexity, prerequisites, usability
- Results are marked with `source="llm"` and `provider="ollama"`

### Fallback Behavior

If Ollama is unavailable, the system automatically falls back to deterministic
assessment and clearly marks it:

```
Assessment: deterministic (fallback)
```

---

## Demo 3: Docker Lab Mode

### 3.1 Start the Docker Lab

```bash
cd lab
docker-compose up -d
```

### 3.2 Run Docker Pivot Scenario

```bash
python -m prototype.cli run \
  --scenario docker_pivot \
  --mode lab \
  --target 172.28.0.2 \
  --port 8080 \
  --max-attempts 2 \
  --assessor deterministic
```

### Expected Output

```
CANDIDATE RANKING
----------------------------------------
  1. docker-vuln-success        prob=0.8500  quality=HIGH     score=0.8500
  2. docker-fail-pivot          prob=0.7000  quality=LOW      score=0.3500

ENGINE EXECUTION
----------------------------------------
  docker-vuln-success        Outcome: SUCCESS  (docker-observed(...))
  docker-fail-pivot          Outcome: FAIL_TIMEOUT  (docker-observed(...))
  docker-fail-pivot          Outcome: FAIL_TIMEOUT  (docker-observed(...))

DECISION TRACE
----------------------------------------
  [INIT]   Engine initialized: 2 candidates, pivot_threshold=2, mode=lab
  [EXECUTE] Attempt: 1/?  Outcome: SUCCESS  Candidate: docker-vuln-success
  [ADVANCE] docker-vuln-success validated. Next candidate.
  [PIVOT]   Redirected to: docker-fail-pivot
  [EXECUTE] Attempt 1/2  Outcome: FAIL_TIMEOUT  Candidate: docker-fail-pivot
  [EXECUTE] Attempt 2/2  Outcome: FAIL_TIMEOUT  Candidate: docker-fail-pivot
  [PIVOT]   Threshold reached for docker-fail-pivot. Abandoning route.
  [PIVOT]   All candidates processed. Workflow complete.

FINAL RESULT
----------------------------------------
Status:         COMPLETED
Total Attempts: 3
Pivot Count:    2
Candidates Processed: 2 (docker-vuln-success, docker-fail-pivot)

SAFETY / EVIDENCE TIER
================================================================
LAB MODE (DOCKER OBSERVED)
Outcomes are observed from the Docker-isolated emulator (real HTTP responses).
Target is allowlisted. No external targets contacted.
================================================================
```

### Key Observations

1. **DOCKER_OBSERVED evidence tier:** Outcomes are from real HTTP responses
   to the isolated emulator, not from ground-truth labels.

2. **Safety enforced:** Only allowlisted targets (172.28.0.2) are permitted.
   The emulator runs on an isolated Docker network with no external access.

3. **Same research logic:** The decision engine behaves identically in
   simulation and Docker modes — only the execution backend changes.

---

## Demo 4: Web Dashboard

### 4.1 Start the Dashboard

```bash
streamlit run frontend/app.py
```

### 4.2 Navigate the Dashboard

1. **Dashboard:** View total runs, success rate, system health
2. **New Assessment:** Configure and run a new assessment
3. **Run History:** Browse past runs with filters
4. **Findings:** View all findings across runs
5. **Intelligence:** Look up CVE intelligence (EPSS, KEV)
6. **Attack Paths:** Visualize pivot/attack paths
7. **Reports:** Generate reports in JSON/TXT/HTML/Markdown
8. **System:** View system health and API endpoints

---

## Demo 5: API

### 5.1 Start the API

```bash
uvicorn services.api:app --reload --port 8000
```

### 5.2 Run a Scenario via API

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "failure_pivot",
    "mode": "simulation",
    "max_attempts": 2,
    "assessor": "deterministic"
  }'
```

### 5.3 Get Results

```bash
curl http://localhost:8000/runs/{run_id}/persisted
curl http://localhost:8000/runs/{run_id}/events
curl http://localhost:8000/runs/{run_id}/report
```

---

## Research Integrity Notes

### GAP-1: Assessment Before Ranking

The engine assesses ALL candidates BEFORE ranking them. This ensures
quality signals influence prioritization.

```python
# decision_engine/core/engine.py:initial_state()
if assess_fn:
    assess_candidates(raw_candidates, assess_fn=assess_fn)  # Assess FIRST
cs = rank_candidates(raw_candidates)  # THEN rank
```

### GAP-2: Bounded Pivot

Per-candidate attempt counters with configurable threshold. The counter
resets after each pivot.

```python
# decision_engine/core/engine.py:_evaluate()
if state["attempt_count"] >= state["max_attempts"]:
    return "pivot"  # Threshold reached → pivot
```

### Evidence Tiers

| Tier | Description | Source |
|------|-------------|--------|
| SIMULATED | Ground-truth labels | `labels.json` |
| OBSERVED_LOCAL | Loopback (127.0.0.1) | Real HTTP |
| DOCKER_OBSERVED | Docker emulator | Real HTTP to isolated container |
| CONTROLLED_VALIDATION | Live target | Real execution |

---

## Troubleshooting

### Ollama not available

The system automatically falls back to deterministic assessment. No action
needed — the demo works identically.

### Docker not available

Use Simulation mode instead. The Docker lab code is complete and tested
(13 tests), but runtime verification requires Docker Desktop.

### Tests failing

```bash
source venv/bin/activate
python -m pytest tests/ -q
```

All 545 tests should pass. If not, check for environment issues.

---

## Summary

| Demo | Mode | Assessor | Evidence Tier | Key Feature |
|------|------|----------|---------------|-------------|
| 1 | Simulation | Deterministic | SIMULATED | GAP-1 + GAP-2 |
| 2 | Simulation | AI (Ollama) | SIMULATED | LLM assessment |
| 3 | Docker Lab | Deterministic | DOCKER_OBSERVED | Real HTTP |
| 4 | Web UI | Any | Any | Professional dashboard |
| 5 | API | Any | Any | REST endpoints |

---

_This demo is reproducible with the commands above. All outcomes are
deterministic in simulation mode._
