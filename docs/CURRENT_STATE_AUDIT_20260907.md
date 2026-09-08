# CURRENT-STATE AUDIT & FUTURE DEVELOPMENT PLAN

**Date:** 2026-09-07
**Repository:** `/home/vinit/ai_vapt_framework`
**Branch:** `prototype-development`
**HEAD:** `0656f37` (Phase 15: OBSERVED_LOCAL)

---

## PHASE 1 — FORENSIC CURRENT-STATE AUDIT

### 1. Git State

| Item | Value |
|------|-------|
| Branch | `prototype-development` |
| HEAD | `0656f37` |
| Working tree | Clean (only untracked demo files) |
| Total commits | 20 (since branch from master) |

**Recent commits:**
```
0656f37 Phase 15: OBSERVED_LOCAL evidence tier
d7c2cee Docker integration tests (7 tests)
a5c9d8a Evidence tier: OBSERVED → DOCKER_OBSERVED
85919c7 Docs: +175 → +772 correction
c22a4e1 Phase 14: Docker lab executor integration
8ba96ec Phase 13: Engine robustness + Docker lab executor
6f67157 Phase 12: Thesis integration report
...
```

### 2. Core Research Engine (`decision_engine/core/`)

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Engine | `engine.py` | **DONE** | LangGraph state graph, assess→execute→pivot→evaluate loop |
| Schemas | `schemas.py` | **DONE** | ActionCandidate, Outcome, QualityRank, EngineStatus |
| Assessor | `assessor.py` | **DONE** | deterministic_assessor, assess_candidates |
| Executor | `executor.py` | **DONE** | simulation/real modes, execute_fn injection |

**Engine workflow:**
1. `rank_candidates()` — sort by priority_score (prob × quality)
2. `_assess_node()` — fill quality_rank via assessor
3. `_execute_node()` — attempt, increment counter, log outcome
4. `_evaluate()` — if attempts ≥ max_attempts → pivot; if SUCCESS → pivot; else → execute
5. `_pivot_node()` — advance to next candidate, reset counter, or COMPLETE

**Key mechanisms:**
- **Gap-1:** Priority scoring via `priority_score()` = prob × (0.5 + 0.5 × quality_factor)
- **Gap-2:** Per-candidate attempt counter, pivot at threshold, bounded termination
- **Checkpoint:** `save_checkpoint()` / `load_checkpoint()` with version guard

### 3. VAPT Integration

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| VAPT adapter | `vapt_adapter.py` | **DONE** | Maps corpus labels → ActionCandidate |
| Scan adapter | `scan_adapter.py` | **DONE** | Converts Finding[] → ActionCandidate[] |
| Corpus ingestion | `vapt_candidates_from_corpus()` | **DONE** | 12 CVE labels + EPSS enrichment |
| LLM assessor | `vapt_assess_fn()` | **DONE** | Delegates to `core/exploit_assessor.py` (requires Ollama) |

**Data flow:**
```
Scan file (Nmap XML/JSON)
  → core.scanner.process_scan() → Finding[]
  → scan_adapter.findings_to_candidates() → ActionCandidate[]
  → decision_engine.run_engine() → final state
```

### 4. Prototype (`prototype/`)

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Demo runner | `run_demo.py` | **DONE** | One-command demo, default failure_pivot |
| Engine integration | `engine_integration.py` | **DONE** | High-level wrapper around run_engine |
| Execution layer | `execution_layer.py` | **DONE** | Factory for simulation/lab executors |
| Lab runner | `lab_runner.py` | **DONE** | Raw HTTP GET, allowlist validation |
| Report generator | `report_generator.py` | **DONE** | JSON + TXT, evidence tiers |
| Trace formatter | `trace_formatter.py` | **DONE** | Human-readable engine logs |
| CLI | `cli.py` | **DONE** | Full CLI with run/resume/version |
| Checkpoints | `checkpoints.py` | **DONE** | Save/resume workflow |
| Demo scenarios | `demo_data.py` | **DONE** | success, failure_pivot, multi_candidate |

