# Full Platform Architecture

**Date:** 2026-09-08
**Status:** Planning only — DO NOT IMPLEMENT without explicit authorization

---

## 1. Current Verified Architecture

### 1.1 What Exists

The repository has TWO parallel code layers:

**Layer A — Original VAPT-specific code (`core/`, `app.py`, `tests/`)**
- `core/scanner.py` — Nmap XML/JSON parser + custom JSON parser + EPSS enrichment
- `core/schemas.py` — Finding model (CVE-centric)
- `core/agent_graph.py` — VAPT-specific LangGraph agent (old)
- `core/exploit_assessor.py` — LLM usability scoring
- `core/executor.py` — VAPT-specific executor
- `core/poc_corpus.py` — PoC corpus management
- `core/report.py` — JSON + PDF report generation

**Layer B — Domain-independent research engine (`decision_engine/`)**
- `decision_engine/core/engine.py` — Domain-independent LangGraph engine (THE research contribution)
- `decision_engine/core/schemas.py` — ActionCandidate, Outcome, EngineStatus
- `decision_engine/core/assessor.py` — Deterministic + LLM assessor
- `decision_engine/core/executor.py` — Generic simulation + real execution backend
- `decision_engine/adapters/vapt_adapter.py` — VAPT domain adapter
- `decision_engine/adapters/scan_adapter.py` — Scan file → ActionCandidate bridge
- `decision_engine/benchmarks/` — Fair benchmark suite

**Layer C — Prototype interface (`prototype/`, `frontend/`, `services/`)**
- `prototype/cli.py` — CLI for demo scenarios
- `prototype/demo_data.py` — Deterministic demo scenarios
- `prototype/engine_integration.py` — High-level engine wrapper
- `prototype/execution_layer.py` — Executor factory
- `prototype/report_generator.py` — JSON/TXT report generation
- `prototype/lab_runner.py` — Docker lab runner
- `frontend/app.py` — Streamlit GUI
- `services/api.py` — FastAPI backend

### 1.2 What Each Layer Does

| Layer | Purpose | Research Protected? |
|-------|---------|---------------------|
| `decision_engine/core/` | Domain-independent decision engine | **YES — FROZEN** |
| `decision_engine/adapters/` | Domain bridges | Partially (stable) |
| `decision_engine/benchmarks/` | Research evaluation | **YES — FROZEN** |
| `core/` | Original VAPT-specific code | No (can evolve) |
| `prototype/` | Prototype interface | No (can evolve) |
| `frontend/` | Streamlit GUI | No (can evolve) |
| `services/` | FastAPI backend | No (can evolve) |

### 1.3 What Is Already Working

1. **Nmap XML parsing** — `core/scanner.py:parse_nmap_xml()` — handles host, port, service, CPE
2. **Nmap JSON parsing** — `core/scanner.py:parse_nmap_json()` — handles Nmap -oJ output
3. **Custom JSON parsing** — `core/scanner.py:parse_custom_json()` — handles sample_scan.json
4. **EPSS enrichment** — `core/scanner.py:fetch_epss_score()` — live EPSS from FIRST.org
5. **Finding → ActionCandidate** — `decision_engine/adapters/scan_adapter.py:findings_to_candidates()`
6. **Decision engine** — `decision_engine/core/engine.py:run_engine()` — full LangGraph workflow
7. **Simulation execution** — `decision_engine/core/executor.py` — ground-truth resolution
8. **Lab execution** — `prototype/execution_layer.py` — Docker-observed HTTP execution
9. **JSON/TXT reporting** — `prototype/report_generator.py` — full run reports
10. **Streamlit GUI** — `frontend/app.py` — scenario selection + results display
11. **FastAPI** — `services/api.py` — REST API for runs

---

## 2. Architecture Problems in Existing Plan

### 2.1 MULTI_AGENT_PLAN.md Conflicts

