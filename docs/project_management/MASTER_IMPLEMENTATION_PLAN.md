# MASTER IMPLEMENTATION PLAN — AI VAPT Framework

**Generated:** 2026-09-01 (IST)
**Source:** Complete read-only repository audit (every .py file read, all 91 tests run, import graph traced)
**Baseline:** `reference-engine-prequalification-2026-09-01` @ 4dc0599
**Branch:** `prototype-development`
**Status:** READY FOR MULTI-AGENT EXECUTION

---

## 1. EXECUTIVE SUMMARY

This plan converts the current simulation-first research prototype into a complete, demonstrable, end-to-end AI-assisted VAPT research prototype. The central contribution — a domain-independent decision engine that ranks candidate paths and adapts under bounded retry and pivot constraints — is already implemented and tested (55 tests across frozen + new engine). The remaining work wires real inputs, real LLM assessment, a real (isolated lab) executor, a backend/API, a frontend, and a reporting/evaluation layer around that frozen core — WITHOUT rewriting the research engine.

**Current verified state:**
- TRACK0 (`core/`): 39/39 tests — FROZEN, do not modify
- TRACK1 (`decision_engine/`): 16/16 tests — FROZEN, do not modify
- Prototype (`prototype/`): 36/36 tests — UNTRACKED, must be committed
- Combined: 91/91 passing
- No backend, no API, no modern frontend, no Nmap/Nuclei wiring, no lab integration

**Strategy:** Additive integration around a frozen core. One agent per workstream, no parallel edits to the same files, checkpoint commit per verified phase.

---

## 2. CURRENT-STATE ARCHITECTURE

### 2.1 Component map (verified by reading code)

```
decision_engine/                      # Stage-1 generalized engine (ACTIVE)
  core/
    schemas.py         ActionCandidate, QualityRank, Outcome, EngineStatus, priority_score()
    assessor.py        deterministic_assessor, assess_candidates()
    executor.py        Executor(mode="simulation"|"real", execute_fn=...)
    engine.py          run_engine(), build_graph(), save_checkpoint(), load_checkpoint()
  adapters/
    vapt_adapter.py    vapt_candidates_from_corpus(), vapt_assess_fn(), vapt_real_executor()
  benchmarks/
    fair_benchmark.py  4-agent ablation (DUMB/PIVOT-ONLY/PRIORITY-ONLY/SMART), 6 families, noise
    fair_vapt_benchmark.py  Same 4-agent protocol on full VAPT corpus (12 CVEs)
    agnostic_benchmark.py     Non-VAPT "tasks" domain proof
  tests/
    test_engine.py     12 tests (TEST-DE-01..12)
    test_fair_benchmark.py    4 tests (SMART<=DUMB, pivot>=0, JSONL, smoke)

core/                                # Frozen VAPT prototype (TRACK0, DO NOT MODIFY)
  schemas.py           Finding, UsabilityRank, ExecutionOutcome, ExploitAssessment
  scanner.py           Nmap XML/JSON + custom JSON ingestion, EPSS enrichment
  poc_corpus.py        Local corpus lookup, GitHub fetch, labels
  exploit_assessor.py  LLM usability scoring (Ollama/OpenAI), structured output
  executor.py          Simulation + real (connectivity-only default, danger_mode opt-in)
  agent_graph.py       LangGraph assess->execute->pivot, checkpoint/resume
  report.py            JSON + PDF report generation

prototype/                           # Mentor-facing CLI wrapper (UNTRACKED — commit first)
  engine_integration.py  run_decision_scenario(), load_vapt_corpus_scenario(), validate_scenario()
  execution_layer.py     create_simulation_executor(), create_executor()
  demo_data.py           success/failure_pivot/multi_candidate scenarios
  cli.py                 Mentor-facing CLI (--scenario, --max-attempts, --corpus)
  run_demo.py            One-command demo runner
  report_generator.py    JSON + text report generation
  trace_formatter.py     Human-readable decision trace from engine logs
  checkpoints.py         Thin wrapper around engine save/load_checkpoint
  tests/                 36 tests across integration, demo, execution, report

app.py                               # Old Streamlit dashboard (coupled to core/, not decision_engine)
lab/                                 # Docker emulator
  docker-compose.yml   Isolated bridge network (172.28.0.0/16, internal:true)
  emulator/app.py      Flask: /vuln→"VULNERABLE", /fail→"NOT_VULNERABLE", /health

datasets/                            # Real data
  cisa_kev.json        1,682 vulnerabilities
  epss_scores.csv.gz   365k rows
  epss_corpus_enrichment.json  12 CVEs with live EPSS
  poc_corpus/labels.json        Ground-truth labels for 12 CVEs
  poc_corpus_lab/      Behavioral emulators (A.py→/vuln, B.py→/fail, C.py→/fail)
```

### 2.2 Interface contracts (verified)

**Engine entry point:**
```python
from decision_engine.core.engine import run_engine
final = run_engine(
    candidates=[{"id": str, "probability": float, "ground_truth": str}, ...],
    assess_fn=Callable[[ActionCandidate], QualityRank] | None,
    executor=Executor,
    max_attempts=int,
    mode="simulation"|"real",
)  # returns dict with keys: candidates, status, logs, results, current_index, ...
```

**VAPT adapter:**
```python
from decision_engine.adapters.vapt_adapter import (
    vapt_candidates_from_corpus,  # -> List[ActionCandidate]
    vapt_assess_fn,               # -> Callable or deterministic fallback
    vapt_real_executor,           # -> wraps core Executor
)
```

### 2.3 Frozen boundary (verified by grep)
- `decision_engine/core/` imports ONLY `decision_engine.core.*` — zero VAPT code imports
- `adapters/vapt_adapter.py` is the ONLY boundary-crossing file (imports `core.exploit_assessor`)
- `tests/` exercises `core/` (TRACK0)
- `decision_engine/tests/` exercises `decision_engine/` (TRACK1)

---

## 3. DESIRED FINAL ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────┐
│                        WEB FRONTEND (Phase 7)                       │
│  Run config | Target/lab selection | Candidate list | Scores        │
│  Execution state | Retry counter | Pivot events | Decision trace    │
│  Findings | Report | Safety/mode indicator                          │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ HTTP/SSE
┌────────────────────────────────▼────────────────────────────────────┐
│                      BACKEND / API (Phase 6)                         │
│  Run lifecycle | Job state | Streaming status | Report retrieval     │
│  Safety gate: refuse non-allowlisted targets                        │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│                 ORCHESTRATION LAYER (Phase 5)                        │
│  Scan ingestion → Finding normalization → Candidate generation      │
│  Assessment (LLM or deterministic) → Ranking → Decision             │
│  Execution (simulation | loopback | lab) → Observation → Feedback   │
│  Checkpoint/restore workflow                                        │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│             DECISION ENGINE — decision_engine/core/ (FROZEN)        │
│  assess → execute → pivot/advance | bounded retry | checkpoint      │
│  Gap-1 (priority) | Gap-2 (pivot) | Gap-1+2 (SMART)                │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│                   DOMAIN ADAPTERS (Phase 4-5)                        │
│  vapt_adapter.py (existing) | Nmap adapter | Nuclei adapter          │
│  Future: scheduler, robotics, etc. (domain-independent engine)      │
└─────────────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│                   EXECUTION LAYER (Phase 3)                          │
│  simulation (default) | loopback (127.0.0.1) | lab (Docker emulator) │
│  LLM assessment (Ollama/OpenAI) | Deterministic fallback            │
└─────────────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│                     LOCAL LAB (Phase 2)                              │
│  Docker emulator (172.28.0.2:8080) | Behavioral targets A/B/C       │
│  Isolated network (no egress) | No real exploits                    │
└─────────────────────────────────────────────────────────────────────┘

REPORTING (Phase 8) ← Consumes final engine state + observed outcomes
EVALUATION (Phase 9) ← Re-runs benchmarks, ablations, new experiments
DOCUMENTATION (Phase 10) ← Thesis integration, demo script, limitations
```

---

## 4. GAP ANALYSIS

| # | Gap | Current State | Required State | Risk |
|---|-----|---------------|----------------|------|
| G1 | Prototype untracked | 36 tests passing but `??` in git | Committed, reproducible | Low |
| G2 | No real executor wiring | `Executor(mode="real")` exists but not wired to lab | Framework talks to emulator | Low |
| G3 | LLM not exposed via CLI | `exploit_assessor.py` exists, prototype uses only deterministic | CLI flag `--assessor llm` | Low |
| G4 | No scan-to-engine pipeline | `scanner.py` outputs `Finding[]`, engine wants `ActionCandidate[]` | Adapter: Finding[] → normalized candidates | Medium |
| G5 | No Nmap/Nuclei integration | `scanner.py` parses but doesn't invoke | CLI invokes Nmap, pipes XML to scanner | Medium |
| G6 | No backend/API | None | FastAPI: run, status, report endpoints | Medium |
| G7 | No modern frontend | `app.py` (old, coupled to core/) | Streamlit or React frontend for decision engine | Medium |
| G8 | Checkpoint/restore incomplete | Engine has save/load, prototype wraps it | Full CLI workflow: run → interrupt → resume | Low |
| G9 | Lab not connected to framework | Emulator exists, no framework container | Framework container on same network | Low |
| G10 | No E2E validation | Scenarios are unit/integration | Full workflow: scan→rank→decide→execute→report | Medium |
| G11 | Reporting basic | Text + JSON reports | Rich reports with observed-vs-simulated distinction | Low |
| G12 | No mentor demo script | `PROTOTYPE_DEMONSTRATION_PLAN.md` exists but unimplemented | Working demo + rehearsal | Low |

---

## 5. COMPLETE PHASE ROADMAP

### PHASE 0 — Repository / Architecture Verification

**A. Objective:** Establish a clean, committed, verified baseline before any new work.
**B. Why required:** The prototype/ directory is untracked. Starting new work on an uncommitted base risks losing the working state.
**C. Prerequisite state:** 91/91 tests passing, prototype/ untracked, docs modified.
**D. Dependencies:** None.
**E. Components:** git, prototype/, docs.
**F. Files affected:**
   - `prototype/` (commit existing)
   - `docs/project_management/MASTER_IMPLEMENTATION_PLAN.md` (this file)
   - `.gitignore` (verify reports/ excluded)
**G. Must NOT modify:** `core/`, `decision_engine/core/`, `decision_engine/adapters/`, `tests/`, `decision_engine/tests/`, `datasets/`, `decision_engine/benchmarks/`.
**H. Implementation tasks:**
   1. Run `pytest tests/ decision_engine/tests/ prototype/tests/ -q` → confirm 91/91.
   2. `git add prototype/` and commit: "PROTOTYPE: commit existing mentor prototype (36 tests)".
   3. `git add docs/project_management/MASTER_IMPLEMENTATION_PLAN.md`.
   4. Tag: `checkpoint-phase-00-baseline`.
**I. Integration tasks:** None.
**K. Security/safety:** None.
**M. Acceptance criteria:** `git log` shows prototype committed; 91/91 tests pass; `git diff` on frozen dirs is empty.
**N. Demonstration criteria:** `git status` clean on frozen dirs.
**O. Definition of DONE:** Tagged commit `checkpoint-phase-00-baseline` with prototype/ tracked and 91 tests green.
**P. Rollback:** `git revert` the commit.
**Q. Agent:** One documentation/ops agent (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** `git show --stat HEAD` includes prototype/; `pytest` 91/91.

---

### PHASE 1 — Local Lab Integration

**A. Objective:** Wire the existing Docker emulator so the engine's `mode="real"` path produces OBSERVED (not simulated) outcomes against controlled targets.
**B. Why required:** The research contribution needs at least one OBSERVED data point (currently all results are SIMULATION). The emulator already exists with `/vuln` and `/fail` endpoints.
**C. Prerequisite state:** Phase 0 done; emulator Dockerfile + docker-compose.yml exist; behavioral modules A/B/C exist.
**D. Dependencies:** Phase 0.
**E. Components:** `lab/`, `prototype/execution_layer.py`, `decision_engine/adapters/vapt_adapter.py`.
**F. Files affected:**
   - `lab/docker-compose.yml` (add framework service)
   - `lab/framework/Dockerfile` (new — optional, can also run host-side)
   - `prototype/lab_runner.py` (new — loopback runner)
   - `prototype/execution_layer.py` (extend with lab executor)
   - `prototype/tests/test_lab_runner.py` (new)
**G. Must NOT modify:** `core/`, `decision_engine/core/`, `tests/`, `decision_engine/tests/`, `datasets/`, `benchmarks/`.
**H. Implementation tasks:**
   1. Create `prototype/lab_runner.py`: a function `run_lab_scenario(target_ip, port, endpoint)` that uses the existing `vapt_real_executor` pattern to hit the emulator.
   2. Add `create_lab_executor(target, port)` to `prototype/execution_layer.py` that returns an `Executor(mode="real", execute_fn=...)`.
   3. The execute_fn performs an HTTP GET to `http://{target}:{port}{endpoint}` and maps the response body to Outcome (VULNERABLE→SUCCESS, NOT_VULNERABLE→FAIL_TIMEOUT).
   4. Add `--mode lab` to `prototype/cli.py` with `--target` defaulting to `172.28.0.2` and `--port` to `8080`.
   5. Add tests in `prototype/tests/test_lab_runner.py` that mock `socket.create_connection` / HTTP calls (offline) and assert correct Outcome mapping.
   6. Document the lab startup procedure in `lab/README.md` (already exists — verify accuracy).