### 5. GUI (`frontend/`)

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Streamlit app | `app.py` | **DONE** | Scenario/mode selection, results display |
| Tests | `test_frontend_smoke.py` | **DONE** | 3 smoke tests |

**GUI features:**
- Scenario selection (success/failure_pivot/multi_candidate/corpus)
- Mode selection (simulation/lab)
- Lab target dropdown (allowlisted only)
- Candidate ranking table
- Execution timeline
- Decision trace
- Final report with evidence tier badge
- Download JSON/TXT buttons

### 6. Backend/API (`services/`)

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| FastAPI app | `services/api.py` | **DONE** | REST API for engine runs |
| Job manager | `services/jobs.py` | **DONE** | In-memory job tracking |
| Schemas | `services/schemas.py` | **DONE** | Request/response models |
| Tests | `test_api.py` | **DONE** | API endpoint tests |

**Endpoints:**
- `POST /runs` — Start a run
- `GET /runs/{id}` — Get status
- `GET /runs/{id}/trace` — Get decision trace
- `GET /runs/{id}/report` — Get JSON report
- `GET /health` — Health check

### 7. Docker Lab (`lab/`)

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Compose | `docker-compose.yml` | **DONE** | emulator + executor services |
| Emulator | `emulator/app.py` | **DONE** | Flask: /vuln, /fail, /health |
| Executor | `executor_server.py` | **DONE** | Flask: /execute, /health, allowlist |
| Executor Dockerfile | `executor.Dockerfile` | **DONE** | python:3.11-slim, non-root |
| Emulator Dockerfile | `emulator/Dockerfile` | **DONE** | python:3.11-slim, non-root |
| Engine verify | `engine_verify.py` | **DONE** | Comprehensive verification script |

**Network isolation:**
- `vuln-lab-network` — internal bridge (no egress), 172.28.0.0/16
- `executor-network` — bridge (port 9090 to host)
- Emulator only on internal network
- Executor on both networks (can reach emulator + host)

**Safety:**
- Allowlist: {127.0.0.1, 172.28.0.2}
- `no-new-privileges:true`, `read_only: true`, non-root user
- Resource limits (CPU/memory)
- Port 9090 required for host-to-executor communication

### 8. Tests

| Suite | Count | Status |
|-------|-------|--------|
| `tests/` (core) | 39 | **DONE** |
| `decision_engine/tests/` | 16 | **DONE** |
| `prototype/tests/` | 122 | **DONE** |
| `frontend/tests/` | 3 | **DONE** |
| `services/tests/` | 10 | **DONE** |
| **Total** | **190** | **PASSING** |

**Breakdown of prototype/tests:**
- test_checkpoint_workflow.py
- test_demo_scenarios.py
- test_docker_lab.py (7 tests, skip if Docker unavailable)
- test_execution_layer.py
- test_integration.py
- test_lab_runner.py
- test_llm_assessor.py
- test_report.py
- test_safety.py

### 9. Benchmarks

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Fair benchmark | `fair_benchmark.py` | **DONE** | 4-agent ablation, 30 seeds, 6 families |
| Fair VAPT benchmark | `fair_vapt_benchmark.py` | **DONE** | VAPT corpus evaluation |
| Agnostic benchmark | `agnostic_benchmark.py` | **DONE** | Domain-independence proof |
| LLM assessor benchmark | `llm_assessor_benchmark.py` | **DONE** | LLM accuracy impact |

**Key results:**
- VAPT T=2: +77 requests saved (pivot component)
- VAPT T=5: +200 requests saved
- Agnostic sparse T=5: +772 requests saved
- Priority component = 0 (Gap-1 not independently proven)

### 10. Datasets

| Dataset | File | Size | Status |
|---------|------|------|--------|
| CISA KEV | `cisa_kev.json` | 1.6 MB (1,682 CVEs) | **DONE** |
| EPSS scores | `epss_scores.csv.gz` | 2.5 MB (365k) | **DONE** |
| EPSS enrichment | `epss_corpus_enrichment.json` | 342 B (12 CVEs) | **DONE** |
| PoC corpus | `data/poc_corpus/` | 12 CVEs + labels | **DONE** |
| PoC lab | `data/poc_corpus_lab/` | 3 files | **DONE** |