| Problem | Details |
|---------|---------|
| **Agent-001 vs Agent-002 file conflict** | Both modify `core/scanner.py` but plan claims they can run parallel |
| **Agent-003 modifies `core/schemas.py`** | This is the OLD schema; the engine uses `decision_engine/core/schemas.py` — confusing ownership |
| **Missing integration agent** | No agent ties parsers → engine → report together |
| **Missing Nuclei parser location** | Plan says add to `core/scanner.py` but this creates conflict |
| **Agent-006 GUI work unnecessary** | GUI already works; polish is not needed for first milestone |
| **Agent-007 report work unnecessary** | JSON/TXT reports already work; HTML/PDF can wait |

### 2.2 FUTURE_PLATFORM_ROADMAP.md Problems

| Problem | Details |
|---------|---------|
| **F1 lists "Nmap XML parser (exists, needs enhancement)"** | True, but the parser already exists in `core/scanner.py` — the plan should say "reuse existing" |
| **F2 "extends existing ActionCandidate"** | ActionCandidate is in `decision_engine/core/schemas.py` (research-protected) — should NOT be extended; use adapters |
| **F1→F10 strictly sequential** | Many phases can run in parallel with proper file ownership |
| **Missing "integration" phases** | No milestone for "scan file → engine → report" end-to-end |
| **F6 Multi-agent too early** | Multi-agent orchestration is not needed for scan ingestion or normalization |

---

## 3. Corrected Architecture

### 3.1 Design Principles

1. **Research engine is frozen** — `decision_engine/core/` is never modified
2. **Adapters bridge domains** — New domains attach via `decision_engine/adapters/`
3. **Platform code is separate** — New features live in new modules, not inside existing ones
4. **Reuse before rebuild** — `core/scanner.py` already parses Nmap; don't duplicate
5. **Vertical slices over horizontal layers** — Each milestone delivers a working end-to-end path

### 3.2 Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     SCAN INGESTION LAYER                         │
│                                                                  │
│  Nmap XML/JSON  ──→  core/scanner.py (existing)                 │
│  Nuclei JSON    ──→  platform/parsers/nuclei_parser.py (new)    │
│  Web recon      ──→  platform/parsers/web_parser.py (future)    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   NORMALIZATION LAYER                            │
│                                                                  │
│  platform/normalization.py (new)                                 │
│    - Convert parser output to canonical Finding format           │
│    - Deduplicate by CVE + host + port                           │
│    - Asset identification                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   ENRICHMENT LAYER                               │
│                                                                  │
│  core/scanner.py:enrich() (existing EPSS)                        │
│  platform/enrichment.py (new: CVSS, CISA KEV, caching)          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   CANDIDATE LAYER                                │
│                                                                  │
│  decision_engine/adapters/scan_adapter.py (existing bridge)      │
│    - Finding[] → ActionCandidate[]                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              DECISION ENGINE (RESEARCH-PROTECTED)                │
│                                                                  │
│  decision_engine/core/engine.py                                  │
│    - assess → execute → evaluate → pivot/advance                │
│    - Per-candidate attempt counting (Gap-2)                      │
│    - Bounded failure-threshold pivoting                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   EXECUTION LAYER                                │
│                                                                  │
│  Simulation  ──→ ground_truth labels (existing)                  │
│  Lab         ──→ Docker emulator (existing)                      │
│  Real        ──→ Future: authorized controlled execution        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   OUTPUT LAYER                                   │
│                                                                  │
│  prototype/report_generator.py (existing JSON/TXT)               │
│  frontend/app.py (existing Streamlit)                            │
│  services/api.py (existing FastAPI)                              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 File Ownership (Corrected)

| Module | Owner | Research Protected? |
|--------|-------|---------------------|
| `decision_engine/core/` | FROZEN | Yes |
| `decision_engine/benchmarks/` | FROZEN | Yes |
| `decision_engine/adapters/` | Platform team | No (but stable) |
| `core/scanner.py` | Platform team | No |
| `core/schemas.py` | Platform team | No |
| `platform/parsers/` | Platform team | No |
| `platform/normalization.py` | Platform team | No |
| `platform/enrichment.py` | Platform team | No |
| `prototype/` | Platform team | No |
| `frontend/` | Platform team | No |
| `services/` | Platform team | No |

---

## 4. Key Design Decisions

### 4.1 Scan Execution: Ingest Output Files (Option B)

