# UI Architecture

**Date:** 2026-09-21
**Branch:** `prototype-development`
**Status:** COMPLETE

---

## Overview

The AI-VAPT frontend is a dedicated single-page application (SPA) built with
vanilla HTML, CSS, and JavaScript. It communicates with the FastAPI backend
via REST API calls and renders a professional security operations dashboard.

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Markup | HTML5 | Semantic, accessible |
| Styling | CSS3 (custom properties) | Full control over dark theme |
| Logic | Vanilla JavaScript (ES6+) | No build tools, no dependencies |
| Routing | Hash-based SPA router | Simple, no server config |
| API | Fetch API | Native browser support |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (SPA)                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  index.html                                                 │   │
│  │  ├── Top Header (brand, system status)                     │   │
│  │  ├── Sidebar Navigation (12 pages)                         │   │
│  │  └── Content Area (dynamic)                                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  styles.css                                                 │   │
│  │  ├── CSS Variables (colors, spacing, typography)           │   │
│  │  ├── Layout (flexbox, grid)                                │   │
│  │  ├── Components (cards, badges, tables, stepper)           │   │
│  │  └── Responsive (mobile, tablet, desktop)                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  app.js                                                     │   │
│  │  ├── API Client (fetch wrapper)                            │   │
│  │  ├── State Management (local state)                        │   │
│  │  ├── Router (hash-based)                                   │   │
│  │  ├── Utility Functions (formatting, escaping)              │   │
│  │  └── Page Renderers (12 pages)                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        BACKEND                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  FastAPI (services/api.py)                                  │   │
│  │  ├── Static file serving (/css, /js, /)                     │   │
│  │  ├── CORS middleware                                        │   │
│  │  └── API endpoints (15 endpoints)                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  VAPTApplication (vapt_platform/application.py)             │   │
│  │  └── Canonical workflow                                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
frontend/web/
├── index.html          # Main HTML shell
├── css/
│   └── styles.css      # Dark SOC theme
└── js/
    └── app.js          # Vanilla JS application
```

---

## Page Structure

### Navigation

| Section | Page | Route | Description |
|---------|------|-------|-------------|
| Overview | Dashboard | `#/dashboard` | Metrics, recent runs, system health |
| Assessment | New Assessment | `#/assessment/new` | Configuration form |
| Assessment | Active Assessment | `#/assessment/active` | Current run details |
| Findings | Findings | `#/findings` | All findings table |
| Intelligence | Vulnerability Intelligence | `#/intelligence` | CVE lookup, EPSS, KEV |
| Intelligence | Candidate Ranking | `#/candidates` | GAP-1 ranking visualization |
| Attack Paths | Decision Paths | `#/attack-paths` | Decision trace visualization |
| Attack Paths | Pivot Analysis | `#/pivot-analysis` | GAP-2 pivot visualization |
| Run History | Runs | `#/runs` | Persisted run history |
| Reports | Reports | `#/reports` | Report generation |
| System | System Health | `#/system` | Component status |
| System | Configuration | `#/configuration` | Safety settings |

### Dashboard

- **Metric Cards:** Total Runs, Successful, Pivots, CRIT Findings
- **Recent Runs:** Table of last 10 runs
- **System Health:** Application, Persistence, Ollama, Docker status

### New Assessment

- **Execution Mode:** Simulation or Docker Lab
- **Target:** Allowlisted targets only (127.0.0.1, 172.28.0.2)
- **Scenario:** Dropdown from API
- **Assessor:** Deterministic or AI
- **Pivot Threshold:** 1-10 attempts
- **Safety Status:** Shows AUTHORIZED/ALLOWLISTED before execution

### Active Assessment

- **Run Details:** Scenario, mode, target, status
- **Pipeline Stepper:** Visual progress through 10 stages
- **Candidates:** Quality rank, outcome
- **Assessment:** Mode, provider, fallback status

### Findings

