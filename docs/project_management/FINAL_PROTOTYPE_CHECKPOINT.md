# Final Prototype Checkpoint

**Date:** 2026-09-21
**Branch:** `prototype-development`
**Commit:** 5027262
**Status:** PROTOTYPE COMPLETE

---

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INTERFACES                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Dedicated HTML/CSS/JS Frontend (frontend/web/)             │   │
│  │  ├── index.html (SPA shell)                                 │   │
│  │  ├── css/styles.css (dark SOC theme)                        │   │
│  │  └── js/app.js (vanilla JS, hash routing)                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  FastAPI Backend (services/api.py)                          │   │
│  │  ├── Static file serving (/css, /js, /)                     │   │
│  │  ├── CORS middleware                                        │   │
│  │  └── 16 API endpoints                                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  VAPTApplication (vapt_platform/application.py)             │   │
│  │  └── Canonical workflow                                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Decision Engine (FROZEN)                                   │   │
│  │  └── GAP-1: assess → rank → decide                         │   │
│  │  └── GAP-2: attempt → count → pivot                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Platform Services                                          │   │
│  │  └── enrichment, normalization, scanners, authorization     │   │
│  │  └── pipeline, persistence, events, reporting               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Docker Lab                                                 │   │
│  │  └── emulator (172.28.0.2:8080)                             │   │
│  │  └── executor (localhost:9090)                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Application Flow

```
User (Browser)
 ↓
Frontend (HTML/CSS/JS)
 ↓
FastAPI (/runs, /health, /scenarios, etc.)
 ↓
VAPTApplication.run(VAPTRequest)
 ↓
Finding Ingestion → Normalization → Enrichment
 ↓
Candidate Generation → AI Assessment → Ranking
 ↓
Decision Engine (GAP-1: assess before rank)
 ↓
Planner → SafetyGate → AuthorizationTracker
 ↓
Executor (simulation or Docker)
 ↓
Verifier → Evidence → Persistence → Events
 ↓
Report
 ↓
UI Display
```

---

## UI Pages

| Page | Route | Description |
|------|-------|-------------|
| Dashboard | `#/dashboard` | Metrics, recent runs, system health |
| New Assessment | `#/assessment/new` | Configuration form |
| Active Assessment | `#/assessment/active` | Current run details |
| Findings | `#/findings` | All findings table |
| Intelligence | `#/intelligence` | CVE lookup, EPSS, KEV |
| Candidates | `#/candidates` | Candidate ranking (GAP-1) |
| Attack Paths | `#/attack-paths` | Decision trace visualization |
| Pivot Analysis | `#/pivot-analysis` | Pivot events (GAP-2) |
| Run History | `#/runs` | Persisted runs |
| Reports | `#/reports` | Report generation |
| System Health | `#/system` | Component status |
| Configuration | `#/configuration` | Safety settings |

---

## How to Start

```bash
# Activate environment
source venv/bin/activate

# Start the application
uvicorn services.api:app --reload --port 8000

# Open in browser
http://localhost:8000
```

### Optional: Start Ollama

```bash
ollama serve &
ollama pull llama3.2:3b
```

### Optional: Start Docker Lab

```bash
cd lab
docker-compose up -d
cd ..
```

---

## How to Run Simulation

1. Open http://localhost:8000
2. Click "New Assessment"
3. Select Mode: "Simulation"
4. Select Scenario: "failure_pivot"
5. Select Assessor: "deterministic"
6. Click "Run Assessment"
8. View pipeline, candidates, decision trace, evidence

---

## How to Run AI Assessment

1. Start Ollama: `ollama serve &`
2. Open http://localhost:8000
3. Click "New Assessment"
4. Select Assessor: "ai"
5. Select Provider: "ollama"
6. Click "Run Assessment"
7. View AI quality ranks and assessment

---

## How to Run Docker Lab

