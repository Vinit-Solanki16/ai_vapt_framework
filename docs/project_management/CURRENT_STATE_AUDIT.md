# Current State Audit — AI VAPT Framework

**Date:** 2026-09-21
**Branch:** `prototype-development`
**HEAD:** `359eac5`
**Auditor:** Lead Engineer (automated)

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

## 2. Working Features

| Feature | Location | Status | Evidence |
|---------|----------|--------|----------|
| Decision engine (GAP-1, GAP-2) | `decision_engine/core/engine.py` | ✅ Working | 545 tests collected |
| LangGraph orchestration | `decision_engine/core/engine.py` | ✅ Working | `build_graph()`, `run_engine()` |
| Simulation executor | `prototype/execution_layer.py` | ✅ Working | `create_simulation_executor()` |
| Loopback executor (127.0.0.1) | `prototype/execution_layer.py` | ✅ Working | `create_lab_executor()` |
| Docker lab executor (172.28.0.2) | `prototype/execution_layer.py` | ✅ Code complete | `create_docker_lab_executor()` |
| Vulnerability enrichment (EPSS, KEV) | `vapt_platform/enrichment.py` | ✅ Working | Local dataset provider |
| Candidate ranking | `vapt_platform/decision_intelligence.py` | ✅ Working | Transparent scoring |
| Safety allowlist | `prototype/lab_runner.py` | ✅ Working | `LAB_TARGET_ALLOWLIST` |
| Authorization tracker | `vapt_platform/authorization.py` | ✅ Working | `AuthorizationTracker` |
| Validation pipeline | `vapt_platform/pipeline.py` | ✅ Working | `ValidationPipeline` |
| Persistence (JSON) | `vapt_platform/persistence/` | ✅ Working | `JSONRunRepository` |
| Event system | `vapt_platform/events/` | ✅ Working | `EventBus`, `EventPublisher` |
| Reporting (JSON/TXT/HTML/MD) | `vapt_platform/reporting/` | ✅ Working | Multiple renderers |
| Streamlit GUI | `frontend/app.py` | ✅ Working | Basic dashboard |
| FastAPI backend | `services/api.py` | ✅ Working | REST endpoints |
| CLI | `prototype/cli.py` | ✅ Working | run/history/show/report |
| Scanner adapters | `vapt_platform/scanners.py` | ✅ Working | Nmap XML/JSON, custom, Nuclei |
| Checkpoint/resume | `prototype/checkpoints.py` | ✅ Working | Save/load state |
| Ollama integration | `core/exploit_assessor.py` | ✅ Working | `get_llm(provider="ollama")` |
| Deterministic fallback | `decision_engine/core/assessor.py` | ✅ Working | `deterministic_assessor()` |

---

## 3. Partially Working Features

| Feature | Location | Status | Notes |
|---------|----------|--------|-------|
| Docker lab execution | `lab/` | ⚠️ Code complete, not runtime-verified | Docker daemon not available in this WSL environment |
| Ollama live assessment | `core/exploit_assessor.py` | ⚠️ Installed, not integration-tested | `llama3.2:3b` available |
| PDF reports | `vapt_platform/reporting/` | ⚠️ Not implemented | Only JSON/TXT/HTML/MD |
| GUI visualization | `frontend/app.py` | ⚠️ Basic | Needs professional redesign |
| Live progress display | `frontend/app.py` | ⚠️ Not implemented | No real-time pipeline progress |
| Attack path visualization | `frontend/app.py` | ⚠️ Not implemented | No visual attack path |
| System health page | `frontend/app.py` | ⚠️ Not implemented | No health monitoring UI |
| Findings intelligence page | `frontend/app.py` | ⚠️ Not implemented | No dedicated intelligence view |
| Run history filters | `frontend/app.py` | ⚠️ Basic | No filtering by status/date/evidence |

---

## 4. Broken Features

| Feature | Location | Status | Notes |
|---------|----------|--------|-------|
| None identified | — | — | All code paths have tests |

---

## 5. Missing Features

| Feature | Priority | Notes |
|---------|----------|-------|
| Professional UI redesign | **P0** | Current UI is basic Streamlit |
| Dashboard with metrics | **P0** | No system overview |
| Live assessment progress | **P0** | No real-time pipeline state |
| Attack path visualization | **P1** | No visual representation |
| Findings intelligence page | **P1** | No dedicated intelligence view |
| System health page | **P1** | No health monitoring |
| PDF report generation | **P2** | Only JSON/TXT/HTML/MD |
| Run history filters | **P2** | No filtering capabilities |
| API endpoints for findings/intelligence | **P2** | Partial API coverage |
| Docker runtime verification | **P0** | Docker not available |

---

## 6. Stale Documentation

