# UI Implementation Audit

**Date:** 2026-09-21
**Branch:** `prototype-development`
**HEAD:** `cca226d`
**UI Reference:** `docs/UI/AI_VAPT_UI.png`

---

## 1. Current Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INTERFACES                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Streamlit   │  │   FastAPI    │  │     CLI      │              │
│  │  frontend/   │  │  services/   │  │  prototype/  │              │
│  │  app.py      │  │  api.py      │  │  cli.py      │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         └─────────────────┼─────────────────┘                       │
│                           ▼                                         │
│              ┌─────────────────────────┐                            │
│              │    VAPTApplication      │                            │
│              │  vapt_platform/         │                            │
│              │  application.py         │                            │
│              └───────────┬─────────────┘                            │
│                          │                                          │
│  ┌───────────────────────┼───────────────────────┐                  │
│  │                       ▼                       │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │         DECISION ENGINE (FROZEN)        │  │                  │
│  │  │  decision_engine/core/                  │  │                  │
│  │  │  GAP-1: assess → rank → decide         │  │                  │
│  │  │  GAP-2: attempt → count → pivot        │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │      VAPT RESEARCH CORE (FROZEN)        │  │                  │
│  │  │  core/                                  │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │           PLATFORM SERVICES             │  │                  │
│  │  │  vapt_platform/                         │  │                  │
│  │  │  enrichment, normalization, scanners    │  │                  │
│  │  │  authorization, pipeline, persistence  │  │                  │
│  │  │  events, reporting                      │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │         PROTOTYPE LAYER                 │  │                  │
│  │  │  prototype/                             │  │                  │
│  │  │  execution_layer, lab_runner, demo_data │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │         DOCKER LAB                      │  │                  │
│  │  │  lab/                                   │  │                  │
│  │  │  docker-compose.yml, emulator, executor │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  └───────────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Existing Reusable Backend Components

### 2.1 VAPTApplication (Canonical Workflow)

| Component | File | Purpose |
|-----------|------|---------|
| VAPTApplication | `vapt_platform/application.py` | Single canonical workflow |
| VAPTRequest | `vapt_platform/application.py` | Unified request model |
| DomainResult | `vapt_platform/application.py` | Pure domain result |
| PresentationResult | `vapt_platform/application.py` | Presentation-layer result |

### 2.2 Platform Services

| Component | File | Purpose |
|-----------|------|---------|
| Enrichment | `vapt_platform/enrichment.py` | EPSS, CISA KEV intelligence |
| Normalization | `vapt_platform/normalization.py` | Canonical finding model |
| Decision Intelligence | `vapt_platform/decision_intelligence.py` | Transparent scoring |
| Scanners | `vapt_platform/scanners.py` | Nmap, Nuclei adapters |
| Authorization | `vapt_platform/authorization.py` | Target authorization |
| Pipeline | `vapt_platform/pipeline.py` | Validation pipeline |
| Persistence | `vapt_platform/persistence/` | JSON run repository |
| Events | `vapt_platform/events/` | Event bus and publisher |
| Reporting | `vapt_platform/reporting/` | Report builders and renderers |

### 2.3 Decision Engine (FROZEN)

| Component | File | Purpose |
|-----------|------|---------|
| Engine | `decision_engine/core/engine.py` | LangGraph state machine |
| Assessor | `decision_engine/core/assessor.py` | GAP-1 quality assessment |
| Executor | `decision_engine/core/executor.py` | Execution abstraction |
| Schemas | `decision_engine/core/schemas.py` | ActionCandidate, QualityRank, Outcome |

### 2.4 VAPT Research Core (FROZEN)

| Component | File | Purpose |
|-----------|------|---------|
| Agent Graph | `core/agent_graph.py` | VAPT LangGraph implementation |
| Exploit Assessor | `core/exploit_assessor.py` | LLM usability scoring |
| Executor | `core/executor.py` | VAPT execution |
| Schemas | `core/schemas.py` | Finding, ExploitAssessment |

---

## 3. Existing API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/scenarios` | GET | List scenarios |
| `/system/health` | GET | System health |
| `/runs` | POST | Start a run |
| `/runs` | GET | List runs |
| `/runs/{id}` | GET | Get run status |
| `/runs/{id}/persisted` | GET | Get persisted run |
| `/runs/{id}/trace` | GET | Get decision trace |
| `/runs/{id}/events` | GET | Get run events |
| `/runs/{id}/report` | GET | Get report |
| `/runs/{id}/evidence` | GET | Get evidence |
| `/runs/{id}/findings` | GET | Get findings |
| `/runs/{id}/candidates` | GET | Get candidates |
| `/runs/{id}/assessment` | GET | Get assessment |

---

## 4. Existing Frontend

| Component | File | Technology |
|-----------|------|------------|
| Streamlit App | `frontend/app.py` | Streamlit (Python) |
| Tests | `frontend/tests/` | pytest |

**Current State:** Streamlit with custom CSS. Functional but cannot reproduce the professional SOC dashboard reference.

---

## 5. Missing UI Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| Professional dark theme | ⚠️ Partial | Streamlit CSS is limited |
| Left sidebar navigation | ⚠️ Partial | Streamlit sidebar is basic |
| Metric cards | ⚠️ Partial | Streamlit columns are limited |
| Execution pipeline visualization | ❌ Missing | No stepper component |
| Attack path visualization | ❌ Missing | No visual representation |
| Decision trace visualization | ❌ Missing | No flowchart component |
| Pivot analysis visualization | ❌ Missing | No visual representation |
| Real-time progress | ❌ Missing | No WebSocket/polling |
| Responsive layout | ⚠️ Partial | Streamlit is responsive but limited |
| Professional typography | ⚠️ Partial | Streamlit fonts are limited |
| Loading states | ⚠️ Partial | Streamlit spinners only |
| Empty states | ⚠️ Partial | Basic info messages |
| Error states | ⚠️ Partial | Basic error messages |

