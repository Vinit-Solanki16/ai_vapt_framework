# UI User Guide

**Date:** 2026-09-21
**Branch:** `prototype-development`

---

## Getting Started

### Starting the Application

```bash
# Activate environment
source venv/bin/activate

# Start the API server (serves both API and frontend)
uvicorn services.api:app --reload --port 8000
```

Then open: http://localhost:8000

### Starting Ollama (Optional)

For AI-powered assessment:

```bash
ollama serve &
ollama pull llama3.2:3b
```

Without Ollama, the system uses deterministic fallback automatically.

---

## Navigation

The left sidebar provides access to all pages:

### Overview
- **Dashboard:** System overview with metrics and recent runs

### Assessment
- **New Assessment:** Configure and start a new assessment
- **Active Assessment:** View the current/active assessment

### Findings
- **Findings:** Browse all findings across runs

### Intelligence
- **Vulnerability Intelligence:** CVE lookup and evidence provenance
- **Candidate Ranking:** How AI assessment affects prioritization (GAP-1)

### Attack Paths
- **Decision Paths:** Visualize decision traces
- **Pivot Analysis:** How failure counters trigger pivots (GAP-2)

### Run History
- **Runs:** Browse persisted run history

### Reports
- **Reports:** Generate and download reports

### System
- **System Health:** Component status and API endpoints
- **Configuration:** Safety settings and allowlist

---

## Running an Assessment

### Step 1: Navigate to New Assessment

Click "New Assessment" in the sidebar.

### Step 2: Configure the Assessment

1. **Execution Mode:**
   - Simulation: Offline, uses ground-truth labels
   - Docker Lab: Real HTTP to isolated emulator

2. **Target (Docker Lab only):**
   - Select from allowlisted targets (127.0.0.1, 172.28.0.2)
   - No free-text input — safety is enforced

3. **Scenario:**
   - Select from available scenarios
   - failure_pivot, success, multi_candidate, docker_pivot, etc.

4. **Assessor Mode:**
   - Deterministic: Offline, reproducible
   - AI / Ollama: LLM-based quality scoring

5. **Pivot Threshold:**
   - Number of attempts before pivot (1-10)

### Step 3: Verify Safety Status

The safety status shows:
- **AUTHORIZED / ALLOWLISTED** for Docker Lab targets
- **SIMULATION** for simulation mode

### Step 4: Run

Click "Run Assessment" and wait for results.

### Step 5: View Results

The results show:
- Run ID, scenario, mode, status
- Pipeline progress (Ingest → Enrich → Assess → Rank → Decide → Safety → Execute → Verify → Evidence → Report)
- Candidates with quality ranks and outcomes
- Assessment mode and provider

---

## Understanding the Dashboard

### Metric Cards

| Card | Description |
|------|-------------|
| Total Runs | Number of all runs in the system |
| Successful | Runs that completed successfully |
| Pivots | Total pivot events across all runs |
| CRIT Findings | Critical severity findings |

### Recent Runs

Shows the last 10 runs with:
- Run ID, scenario, mode, status
- Evidence tier, attempts, pivots
- Timestamp

### System Health

Shows real status for:
- Application, Persistence, Ollama, Docker Lab

---

## Understanding Findings

### Findings Table

Shows all findings across all runs:
- **Finding:** Candidate ID
- **Severity:** Critical, High, Medium, Low
- **Quality:** AI-assessed quality rank
- **Outcome:** SUCCESS or failure
- **Evidence:** Evidence tier (SIMULATED, DOCKER_OBSERVED, etc.)
- **Run:** Link to source run

### Evidence Tiers

| Tier | Description |
|------|-------------|
| SIMULATED | Ground-truth labels, no real execution |
| OBSERVED_LOCAL | Real HTTP to loopback (127.0.0.1) |
| DOCKER_OBSERVED | Real HTTP to isolated Docker emulator |
| CONTROLLED_VALIDATION | Real execution against live targets |

---

## Understanding AI Assessment

### Assessment Modes

| Mode | Description |
|------|-------------|
| Deterministic | Offline, reproducible scoring |
| AI / Ollama | LLM-based usability scoring |

### Quality Ranks