**I. Integration tasks:** Verify `create_lab_executor` returns a real `Executor` instance; verify CLI `--mode lab` runs end-to-end.
**K. Security/safety:** Lab executor MUST only target IPs in the allowlist (default: 127.0.0.1, 172.28.0.2). Refuse all other targets with FAIL_NO_TARGET.
**M. Acceptance criteria:** `prototype/cli.py run --scenario success --mode lab --target 172.28.0.2` produces an OBSERVED outcome (not simulated); 91+ new tests pass.
**N. Demonstration criteria:** Run against emulator, show OBSERVED outcome in report.
**O. Definition of DONE:** Lab executor works against emulator; allowlist enforced; tests pass.
**P. Rollback:** Revert `prototype/lab_runner.py` and `prototype/tests/test_lab_runner.py`.
**Q. Agent:** Local lab / execution specialist (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** `pytest prototype/tests/test_lab_runner.py -q` passes; `git diff -- core/ decision_engine/core/` empty.

---

### PHASE 2 — LLM Assessment via CLI

**A. Objective:** Expose the existing `core/exploit_assessor.py` LLM scoring through the prototype CLI as an alternative to the deterministic assessor.
**B. Why required:** The research contribution (Gap-1) is the pre-execution quality scoring. Currently the prototype only uses the deterministic fallback. The LLM path exists in `core/` but is not wired to the engine.
**C. Prerequisite state:** Phase 0; `vapt_adapter.vapt_assess_fn(use_llm=True)` exists but is untested.
**D. Dependencies:** Phase 0.
**E. Components:** `prototype/cli.py`, `decision_engine/adapters/vapt_adapter.py`, `prototype/engine_integration.py`.
**F. Files affected:**
   - `prototype/cli.py` (add `--assessor llm|deterministic`)
   - `prototype/engine_integration.py` (use assessor flag)
   - `prototype/tests/test_llm_assessor.py` (new — mocked LLM)
**G. Must NOT modify:** `core/`, `decision_engine/core/`, `tests/`, `decision_engine/tests/`.
**H. Implementation tasks:**
   1. Add `--assessor {deterministic,llm}` flag to `prototype/cli.py` (default: deterministic).
   2. In `run_decision_scenario()`, branch: if `assessor="llm"`, pass `vapt_assess_fn(use_llm=True)` as `assess_fn`; else `deterministic_assessor`.
   3. Add a test that mocks `core.exploit_assessor.assess_exploit_quality` and verifies the LLM path is invoked and its `usability_rank` is mapped to `QualityRank`.
   4. Document in CLI help that `--assessor llm` requires `ollama serve` running.
**I. Integration tasks:** Verify the LLM assessor output (HIGH/MEDIUM/LOW) maps correctly to `decision_engine.core.schemas.QualityRank`.
**K. Security/safety:** LLM assessment is read-only (scores code, does not execute). No safety risk.
**M. Acceptance criteria:** `prototype/cli.py run --corpus --assessor llm` runs with real Ollama; mocked test passes.
**N. Demonstration criteria:** Show side-by-side deterministic vs LLM ranking for the same corpus.
**O. Definition of DONE:** LLM assessor wired and tested; deterministic remains default.
**P. Rollback:** Revert CLI flag and test file.
**Q. Agent:** LLM/assessment specialist (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** Mocked test passes; real Ollama path manually verified.

---

### PHASE 3 — VAPT Ingestion Pipeline

**A. Objective:** Build a scan-ingestion → finding-normalization → candidate-generation pipeline that feeds real scanner output into the decision engine.
**B. Why required:** The engine needs candidates. Currently candidates come only from hardcoded demo scenarios or the corpus adapter. Real scans (Nmap XML/JSON) must be normalized into `ActionCandidate[]`.
**C. Prerequisite state:** Phase 0; `core/scanner.py` parses scans into `Finding[]`; engine wants `ActionCandidate[]`.
**D. Dependencies:** Phase 0.
**E. Components:** `core/scanner.py` (read-only), `decision_engine/adapters/vapt_adapter.py`, new adapter module.
**F. Files affected:**
   - `decision_engine/adapters/scan_adapter.py` (new — Finding[] → ActionCandidate[])
   - `prototype/cli.py` (add `--scan <file>` option)
   - `prototype/tests/test_scan_adapter.py` (new)
**G. Must NOT modify:** `core/`, `decision_engine/core/`, `tests/`, `decision_engine/tests/`.
**H. Implementation tasks:**
   1. Create `decision_engine/adapters/scan_adapter.py` with `candidates_from_scan(file_path) → List[ActionCandidate]`.
   2. The adapter calls `core.scanner.process_scan()` (read-only import), then maps each `Finding` to an `ActionCandidate` with `id=cve`, `probability=epss_score`, `quality_rank=None` (to be filled by assessor).
   3. Add `--scan <file>` to `prototype/cli.py`: loads candidates from scan file instead of demo scenario.
   4. Add tests: feed `data/sample_scan.json` through the adapter, assert correct candidate count and IDs.
**I. Integration tasks:** Verify `--scan data/sample_scan.json` runs through the engine end-to-end.
**K. Security/safety:** Scan ingestion is read-only. No execution.
**M. Acceptance criteria:** `prototype/cli.py run --scan data/sample_scan.json` produces a ranked candidate list and runs the engine.
**N. Demonstration criteria:** Show a real scan file → ranked candidates → engine trace.
**O. Definition of DONE:** Scan adapter works; CLI accepts scan files.
**P. Rollback:** Revert new adapter file and CLI changes.
**Q. Agent:** VAPT/scanner specialist (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** Test passes; `git diff -- core/ decision_engine/core/` empty.

---

### PHASE 4 — Decision Orchestration & Checkpoint/Restore

**A. Objective:** Expose the engine's checkpoint/restore as a complete CLI workflow and improve the decision trace.
**B. Why required:** The engine has `save_checkpoint`/`load_checkpoint` but the prototype only wraps them thinly. A mentor demo needs: run → interrupt → resume.
**C. Prerequisite state:** Phase 0; engine checkpoint exists; `prototype/checkpoints.py` wraps it.
**D. Dependencies:** Phase 0.
**E. Components:** `prototype/checkpoints.py`, `prototype/cli.py`, `prototype/trace_formatter.py`.
**F. Files affected:**
   - `prototype/cli.py` (add `resume` subcommand)
   - `prototype/checkpoints.py` (extend with auto-checkpoint)
   - `prototype/tests/test_checkpoint_workflow.py` (new)
**G. Must NOT modify:** `core/`, `decision_engine/core/`.
**H. Implementation tasks:**
   1. Add `prototype/cli.py resume <checkpoint.json>` subcommand that loads and continues.
   2. Add `--checkpoint <path>` to `run` subcommand: auto-saves checkpoint on each pivot.
   3. Add test: run a scenario, save checkpoint, resume from it, verify state matches.
   4. Improve `trace_formatter.py` to show per-candidate attempt bars.
**I. Integration tasks:** Verify resume produces the same final state as a continuous run.
**K. Security/safety:** Checkpoint files are local JSON. No risk.
**M. Acceptance criteria:** `prototype/cli.py run --scenario failure_pivot --checkpoint ./ckpt.json` then `prototype/cli.py resume ./ckpt.json` completes correctly.
**N. Demonstration criteria:** Show interrupt/resume in demo.
**O. Definition of DONE:** Checkpoint/restore workflow works end-to-end.
**P. Rollback:** Revert CLI and test changes.
**Q. Agent:** Backend/API specialist (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** Test passes; manual resume works.

---

### PHASE 5 — Backend / API Layer

**A. Objective:** Build a FastAPI backend that runs decision engine jobs asynchronously and exposes REST endpoints.
**B. Why required:** The frontend needs a backend. Direct engine calls from a web UI block the request thread. A backend enables job queuing, status streaming, and report retrieval.
**C. Prerequisite state:** Phase 0-4 complete; engine is stable.
**D. Dependencies:** Phase 0.
**E. Components:** New `services/` directory.
**F. Files affected:**
   - `services/__init__.py` (new)
   - `services/api.py` (new — FastAPI app)
   - `services/jobs.py` (new — job state manager)
   - `services/schemas.py` (new — API request/response models)
   - `services/tests/test_api.py` (new)
   - `requirements.txt` (add fastapi, uvicorn)
**G. Must NOT modify:** `core/`, `decision_engine/core/`, `tests/`, `decision_engine/tests/`.
**H. Implementation tasks:**
   1. Create `services/api.py` with endpoints:
      - `POST /runs` — start a run (scenario + config), returns `run_id`
      - `GET /runs/{run_id}` — get status (running/completed + state)
      - `GET /runs/{run_id}/trace` — get decision trace (SSE for streaming)
      - `GET /runs/{run_id}/report` — get JSON report
      - `POST /runs/{run_id}/checkpoint` — save checkpoint
      - `POST /runs/{run_id}/resume` — resume from checkpoint
   2. Create `services/jobs.py`: in-memory job store (run_id → EngineState + status).
   3. Create `services/schemas.py`: Pydantic models for request/response.
   4. Add tests: start a run, poll status, retrieve report.
   5. Add safety gate: `/runs` rejects non-allowlisted targets.
**I. Integration tasks:** Verify the API can run a demo scenario end-to-end.
**K. Security/safety:** API must refuse targets not in allowlist. No arbitrary exploitation.
**M. Acceptance criteria:** `uvicorn services.api:app` starts; `curl localhost:8000/runs` with a scenario body returns a run_id and completes.
**N. Demonstration criteria:** Show API running a scenario.
**O. Definition of DONE:** API runs scenarios, streams status, retrieves reports.
**P. Rollback:** Revert `services/` directory.
**Q. Agent:** Backend/API specialist (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** `pytest services/tests/ -q` passes; manual API test works.

---

### PHASE 6 — Frontend / UI

**A. Objective:** Build a web UI that exposes the decision engine's run configuration, candidate ranking, execution state, pivot events, decision trace, and reports.
**B. Why required:** The mentor demo needs a visual interface. The old `app.py` is coupled to `core/` and does not show the decision engine.
**C. Prerequisite state:** Phase 5 (API exists) or Phase 0 (direct engine calls for simpler version).
**D. Dependencies:** Phase 5 (for API-backed UI) OR Phase 0 (for direct-call UI).
**E. Components:** New `frontend/` directory OR extend Streamlit.
**F. Files affected:**
   - `frontend/app.py` (new — Streamlit frontend for decision engine)
   - `frontend/components/` (new — optional, for richer UI)
   - `frontend/tests/test_frontend_smoke.py` (new)
**G. Must NOT modify:** `core/`, `decision_engine/core/`, `tests/`, `decision_engine/tests/`.
**H. Implementation tasks:**
   1. Create `frontend/app.py` (Streamlit) with:
      - Sidebar: scenario selector, max_attempts slider, mode (simulation/loopback/lab), assessor (deterministic/llm)
      - Main: "Run" button → calls engine (directly or via API)
      - Results: candidate ranking table, execution timeline, attempt counters, pivot event markers, final status, decision trace
      - Safety indicator: always-visible badge showing SIMULATED / OBSERVED / LAB
   2. Add download buttons for JSON + text reports.
   3. Add smoke test: verify the Streamlit app imports without error.
**I. Integration tasks:** Verify frontend can run all demo scenarios and display results.
**K. Safety:** UI must NOT have a free-text target input. Target selection is a dropdown (simulation, 127.0.0.1, 172.28.0.2).
**M. Acceptance criteria:** `streamlit run frontend/app.py` starts; running a scenario shows all required visualizations.
**N. Demonstration criteria:** Full mentor demo runs in the UI.
**O. Definition of DONE:** Frontend works for all scenarios.
**P. Rollback:** Revert `frontend/` directory.
**Q. Agent:** Frontend/UI specialist (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** Streamlit app starts; manual click-through works.

---

### PHASE 7 — Reporting Enhancement

**A. Objective:** Enhance reports to clearly distinguish SIMULATED vs OBSERVED vs LAB outcomes and include the decision trace.
**B. Why required:** The thesis must never overstate. Reports must be unambiguous about what was simulated vs what was observed.
**C. Prerequisite state:** Phase 0; `prototype/report_generator.py` exists.
**D. Dependencies:** Phase 0.
**E. Components:** `prototype/report_generator.py`, `core/report.py` (read-only reference).
**F. Files affected:**
   - `prototype/report_generator.py` (enhance)
   - `prototype/tests/test_report.py` (extend)
**G. Must NOT modify:** `core/`, `decision_engine/core/`.
**H. Implementation tasks:**
   1. Add a prominent "EVIDENCE TIER" section to reports: SIMULATION / CONTROLLED VALIDATION / OBSERVED (lab).
   2. Include the full decision trace in the report.
   3. Include per-candidate attempt counts and pivot events.
   4. Include the safety notice (existing — verify it's prominent).
   5. Add test: verify report contains the evidence tier label.
**I. Integration tasks:** Verify reports from `--mode lab` say OBSERVED; reports from `--mode simulation` say SIMULATED.
**K. Safety:** Reports must not describe simulated outcomes as real.
**M. Acceptance criteria:** Report from lab mode says "OBSERVED"; report from simulation says "SIMULATED".
**N. Demonstration criteria:** Show report with evidence tier.
**O. Definition of DONE:** Reports are unambiguous.
**P. Rollback:** Revert report changes.
**Q. Agent:** Documentation/research agent (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** Test passes; manual inspection of report.

---

### PHASE 8 — Evaluation / Benchmarks

**A. Objective:** Extend the benchmark suite to include new experiments (LLM assessor quality, lab observed runs, cross-domain).
**B. Why required:** The thesis needs evidence beyond the existing fair benchmark.
**C. Prerequisite state:** Phase 0; `decision_engine/benchmarks/` exists.
**D. Dependencies:** Phase 0.
**E. Components:** `decision_engine/benchmarks/`, `decision_engine/tests/`.
**F. Files affected:**
   - `decision_engine/benchmarks/llm_assessor_benchmark.py` (new)
   - `decision_engine/tests/test_llm_assessor_benchmark.py` (new)
**G. Must NOT modify:** `core/`, `decision_engine/core/`, `tests/`, `datasets/`.
**H. Implementation tasks:**
   1. Create `llm_assessor_benchmark.py`: runs the LLM assessor on the VAPT corpus, compares against corpus labels, computes accuracy.
   2. Add test: verify benchmark runs and produces accuracy metrics.
   3. Document: LLM assessor accuracy is NOT a thesis claim — it's an experimental observation.
**I. Integration tasks:** Verify benchmark runs offline (mocked LLM).
**K. Safety:** No external targets.
**M. Acceptance criteria:** Benchmark runs; produces accuracy number.
**N. Demonstration criteria:** Show LLM vs deterministic ranking comparison.
**O. Definition of DONE:** Benchmark exists and runs.
**P. Rollback:** Revert benchmark files.
**Q. Agent:** Research/evaluation specialist (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** Test passes; benchmark runs.

---

### PHASE 9 — Security / Safety Hardening

**A. Objective:** Audit all code paths for safety gaps and harden the allowlist, target validation, and report labeling.
**B. Why required:** Before any demo or external presentation, verify no path allows uncontrolled targeting.
**C. Prerequisite state:** All prior phases.
**D. Dependencies:** Phase 0-8.
**E. Components:** All `prototype/`, `services/`, `frontend/`.
**F. Files affected:**
   - `services/api.py` (add target allowlist middleware)
   - `frontend/app.py` (verify no free-text target)
   - `prototype/cli.py` (verify target validation)
   - `docs/project_management/SAFETY_AUDIT.md` (new)
**G. Must NOT modify:** `core/`, `decision_engine/core/`.
**H. Implementation tasks:**
   1. Audit every entry point that accepts a target/IP. Verify allowlist enforcement.
   2. Write `SAFETY_AUDIT.md` documenting the safety model.
   3. Add tests that assert non-allowlisted targets are refused.
**I. Integration tasks:** Verify all layers enforce the same allowlist.
**K. Safety:** This IS the safety phase.
**M. Acceptance criteria:** Non-allowlisted target → FAIL_NO_TARGET at every layer.
**N. Demonstration criteria:** Show safety audit doc.
**O. Definition of DONE:** Safety audit complete; all layers enforce allowlist.
**P. Rollback:** N/A (additive).
**Q. Agent:** Security/safety specialist (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** Tests pass; audit doc complete.

---

### PHASE 10 — End-to-End Validation

**A. Objective:** Run the complete workflow (scan → normalize → assess → rank → decide → execute → report) and verify it works.
**B. Why required:** The sum of parts must work together.
**C. Prerequisite state:** Phase 0-9.
**D. Dependencies:** All prior phases.
**E. Components:** All.
**F. Files affected:**
   - `docs/project_management/E2E_VALIDATION_REPORT.md` (new)
**G. Must NOT modify:** `core/`, `decision_engine/core/`.
**H. Implementation tasks:**
   1. Run the full pipeline with demo data (simulation mode).
   2. Run the full pipeline with demo data (lab mode, if Docker available).
   3. Document results, note any gaps.
**I. Integration tasks:** Verify all components connect.
**K. Safety:** Use only allowlisted targets.
**M. Acceptance criteria:** Full pipeline runs without errors.
**N. Demonstration criteria:** Show E2E run.
**O. Definition of DONE:** E2E validation report written.
**P. Rollback:** N/A.
**Q. Agent:** Testing/QA specialist (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** E2E report complete.

---

### PHASE 11 — Mentor Demonstration

**A. Objective:** Produce a deterministic, reproducible mentor demo script and rehearse it.
**B. Why required:** The thesis defense needs a polished demo.
**C. Prerequisite state:** Phase 0-10.
**D. Dependencies:** All prior phases.
**E. Components:** `prototype/`, `frontend/`, docs.
**F. Files affected:**
   - `docs/project_management/MENTOR_DEMO_SCRIPT.md` (new)
**G. Must NOT modify:** `core/`, `decision_engine/core/`.
**H. Implementation tasks:**
   1. Write the demo script (opening, scenario walkthrough, closing).
   2. Rehearse: run all scenarios, verify deterministic output.
   3. Prepare backup: if live demo fails, use pre-recorded output.
**I. Integration tasks:** Demo uses the real engine.
**K. Safety:** Demo uses simulation or lab only.
**M. Acceptance criteria:** Demo script written; rehearsal successful.
**N. Demonstration criteria:** This IS the demonstration.
**O. Definition of DONE:** Demo rehearsed and documented.
**P. Rollback:** N/A.
**Q. Agent:** Documentation/research agent (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** Demo script complete.

---

### PHASE 12 — Research Documentation

**A. Objective:** Integrate all findings, limitations, and methodology into thesis-ready documentation.
**B. Why required:** The thesis must be self-consistent.
**C. Prerequisite state:** Phase 0-11.
**D. Dependencies:** All prior phases.
**E. Components:** `docs/`.
**F. Files affected:**
   - `docs/project_management/THESIS_INTEGRATION_REPORT.md` (new)
**G. Must NOT modify:** `core/`, `decision_engine/core/`.
**H. Implementation tasks:**
   1. Consolidate evidence from all phases.
   2. Update limitations section.
   3. Verify all claims are backed by file:line references.
**I. Integration tasks:** Cross-reference with R1-R7 documents.
**K. Safety:** No overclaiming.
**M. Acceptance criteria:** Thesis integration report complete.
**N. Demonstration criteria:** N/A.
**O. Definition of DONE:** Documentation complete.
**P. Rollback:** N/A.
**Q. Agent:** Documentation/research agent (leaf).
**R. Agent:** Hermes verifies.
**S. Hermes verification:** Report complete.

---

## 6. PHASE DEPENDENCY GRAPH

```
Phase 0 (Verification)
  ├── Phase 1 (Lab Integration) ─────────────┐
  ├── Phase 2 (LLM Assessment) ─────────────┤
  ├── Phase 3 (VAPT Ingestion) ────────────┤
  ├── Phase 4 (Orchestration/Checkpoint) ───┤
  │                                          │
  │  Phase 0 complete → Phases 1,2,3,4 run in PARALLEL
  │                                          │
  ├── Phase 5 (Backend/API) ←── Phase 0 ────┤
  │       │                                  │
  │       └── Phase 6 (Frontend) ←───────────┤
  │                                          │
  ├── Phase 7 (Reporting) ←── Phase 0 ──────┤
  ├── Phase 8 (Evaluation) ←── Phase 0 ─────┤
  │                                          │
  │  Phases 5-8 run AFTER 1-4 merge ────────┘
  │
  ├── Phase 9 (Safety Hardening) ←── Phases 1-8
  ├── Phase 10 (E2E Validation) ←── Phase 9
  ├── Phase 11 (Mentor Demo) ←── Phase 10
  └── Phase 12 (Research Docs) ←── Phase 11
```

**PARALLEL BATCH 1 (after Phase 0):** Phases 1, 2, 3, 4
**PARALLEL BATCH 2 (after Batch 1):** Phases 5, 7, 8
**SEQUENTIAL:** Phase 6 after 5; Phase 9 after 1-8; Phase 10 after 9; Phase 11 after 10; Phase 12 after 11

---

## 7. AGENT RESPONSIBILITY MATRIX

| Agent | Role | Phases | File ownership |
|-------|------|--------|----------------|
| **A** (Lab/Execution) | Wire emulator, lab executor, real outcomes | 1 | `prototype/lab_runner.py`, `prototype/execution_layer.py`, `lab/` |
| **B** (LLM/Assessment) | Expose LLM assessor via CLI | 2 | `prototype/cli.py`, `prototype/engine_integration.py` |
| **C** (VAPT/Ingestion) | Scan adapter, Nmap pipeline | 3 | `decision_engine/adapters/scan_adapter.py`, `prototype/cli.py` |
| **D** (Orchestration) | Checkpoint/restore workflow | 4 | `prototype/cli.py`, `prototype/checkpoints.py`, `prototype/trace_formatter.py` |
| **E** (Backend) | FastAPI backend, job manager | 5 | `services/` |
| **F** (Frontend) | Streamlit/React UI | 6 | `frontend/` |
| **G** (Reporting) | Report enhancement | 7 | `prototype/report_generator.py` |
| **H** (Evaluation) | Benchmark extension | 8 | `decision_engine/benchmarks/llm_assessor_benchmark.py` |
| **I** (Safety) | Security audit, allowlist | 9 | `docs/SAFETY_AUDIT.md`, audit touches all |
| **J** (QA) | E2E validation | 10 | `docs/E2E_VALIDATION_REPORT.md` |
| **K** (Documentation) | Demo script, thesis integration | 11, 12 | `docs/MENTOR_DEMO_SCRIPT.md`, `docs/THESIS_INTEGRATION_REPORT.md** |

**File conflict avoidance:** `prototype/cli.py` is touched by agents B, C, D. Solution: merge sequentially (B → C → D) or assign one agent to own cli.py with others providing patches.

---

## 8. FILE OWNERSHIP MATRIX

| File | Owner | Phase | Writable by |
|------|-------|-------|-------------|
| `prototype/lab_runner.py` | A | 1 | A |
| `prototype/execution_layer.py` | A | 1 | A |
| `prototype/cli.py` | B/C/D | 2/3/4 | B, then C, then D (sequential) |
| `prototype/engine_integration.py` | B | 2 | B |
| `decision_engine/adapters/scan_adapter.py` | C | 3 | C |
| `prototype/checkpoints.py` | D | 4 | D |
| `prototype/trace_formatter.py` | D | 4 | D |
| `services/` | E | 5 | E |
| `frontend/` | F | 6 | F |
| `prototype/report_generator.py` | G | 7 | G |
| `decision_engine/benchmarks/llm_assessor_benchmark.py` | H | 8 | H |
| `docs/project_management/SAFETY_AUDIT.md` | I | 9 | I |
| `docs/project_management/E2E_VALIDATION_REPORT.md` | J | 10 | J |
| `docs/project_management/MENTOR_DEMO_SCRIPT.md` | K | 11 | K |
| `docs/project_management/THESIS_INTEGRATION_REPORT.md` | K | 12 | K |

**FROZEN (no agent may modify):**
- `core/` (all)
- `decision_engine/core/` (all)
- `decision_engine/adapters/vapt_adapter.py` (unless task explicitly allows)
- `decision_engine/benchmarks/fair_benchmark.py`, `fair_vapt_benchmark.py`, `agnostic_benchmark.py`
- `tests/` (all)
- `decision_engine/tests/` (all)
- `datasets/` (all)

---

## 9. GOLDEN BASELINE PROTECTION STRATEGY

| Artifact | Can be modified? | Conditions |
|----------|-----------------|------------|
| `decision_engine/core/` | **NO** | FROZEN. If a genuine bug is found, file an ENGINE CHANGE REQUEST (see below). |
| `decision_engine/adapters/vapt_adapter.py` | **YES** | Only by explicit task authorization. Log the change. |
| `decision_engine/benchmarks/` | **NO** (existing files) | New benchmark files may be added (Phase 8). Existing files frozen. |
| `tests/` | **NO** | FROZEN. New tests go in `prototype/tests/` or `services/tests/`. |
| `decision_engine/tests/` | **NO** | FROZEN. |
| `datasets/` | **NO** | FROZEN. |
| `core/` | **NO** | FROZEN. |

**ENGINE CHANGE REQUEST format** (if genuinely needed):
1. Reason: why the change is necessary
2. Evidence: test or benchmark showing the bug
3. Exact files and lines
4. Expected behavior after change
5. Regression impact: which tests/benchmarks change
6. Alternative approaches considered
7. Rollback plan
8. New baseline requirements (re-tag?)

No engine change is authorized without explicit user approval.

---

## 10. TESTING STRATEGY

| Level | Where | Minimum tests per phase |
|-------|-------|------------------------|
| Unit | `prototype/tests/`, `services/tests/` | Every new function has a test |
| Integration | `prototype/tests/test_integration.py` | Every new integration point |
| Engine regression | `decision_engine/tests/` | Must stay 16/16 |
| Baseline regression | `tests/` | Must stay 39/39 |
| API | `services/tests/test_api.py` | Every endpoint |
| UI | `frontend/tests/test_frontend_smoke.py` | Import + render smoke |
| Lab | `prototype/tests/test_lab_runner.py` | Mocked + real (if Docker) |
| Security | `prototype/tests/test_safety.py` | Allowlist enforcement |
| E2E | Manual + documented | Full pipeline run |
| Reproducibility | Benchmark re-run | Same seeds → same numbers |

**Cumulative regression matrix:**
- After Phase 0: 91/91
- After Phase 1: 91+ (lab tests)
- After Phase 2: 91+ (LLM tests)
- After Phase 3: 91+ (scan adapter tests)
- After Phase 4: 91+ (checkpoint tests)
- After Phase 5: 91+ (API tests)
- After Phase 6: 91+ (frontend smoke)
- After Phase 7: 91+ (report tests)
- After Phase 8: 91+ (benchmark tests)
- After Phase 9: 91+ (safety tests)

---

## 11. LOCAL LAB STRATEGY

**What exists:**
- Docker emulator at `lab/emulator/app.py` (Flask: /vuln, /fail, /health)
- Isolated bridge network `vuln-lab-network` (172.28.0.0/16, internal:true)
- Behavioral modules A.py (→/vuln), B.py (→/fail), C.py (→/fail)
- Resource limits, read-only rootfs, no-new-privileges

**What's missing:**
- Framework container on the same network
- Automated lab lifecycle (start emulator → run scenario → capture logs → stop)
- Integration with `prototype/cli.py --mode lab`

**Plan (Phase 1):**
1. Add a `framework` service to `lab/docker-compose.yml` (or run host-side with `--network vuln-lab-network`).
2. Create `prototype/lab_runner.py` with lifecycle management.
3. Enforce target allowlist: only 172.28.0.2 and 127.0.0.1 are valid lab targets.
4. Reset/reproducibility: `docker compose down && docker compose up -d` resets the lab.

---

## 12. LLM STRATEGY

**Where LLM adds value:**
- Gap-1 pre-execution assessment (scoring exploit usability)
- NOT in the engine core (keeps it deterministic and testable)
- NOT in the pivot logic (deterministic by design)

**For each LLM component, specify:**

| Component | Input | Output schema | Deterministic fallback | Validation | Failure handling | Hallucination control | Reproducibility | Metric |
|-----------|-------|---------------|------------------------|------------|------------------|----------------------|-----------------|--------|
| `exploit_assessor.assess_exploit_quality()` | CVE id + code sample | `ExploitAssessment` (Pydantic, enum-constrained) | `deterministic_assessor` (priority-based) | Pydantic schema + enum constraints | Exception → fallback MEDIUM | Structured output (not free text); cross-check with corpus label | temperature=0.1; same model+prompt → same output | Agreement rate with corpus labels |

**LLM is NOT required for:** ranking (deterministic formula), pivot (deterministic threshold), execution (ground-truth or observed), reporting (template-based).

---

## 13. VAPT / TOOL INTEGRATION STRATEGY

```
INPUT (Nmap XML/JSON, custom JSON)
  → NORMALIZATION (core/scanner.py → Finding[])
  → CANDIDATE GENERATION (scan_adapter.py → ActionCandidate[])
  → ASSESSMENT (LLM or deterministic → QualityRank)
  → RANKING (engine: priority_score = prob * quality)
  → DECISION (engine: assess → execute → pivot)
  → CONTROLLED EXECUTION (simulation | loopback | lab)
  → OBSERVATION (Outcome + detail)
  → FEEDBACK (engine state update, attempt_count++, pivot if threshold)
  → TERMINATION (COMPLETED or SUCCESS)
  → TRACE (engine logs)
  → REPORT (JSON + text + evidence tier)
```

**Component ownership:**
- INPUT: `core/scanner.py` (frozen)
- NORMALIZATION: `core/scanner.py` (frozen)
- CANDIDATE GENERATION: `decision_engine/adapters/scan_adapter.py` (Phase 3)
- ASSESSMENT: `core/exploit_assessor.py` (frozen) + `vapt_adapter.py` (boundary)
- RANKING: `decision_engine/core/engine.py` (frozen)
- DECISION: `decision_engine/core/engine.py` (frozen)
- EXECUTION: `prototype/execution_layer.py` (Phase 1)
- OBSERVATION: `decision_engine/core/executor.py` (frozen)
- FEEDBACK: `decision_engine/core/engine.py` (frozen)
- TRACE: `prototype/trace_formatter.py` (Phase 4)
- REPORT: `prototype/report_generator.py` (Phase 7)

---

## 14. BACKEND STRATEGY

**Does a backend exist?** No.

**Plan (Phase 5):** Build a FastAPI backend under `services/`.

**API boundaries:**
- `POST /runs` — start a run
- `GET /runs/{run_id}` — get status
- `GET /runs/{run_id}/trace` — SSE stream of decision trace
- `GET /runs/{run_id}/report` — get JSON report
- `POST /runs/{run_id}/checkpoint` — save checkpoint
- `POST /runs/{run_id}/resume` — resume from checkpoint

**Run lifecycle:** created → running → completed | failed | paused

**Job state:** In-memory dict (run_id → {status, state, created_at, updated_at})

**Streaming:** SSE for real-time trace updates

**Report retrieval:** Same as prototype report_generator output

**Error handling:** 400 for invalid input, 404 for missing run, 500 for engine error (with detail)

**Security controls:** Target allowlist enforced at API layer; no arbitrary exploitation

---

## 15. FRONTEND STRATEGY

**Does a frontend exist?** `app.py` (old, coupled to core/, does not show decision engine).

**Plan (Phase 6):** Build a new Streamlit frontend under `frontend/`.

**Why Streamlit (not React):**
- Already in requirements.txt
- Faster to build for a research prototype
- The user knows it
- No build step

**UI must expose:**
- Run configuration (scenario, max_attempts, mode, assessor)
- Target/lab selection (dropdown, not free-text)
- Candidate list with scores
- Selected path
- Execution state
- Retry counter
- Pivot events
- Decision trace
- Findings
- Report
- Safety/mode indicator (always visible)

---

## 16. REPORTING STRATEGY

**Existing:** `prototype/report_generator.py` (JSON + text), `core/report.py` (JSON + PDF, old).

**Plan (Phase 7):** Enhance `prototype/report_generator.py` to include:
- Evidence tier (SIMULATED / CONTROLLED VALIDATION / OBSERVED)
- Full decision trace
- Per-candidate attempt counts
- Pivot event markers
- Safety notice (prominent)
- Clear labeling of what was simulated vs observed

**Report formats:** JSON (machine-readable) + text (human-readable). PDF optional (via reportlab, already in requirements).

---

## 17. RESEARCH / EVALUATION STRATEGY

**Experiments that demonstrate the contribution:**

| Experiment | What it shows | How |
|------------|---------------|-----|
| Baseline ranking | Priority ordering works | Compare DUMB vs PRIORITY-ONLY |
| Intelligent ranking | Gap-1 + Gap-2 together | Compare DUMB vs SMART |
| Bounded retry | No infinite loops | Show attempt_count ≤ max_attempts |
| Pivot behavior | Abandon after threshold | Show pivot events in trace |
| Outcome-aware adaptation | Engine reacts to real outcomes | Lab run: success vs failure paths |
| LLM vs deterministic | LLM assessment quality | Phase 8 benchmark |
| Ablations | Gap-1 vs Gap-2 contribution | 4-agent fair benchmark (existing) |
| Reproducibility | Same seeds → same results | Re-run benchmarks |
| Failure cases | When does the engine fail? | Document |

**Measurable metrics:**
- Attempts per successful validation (lower is better)
- Unnecessary attempts (wasted_requests, lower is better)
- Pivot efficiency (pivot_events / total_pivots_possible)
- Ranking quality (Spearman rho between priority and ground truth)
- Decision latency (wall-clock per candidate — NOT a thesis claim, just observational)
- Reproducibility (same seeds → same numbers)

**Only use metrics justified by the actual system.** Do NOT claim speedup, universal accuracy, or real-world superiority.

---

## 18. SECURITY / SAFETY STRATEGY

**Principles:**
1. Default mode is simulation. No network activity.
2. Lab mode targets only allowlisted IPs (127.0.0.1, 172.28.0.2).
3. No free-text target input in any UI or API.
4. No real exploit execution in default mode.
5. Reports always label evidence tier.
6. danger_mode (opt-in, isolated lab only) requires explicit target_allowlist.

**Safety boundaries by layer:**
- CLI: `--target` validated against allowlist
- API: middleware rejects non-allowlisted targets
- Frontend: dropdown only, no free-text
- Lab: isolated Docker network, no egress

---

## 19. CHECKPOINT / TAG STRATEGY

**Naming convention:** `checkpoint-phase-{NN}-{short-desc}`

| Tag | Phase | When |
|-----|-------|------|
| `checkpoint-phase-00-baseline` | 0 | After committing prototype/ |
| `checkpoint-phase-01-lab` | 1 | After lab integration |
| `checkpoint-phase-02-llm` | 2 | After LLM CLI |
| `checkpoint-phase-03-ingestion` | 3 | After scan adapter |
| `checkpoint-phase-04-checkpoint` | 4 | After checkpoint workflow |
| `checkpoint-phase-05-api` | 5 | After backend |
| `checkpoint-phase-06-frontend` | 6 | After frontend |
| `checkpoint-phase-07-reporting` | 7 | After reporting |
| `checkpoint-phase-08-evaluation` | 8 | After benchmarks |
| `checkpoint-phase-09-safety` | 9 | After safety audit |
| `checkpoint-phase-10-e2e` | 10 | After E2E validation |
| `checkpoint-phase-11-demo` | 11 | After demo rehearsal |
| `checkpoint-phase-12-docs` | 12 | After thesis integration |

**Each checkpoint includes:**
- `git commit` (atomic, one task)
- `git tag` (named as above)
- Tests pass (91+ count)
- `git diff -- core/ decision_engine/core/` empty
- Demo command documented
- Rollback command: `git revert HEAD` or `git checkout <prev-tag>`

---

## 20. FINAL MENTOR DEMONSTRATION PLAN

**Deterministic demo (simulation):**
1. Open `frontend/app.py` (or CLI)
2. Scenario: "Repeated failure → pivot"
3. Show: candidate ranking (DEMO-DEAD-END high priority but fails)
4. Show: execution (2 attempts, both FAIL_TIMEOUT)
5. Show: pivot event (threshold reached, redirect to DEMO-WORKER)
6. Show: success on DEMO-WORKER
7. Show: complete decision trace
8. Show: final report with evidence tier = SIMULATED

**Observed demo (lab, if Docker available):**
1. Start emulator: `cd lab && docker compose up -d`
2. Run: `prototype/cli.py run --scenario success --mode lab --target 172.28.0.2`
3. Show: OBSERVED outcome (not simulated)
4. Show: report with evidence tier = OBSERVED

**Mentor sees:**
1. findings/candidates (ranked table)
2. why candidates were ranked (priority_score breakdown)
3. selected candidate (highest priority)
4. execution (attempt timeline)
5. observed result (outcome + detail)
6. failure (if applicable)
7. retry (attempt counter)
8. bounded attempt count (threshold)
9. pivot (event marker)
10. alternative candidate (next in ranking)
11. success (final outcome)
12. complete decision trace (all engine logs)
13. final report (JSON + text)

**The demonstration must clearly distinguish:**
- SIMULATION (default, outcomes from ground_truth labels)
- CONTROLLED VALIDATION (offline ablations)
- OBSERVED (lab, real HTTP to emulator)

---

## 21. RISKS AND MITIGATIONS

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Docker unavailable for lab | Medium | Can't show OBSERVED | Use loopback (127.0.0.1) or pre-recorded lab output |
| Ollama down for LLM demo | Medium | Can't show LLM assessment | Use deterministic fallback; show mocked LLM test |
| Prototype/ uncommitted → lost | Low (now committed in Phase 0) | Loss of working code | Phase 0 commits it |
| Agent modifies frozen code | Medium | Breaks baseline | Hermes verifies `git diff` on frozen dirs |
| Two agents edit same file | Medium | Merge conflict | Sequential assignment; file ownership matrix |
| Overclaiming in reports | Medium | Thesis rejection | Evidence tier labeling; claim register (R3) |
| Scope creep | High | Never finishes | Strict phase boundaries; definition of done |
| Engine bug discovered | Low | Blocks progress | ENGINE CHANGE REQUEST process |

---

## 22. ESTIMATED IMPLEMENTATION COMPLEXITY PER PHASE

| Phase | Effort | Complexity | Risk |
|-------|--------|------------|------|
| 0 — Verification | Low | Trivial | None |
| 1 — Lab Integration | Low-Medium | Docker networking | Docker availability |
| 2 — LLM Assessment | Low | Flag wiring | Ollama availability |
| 3 — VAPT Ingestion | Medium | Adapter pattern | Scan format edge cases |
| 4 — Orchestration | Low | CLI extension | None |
| 5 — Backend/API | Medium | FastAPI + async | Streaming complexity |
| 6 — Frontend | Medium-High | Streamlit layout | UI polish |
| 7 — Reporting | Low | Template changes | None |
| 8 — Evaluation | Medium | Benchmark design | Statistical validity |
| 9 — Safety | Low | Audit + tests | None |
| 10 — E2E | Low | Documentation | Integration bugs |
| 11 — Demo | Low | Script + rehearsal | Live demo risk |
| 12 — Docs | Medium | Writing | None |

---

## 23. EXACT COPY-PASTEABLE PROMPTS FOR EACH AI AGENT TASK

=== PROMPT 1: PHASE 0 — BASELINE COMMIT ===

ROLE: Repository operations agent.
PROJECT CONTEXT: AI VAPT framework at /home/vinit/ai_vapt_framework. The prototype/ directory (mentor-facing CLI + tests) exists but is untracked. We need to commit it as the baseline before any new work.
CURRENT STATE: 91/91 tests passing (39 TRACK0 + 16 TRACK1 + 36 prototype). prototype/ is untracked (git status shows ?? prototype/).
OBJECTIVE: Commit prototype/ and this Master Plan, then tag the baseline.
FILE OWNERSHIP: You may CREATE/ADD prototype/ and docs/project_management/MASTER_IMPLEMENTATION_PLAN.md.
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/, any .py file.
REPOSITORY SAFETY CHECK:
  1. Run: source venv/bin/activate && python -m pytest tests/ decision_engine/tests/ prototype/tests/ -q
  2. Confirm 91 passed.
  3. Run: git diff -- core/ decision_engine/core/ tests/ decision_engine/tests/ datasets/ decision_engine/benchmarks/
  4. Confirm empty diff.
IMPLEMENTATION TASKS:
  1. Run the safety checks above.
  2. git add prototype/ docs/project_management/MASTER_IMPLEMENTATION_PLAN.md
  3. git commit -m "PROTOTYPE: commit existing mentor prototype (36 tests) + master plan"
  4. git tag checkpoint-phase-00-baseline
  5. git log --oneline -3 && git tag -l
INTEGRATION CONTRACT: None (documentation/ops only).
TEST REQUIREMENTS: pytest tests/ decision_engine/tests/ prototype/tests/ -q → 91 passed.
REGRESSION REQUIREMENTS: 91/91 must remain unchanged.
SECURITY REQUIREMENTS: None.
ACCEPTANCE CRITERIA: git log shows the commit; git tag shows checkpoint-phase-00-baseline; 91 tests pass.
FINAL REPORT FORMAT: "Committed: <commit hash>. Tag: checkpoint-phase-00-baseline. Tests: 91/91. Frozen diff: empty."
STOP CONDITIONS: If tests fail or frozen diff is non-empty, STOP and report.
WHAT TO RETURN: commit hash, tag name, test count, confirmation of empty frozen diff.

=== PROMPT 2: PHASE 1 — LAB INTEGRATION ===

ROLE: Local lab / execution specialist.
PROJECT CONTEXT: AI VAPT framework. The decision engine (decision_engine/core/) is frozen. The prototype/ wraps it. The lab/ directory has a Docker emulator (Flask: /vuln→"VULNERABLE", /fail→"NOT_VULNERABLE") on an isolated network (172.28.0.0/16). We need to wire the engine's "real" mode to produce OBSERVED outcomes against the emulator.
CURRENT STATE: prototype/execution_layer.py has create_simulation_executor() and create_executor(mode, execute_fn). The emulator exists but is not connected to the framework.
OBJECTIVE: Create a lab executor that hits the emulator and maps HTTP responses to Outcome values.
FILE OWNERSHIP: You may CREATE prototype/lab_runner.py and prototype/tests/test_lab_runner.py. You may MODIFY prototype/execution_layer.py and prototype/cli.py.
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/.
REPOSITORY SAFETY CHECK:
  1. Run: source venv/bin/activate && python -m pytest tests/ decision_engine/tests/ prototype/tests/ -q
  2. Confirm 91 passed.
  3. Run: git diff -- core/ decision_engine/core/ tests/ decision_engine/tests/ datasets/ decision_engine/benchmarks/
  4. Confirm empty diff.
IMPLEMENTATION TASKS:
  1. Create prototype/lab_runner.py with:
     - function run_lab_scenario(target: str, port: int, endpoint: str) -> Outcome
     - performs HTTP GET to http://{target}:{port}{endpoint}
     - maps "VULNERABLE" in body → Outcome.SUCCESS
     - maps "NOT_VULNERABLE" / other → Outcome.FAIL_TIMEOUT
     - enforces allowlist: only 127.0.0.1 and 172.28.0.2 are valid targets; others raise ValueError
  2. Add create_lab_executor(target: str, port: int) → Executor to prototype/execution_layer.py:
     - returns Executor(mode="real", execute_fn=<fn that calls run_lab_scenario>)
     - the execute_fn takes an ActionCandidate and returns an ExecutionResult
  3. Add --mode lab to prototype/cli.py with --target (default 172.28.0.2) and --port (default 8080).
  4. Add tests in prototype/tests/test_lab_runner.py:
     - mock socket/HTTP and assert correct Outcome mapping
     - assert non-allowlisted target raises ValueError
     - assert create_lab_executor returns a real Executor instance
INTEGRATION CONTRACT: create_lab_executor must return decision_engine.core.executor.Executor; CLI --mode lab must run end-to-end.
TEST REQUIREMENTS: pytest prototype/tests/test_lab_runner.py -q → all pass.
REGRESSION REQUIREMENTS: 91/91 existing tests must remain passing.
SECURITY REQUIREMENTS: Lab executor MUST refuse non-allowlisted targets. Default allowlist: 127.0.0.1, 172.28.0.2.
ACCEPTANCE CRITERIA: create_lab_executor works; allowlist enforced; tests pass.
FINAL REPORT FORMAT: "Lab executor created. Tests: X new, 91 existing. Allowlist: enforced. Frozen diff: empty."
STOP CONDITIONS: If frozen diff becomes non-empty or existing tests fail, STOP.
WHAT TO RETURN: files created/modified, test count, allowlist verification.

=== PROMPT 3: PHASE 2 — LLM ASSESSMENT VIA CLI ===

ROLE: LLM/assessment specialist.
PROJECT CONTEXT: AI VAPT framework. core/exploit_assessor.py provides LLM-based usability scoring. decision_engine/adapters/vapt_adapter.py has vapt_assess_fn(use_llm=True) that delegates to it. The prototype currently only uses the deterministic assessor.
CURRENT STATE: prototype/engine_integration.py calls run_decision_scenario() with assess_fn=deterministic_assessor. The LLM path exists but is not wired to the CLI.
OBJECTIVE: Expose the LLM assessor through the prototype CLI as an alternative to deterministic.
FILE OWNERSHIP: You may MODIFY prototype/cli.py, prototype/engine_integration.py. You may CREATE prototype/tests/test_llm_assessor.py.
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/.
REPOSITORY SAFETY CHECK: Run pytest tests/ decision_engine/tests/ prototype/tests/ -q → confirm 91+ passed. Confirm frozen diff empty.
IMPLEMENTATION TASKS:
  1. Add --assessor {deterministic,llm} flag to prototype/cli.py (default: deterministic).
  2. In run_decision_scenario() (prototype/engine_integration.py), branch on assessor:
     - "llm" → pass vapt_assess_fn(use_llm=True) as assess_fn
     - "deterministic" → pass deterministic_assessor
  3. Add test in prototype/tests/test_llm_assessor.py:
     - mock core.exploit_assessor.assess_exploit_quality to return a fixed ExploitAssessment
     - verify the LLM path is invoked and its usability_rank maps to QualityRank
     - verify deterministic path does NOT invoke the LLM
INTEGRATION CONTRACT: vapt_assess_fn(use_llm=True) returns a Callable[[ActionCandidate], QualityRank]; verify the mapping chain.
TEST REQUIREMENTS: pytest prototype/tests/test_llm_assessor.py -q → all pass.
REGRESSION REQUIREMENTS: 91+ existing tests must remain passing.
SECURITY REQUIREMENTS: LLM assessment is read-only (scores code, does not execute). No safety risk.
ACCEPTANCE CRITERIA: --assessor llm works with mocked LLM; deterministic remains default.
FINAL REPORT FORMAT: "LLM assessor wired. Tests: X new, 91+ existing. Frozen diff: empty."
STOP CONDITIONS: If frozen diff becomes non-empty or existing tests fail, STOP.
WHAT TO RETURN: files modified, test count, mapping verification.

=== PROMPT 4: PHASE 3 — VAPT INGESTION ===

ROLE: VAPT/scanner specialist.
PROJECT CONTEXT: AI VAPT framework. core/scanner.py parses Nmap XML/JSON and custom JSON into Finding[] with EPSS enrichment. The decision engine wants ActionCandidate[]. We need an adapter.
CURRENT STATE: core/scanner.py is frozen and outputs Finding[]. decision_engine/adapters/vapt_adapter.py builds candidates from the corpus. No adapter exists for scan output.
OBJECTIVE: Build a scan-adapter that converts Finding[] → ActionCandidate[] and wire it to the CLI.
FILE OWNERSHIP: You may CREATE decision_engine/adapters/scan_adapter.py and prototype/tests/test_scan_adapter.py. You may MODIFY prototype/cli.py.
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/.
REPOSITORY SAFETY CHECK: Run pytest tests/ decision_engine/tests/ prototype/tests/ -q → confirm 91+ passed. Confirm frozen diff empty.
IMPLEMENTATION TASKS:
  1. Create decision_engine/adapters/scan_adapter.py with:
     - candidates_from_scan(file_path: str) → List[ActionCandidate]
     - calls core.scanner.process_scan(file_path) (read-only import)
     - maps each Finding to ActionCandidate(id=cve, probability=epss_score, quality_rank=None)
  2. Add --scan <file> option to prototype/cli.py: loads candidates from scan file.
  3. Add tests in prototype/tests/test_scan_adapter.py:
     - feed data/sample_scan.json through the adapter
     - assert correct candidate count and IDs
     - assert probability matches EPSS (or 0.0 if offline)
INTEGRATION CONTRACT: scan_adapter imports core.scanner read-only; outputs ActionCandidate[] compatible with run_engine().
TEST REQUIREMENTS: pytest prototype/tests/test_scan_adapter.py -q → all pass.
REGRESSION REQUIREMENTS: 91+ existing tests must remain passing.
SECURITY REQUIREMENTS: Scan ingestion is read-only. No execution.
ACCEPTANCE CRITERIA: candidates_from_scan works; CLI --scan runs end-to-end.
FINAL REPORT FORMAT: "Scan adapter created. Tests: X new, 91+ existing. Frozen diff: empty."
STOP CONDITIONS: If frozen diff becomes non-empty or existing tests fail, STOP.
WHAT TO RETURN: files created/modified, test count, sample output.

=== PROMPT 5: PHASE 4 — CHECKPOINT/RESTORE WORKFLOW ===

ROLE: Orchestration specialist.
PROJECT CONTEXT: AI VAPT framework. decision_engine/core/engine.py has save_checkpoint/load_checkpoint. prototype/checkpoints.py wraps them thinly. We need a full CLI workflow: run → interrupt → resume.
CURRENT STATE: Checkpoint functions exist but are not exposed as a complete CLI workflow.
OBJECTIVE: Add resume subcommand and auto-checkpoint to the CLI.
FILE OWNERSHIP: You may MODIFY prototype/cli.py, prototype/checkpoints.py, prototype/trace_formatter.py. You may CREATE prototype/tests/test_checkpoint_workflow.py.
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/.
REPOSITORY SAFETY CHECK: Run pytest tests/ decision_engine/tests/ prototype/tests/ -q → confirm 91+ passed. Confirm frozen diff empty.
IMPLEMENTATION TASKS:
  1. Add prototype/cli.py resume <checkpoint.json> subcommand that loads and continues.
  2. Add --checkpoint <path> to run subcommand: auto-saves checkpoint on each pivot.
  3. Add test in prototype/tests/test_checkpoint_workflow.py:
     - run a scenario with --checkpoint, verify file is created
     - resume from it, verify final state matches a continuous run
  4. Improve trace_formatter.py to show per-candidate attempt bars (e.g., "DEMO-DEAD-END: [██] 2/2").
INTEGRATION CONTRACT: resume uses engine's load_checkpoint + build_graph(entry=...); verify state round-trip.
TEST REQUIREMENTS: pytest prototype/tests/test_checkpoint_workflow.py -q → all pass.
REGRESSION REQUIREMENTS: 91+ existing tests must remain passing.
SECURITY REQUIREMENTS: Checkpoint files are local JSON. No risk.
ACCEPTANCE CRITERIA: resume works; auto-checkpoint works; trace shows attempt bars.
FINAL REPORT FORMAT: "Checkpoint workflow complete. Tests: X new, 91+ existing. Frozen diff: empty."
STOP CONDITIONS: If frozen diff becomes non-empty or existing tests fail, STOP.
WHAT TO RETURN: files modified, test count, resume verification.

=== PROMPT 6: PHASE 5 — BACKEND/API ===

ROLE: Backend/API specialist.
PROJECT CONTEXT: AI VAPT framework. The decision engine runs synchronously. A web frontend needs a backend for async job management.
CURRENT STATE: No backend exists.
OBJECTIVE: Build a FastAPI backend under services/ with run/status/trace/report endpoints.
FILE OWNERSHIP: You may CREATE services/ (all files). You may MODIFY requirements.txt.
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/, prototype/.
REPOSITORY SAFETY CHECK: Run pytest tests/ decision_engine/tests/ prototype/tests/ -q → confirm 91+ passed. Confirm frozen diff empty.
IMPLEMENTATION TASKS:
  1. Create services/api.py with FastAPI endpoints:
     - POST /runs (scenario + config) → {run_id}
     - GET /runs/{run_id} → {status, state}
     - GET /runs/{run_id}/trace → SSE stream
     - GET /runs/{run_id}/report → JSON report
     - POST /runs/{run_id}/checkpoint → save
     - POST /runs/{run_id}/resume → resume
  2. Create services/jobs.py: in-memory job store.
  3. Create services/schemas.py: Pydantic request/response models.
  4. Create services/tests/test_api.py: test each endpoint.
  5. Add fastapi and uvicorn to requirements.txt.
  6. Add target allowlist middleware (refuse non-allowlisted).
INTEGRATION CONTRACT: services/api.py imports decision_engine.core.engine.run_engine; does NOT modify it.
TEST REQUIREMENTS: pytest services/tests/ -q → all pass.
REGRESSION REQUIREMENTS: 91+ existing tests must remain passing.
SECURITY REQUIREMENTS: API must refuse non-allowlisted targets.
ACCEPTANCE CRITERIA: uvicorn services.api:app starts; endpoints work.
FINAL REPORT FORMAT: "API created. Endpoints: 6. Tests: X new, 91+ existing. Frozen diff: empty."
STOP CONDITIONS: If frozen diff becomes non-empty or existing tests fail, STOP.
WHAT TO RETURN: files created, endpoint list, test count.

=== PROMPT 7: PHASE 6 — FRONTEND ===

ROLE: Frontend/UI specialist.
PROJECT CONTEXT: AI VAPT framework. app.py (old) is coupled to core/ and doesn't show the decision engine. We need a new UI.
CURRENT STATE: No frontend for the decision engine.
OBJECTIVE: Build a Streamlit frontend under frontend/ that exposes the decision engine.
FILE OWNERSHIP: You may CREATE frontend/ (all files).
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/, prototype/, services/.
REPOSITORY SAFETY CHECK: Run pytest tests/ decision_engine/tests/ prototype/tests/ -q → confirm 91+ passed. Confirm frozen diff empty.
IMPLEMENTATION TASKS:
  1. Create frontend/app.py (Streamlit) with:
     - Sidebar: scenario selector, max_attempts slider, mode (simulation/loopback/lab), assessor (deterministic/llm)
     - Target selection: dropdown (simulation, 127.0.0.1, 172.28.0.2) — NO free-text
     - Main: "Run" button → calls engine (via services/api.py or directly)
     - Results: candidate ranking table, execution timeline, attempt counters, pivot markers, final status, decision trace
     - Safety indicator: always-visible badge (SIMULATED/OBSERVED/LAB)
     - Download buttons for JSON + text reports
  2. Create frontend/tests/test_frontend_smoke.py: verify import without error.
INTEGRATION CONTRACT: frontend imports decision_engine.core.engine.run_engine (or services/api.py); does NOT modify engine.
TEST REQUIREMENTS: pytest frontend/tests/ -q → import passes.
REGRESSION REQUIREMENTS: 91+ existing tests must remain passing.
SECURITY REQUIREMENTS: NO free-text target input. Dropdown only.
ACCEPTANCE CRITERIA: streamlit run frontend/app.py starts; all visualizations render.
FINAL REPORT FORMAT: "Frontend created. Pages: 1. Tests: X smoke. Frozen diff: empty."
STOP CONDITIONS: If frozen diff becomes non-empty or existing tests fail, STOP.
WHAT TO RETURN: files created, screenshot description, test count.

=== PROMPT 8: PHASE 7 — REPORTING ENHANCEMENT ===

ROLE: Reporting specialist.
PROJECT CONTEXT: AI VAPT framework. prototype/report_generator.py produces JSON + text reports. They need to clearly distinguish evidence tiers.
CURRENT STATE: Reports include a safety notice but not a prominent evidence tier section.
OBJECTIVE: Enhance reports to include evidence tier, decision trace, and per-candidate attempt counts.
FILE OWNERSHIP: You may MODIFY prototype/report_generator.py. You may CREATE/EXTEND prototype/tests/test_report.py.
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/.
REPOSITORY SAFETY CHECK: Run pytest tests/ decision_engine/tests/ prototype/tests/ -q → confirm 91+ passed. Confirm frozen diff empty.
IMPLEMENTATION TASKS:
  1. Add "EVIDENCE TIER" section to reports: SIMULATION / CONTROLLED VALIDATION / OBSERVED.
  2. Include the full decision trace in the report.
  3. Include per-candidate attempt counts and pivot events.
  4. Verify the safety notice is prominent.
  5. Add test: verify report contains the evidence tier label.
INTEGRATION CONTRACT: report_generator consumes engine state; does not modify engine.
TEST REQUIREMENTS: pytest prototype/tests/test_report.py -q → all pass.
REGRESSION REQUIREMENTS: 91+ existing tests must remain passing.
SECURITY REQUIREMENTS: Reports must not describe simulated outcomes as real.
ACCEPTANCE CRITERIA: Lab mode report says OBSERVED; simulation says SIMULATED.
FINAL REPORT FORMAT: "Reports enhanced. Evidence tier: present. Tests: X new, 91+ existing. Frozen diff: empty."
STOP CONDITIONS: If frozen diff becomes non-empty or existing tests fail, STOP.
WHAT TO RETURN: files modified, test count, sample report excerpt.

=== PROMPT 9: PHASE 8 — EVALUATION ===

ROLE: Research/evaluation specialist.
PROJECT CONTEXT: AI VAPT framework. decision_engine/benchmarks/ has fair_benchmark.py (4-agent ablation). We need an LLM assessor benchmark.
CURRENT STATE: No benchmark for LLM assessor quality.
OBJECTIVE: Create a benchmark that measures LLM assessor agreement with corpus labels.
FILE OWNERSHIP: You may CREATE decision_engine/benchmarks/llm_assessor_benchmark.py and decision_engine/tests/test_llm_assessor_benchmark.py.
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, datasets/, decision_engine/benchmarks/fair_benchmark.py, fair_vapt_benchmark.py, agnostic_benchmark.py.
REPOSITORY SAFETY CHECK: Run pytest tests/ decision_engine/tests/ prototype/tests/ -q → confirm 91+ passed. Confirm frozen diff empty.
IMPLEMENTATION TASKS:
  1. Create llm_assessor_benchmark.py:
     - runs LLM assessor on each CVE in the corpus
     - compares predicted usability_rank with corpus label
     - computes accuracy, per-class precision/recall
     - outputs JSON summary
  2. Add test in test_llm_assessor_benchmark.py:
     - mock LLM to return fixed assessments
     - verify accuracy computation
  3. Document: LLM assessor accuracy is an experimental observation, NOT a thesis claim.
INTEGRATION CONTRACT: benchmark imports core.exploit_assessor read-only; does not modify it.
TEST REQUIREMENTS: pytest decision_engine/tests/test_llm_assessor_benchmark.py -q → all pass.
REGRESSION REQUIREMENTS: 91+ existing tests must remain passing.
SECURITY REQUIREMENTS: No external targets.
ACCEPTANCE CRITERIA: Benchmark runs; produces accuracy number.
FINAL REPORT FORMAT: "LLM benchmark created. Tests: X new, 91+ existing. Frozen diff: empty."
STOP CONDITIONS: If frozen diff becomes non-empty or existing tests fail, STOP.
WHAT TO RETURN: files created, test count, sample accuracy output.

=== PROMPT 10: PHASE 9 — SAFETY AUDIT ===

ROLE: Security/safety specialist.
PROJECT CONTEXT: AI VAPT framework. Multiple layers (CLI, API, frontend) accept targets. We need to verify all enforce the allowlist.
CURRENT STATE: Target validation exists in core/executor.py (danger_mode allowlist) but the prototype/API/frontend layers may not all enforce it.
OBJECTIVE: Audit all code paths for safety gaps and document the safety model.
FILE OWNERSHIP: You may CREATE docs/project_management/SAFETY_AUDIT.md. You may CREATE prototype/tests/test_safety.py, services/tests/test_safety.py.
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/.
REPOSITORY SAFETY CHECK: Run pytest tests/ decision_engine/tests/ prototype/tests/ -q → confirm 91+ passed. Confirm frozen diff empty.
IMPLEMENTATION TASKS:
  1. Audit every entry point that accepts a target/IP (CLI, API, frontend, lab_runner).
  2. Verify allowlist enforcement at each layer.
  3. Write docs/project_management/SAFETY_AUDIT.md documenting:
     - The safety model (simulation default, lab allowlist, no free-text targets)
     - Each layer's enforcement
     - Known limitations
  4. Add tests that assert non-allowlisted targets are refused.
INTEGRATION CONTRACT: Safety tests verify behavior; they don't change the engine.
TEST REQUIREMENTS: pytest prototype/tests/test_safety.py services/tests/test_safety.py -q → all pass.
REGRESSION REQUIREMENTS: 91+ existing tests must remain passing.
SECURITY REQUIREMENTS: This IS the safety phase.
ACCEPTANCE CRITERIA: Non-allowlisted target → refused at every layer; audit doc complete.
FINAL REPORT FORMAT: "Safety audit complete. Layers audited: X. Tests: X new, 91+ existing. Frozen diff: empty."
STOP CONDITIONS: If a safety gap is found that requires engine modification, STOP and file an ENGINE CHANGE REQUEST.
WHAT TO RETURN: audit doc path, test count, gaps found (if any).

=== PROMPT 11: PHASE 10 — E2E VALIDATION ===

ROLE: Testing/QA specialist.
PROJECT CONTEXT: AI VAPT framework. All phases 0-9 are complete. We need to verify the full pipeline works.
CURRENT STATE: Components exist but haven't been tested together.
OBJECTIVE: Run the complete workflow end-to-end and document results.
FILE OWNERSHIP: You may CREATE docs/project_management/E2E_VALIDATION_REPORT.md.
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/.
REPOSITORY SAFETY CHECK: Run pytest tests/ decision_engine/tests/ prototype/tests/ -q → confirm 91+ passed. Confirm frozen diff empty.
IMPLEMENTATION TASKS:
  1. Run the full pipeline with demo data (simulation mode): scan → normalize → assess → rank → decide → execute → report.
  2. Run the full pipeline with demo data (lab mode, if Docker available).
  3. Document results in E2E_VALIDATION_REPORT.md: what worked, what didn't, gaps.
INTEGRATION CONTRACT: E2E uses existing components; does not modify them.
TEST REQUIREMENTS: Existing tests pass.
REGRESSION REQUIREMENTS: 91+ existing tests must remain passing.
SECURITY REQUIREMENTS: Use only allowlisted targets.
ACCEPTANCE CRITERIA: Full pipeline runs without errors; report written.
FINAL REPORT FORMAT: "E2E validation complete. Simulation: OK/Lab: OK. Report: <path>. Frozen diff: empty."
STOP CONDITIONS: If a gap requires engine modification, STOP and file ENGINE CHANGE REQUEST.
WHAT TO RETURN: report path, pass/fail per mode, gaps found.

=== PROMPT 12: PHASE 11 — MENTOR DEMO ===

ROLE: Documentation/research agent.
PROJECT CONTEXT: AI VAPT framework. All technical work is complete. We need a polished demo script.
CURRENT STATE: PROTOTYPE_DEMONSTRATION_PLAN.md exists but was never implemented.
OBJECTIVE: Write a deterministic, reproducible mentor demo script and rehearse it.
FILE OWNERSHIP: You may CREATE docs/project_management/MENTOR_DEMO_SCRIPT.md.
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/.
REPOSITORY SAFETY CHECK: Run pytest tests/ decision_engine/tests/ prototype/tests/ -q → confirm 91+ passed. Confirm frozen diff empty.
IMPLEMENTATION TASKS:
  1. Write the demo script:
     - Opening (what the demo shows)
     - Scenario walkthrough (success, failure→pivot, multi_candidate, DUMB vs SMART)
     - Closing (what was demonstrated, what was NOT claimed)
  2. Rehearse: run all scenarios, verify deterministic output.
  3. Prepare backup: pre-recorded output in case live demo fails.
INTEGRATION CONTRACT: Demo uses real engine; does not modify it.
TEST REQUIREMENTS: Existing tests pass.
REGRESSION REQUIREMENTS: 91+ existing tests must remain passing.
SECURITY REQUIREMENTS: Demo uses simulation or lab only.
ACCEPTANCE CRITERIA: Demo script written; rehearsal successful.
FINAL REPORT FORMAT: "Demo script complete. Scenarios: 4. Rehearsal: OK. Backup: <path>."
STOP CONDITIONS: None.
WHAT TO RETURN: script path, rehearsal notes.

=== PROMPT 13: PHASE 12 — THESIS INTEGRATION ===

ROLE: Documentation/research agent.
PROJECT CONTEXT: AI VAPT framework. All technical work and demo are complete. We need thesis-ready documentation.
CURRENT STATE: R1-R7 documents exist. Need consolidation.
OBJECTIVE: Integrate all findings, limitations, and methodology into thesis-ready documentation.
FILE OWNERSHIP: You may CREATE docs/project_management/THESIS_INTEGRATION_REPORT.md.
FILES YOU MUST NOT MODIFY: core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/.
REPOSITORY SAFETY CHECK: Run pytest tests/ decision_engine/tests/ prototype/tests/ -q → confirm 91+ passed. Confirm frozen diff empty.
IMPLEMENTATION TASKS:
  1. Consolidate evidence from all phases.
  2. Update limitations section.
  3. Verify all claims are backed by file:line references.
  4. Cross-reference with R1-R7 documents.
INTEGRATION CONTRACT: Documentation only; no source changes.
TEST REQUIREMENTS: Existing tests pass.
REGRESSION REQUIREMENTS: 91+ existing tests must remain passing.
SECURITY REQUIREMENTS: No overclaiming.
ACCEPTANCE CRITERIA: Thesis integration report complete.
FINAL REPORT FORMAT: "Thesis integration complete. Claims: X. Limitations: Y. Report: <path>."
STOP CONDITIONS: None.
WHAT TO RETURN: report path, claim count, limitation count.

---

## 24. HERMES REVIEW PROMPT/CHECKLIST FOR EACH COMPLETED PHASE

After each agent returns, Hermes verifies:

**Universal checklist (all phases):**
- [ ] `pytest tests/ decision_engine/tests/ prototype/tests/ -q` → count matches expected
- [ ] `git diff -- core/ decision_engine/core/ tests/ decision_engine/tests/ datasets/ decision_engine/benchmarks/` → empty
- [ ] No new files in frozen directories
- [ ] Agent's reported files match `git diff --stat`
- [ ] No overclaiming in any new doc (no "faster", no "universal", no "real-world superiority")
- [ ] Safety: no free-text target input in new UI/API
- [ ] Tests: every new function has a test
- [ ] Commit is atomic (one task per commit)

**Phase-specific additions:**
- Phase 0: prototype/ tracked, tag exists
- Phase 1: lab executor allowlist enforced
- Phase 2: LLM path mocked test passes
- Phase 3: scan adapter test passes
- Phase 4: checkpoint resume test passes
- Phase 5: API endpoints respond
- Phase 6: Streamlit app starts
- Phase 7: report contains evidence tier
- Phase 8: benchmark runs
- Phase 9: safety audit doc complete
- Phase 10: E2E report complete
- Phase 11: demo script complete
- Phase 12: thesis integration report complete

---

## 25. FINAL END-TO-END ACCEPTANCE CHECKLIST

**Technical:**
- [ ] 91+ tests passing (91 baseline + new tests)
- [ ] `git diff -- core/ decision_engine/core/` empty
- [ ] All phases tagged (checkpoint-phase-00 through checkpoint-phase-12)
- [ ] Lab emulator runs and produces OBSERVED outcomes
- [ ] LLM assessor works via CLI (with deterministic fallback)
- [ ] Scan ingestion works (Nmap XML → candidates)
- [ ] Checkpoint/restore works end-to-end
- [ ] API runs scenarios asynchronously
- [ ] Frontend shows all required visualizations
- [ ] Reports clearly label evidence tier
- [ ] Safety audit complete; allowlist enforced at all layers

**Research:**
- [ ] Contribution is clear: decision engine, not "another scanner"
- [ ] Gap-1 (priority) and Gap-2 (pivot) are both demonstrated
- [ ] SIMULATION vs OBSERVED vs REAL are always distinguished
- [ ] No overclaiming (no speedup, no universal accuracy, no real-world superiority)
- [ ] All claims backed by file:line or dataset references
- [ ] Limitations documented honestly

**Demo:**
- [ ] Mentor demo script written and rehearsed
- [ ] All scenarios run deterministically
- [ ] Backup output prepared
- [ ] Demo clearly shows: ranking → execution → failure → retry → bounded attempts → pivot → success → trace → report

---

## 26. DEFINITION OF FINAL PROJECT COMPLETION

The project is COMPLETE when:

1. **All 12 phases are tagged** (checkpoint-phase-00 through checkpoint-phase-12).
2. **91+ tests pass** and the frozen baseline is unchanged.
3. **The mentor demo runs successfully** (simulation mode at minimum; lab mode if Docker available).
4. **The thesis integration report** documents all claims, evidence, and limitations.
5. **The safety audit** confirms no uncontrolled targeting is possible.
6. **The decision engine** (the research contribution) is clearly demonstrated as distinct from a vulnerability scanner.

The project is NOT complete if:
- Any claim lacks a file:line or dataset reference
- SIMULATION results are presented as REAL
- The frozen engine has been modified without an approved ENGINE CHANGE REQUEST
- The safety audit finds a gap

---

## HERMES FINAL VERDICT

**MASTER PLAN STATUS: READY FOR MULTI-AGENT EXECUTION**

The plan is grounded in verified repository state (every file read, all 91 tests run, import graph traced). No information was invented. The frozen boundary is respected. The phases are ordered to maximize parallel work while avoiding file conflicts. Every prompt is self-contained and copy-pasteable.

**First action:** Dispatch PROMPT 1 (Phase 0 — Baseline Commit). This is unblocks everything else.

**Estimated total phases:** 12
**Parallel batches:** 2 (phases 1-4, then 5-8)
**Sequential tail:** Phases 9-12
**Total agent tasks:** 13 prompts
**Hermes review gates:** 12 (one per phase)
