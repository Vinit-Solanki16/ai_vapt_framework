# Current Architecture

**Date:** 2026-09-21
**Branch:** `prototype-development`
**HEAD:** `359eac5`

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INTERFACES                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Streamlit   │  │   FastAPI    │  │     CLI      │              │
│  │  frontend/   │  │  services/   │  │  prototype/  │              │
│  │  app.py      │  │  api.py      │  │  cli.py      │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                 │                       │
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
│  │  │  engine.py, assessor.py, executor.py   │  │                  │
│  │  │  schemas.py                            │  │                  │
│  │  │  GAP-1: assess → rank → decide         │  │                  │
│  │  │  GAP-2: attempt → count → pivot        │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │      VAPT RESEARCH CORE (FROZEN)        │  │                  │
│  │  │  core/                                  │  │                  │
│  │  │  agent_graph.py, exploit_assessor.py    │  │                  │
│  │  │  executor.py, schemas.py, report.py     │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │           PLATFORM SERVICES             │  │                  │
│  │  │  vapt_platform/                         │  │                  │
│  │  │  enrichment.py, normalization.py       │  │                  │
│  │  │  decision_intelligence.py, scanners.py  │  │                  │
│  │  │  authorization.py, pipeline.py          │  │                  │
│  │  │  persistence/, events/, reporting/      │  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │         PROTOTYPE LAYER                 │  │                  │
│  │  │  prototype/                             │  │                  │
│  │  │  execution_layer.py, lab_runner.py      │  │                  │
│  │  │  demo_data.py, docker_demo_data.py      │  │                  │
│  │  │  engine_integration.py, report_generator│  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  │  ┌─────────────────────────────────────────┐  │                  │
│  │  │         DOCKER LAB                      │  │                  │
│  │  │  lab/                                   │  │                  │
│  │  │  docker-compose.yml, emulator/, executor│  │                  │
│  │  └─────────────────────────────────────────┘  │                  │
│  │                                               │                  │
│  └───────────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Interfaces

| Component | File | Purpose |
|-----------|------|---------|
| Streamlit GUI | `frontend/app.py` | Professional SOC-style dashboard |
| FastAPI | `services/api.py` | REST API for programmatic access |
| CLI | `prototype/cli.py` | Command-line interface |

All interfaces use the canonical `VAPTApplication.run()` workflow.

### 2. Application Layer

| Component | File | Purpose |
|-----------|------|---------|
| VAPTApplication | `vapt_platform/application.py` | Single canonical workflow |
| VAPTRequest | `vapt_platform/application.py` | Unified request model |
| DomainResult | `vapt_platform/application.py` | Pure domain result |

### 3. Decision Engine (FROZEN)

| Component | File | Purpose |
|-----------|------|---------|
| Engine | `decision_engine/core/engine.py` | LangGraph state machine |
| Assessor | `decision_engine/core/assessor.py` | GAP-1 quality assessment |
| Executor | `decision_engine/core/executor.py` | Execution abstraction |
| Schemas | `decision_engine/core/schemas.py` | ActionCandidate, QualityRank, Outcome |

### 4. VAPT Research Core (FROZEN)

| Component | File | Purpose |
|-----------|------|---------|
| Agent Graph | `core/agent_graph.py` | VAPT LangGraph implementation |
| Exploit Assessor | `core/exploit_assessor.py` | LLM usability scoring |
| Executor | `core/executor.py` | VAPT execution |
| Schemas | `core/schemas.py` | Finding, ExploitAssessment |

### 5. Platform Services

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

### 6. Prototype Layer

| Component | File | Purpose |
|-----------|------|---------|
| Execution Layer | `prototype/execution_layer.py` | Simulation/Docker executors |
| Lab Runner | `prototype/lab_runner.py` | Docker lab HTTP client |
| Demo Data | `prototype/demo_data.py` | Simulation scenarios |
| Docker Demo Data | `prototype/docker_demo_data.py` | Docker lab scenarios |
| Engine Integration | `prototype/engine_integration.py` | Engine wrapper |

### 7. Docker Lab

| Component | File | Purpose |
|-----------|------|---------|
| Compose | `lab/docker-compose.yml` | Container orchestration |
| Emulator | `lab/emulator/app.py` | Vulnerability emulator |
| Executor | `lab/executor_server.py` | HTTP execution API |

---

## Data Flow

```
User Request (GUI/API/CLI)
    │
    ▼
VAPTApplication.run(VAPTRequest)
    │
    ├── 1. Load candidates (scenario or scan file)
    ├── 2. Enrich with vulnerability intelligence (EPSS, KEV)
    ├── 3. Build asset/vulnerability graph
    ├── 4. Score candidates (decision intelligence)
    ├── 5. Build executor (simulation or lab)
    ├── 6. Run validation pipeline (safety gate)
    ├── 7. Run decision engine (GAP-1 + GAP-2)
    │       ├── Assess candidates (quality rank)
    │       ├── Rank candidates (priority score)
    │       ├── Execute candidate
    │       ├── Count attempts
    │       ├── Check threshold
    │       └── Pivot if needed
    ├── 8. Verify results
    ├── 9. Generate report
    ├── 10. Persist run
    └── 11. Emit events
```

---

## Research Core Protection

### Frozen Files

| File | Reason |
|------|--------|
| `decision_engine/core/schemas.py` | GAP-1/GAP-2 data models |
| `decision_engine/core/assessor.py` | GAP-1 assessment logic |
| `decision_engine/core/executor.py` | Execution abstraction |
| `decision_engine/core/engine.py` | GAP-2 pivot logic |
| `core/schemas.py` | VAPT research schemas |
| `core/agent_graph.py` | VAPT LangGraph |
| `core/exploit_assessor.py` | LLM assessment |
| `core/executor.py` | VAPT execution |
| `core/report.py` | VAPT reporting |

### GAP-1 Verification

```python
# decision_engine/core/engine.py:initial_state()
if assess_fn:
    assess_candidates(raw_candidates, assess_fn=assess_fn)  # Assess FIRST
cs = rank_candidates(raw_candidates)  # THEN rank
```

### GAP-2 Verification

```python
# decision_engine/core/engine.py:_evaluate()
if state["attempt_count"] >= state["max_attempts"]:
    return "pivot"  # Threshold reached → pivot
```

---

## Evidence Tiers

| Tier | Description | Source |
|------|-------------|--------|
| SIMULATED | Ground-truth labels | `labels.json` |
| OBSERVED_LOCAL | Loopback (127.0.0.1) | Real HTTP |
| DOCKER_OBSERVED | Docker emulator | Real HTTP to isolated container |
| CONTROLLED_VALIDATION | Live target | Real execution |

---

## Safety Controls

1. **Target allowlist:** Only `127.0.0.1` and `172.28.0.2` are permitted
2. **Fail-closed validation:** Non-allowlisted targets are rejected
3. **Authorization tracking:** All targets must be explicitly authorized
4. **Scope enforcement:** Ports and protocols are validated
5. **Evidence provenance:** All results track their source

---

## API Endpoints

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

## Test Coverage

| Suite | Tests | Status |
|-------|-------|--------|
| `tests/` | 315 | ✅ Passing |
| `decision_engine/tests/` | 16 | ✅ Passing |
| `prototype/tests/` | 36 | ✅ Passing |
| `services/tests/` | 10 | ✅ Passing |
| `frontend/tests/` | 7 | ✅ Passing |
| **Total** | **545** | **✅ Passing** |

---

_This architecture is the source of truth. All documentation matches implementation._