### 11. Documentation

| Category | Files | Status |
|----------|-------|--------|
| Project management | 40+ docs | **DONE** |
| Roadmap | 10+ docs | **DONE** |
| External reviews | 6 docs | **DONE** |
| Thesis | THESIS_FINAL.md | **DONE** |
| Agent prompts | AGENT_PROMPTS.md | **DONE** |

---

## PHASE 2 — WHAT HAS ACTUALLY BEEN ACHIEVED

| Area | Status | Evidence | Notes |
|------|--------|----------|-------|
| Research engine | **DONE** | `decision_engine/core/engine.py` | LangGraph, Gap-1 + Gap-2 |
| Gap-1 (priority scoring) | **DONE** | `assessor.py`, `schemas.py` | priority_score() |
| Gap-2 (bounded pivot) | **DONE** | `engine.py:_evaluate()`, `_pivot_node()` | attempt counter + threshold |
| VAPT adapter | **DONE** | `vapt_adapter.py` | Corpus → ActionCandidate |
| Scan ingestion | **DONE** | `scan_adapter.py` | Finding[] → ActionCandidate[] |
| Backend API | **DONE** | `services/api.py` | FastAPI, 5 endpoints |
| GUI | **DONE** | `frontend/app.py` | Streamlit, full workflow |
| Reporting | **DONE** | `report_generator.py` | JSON + TXT, evidence tiers |
| Docker lab | **DONE** | `lab/docker-compose.yml` | Emulator + executor, isolated |
| Prototype demo | **DONE** | `prototype/run_demo.py` | One-command demo |
| Thesis | **DONE** | `THESIS_FINAL.md` | Full thesis document |
| Tests | **DONE** | 190 tests passing | All suites |
| Fair benchmarks | **DONE** | `fair_benchmark.py` | +77/+200/+772 results |
| Evidence tiers | **DONE** | `report_generator.py` | SIMULATED/OBSERVED_LOCAL/DOCKER_OBSERVED/CONTROLLED VALIDATION |
| Safety model | **DONE** | `lab_runner.py`, `executor_server.py` | Allowlist, fail-closed, isolation |

---

## PHASE 3 — MENTOR PROTOTYPE READINESS

### Can you show the prototype to your mentor today?

**YES — with caveats.**

### What will work reliably:

1. **Simulation mode** — fully deterministic, no external dependencies
2. **CLI demo** — `python prototype/cli.py run --scenario failure_pivot --max-attempts 2`
3. **Streamlit GUI** — `streamlit run frontend/app.py`
4. **JSON/TXT reports** — generated automatically
5. **Decision trace** — step-by-step engine log
6. **Evidence tier labeling** — correct for each mode

### What requires Docker (may not work in all environments):

1. **Lab mode** — requires `docker-compose up` first
2. **Docker tests** — skip if Docker unavailable

### What to avoid demonstrating:

1. **LLM assessor** — requires local Ollama running
2. **Real mode** — prohibited by safety rules
3. **External scanning** — prohibited by safety rules

### Recommended 5–10 minute mentor demo flow:

1. **Start CLI:** `python prototype/cli.py run --scenario failure_pivot --max-attempts 2`
2. **Show candidate ranking:** Explain priority_score (prob × quality)
3. **Show execution:** DEMO-DEAD-END fails twice, then pivot
4. **Show success:** DEMO-WORKER succeeds, workflow completes
5. **Show report:** Open generated JSON/TXT, explain evidence tier
6. **Explain research:** Gap-2 pivot mechanism, fair benchmark results (+77/+200/+772)
7. **Optional:** Start Streamlit GUI for visual demo

### Readiness scores (0–10):

