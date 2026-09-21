# Mentor Demo Guide

**Date:** 2026-09-21
**Branch:** `prototype-development`
**Status:** READY FOR DEMONSTRATION

---

## Overview

This guide provides the exact click-by-click sequence for demonstrating
the AI-VAPT Operations Console to mentors and evaluators.

---

## Prerequisites

```bash
# Activate environment
source venv/bin/activate

# Start the application
uvicorn services.api:app --reload --port 8000

# Optional: Start Ollama for AI assessment
ollama serve &

# Optional: Start Docker lab
cd lab && docker-compose up -d && cd ..
```

Open: http://localhost:8000

---

## Exact Click-by-Click Demo Sequence

### Step 1: Dashboard

1. Open http://localhost:8000
2. Observe:
   - Top header: "AI-VAPT" + "SYSTEM OPERATIONAL"
   - Left sidebar: 12 navigation items
   - Metric cards: Total Runs, Successful, Pivots, CRIT Findings
   - Recent Runs table
   - System Health panel

### Step 2: New Assessment

1. Click "New Assessment" in sidebar
2. Observe:
   - Execution Mode dropdown
   - Scenario dropdown
   - Assessor Mode dropdown
   - Pivot Threshold slider
   - Safety Status section

### Step 3: Configure Simulation

1. Select Execution Mode: "Simulation"
2. Select Scenario: "failure_pivot"
3. Select Assessor: "deterministic"
4. Set Pivot Threshold: 2
5. Verify Safety Status shows "SIMULATION"

### Step 4: Run Assessment

1. Click "Run Assessment" button
2. Observe:
   - Loading state
   - Pipeline stepper appears
   - Candidates table populates
   - Assessment panel shows "deterministic"
   - Decision trace shows events
   - Evidence tier shows "SIMULATED"

### Step 5: View Results

1. Observe pipeline: Ingest → Enrich → Assess → Rank → Decide → Safety → Execute → Verify → Evidence → Report
2. Observe candidates:
   - DEMO-WORKER: Quality HIGH, Outcome SUCCESS
   - DEMO-DEAD-END: Quality LOW, Outcome FAIL_TIMEOUT
3. Observe decision trace:
   - Attempt 1 → SUCCESS on DEMO-WORKER
   - Pivot to DEMO-DEAD-END
   - Attempt 1/2 → FAIL_TIMEOUT
   - Attempt 2/2 → FAIL_TIMEOUT
   - Threshold reached → PIVOT

### Step 6: View Findings

1. Click "Findings" in sidebar
2. Observe table with all findings
3. Columns: Finding, Severity, Quality, Outcome, Evidence, Run

### Step 7: View Candidate Ranking (GAP-1)

1. Click "Candidate Ranking" in sidebar
2. Observe table with candidates
3. Note: Quality rank affects priority score
4. Explanation: "Assessment → Candidate scoring → Priority"

### Step 8: View Decision Paths

1. Click "Decision Paths" in sidebar
2. Select a completed run
3. Observe decision trace and execution flow

### Step 9: View Pivot Analysis (GAP-2)

1. Click "Pivot Analysis" in sidebar
2. Observe pivot events
3. Note: Attempt counts, thresholds, pivot events
4. Explanation: "Per-candidate attempt counter → Threshold → Pivot"

### Step 10: View Run History

1. Click "Runs" in sidebar
2. Observe table of persisted runs
3. Click any run to view details
4. Observe: metadata, candidates, events

### Step 11: Generate Reports

1. Click "Reports" in sidebar
2. Select a run
3. Click download buttons: JSON, HTML, Markdown, TXT
4. Verify files download successfully

### Step 12: View Intelligence

1. Click "Vulnerability Intelligence" in sidebar
2. Enter CVE ID: CVE-2021-44228
3. Click "Lookup"
4. Observe: EPSS, KEV, CVSS, CWE data

### Step 13: View System Health

1. Click "System Health" in sidebar
2. Observe component statuses
3. Note: Application, API, Persistence, Research Core, Safety, Ollama, Docker

### Step 14: View Configuration

1. Click "Configuration" in sidebar
2. Observe safety configuration
3. Note: Target allowlist, authorization status

---

## Research Contribution Explanation

### GAP-1: AI Assessment Before Ranking

```
Candidate → AI Assessment → Quality Rank → Priority Score → Ranking
```

The UI shows:
- Assessment panel with quality rank (HIGH/MEDIUM/LOW)
- Candidate ranking table with priority scores
- Clear explanation: "Assessment → Candidate scoring → Priority"

### GAP-2: Bounded Pivot

```
Candidate → Execute → Attempt Count → Threshold Check → Pivot
```

The UI shows:
- Pivot Analysis page with attempt counts
- Threshold indicators
- Visual pipeline showing failure → threshold → pivot

---

## Evidence Tiers

| Tier | Description | UI Display |
|------|-------------|------------|
| SIMULATED | Ground-truth labels | Yellow badge |
| OBSERVED_LOCAL | Loopback HTTP | Blue badge |
| DOCKER_OBSERVED | Docker emulator | Green badge |
| CONTROLLED_VALIDATION | Live target | Purple badge |

---

## Safety Model

- **Target Allowlist:** 127.0.0.1, 172.28.0.2 only
- **AuthorizationTracker:** All targets must be authorized
- **SafetyGate:** Validates all actions before execution
- **UI:** No free-text target input (selectbox only)
- **Status:** "AUTHORIZED / ALLOWLISTED" or "SIMULATION" displayed before execution

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
| Reset demo | `./scripts/reset_demo.sh` |

---

## Expected Results

### Simulation (failure_pivot)

- DEMO-WORKER: SUCCESS (attempt 1)
- DEMO-DEAD-END: FAIL_TIMEOUT (attempts 1-2) → PIVOT
- Evidence: SIMULATED

### AI Assessment (Ollama)

- Quality ranks from LLM
- Assessment mode: ai, provider: ollama
- Evidence: SIMULATED

### Docker Lab (docker_pivot)

- docker-vuln-success: SUCCESS
- docker-fail-pivot: FAIL_TIMEOUT → PIVOT
- Evidence: DOCKER_OBSERVED

---

_This guide provides the exact sequence for a successful mentor demonstration._