---

## 6. Recommended Frontend Architecture

### 6.1 Technology Choice

**Recommendation:** Dedicated HTML/CSS/JS frontend

**Rationale:**
- Streamlit cannot reproduce the professional SOC dashboard reference
- The reference requires custom components (stepper, flowchart, cards)
- A dedicated frontend provides full control over visual design
- No build tools needed — vanilla HTML/CSS/JS
- FastAPI serves the frontend as static files

### 6.2 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  index.html                                                  │   │
│  │  ├── Sidebar Navigation                                     │   │
│  │  ├── Top Header (System Status)                             │   │
│  │  └── Main Content Area                                      │   │
│  │      ├── Dashboard (metric cards, active assessment)        │   │
│  │      ├── New Assessment (configuration form)                  │   │
│  │      ├── Active Assessment (pipeline, candidates, trace)    │   │
│  │      ├── Findings (table with details)                      │   │
│  │      ├── Intelligence (CVE lookup, EPSS, KEV)               │   │
│  │      ├── Attack Paths (decision trace, pivot analysis)      │   │
│  │      ├── Run History (persisted runs)                       │   │
│  │      ├── Reports (preview, download)                        │   │
│  │      └── System (health, configuration)                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  app.js (vanilla JavaScript)                                │   │
│  │  ├── API client (fetch)                                     │   │
│  │  ├── Router (hash-based)                                    │   │
│  │  ├── State management (localStorage)                        │   │
│  │  └── Component renderers                                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  styles.css (dark SOC theme)                                │   │
│  │  ├── CSS variables (colors, spacing)                        │   │
│  │  ├── Layout (grid, flexbox)                                 │   │
│  │  ├── Components (cards, badges, tables, stepper)            │   │
│  │  └── Animations (subtle transitions)                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        BACKEND                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  FastAPI (services/api.py)                                  │   │
│  │  ├── Static file serving (frontend/)                        │   │
│  │  ├── API endpoints (/runs, /health, etc.)                   │   │
│  │  └── CORS middleware                                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  VAPTApplication (vapt_platform/application.py)             │   │
│  │  └── Canonical workflow                                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.3 File Structure

```
frontend/
├── index.html          # Main HTML shell
├── css/
│   └── styles.css      # Dark SOC theme
├── js/
│   └── app.js          # Vanilla JS application
├── api/
│   └── client.js       # API client
└── assets/
    └── icons.svg       # SVG icons
```

---

## 7. Exact Integration Points

### 7.1 API Endpoints Used

| Endpoint | Usage |
|----------|-------|
| `GET /health` | System status |
| `GET /system/health` | Detailed health |
| `GET /scenarios` | Scenario list |
| `POST /runs` | Start assessment |
| `GET /runs` | Run history |
| `GET /runs/{id}/persisted` | Run details |
| `GET /runs/{id}/events` | Run events |
| `GET /runs/{id}/trace` | Decision trace |
| `GET /runs/{id}/evidence` | Evidence |
| `GET /runs/{id}/findings` | Findings |
| `GET /runs/{id}/candidates` | Candidates |
| `GET /runs/{id}/assessment` | Assessment |
| `GET /runs/{id}/report` | Report |

### 7.2 Data Flow

```
User Action (UI)
    │
    ▼
API Client (fetch)
    │
    ▼
FastAPI Endpoint
    │
    ▼
VAPTApplication.run()
    │
    ├── Decision Engine (FROZEN)
    ├── Platform Services
    └── Persistence/Events/Reporting
    │
    ▼
JSON Response
    │
    ▼
UI Renderer (DOM manipulation)
    │
    ▼
User Sees Result
```

---

## 8. Research Core Protection

### 8.1 Frozen Files (DO NOT MODIFY)

| File | Reason |
|------|--------|
| `decision_engine/core/schemas.py` | GAP-1/GAP-2 data models |
| `decision_engine/core/assessor.py` | GAP-1 assessment logic |
| `decision_engine/core/executor.py` | Execution abstraction |
| `decision_engine/core/engine.py` | GAP-2 pivot logic |
| `decision_engine/benchmarks/` | Research benchmarks |
| `core/schemas.py` | VAPT research schemas |
| `core/agent_graph.py` | VAPT LangGraph |
| `core/exploit_assessor.py` | LLM assessment |
| `core/executor.py` | VAPT execution |
| `core/report.py` | VAPT reporting |

### 8.2 UI Responsibilities

The UI is PRESENTATION + CONTROL only:
- Display data from API
- Send user input to API
- Navigate between views
- Show loading/empty/error states

The UI does NOT:
- Implement scoring algorithms
- Implement AI assessment
- Implement pivot logic
- Implement safety decisions
- Implement execution logic
- Store data locally (except UI state)

---

## 9. Implementation Plan

### Phase 0: Audit ✅ (this document)

### Phase 1: Preserve Research Core
- Verify no modifications to frozen files
- Document protection boundary

### Phase 2: UI Reference Analysis
- Analyze reference image ✅
- Identify design language ✅

### Phase 3: Frontend Implementation
- Create HTML shell
- Create CSS theme
- Create JS application
- Implement all pages

### Phase 4: API Integration
- Add static file serving to FastAPI
- Add CORS middleware
- Verify all endpoints work

### Phase 5: Testing
- Run full test suite
- Add frontend tests
- Verify integration

### Phase 6: Documentation
- Create UI architecture doc
- Create user guide
- Create demo guide

---

_Audit complete. Proceeding with implementation._
