# UI Demo Guide

**Date:** 2026-09-21
**Branch:** `prototype-development`
**Status:** READY FOR DEMONSTRATION

---

## Overview

This guide provides a step-by-step demonstration of the AI-VAPT
Operations Console for mentors and evaluators.

---

## Prerequisites

```bash
# Activate environment
source venv/bin/activate

# Start the application
uvicorn services.api:app --reload --port 8000
```

Open: http://localhost:8000

### Optional: Start Ollama for AI Assessment

```bash
ollama serve &
ollama pull llama3.2:3b
```

Without Ollama, the system uses deterministic fallback automatically.

---

## Demo 1: Dashboard Overview

### Steps

1. Open http://localhost:8000
2. The Dashboard loads automatically
3. Observe:
   - System status: "SYSTEM OPERATIONAL"
   - Metric cards: Total Runs, Successful, Pivots, CRIT Findings
   - Recent runs table
   - System health panel

### Expected

- All metrics come from actual persisted data
- No hardcoded values
- Real-time system health status

---

## Demo 2: Run a Simulation Assessment

### Steps

1. Click "New Assessment" in the sidebar
2. Select Mode: "Simulation"
3. Select Scenario: "failure_pivot"
4. Select Assessor: "deterministic"
5. Set Pivot Threshold: 2
6. Verify safety status shows "SIMULATION"
7. Click "Run Assessment"

### Expected

- Pipeline stepper shows progress
- Candidates table shows quality ranks
- Assessment panel shows "deterministic" mode
- Results show actual execution outcomes

### Key Observations

- **GAP-1:** Candidates are assessed before ranking
- **GAP-2:** Failed candidates trigger pivot after threshold

---

## Demo 3: Run with AI Assessment

### Prerequisites

```bash
ollama serve &
```

### Steps

1. Click "New Assessment" in the sidebar
2. Select Mode: "Simulation"
3. Select Scenario: "failure_pivot"
4. Select Assessor: "ai"
5. Select Provider: "ollama"
6. Click "Run Assessment"

### Expected

- Assessment panel shows "ai" mode
- Provider shows "ollama"
- Quality ranks come from LLM assessment

### Fallback Behavior

If Ollama is unavailable:
- System uses deterministic fallback
- Clearly marked as "Fallback active"
- Never displayed as AI assessment

---

## Demo 4: Docker Lab Assessment

### Prerequisites

```bash
# Start Docker Desktop
# Then:
cd lab
docker-compose up -d
cd ..
```

### Steps

1. Click "New Assessment" in the sidebar
2. Select Mode: "Docker Lab"
3. Select Target: "172.28.0.2"
4. Select Scenario: "docker_pivot"
5. Verify safety status shows "AUTHORIZED / ALLOWLISTED"
6. Click "Run Assessment"

### Expected

- Evidence tier: DOCKER_OBSERVED
- Real HTTP responses from emulator
- Pipeline shows actual execution

### If Docker Unavailable

The UI shows "Docker unavailable in current environment" instead of
pretending the demo ran.

---

## Demo 5: View Findings

### Steps

1. Click "Findings" in the sidebar
2. View table of all findings
3. Observe columns: Finding, Severity, Quality, Outcome, Evidence, Run

### Expected

- All findings from all runs
- Color-coded severity
- Evidence tier badges

---

## Demo 6: View Candidate Ranking (GAP-1)

### Steps

1. Click "Candidate Ranking" in the sidebar
2. View table of all candidates
3. Observe how quality rank affects priority

### Expected

- Candidates sorted by priority score
- Clear explanation of GAP-1
- Quality rank directly influences ranking

---

## Demo 7: View Decision Paths

### Steps

1. Click "Decision Paths" in the sidebar
2. Select a completed run
3. View decision trace and execution flow

### Expected

- Color-coded trace events
- Success/fail/pivot indicators
- Execution results per candidate

---

## Demo 8: View Pivot Analysis (GAP-2)

### Steps

1. Click "Pivot Analysis" in the sidebar
2. View runs with pivot events
3. Observe attempt counts and thresholds

### Expected

- Visual pipeline per candidate
- Attempt counts
- Threshold indicators
- Clear GAP-2 explanation

---

## Demo 9: View Run History

### Steps

1. Click "Runs" in the sidebar
2. View table of all persisted runs
3. Click any run to see details

### Expected

- All runs from persistence layer
- Detail modal with full information
- Events timeline

---

## Demo 10: Generate Reports

### Steps

1. Click "Reports" in the sidebar
2. Select a run
3. Click download button (JSON, HTML, Markdown, TXT)

### Expected

- Report downloads successfully
- Contains all run information
- Professional formatting

---

## Demo 11: System Health

### Steps

1. Click "System Health" in the sidebar
2. View component status grid
3. View API endpoints table

### Expected

- Real status for all components
- READY/UNAVAILABLE indicators
- Complete API endpoint list

---

## Demo 12: Configuration

### Steps

1. Click "Configuration" in the sidebar
2. View safety configuration
3. View AI configuration
4. View research core protection status

### Expected

- Target allowlist displayed
- Authorization status
- Ollama and Docker status
- Research core: PROTECTED

---

## Research Integrity Verification

### GAP-1: Assessment Before Ranking

```python
# decision_engine/core/engine.py:initial_state()
if assess_fn:
    assess_candidates(raw_candidates, assess_fn=assess_fn)  # Assess FIRST
cs = rank_candidates(raw_candidates)  # THEN rank
```

### GAP-2: Bounded Pivot

```python
# decision_engine/core/engine.py:_evaluate()
if state["attempt_count"] >= state["max_attempts"]:
    return "pivot"  # Threshold reached → pivot
```

### Evidence Provenance

- SIMULATED: Ground-truth labels
- OBSERVED_LOCAL: Loopback HTTP
- DOCKER_OBSERVED: Docker emulator HTTP
- CONTROLLED_VALIDATION: Live target

---

## Quick Reference

| Action | Path |
|--------|------|
| Start application | `uvicorn services.api:app --reload --port 8000` |
| Open dashboard | http://localhost:8000 |
| New assessment | Sidebar → Assessment → New Assessment |
| View findings | Sidebar → Findings |
| View candidates | Sidebar → Intelligence → Candidate Ranking |
| View pivots | Sidebar → Attack Paths → Pivot Analysis |
| View runs | Sidebar → Run History → Runs |
| Generate reports | Sidebar → Reports |
| System health | Sidebar → System → System Health |

---

_This demo guide covers all UI features. For detailed documentation, see UI_ARCHITECTURE.md and UI_USER_GUIDE.md._
