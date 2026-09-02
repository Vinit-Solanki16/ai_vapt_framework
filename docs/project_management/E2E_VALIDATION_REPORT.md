# Phase 10 — End-to-End Validation Report

**Date:** 2026-09-02
**Validator:** opencode agent (Phase 10 E2E)
**Framework:** AI VAPT (`/home/vinit/ai_vapt_framework`)
**Commit:** (current HEAD)

---

## Safety Check

| Check | Result |
|-------|--------|
| All tests pass | **192 passed** (tests/, decision_engine/tests/, prototype/tests/, services/tests/, frontend/tests/) |
| Frozen diff clean | **Empty** (core/, decision_engine/core/, tests/, decision_engine/tests/, datasets/, decision_engine/benchmarks/ — no modifications) |

---

## E2E Pipeline Results

### 1. Simulation Mode — `failure_pivot`

**Command:**
```
PYTHONPATH=. python prototype/cli.py run --scenario failure_pivot --max-attempts 2
```

| Aspect | Result |
|--------|--------|
| Pipeline executes | **PASS** |
| Candidates ranked | **PASS** (2 candidates: DEMO-WORKER, DEMO-DEAD-END) |
| Engine runs pivot logic | **PASS** (3 total attempts, 2 pivots) |
| Report written (JSON + TXT) | **PASS** (`report_failure_pivot_vapt.json`, `report_failure_pivot_vapt.txt`) |
| Evidence tier | **SIMULATED** (correct — no external targets) |

**Gaps:** None.

---

### 2. Scan Mode — `sample_scan.json`

**Command:**
```
PYTHONPATH=. python prototype/cli.py run --scan data/sample_scan.json --max-attempts 2
```

| Aspect | Result |
|--------|--------|
| Scan file parsed | **PASS** (2 findings: CVE-2021-44228, CVE-2023-38408) |
| EPSS ranking applied | **PASS** (CVE-2021-44228 epss=1.0000 ranked first) |
| Candidates loaded into engine | **PASS** |
| Engine runs | **PASS** (4 total attempts, 3 pivots) |
| Report written | **PASS** (`report_scan:sample_scan.json_vapt.json`, `.txt`) |

**Gaps:** None.

---

### 3. Corpus Mode — `corpus`

**Command:**
```
PYTHONPATH=. python prototype/cli.py run --scenario corpus --max-attempts 2
```

| Aspect | Result |
|--------|--------|
| Corpus loaded | **PASS** (12 candidates from poc_corpus) |
| EPSS ranking applied | **PASS** (top: CVE-2021-44228, CVE-2021-26855 at score=1.0000) |
| Engine runs full corpus | **PASS** (19 total attempts, 18 pivots) |
| Report written | **PASS** (`report_corpus_vapt.json`, `.txt`) |

**Gaps:** None.

---

### 4. API Mode — REST Endpoints

**Command:**
```
uvicorn services.api:app --port 8000
```

| Endpoint | Method | Result |
|----------|--------|--------|
| `/health` | GET | **PASS** — `{"status":"healthy"}` |
| `/runs` | POST | **PASS** — run initiated, returned run_id (e.g. `713b2544`), status=completed |
| `/runs/{id}/report` | GET | **PASS** — full report returned as JSON with keys: run_id, scenario, execution_mode, final_status, candidates, execution_results, decision_trace, total_attempts, pivot_count, candidates_processed, safety_notice |
| `/docs` | GET | **PASS** — OpenAPI docs served (200 OK) |

**Gaps:** None.

---

## Gap Analysis

| Area | Gap | Requires Engine Change? | Notes |
|------|-----|------------------------|-------|
| CLI argument naming | `--corpus` is `--scenario corpus`, not a standalone `--corpus` flag | No | Minor UX; CLI accepts `--scenario corpus` correctly |
| Scan mode ground truth | CVEs without ground truth labels return FAIL_TIMEOUT by default | No | Expected behavior in simulation mode |
| API persistence | In-memory store only (no disk persistence between restarts) | No | Design choice; acceptable for prototype |
| Report naming | Scan reports use `:` in filename (e.g. `report_scan:sample_scan.json_vapt.json`) | No | Minor; filesystem-safe output would be nicer |

**No engine modifications required. No ENGINE CHANGE REQUEST filed.**

---

## Summary

| Mode | Status |
|------|--------|
| Simulation | **OK** |
| Scan | **OK** |
| Corpus | **OK** |
| API | **OK** |

**Final Report Path:** `./report_failure_pivot_vapt.json`, `./report_scan:sample_scan.json_vapt.json`, `./report_corpus_vapt.json` (also `.txt` variants)

**Frozen Diff:** Empty.

**Regression:** 192 existing tests remain passing.

---

## Pipeline Architecture (confirmed working)

```
CLI (prototype/cli.py)
  └─ engine_integration.py → Decision Engine (decision_engine/core/)
  └─ execution_layer.py    → Lab Runner (prototype/lab_runner.py)
  └─ report_generator.py   → Report output
  └─ services.api:app     → REST API
      └─ engine_integration.py → Decision Engine
```

All stages (scan → normalize → assess → rank → decide → execute → report) executed successfully across all four modes.