| Document | Status | Notes |
|----------|--------|-------|
| `docs/project_management/PROTOTYPE_STATUS.md` | ⚠️ Stale | Claims 195 tests, current is 545 |
| `docs/project_management/01_PROJECT_STATE.md` | ⚠️ Stale | Last updated 2026-08-24 |
| `docs/project_management/07_TEST_STATUS.md` | ⚠️ Stale | Last updated 2026-08-24 |
| `README.md` | ⚠️ Partial | Missing recent features |
| `docs/project_management/MASTER_IMPLEMENTATION_PLAN.md` | ⚠️ Stale | Baseline is old |

---

## 7. Research Core Protection

### 7.1 Frozen Files (DO NOT MODIFY)

| File | Reason |
|------|--------|
| `decision_engine/core/schemas.py` | GAP-1/GAP-2 data models |
| `decision_engine/core/assessor.py` | GAP-1 assessment logic |
| `decision_engine/core/executor.py` | Execution abstraction |
| `decision_engine/core/engine.py` | GAP-2 pivot logic, LangGraph |
| `core/schemas.py` | VAPT research schemas |
| `core/agent_graph.py` | VAPT LangGraph implementation |
| `core/exploit_assessor.py` | LLM assessment |
| `core/executor.py` | VAPT execution |
| `core/report.py` | VAPT reporting |

### 7.2 Research Integrity Verification

**GAP-1 (Assessment before Ranking):**
```
Candidate → assess_candidates() → quality_rank → rank_candidates() → priority_score
```
✅ Verified in `decision_engine/core/engine.py:initial_state()`:
```python
if assess_fn:
    assess_candidates(raw_candidates, assess_fn=assess_fn)
cs = rank_candidates(raw_candidates)
```

**GAP-2 (Bounded Pivot):**
```
Candidate → execute → attempt_count++ → threshold check → pivot
```
✅ Verified in `decision_engine/core/engine.py:_evaluate()`:
```python
if state["attempt_count"] >= state["max_attempts"]:
    return "pivot"
```

**Per-candidate counters:**
✅ Verified in `decision_engine/core/engine.py:_pivot_node()`:
```python
state["attempt_count"] = 0  # reset per-candidate counter (Gap-2)
```

---

## 8. Test Status

| Test Suite | Count | Status |
|------------|-------|--------|
| `tests/` (root) | ~545 | ✅ All passing |
| `decision_engine/tests/` | ~16 | ✅ All passing |
| `prototype/tests/` | ~36 | ✅ All passing |
| `services/tests/` | ~5 | ✅ All passing |
| `frontend/tests/` | ~1 | ✅ All passing |

**Total: 545 tests collected, all passing**

---

## 9. Environment Status

| Component | Status | Notes |
|-----------|--------|-------|
| Python | ✅ 3.10 | venv at `./venv` |
| Docker | ❌ Not available | WSL without Docker Desktop |
| Ollama | ✅ Available | `llama3.2:3b` installed |
| Dependencies | ✅ Installed | All requirements.txt packages |

---

## 10. Recommended Implementation Order

### Phase 0: Audit ✅ (this document)

### Phase 1: Protect Research Core
- Verify no modifications to frozen files
- Create protection boundary documentation

### Phase 2: Full Application Workflow
- Verify VAPTApplication canonical workflow
- Ensure all interfaces use it

### Phase 3: Docker Lab
- Document Docker limitation
- Verify code correctness (runtime not possible)

### Phase 4: Local AI / Ollama
- Verify Ollama integration works
- Test deterministic fallback

### Phase 5: Professional UI Redesign (MAJOR)
- Redesign Streamlit dashboard
- Add dashboard, findings, intelligence, reports, system pages
- Add live assessment view
- Add attack path visualization

### Phase 6: API Enhancements
- Add missing endpoints
- Verify existing endpoints

### Phase 7: CLI Verification
- Verify all commands work

### Phase 8: Testing
- Run full test suite
- Add tests for new features

### Phase 9: Mentor Demo
- Create demonstration workflow

### Phase 10: Documentation
- Update all stale docs
- Create architecture docs

---

## 11. Key Technical Decisions

1. **Single canonical workflow**: `VAPTApplication.run()` is the only entry point
2. **Research core frozen**: No modifications to `decision_engine/core/` or `core/`
3. **Evidence tier discipline**: SIMULATED / OBSERVED_LOCAL / DOCKER_OBSERVED / CONTROLLED_VALIDATION
4. **Safety first**: Allowlist-based target validation, no external targets
5. **Offline-first**: Local Ollama, local datasets, no cloud dependencies
6. **Provenance tracking**: All assessments track source (deterministic vs LLM)

---

## 12. Immediate Blockers

1. **Docker not available**: Cannot verify Docker lab runtime
2. **GUI needs redesign**: Current UI is functional but not professional
3. **Documentation stale**: Multiple docs need updating

---

_Audit complete. Proceeding with implementation phases._