| Category | Score | Notes |
|----------|-------|-------|
| UI | 7 | Streamlit functional but basic |
| Stability | 9 | 190 tests pass, deterministic |
| Research novelty | 8 | Gap-2 is genuine, evidence discipline strong |
| Demonstration quality | 8 | CLI + GUI + reports |
| Realism | 6 | Simulation + Docker lab, no real targets |
| Safety | 9 | Allowlist, fail-closed, isolation |
| Engineering quality | 8 | Clean architecture, good test coverage |

---

## PHASE 4 — GAP ANALYSIS

### Completed

- [x] Domain-independent decision engine
- [x] Gap-1 priority scoring
- [x] Gap-2 bounded pivot
- [x] LangGraph orchestration
- [x] VAPT adapter
- [x] Scan adapter
- [x] Corpus ingestion
- [x] Simulation mode
- [x] Docker lab (emulator + executor)
- [x] Loopback mode (127.0.0.1)
- [x] Docker-isolated mode (172.28.0.2)
- [x] Evidence tier taxonomy (4 tiers)
- [x] JSON/TXT reporting
- [x] Streamlit GUI
- [x] FastAPI backend
- [x] CLI
- [x] Checkpoint/resume
- [x] Fair benchmarks
- [x] 190 tests
- [x] Thesis document

### Remaining for prototype (minor)

- [ ] GUI polish (better visualization)
- [ ] Decision trace animation
- [ ] Interactive workflow
- [ ] More demo scenarios

### Remaining for full VAPT platform (major)

- [ ] Multi-tool scanning (Nmap, Nuclei, Web recon)
- [ ] CVE enrichment (live EPSS, CPE, CVSS)
- [ ] Asset graph
- [ ] Multi-agent orchestration (Planner/Executor/Verifier)
- [ ] Reporting AI (LLM-generated narratives)
- [ ] Real authorized scanning (with proper authorization)

---

## PHASE 5 — FUTURE DEVELOPMENT ROADMAP

### Phase P1 — Prototype Stabilization (1–2 weeks)

**Goal:** Polish for mentor demonstration.

| Task | Objective | Dependencies | Acceptance |
|------|-----------|--------------|------------|
| P1-01 | GUI polish (better tables, colors) | None | Visual improvement |
| P1-02 | Decision trace visualization | None | Step-by-step animation |
| P1-03 | More demo scenarios | None | 5+ scenarios |
| P1-04 | Mentor demo script | None | 5–10 min flow |

### Phase P2 — Practical VAPT Integration (2–4 weeks)

**Goal:** Safe scan ingestion from real tools.

| Task | Objective | Dependencies | Acceptance |
|------|-----------|--------------|------------|
| P2-01 | Nmap XML/JSON parser | None | Parse real scans |
| P2-02 | Nuclei JSON parser | None | Parse Nuclei output |
| P2-03 | Web recon (optional) | None | Basic web findings |
| P2-04 | CVE enrichment pipeline | None | Live EPSS, CVSS, CPE |
| P2-05 | Asset graph (basic) | P2-01 | Visualize assets |

### Phase P3 — GUI Polish (1–2 weeks)

**Goal:** Production-quality interface.

| Task | Objective | Dependencies | Acceptance |
|------|-----------|--------------|------------|
| P3-01 | Dashboard layout | P1-01 | Professional UI |
| P3-02 | Interactive workflow | P1-02 | Step-through execution |
| P3-03 | Report visualization | P1-03 | Charts, timelines |
| P3-04 | Export options | P1-04 | PDF, HTML reports |

### Phase P4 — Controlled Lab Completion (1 week)

**Goal:** Resolve any remaining Docker issues.

| Task | Objective | Dependencies | Acceptance |
|------|-----------|--------------|------------|
| P4-01 | Verify network isolation | None | Confirmed isolated |
| P4-02 | Test all evidence tiers | None | All 4 tiers work |
| P4-03 | Lab documentation | None | Setup guide |

### Phase P5 — Advanced Features (4+ weeks)

**Goal:** Full AI VAPT platform.

| Task | Objective | Dependencies | Acceptance |
|------|-----------|--------------|------------|
| P5-01 | Multi-agent orchestration | P2 | Planner/Executor/Verifier |
| P5-02 | LLM reporting | P2 | Narrative generation |
| P5-03 | Real authorized scanning | P2 | With proper authorization |
| P5-04 | Full platform integration | All | End-to-end workflow |