**Decision:** The platform should INGEST scan output files, not execute scanners itself.

**Rationale:**
- Safety: No risk of unauthorized scanning
- Simplicity: No subprocess management, no scanner dependencies
- Reproducibility: Same scan file produces same results
- Authorization: User separately authorizes and runs Nmap/Nuclei

**Future:** A separate "scanner runner" module can be added later with explicit authorization checks, rate limiting, and audit logging. This is NOT part of the core platform.

### 4.2 GUI Strategy

**Decision:** No GUI work for first milestone. The existing Streamlit GUI works for demo scenarios. GUI enhancements should only be added when the full platform workflow is proven.

**Rationale:**
- GUI polish does not advance the research or platform architecture
- The existing GUI already demonstrates the decision engine
- GUI work should follow feature work, not lead it

### 4.3 Reporting Strategy

**Decision:** JSON/TXT reports are sufficient for now. HTML/Markdown/PDF can be added later.

**Rationale:**
- Reports already work and are accurate
- Additional formats do not change the research contribution
- Can be added as a standalone agent after core platform is proven

### 4.4 Multi-Agent System Strategy

**Decision:** Do NOT implement Planner/Executor/Verifier multi-agent system yet.

**Rationale:**
- The existing LangGraph engine IS the decision-making component
- Multi-agent orchestration adds complexity without clear benefit for scan ingestion
- The correct time for multi-agent is when multiple scan sources need coordinated analysis
- Current single-agent pipeline is sufficient for the foreseeable future

---

## 5. Research Integrity Model

### 5.1 Protected Components

The following are RESEARCH-PROTECTED and must NOT be modified:

| Component | File | Why |
|-----------|------|-----|
| Engine logic | `decision_engine/core/engine.py` | Gap-2 implementation |
| Engine schemas | `decision_engine/core/schemas.py` | ActionCandidate, Outcome |
| Assessor | `decision_engine/core/assessor.py` | Gap-1 implementation |
| Executor | `decision_engine/core/executor.py` | Execution backend |
| Fair benchmarks | `decision_engine/benchmarks/fair_benchmark.py` | Research results |
| Fair VAPT benchmarks | `decision_engine/benchmarks/fair_vapt_benchmark.py` | Research results |
| Agnostic benchmarks | `decision_engine/benchmarks/agnostic_benchmark.py` | Research results |

### 5.2 Safe-to-Modify Components

| Component | File | Notes |
|-----------|------|-------|
| VAPT adapter | `decision_engine/adapters/vapt_adapter.py` | Domain bridge |
| Scan adapter | `decision_engine/adapters/scan_adapter.py` | Bridge |
| Old scanner | `core/scanner.py` | Can extend |
| Old schemas | `core/schemas.py` | Can extend |
| Prototype CLI | `prototype/cli.py` | Can extend |
| Demo data | `prototype/demo_data.py` | Can extend |
| Report generator | `prototype/report_generator.py` | Can extend |
| Lab runner | `prototype/lab_runner.py` | Can extend |
| Frontend | `frontend/app.py` | Can extend |
| API | `services/api.py` | Can extend |

---

## 6. Safety Model

### 6.1 Current Safety Controls

| Control | Status | Location |
|---------|--------|----------|
| Allowlist: {127.0.0.1, 172.28.0.2} | Active | `prototype/lab_runner.py` |
| Fail-closed validation | Active | `prototype/lab_runner.py:_validate_target()` |
| No external scanning | Enforced | Design (file ingestion only) |
| Docker network isolation | Active | `lab/docker-compose.yml` |
| Non-root containers | Active | `lab/docker-compose.yml` |
| Resource limits | Active | `lab/docker-compose.yml` |

### 6.2 Future Safety Requirements

1. **No autonomous scanning** — Platform ingests files only
2. **No real exploitation** — Simulation or Docker-isolated only
3. **Authorization tracking** — Future: user confirms authorization before any real target
4. **Audit logging** — All engine runs are logged with full trace
5. **Rate limiting** — Future: API rate limits for enrichment calls
6. **Input validation** — All scan file parsers validate and sanitize input

---

*Document prepared by Hermes Agent — 2026-09-08*