| Rank | Description |
|------|-------------|
| HIGH | High-quality exploit, likely to succeed |
| MEDIUM | Moderate quality, may succeed |
| LOW | Low quality, unlikely to succeed |

### Fallback Behavior

If Ollama is unavailable:
- System automatically uses deterministic fallback
- Clearly marked as "Fallback active"
- Never displayed as AI assessment

---

## Understanding Candidate Ranking

### GAP-1: Assessment Before Ranking

The priority score is calculated as:

```
priority = probability × (0.5 + 0.5 × quality_weight)
```

Where quality_weight is:
- HIGH: 1.0
- MEDIUM: 0.6
- LOW: 0.3

This ensures AI assessment directly influences execution order.

### Example

| Candidate | Probability | Quality | Score | Priority |
|-----------|-------------|---------|-------|----------|
| CVE-A | 0.95 | HIGH | 0.95 | #1 |
| CVE-B | 0.70 | LOW | 0.35 | #2 |

Despite CVE-B having probability 0.70, CVE-A is ranked first because
its HIGH quality gives it a higher priority score.

---

## Understanding Pivot Analysis

### GAP-2: Bounded Pivot

Each candidate has a per-candidate attempt counter:
1. Execute candidate
2. Increment counter
3. If counter >= threshold, pivot to next candidate
4. Reset counter for new candidate

### Example

```
Candidate A (threshold=2)
  Attempt 1 → FAIL
  Attempt 2 → FAIL
  THRESHOLD REACHED
       ↓
     PIVOT
       ↓
Candidate B
  Attempt 1 → SUCCESS
       ↓
    ADVANCE
```

---

## Run History

### Browsing Runs

1. Click "Runs" in the sidebar
2. View table of all persisted runs
3. Click any run to see details

### Run Details

The detail modal shows:
- Run metadata (scenario, mode, status)
- Candidates with quality and outcome
- Events timeline
- Link to reports

---

## Reports

### Generating Reports

1. Click "Reports" in the sidebar
2. Select a run
3. Click download button for desired format

### Report Formats

| Format | Description |
|--------|-------------|
| JSON | Machine-readable report |
| HTML | Web-viewable report |
| Markdown | Documentation-friendly |
| TXT | Plain text |

### Report Contents

- Executive summary
- Scope and target
- Findings
- Vulnerability intelligence
- AI assessment
- Candidate ranking
- Decision trace
- Execution results
- Pivot events
- Evidence provenance
- Safety controls
- Limitations

---

## System Health

### Component Status

| Component | Status |
|-----------|--------|
| Application | READY |
| API | READY |
| Persistence | READY |
| Research Core | PROTECTED |
| Safety Gate | READY |
| Authorization | READY |
| Event System | READY |
| Reporting | READY |
| Scanner Registry | READY |
| Ollama | READY / UNAVAILABLE |
| Docker | READY / UNAVAILABLE |

### API Endpoints

The System Health page lists all available API endpoints with methods
and descriptions.

---

## Configuration

### Safety Configuration

- **Target Allowlist:** 127.0.0.1, 172.28.0.2
- **Authorization:** AuthorizationTracker active
- **Scope Enforcement:** Ports and protocols validated

### AI Configuration

- **Ollama Status:** Shows current status
- **Docker Status:** Shows current status

### Research Core

- **Status:** PROTECTED
- **Verification:** GAP-1 and GAP-2 verified intact

---

## Troubleshooting

### API Offline

If the header shows "API OFFLINE":
1. Check if the API server is running: `uvicorn services.api:app --reload`
2. Check the terminal for errors
3. Verify port 8000 is not in use

### Ollama Unavailable

If Ollama shows "UNAVAILABLE":
1. Check if Ollama is running: `ollama serve`
2. Check if model is pulled: `ollama list`
3. The system will use deterministic fallback automatically

### Docker Unavailable

If Docker shows "UNAVAILABLE":
1. Check if Docker Desktop is running
2. The system will show "Docker unavailable" instead of pretending

### No Data

If tables are empty:
1. Run an assessment first
2. Check the API connection
3. Verify persistence directory exists

---

_This guide covers all UI features. For API documentation, see the System Health page._