---

## PHASE 6 — AGENT TASK DECOMPOSITION

### Agent P-PROTO (Prototype Stabilization)

```
TASK ID: P-PROTO
ROLE: Prototype Engineer
OBJECTIVE: Polish prototype for mentor demonstration
PROJECT CONTEXT: AI VAPT framework, Streamlit GUI, CLI demo
EXACT TASK:
  1. Improve Streamlit GUI styling (better tables, colors, layout)
  2. Add decision trace visualization (step-by-step)
  3. Create 2–3 additional demo scenarios
  4. Write mentor demo script (5–10 min flow)
ALLOWED FILES:
  - frontend/app.py
  - prototype/demo_data.py
  - prototype/run_demo.py
  - docs/project_management/MENTOR_DEMO_SCRIPT.md
FORBIDDEN FILES:
  - decision_engine/ (frozen)
  - core/ (frozen)
  - lab/ (frozen)
ACCEPTANCE CRITERIA:
  - GUI looks professional
  - Demo scenarios work
  - Mentor script is clear
TESTS TO RUN: pytest prototype/tests/ frontend/tests/ -q
COMMIT RULE: One commit per task
STOP CONDITION: If changes affect frozen code
```

### Agent P-SCAN (Scan Ingestion)

```
TASK ID: P-SCAN
ROLE: VAPT Integration Engineer
OBJECTIVE: Add Nmap/Nuclei scan parsers
PROJECT CONTEXT: AI VAPT framework, scan adapter
EXACT TASK:
  1. Enhance scan_adapter.py to handle Nmap XML/JSON
  2. Add Nuclei JSON parser
  3. Add tests for new parsers
ALLOWED FILES:
  - decision_engine/adapters/scan_adapter.py
  - decision_engine/tests/test_scan_adapter.py
FORBIDDEN FILES:
  - decision_engine/core/ (frozen)
  - core/ (frozen)
ACCEPTANCE CRITERIA:
  - Nmap XML/JSON parsed correctly
  - Nuclei JSON parsed correctly
  - Tests pass
TESTS TO RUN: pytest decision_engine/tests/test_scan_adapter.py -q
COMMIT RULE: One commit per parser
STOP CONDITION: If changes affect frozen code
```

---

## PHASE 7 — FINAL RECOMMENDATION

### Current maturity

**Research complete, prototype ready.**

The research contribution (Gap-2 bounded pivot) is:
- Implemented
- Tested (190 tests)
- Benchmarked (+77/+200/+772)
- Documented (thesis + evidence)

The prototype is:
- Functional (CLI + GUI + API)
- Safe (allowlist, fail-closed, isolation)
- Demonstrable (simulation + Docker lab)

### Immediate next action

**Single next task:** Run the mentor demo flow yourself once.

```bash
# Terminal 1: Start Docker lab (if not running)
cd lab && docker-compose up -d

# Terminal 2: Run CLI demo
python prototype/cli.py run --scenario failure_pivot --max-attempts 2

# Terminal 3: Start GUI (optional)
streamlit run frontend/app.py
```

### Sequence after that

1. **P1-01:** GUI polish (if mentor feedback requests it)
2. **P1-03:** More demo scenarios (if needed)
3. **P2-01:** Nmap parser (if you want to show real scan ingestion)

### 30-day development roadmap

| Week | Focus | Deliverables |
|------|-------|--------------|
| 1 | Mentor demo rehearsal | Polished demo flow |
| 2 | GUI polish | Better visualization |
| 3 | Scan ingestion | Nmap/Nuclei parsers |
| 4 | Documentation | Thesis finalization |

### Final verdict

**READY FOR MENTOR PROTOTYPE**

The prototype is ready for mentor demonstration. The research is complete, the evidence is solid, and the safety model is sound. Minor polish can be done based on mentor feedback.

---

*Generated by Hermes Agent — 2026-09-07*
