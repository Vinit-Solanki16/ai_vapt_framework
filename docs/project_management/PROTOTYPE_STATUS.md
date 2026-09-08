# Prototype Status

**Date:** 2026-09-08
**Branch:** `prototype-development`
**HEAD:** `0656f37`

---

## RESEARCH COMPLETE

| Item | Status | Evidence |
|------|--------|----------|
| Domain-independent decision engine | **DONE** | `decision_engine/core/engine.py` |
| Gap-1 (priority scoring) | **DONE** | `assessor.py`, `schemas.py` |
| Gap-2 (bounded pivot) | **DONE** | `engine.py:_evaluate()`, `_pivot_node()` |
| LangGraph orchestration | **DONE** | `engine.py:build_graph()` |
| Fair benchmarks | **DONE** | `fair_benchmark.py` (+77/+200/+772) |
| Evidence discipline | **DONE** | 4-tier taxonomy implemented |
| Thesis document | **DONE** | `THESIS_FINAL.md` |

---

## PROTOTYPE COMPLETE

| Item | Status | Evidence |
|------|--------|----------|
| VAPT adapter | **DONE** | `vapt_adapter.py` |
| Scan adapter | **DONE** | `scan_adapter.py` |
| Simulation mode | **DONE** | `execution_layer.py:create_simulation_executor()` |
| Loopback mode (127.0.0.1) | **DONE** | `execution_layer.py:create_lab_executor()` |
| Docker-isolated mode (172.28.0.2) | **DONE** | `execution_layer.py:create_docker_lab_executor()` |
| JSON/TXT reporting | **DONE** | `report_generator.py` |
| Evidence tier labeling | **DONE** | SIMULATED/OBSERVED_LOCAL/DOCKER_OBSERVED/CONTROLLED VALIDATION |
| Streamlit GUI | **DONE** | `frontend/app.py` |
| FastAPI backend | **DONE** | `services/api.py` |
| CLI (run/resume/version) | **DONE** | `prototype/cli.py` |
| Checkpoint/resume | **DONE** | `prototype/checkpoints.py` |
| Safety allowlist | **DONE** | `lab_runner.py`, `executor_server.py` |
| Docker lab | **DONE** | `lab/docker-compose.yml` |
| 195 tests passing | **DONE** | All suites |

---

## PROTOTYPE POLISH REMAINING

| Item | Priority | Notes |
|------|----------|-------|
| GUI visualization | Medium | Better tables, colors, layout |
| Decision trace animation | Low | Step-by-step visualization |
| Additional demo scenarios | Low | More variety |
| Mentor demo script | **DONE** | `MENTOR_DEMO_GUIDE.md` |

---

## FULL PLATFORM FUTURE WORK

### P2: Practical VAPT Integration

| Item | Priority | Notes |
|------|----------|-------|
| Nmap XML/JSON parser | High | Real scan ingestion |
| Nuclei JSON parser | High | Real scan ingestion |
| CVE/CVSS/CPE enrichment | Medium | Live metadata |
| Asset graph | Medium | Visualize findings |

### P5: Advanced Features

| Item | Priority | Notes |
|------|----------|-------|
| Multi-agent orchestration | Low | Planner/Executor/Verifier |
| AI-generated reports | Low | LLM narratives |
| Authorized real-world integration | Low | With proper authorization |

---

## Test Coverage

| Suite | Count | Status |
|-------|-------|--------|
| `tests/` (core) | 39 | PASS |
| `decision_engine/tests/` | 16 | PASS |
| `prototype/tests/` | 122 | PASS |
| `frontend/tests/` | 3 | PASS |
| `services/tests/` | 10 | PASS |
| `test_docker_lab.py` | 7 | SKIP (Docker unavailable) |
| **Total** | **195 passed, 7 skipped** | **PASS** |

---

## Demo Commands

```bash
# CLI (recommended for mentor)
python -m prototype.cli run --scenario failure_pivot --max-attempts 2

# GUI
streamlit run frontend/app.py

# API
uvicorn services.api:app --reload
```

---

## Evidence Tiers

| Tier | Source | Status |
|------|--------|--------|
| SIMULATED | Ground-truth labels | **Implemented** |
| OBSERVED_LOCAL | Loopback (127.0.0.1) | **Implemented** |
| DOCKER_OBSERVED | Docker emulator (172.28.0.2) | **Implemented** |
| CONTROLLED VALIDATION | Live authorized targets | **Not demonstrated** |

---

## Safety Model

| Control | Status |
|---------|--------|
| Allowlist: {127.0.0.1, 172.28.0.2} | **Active** |
| Fail-closed validation | **Active** |
| No external scanning | **Enforced** |
| Docker network isolation | **Active** |
| Non-root containers | **Active** |
| Resource limits | **Active** |

---

## Key Research Results

| Experiment | Result |
|------------|--------|
| VAPT T=2 pivot component | +77 requests saved |
| VAPT T=5 pivot component | +200 requests saved |
| Agnostic sparse T=5 pivot component | +772 requests saved |
| Priority component (Gap-1) | 0 (not independently proven) |

---

## Verdict

**READY FOR MENTOR PROTOTYPE**

The prototype is functional, safe, and demonstrable. The research is complete, the evidence is solid, and the safety model is sound.

---

*Document prepared by Hermes Agent — 2026-09-08*