- **Table:** All findings across all runs
- **Columns:** Finding, Severity, Quality, Outcome, Evidence, Run

### Intelligence

- **CVE Lookup:** Enter CVE ID, get EPSS and KEV status
- **Evidence Provenance:** Explains observed fact vs enriched intelligence vs AI assessment vs decision

### Candidates

- **Ranking Table:** All candidates with probability, quality, score, priority, outcome
- **GAP-1 Explanation:** How assessment affects ranking

### Attack Paths

- **Run Selection:** Dropdown of completed runs
- **Decision Trace:** Color-coded trace events
- **Execution Flow:** Candidates and execution results

### Pivot Analysis

- **Pivot Events:** Runs with pivot events
- **Visual Pipeline:** Attempts per candidate with success/fail indicators
- **GAP-2 Explanation:** How failure counters trigger pivots

### Run History

- **Table:** All persisted runs
- **Detail Modal:** Click any run to see full details
- **Columns:** Run ID, Date, Scenario, Mode, Status, Target, Attempts, Pivots, Evidence

### Reports

- **Table:** All runs with download buttons
- **Formats:** JSON, HTML, Markdown, TXT

### System Health

- **Component Grid:** 11 components with real status
- **API Endpoints:** Table of all available endpoints

### Configuration

- **Safety Configuration:** Target allowlist, authorization status
- **AI Configuration:** Ollama and Docker status
- **Research Core:** Protection status

---

## State Management

The frontend uses a simple global state object:

```javascript
const state = {
    currentRun: null,      // Current active run ID
    runs: [],              // Cached run list
    systemHealth: null,    // System health status
    scenarios: [],         // Available scenarios
    loading: false,        // Loading state
};
```

State is updated after API calls and used to render views.

---

## API Integration

All data comes from the FastAPI backend:

| Endpoint | Usage |
|----------|-------|
| `GET /` | Serve index.html |
| `GET /css/styles.css` | Serve CSS |
| `GET /js/app.js` | Serve JS |
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

---

## Design System

### Colors

| Variable | Value | Usage |
|----------|-------|-------|
| `--bg-primary` | `#0f172a` | Main background |
| `--bg-secondary` | `#1e293b` | Card background |
| `--bg-tertiary` | `#334155` | Table headers |
| `--text-primary` | `#f8fafc` | Primary text |
| `--text-secondary` | `#cbd5e1` | Secondary text |
| `--text-muted` | `#94a3b8` | Muted text |
| `--accent-blue` | `#3b82f6` | Primary accent |
| `--accent-green` | `#22c55e` | Success |
| `--accent-red` | `#ef4444` | Error/Critical |
| `--accent-amber` | `#f59e0b` | Warning |
| `--accent-purple` | `#a855f7` | Pivot |
| `--accent-cyan` | `#06b6d4` | Info |

### Typography

| Element | Size | Weight |
|---------|------|--------|
| Brand name | 1.3rem | 700 |
| Page title | 1.5rem | 700 |
| Card title | 1rem | 700 |
| Metric value | 2rem | 700 |
| Body text | 0.85rem | 400 |
| Label | 0.7rem | 600 |
| Badge | 0.7rem | 600 |

### Spacing

| Variable | Value |
|----------|-------|
| `--space-xs` | 0.25rem |
| `--space-sm` | 0.5rem |
| `--space-md` | 1rem |
| `--space-lg` | 1.5rem |
| `--space-xl` | 2rem |

---

## Responsive Design

| Breakpoint | Layout |
|------------|--------|
| > 1200px | Full grid (4 columns) |
| 768-1200px | 2-column grid |
| < 768px | Single column, collapsed sidebar |

---

## Security

- No business logic in frontend
- All execution through VAPTApplication
- Target allowlist enforced by backend
- Authorization tracked by backend
- Evidence provenance from backend
- No hardcoded metrics or fake data

---

_This architecture separates presentation (frontend) from business logic (backend)._