1. Start Docker Desktop
2. Run: `cd lab && docker-compose up -d`
3. Open http://localhost:8000
4. Click "New Assessment"
5. Select Mode: "Docker Lab"
6. Select Target: "172.28.0.2"
7. Select Scenario: "docker_pivot"
8. Click "Run Assessment"
9. View DOCKER_OBSERVED evidence

---

## Safety Model

- **Target Allowlist:** 127.0.0.1, 172.28.0.2 only
- **AuthorizationTracker:** All targets must be explicitly authorized
- **SafetyGate:** Validates all actions before execution
- **No Free-Text Target:** UI uses selectbox only
- **Backend Enforcement:** Safety is enforced server-side, not just in UI

---

## GAP-1: AI Assessment Before Ranking

```
Candidate → AI Assessment → Quality Rank → Priority Score → Ranking
```

The priority score is calculated as:
```
priority = probability × (0.5 + 0.5 × quality_weight)
```

Where quality_weight is:
- HIGH: 1.0
- MEDIUM: 0.6
- LOW: 0.3

This ensures AI assessment directly influences execution order.

---

## GAP-2: Bounded Pivot

```
Candidate → Execute → Attempt Count → Threshold Check → Pivot
```

Each candidate has a per-candidate attempt counter:
1. Execute candidate
2. Increment counter
3. If counter >= threshold, pivot to next candidate
4. Reset counter for new candidate

---

## Evidence Tiers

| Tier | Description |
|------|-------------|
| SIMULATED | Ground-truth labels, no real execution |
| OBSERVED_LOCAL | Real HTTP to loopback (127.0.0.1) |
| DOCKER_OBSERVED | Real HTTP to isolated Docker emulator |
| CONTROLLED_VALIDATION | Real execution against live targets |

---

## Reports

| Format | Description |
|--------|-------------|
| JSON | Machine-readable report |
| HTML | Web-viewable report |
| Markdown | Documentation-friendly |
| TXT | Plain text |

---

## Known Limitations

1. **Browser testing** — Validated via Chrome headless --dump-dom (all 12 pages render correctly, no JS errors)
2. **Docker runtime** — Verified working (emulator + executor containers running)
3. **Ollama** — Verified working (llama3.2:3b, AI assessment path tested)
4. **Real-time updates** — No WebSocket/polling (page refresh required)
5. **CVE lookup** — Uses local datasets only (no live API)
6. **CVSS and CWE data** — Not available in local datasets (returns None/[])
7. **Cross-platform compatibility** — Not verified
8. **Performance under load** — Not tested

---

## Mentor Demonstration Sequence

```
START
 ↓
Dashboard (http://localhost:8000)
 ↓
New Assessment
 ↓
Select Scenario: failure_pivot
 ↓
Select Mode: Simulation
 ↓
Select Assessor: ai (Ollama)
 ↓
Click "Run Assessment"
 ↓
Pipeline Visualization
 ↓
AI Assessment Panel
 ↓
Candidate Ranking
 ↓
Decision Trace
 ↓
Pivot Analysis
 ↓
Evidence Panel
 ↓
Findings Page
 ↓
Run History
 ↓
Select Run → View Details
 ↓
Reports → Download
 ↓
Research Explanation:
  GAP-1: AI assessment BEFORE ranking
  GAP-2: Bounded per-candidate attempts and pivot
```

---

## Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| `tests/` (root) | 315 | ✅ Passing |
| `decision_engine/tests/` | 16 | ✅ Passing |
| `prototype/tests/` | 36 | ✅ Passing |
| `services/tests/` | 17 | ✅ Passing |
| `frontend/tests/` | 7 | ✅ Passing |
| **Total** | **554** | **✅ Passing** |

---

## Research Integrity

| Check | Status |
|-------|--------|
| `decision_engine/core/` unchanged | ✅ Verified |
| `decision_engine/benchmarks/` unchanged | ✅ Verified |
| GAP-1 intact | ✅ Verified |
| GAP-2 intact | ✅ Verified |
| No duplicate workflows | ✅ Verified |
| UI is presentation-only | ✅ Verified |

---

_This document represents the final prototype checkpoint. The application is ready for mentor demonstration._
