# PHASE 5.5 — ARCHITECTURE STABILIZATION & INTEGRATION AUDIT

**Date:** 2026-09-11
**Repository:** `/home/vinit/ai_vapt_framework`
**Branch:** `prototype-development`
**HEAD:** `9334712` (Wave 5)
**Tests:** 458 passed, 7 skipped

---

## 1. VERIFIED BASELINE

| Metric | Value |
|--------|-------|
| Commit | `9334712` |
| Branch | `prototype-development` |
| Tests | 458 passed, 7 skipped |
| Python files | 99 (excluding venv/data/docs) |
| Research core | FROZEN, untouched |

---

## 2. WHAT ACTUALLY WORKS (VERIFIED)

### 2.1 Canonical Workflow — VERIFIED

All three interfaces invoke `VAPTApplication.run()`:

| Interface | File | Line | Uses VAPTApplication |
|-----------|------|------|---------------------|
| CLI | `prototype/cli.py` | ~85 | YES |
| API | `services/api.py` | 43 | YES |
| GUI | `frontend/app.py` | 292 | YES |

**No bypass paths found.** All interfaces convert their input to `VAPTRequest` and consume `VAPTResult`.

### 2.2 Pipeline Steps — VERIFIED

```
VAPTApplication.run()
├── Step 1: Load candidates (scan/scenario)
├── Step 2: Enrich (EPSS/KEV/CVSS/CWE)
├── Step 3: Build graph (VAPTGraph)
├── Step 4: Score candidates (DecisionIntelligence)
├── Step 5: Build executor
├── Step 6: Validation pipeline (Planner/Safety/Verifier/Evidence)
├── Step 7: Run decision engine (frozen Gap-2)
└── Step 8: Build result
```

### 2.3 Docker Observed Workflow — VERIFIED

- Executor container: HEALTHY
- Emulator container: HEALTHY
- HTTP `/vuln` → SUCCESS
- HTTP `/fail` → FAIL_TIMEOUT
- Evidence tier: `DOCKER_OBSERVED`

### 2.4 Scan Ingestion — VERIFIED

- Nmap XML: WORKS
- Nmap JSON: WORKS
- Custom JSON: WORKS
- Nuclei JSON: WORKS

### 2.5 AI Assessment — VERIFIED

- Deterministic mode: WORKS
- AI mode (Ollama unavailable): Falls back to deterministic
- Fallback is explicit (`fallback=True` in AssessmentResult)

---

## 3. ARCHITECTURAL DEFECTS

### 3.1 VAPTResult is Bloated (MEDIUM)

**Problem:** `VAPTResult` mixes domain and presentation concerns.

Current fields:
- Domain: `run_id`, `scenario`, `mode`, `final_status`, `candidates`, `execution_results`, `decision_trace`, `total_attempts`, `pivot_count`, `candidates_processed`, `evidence_tier`, `assessment`, `safety_notice`
- Presentation: `graph`, `scored_candidates`, `pipeline`, `report`

**Recommendation:** Separate into `DomainResult` and `PresentationResult`.

### 3.2 Duplicate Scanner Infrastructure (HIGH)

**Problem:** Two parallel scanner systems exist:

| Module | Status |
|--------|--------|
| `core/scanner.py` | OLD — uses live EPSS API calls |
| `vapt_platform/scanners.py` | NEW — offline-safe adapters |

Both parse Nmap XML/JSON and custom JSON. The old one (`core/scanner.py`) makes live API calls to FIRST.org EPSS API. The new one uses local datasets.

**Impact:** `decision_engine/adapters/scan_adapter.py` still uses the OLD scanner.

**Recommendation:** Remove `core/scanner.py` and update `scan_adapter.py` to use the new system.

### 3.3 Legacy Agent Graph (MEDIUM)

**Problem:** `core/agent_graph.py` is the old VAPT-specific LangGraph implementation.

- It is NOT used by the canonical workflow
- It contains duplicate logic (assess, execute, pivot nodes)
- It is still imported by tests

**Recommendation:** Mark as deprecated. Remove imports from tests.

### 3.4 Root app.py is Dead Code (LOW)

**Problem:** `./app.py` is the old Streamlit dashboard.

- It is NOT used (the active GUI is `frontend/app.py`)
- It imports from `core.agent_graph` (legacy)

**Recommendation:** Delete or move to `archive/`.

### 3.5 Duplicate Executor Implementations (MEDIUM)

**Problem:** Two Executor classes:

| Module | Status |
|--------|--------|
| `core/executor.py` | OLD — VAPT-specific with danger_mode |
| `decision_engine/core/executor.py` | NEW — domain-independent |
| `prototype/execution_layer.py` | Wrapper for NEW executor |

**Recommendation:** Remove `core/executor.py` references.

### 3.6 Unused Modules (LOW)

The following modules appear to be dead code:

| Module | Status |
|--------|--------|
| `tests/ablation.py` | Script, not test |
| `tests/benchmark_var.py` | Script, not test |
| `tests/evaluate.py` | Script, not test |
| `tests/gap1_ablation.py` | Script, not test |
| `tests/run_tdocker_scenarios.py` | Script, not test |
| `tests/test_ttests_gaps.py` | Empty? |
| `tests/test_openai_provider.py` | Empty? |
| `tests/test_orchestration.py` | Empty? |

---

## 4. DEPENDENCY GRAPH

### 4.1 Clean Dependencies (No Circular Imports)

```
frontend/app.py
    └── vapt_platform/application.py
            ├── vapt_platform/enrichment.py
            ├── vapt_platform/graph_builder.py
            ├── vapt_platform/decision_intelligence.py
            ├── vapt_platform/scanners.py
            │       └── vapt_platform/parsers/nuclei_parser.py
            ├── vapt_platform/pipeline.py
            ├── prototype/execution_layer.py
            │       └── decision_engine/core/executor.py (FROZEN)
            ├── prototype/demo_data.py
            ├── prototype/docker_demo_data.py
            ├── decision_engine/adapters/scan_adapter.py
            │       └── core/scanner.py (LEGACY)
            └── decision_engine/core/schemas.py (FROZEN)

services/api.py
    └── vapt_platform/application.py (same as above)

prototype/cli.py
    └── vapt_platform/application.py (same as above)
```

### 4.2 Legacy Dependencies (Should be removed)

```
core/agent_graph.py (LEGACY)
    ├── core/executor.py (LEGACY)
    ├── core/exploit_assessor.py (still used by vapt_platform/assessment.py)
    └── core/schemas.py (LEGACY)

decision_engine/adapters/scan_adapter.py
    └── core/scanner.py (LEGACY)
```

---

## 5. DOMAIN MODEL AUDIT

### 5.1 VAPTResult Analysis

**Current state:** 15 fields, mixing domain and presentation.

**Recommendation:** YES, separate into DomainResult and PresentationResult.

**Rationale:**
- `graph`, `scored_candidates`, `pipeline` are presentation concerns
- API/GUI need different presentation formats
- Domain result should be serializable without presentation overhead

### 5.2 Evidence Model

**Current state:** `EvidenceRecord` has chain integrity (hash chain).

**Status:** GOOD. No changes needed.

### 5.3 Graph Model

**Current state:** `VAPTGraph` with `GraphNode` and `GraphEdge`.

**Status:** GOOD. Clean separation.

---

## 6. ENRICHMENT VERIFICATION

### 6.1 EPSS Enrichment

- Source: `datasets/epss_corpus_enrichment.json` (local)
- Normalization: 0.0 to 1.0
- Provenance: Preserved in `metadata["epss_score"]`
- Offline: YES (local file)
- Tests: YES (fixture-based)

### 6.2 CISA KEV

- Source: `datasets/cisa_kev.json` (local)
- Lookup: O(1) via set
- Provenance: `metadata["cisa_kev"]` (bool)
- Offline: YES
- Tests: YES

### 6.3 CVSS

- Source: From Nuclei metadata or finding metadata
- Normalization: 0.0 to 10.0 → 0.0 to 1.0 in scoring
- Provenance: `metadata["cvss_score"]`
- Offline: YES
- Tests: YES

### 6.4 CWE

- Source: From Nuclei metadata
- Provenance: `metadata["cwe_ids"]`
- Offline: YES
- Tests: YES

---

## 7. ASSET MODEL VERIFICATION

### 7.1 Graph Construction

- Input: Enriched `CanonicalFinding` objects
- Output: `VAPTGraph` with hosts, services, vulnerabilities, CVEs
- Deterministic IDs: YES (`host:IP`, `svc:IP:port:service`, `cve:CVE-XXXX`)

### 7.2 Downstream Consumption

- **DecisionIntelligence** uses graph for `asset_exposure` scoring
- **ValidationPipeline** receives graph but does NOT currently use it
- **VAPTResult** stores graph for presentation

**Gap:** Graph is built but only used for scoring exposure. Attack path analysis is available but not consumed.

---

## 8. CONTROLLED VALIDATION PIPELINE VERIFICATION

### 8.1 Planner

- Generates `PlannedAction` from enriched candidates
- Sorts by priority (risk score)
- Respects `max_actions` limit

### 8.2 Safety Gate

- Validates target against allowlist
- Explicit authorization check
- Risk score check
- Returns `ValidationResult` with detailed reason

### 8.3 Verifier

- Compares observed vs expected outcome
- Assigns confidence score
- Does NOT depend on LLM output

### 8.4 Evidence

- Immutable records with hash chain
- Chain integrity verification
- Provenance tracking

### 8.5 Safety Boundaries

- LLM output NEVER directly becomes shell execution
- All actions pass through deterministic safety controls
- Allowlist is authoritative
- Default: refuse everything until explicitly authorized

---

## 9. CLI/API/GUI CONSISTENCY

### 9.1 Input Equivalence

| Input | CLI | API | GUI |
|-------|-----|-----|-----|
| Scenario | `--scenario` | `scenario` | selectbox |
| Mode | `--mode` | `mode` | radio |
| Target | `--target` | `target` | selectbox |
| Port | `--port` | `port` | number_input |
| Path | `--path` | `path` | text_input |
| Assessor | `--assessor` | `assessor` | radio |
| Max Attempts | `--max-attempts` | `max_attempts` | slider |
| Scan File | `--scan` | `scan_file` | file_uploader |

### 9.2 Output Equivalence

All three consume `VAPTResult` and display:
- Status
- Candidates
- Attempts
- Pivots
- Evidence tier
- Decision trace
- Reports

---

## 10. TEST QUALITY AUDIT

### 10.1 Test Classification

| Category | Count | Files |
|----------|-------|-------|
| Unit | ~250 | All test files |
| Integration | ~120 | test_application, test_pipeline, test_graph |
| End-to-End | ~30 | test_integration, test_scan_integration |
| Runtime | ~20 | test_docker_lab (Docker required) |
| Mocked | ~50 | test_assessment, test_decision |
| Skipped | 7 | test_docker_lab (when Docker unavailable) |

### 10.2 Coverage Gaps

| Gap | Severity | Recommendation |
|-----|----------|----------------|
| No API integration tests | HIGH | Add test for POST /runs |
| No GUI integration tests | MEDIUM | Add test for display_results |
| No scan→enrich→graph→score→pipeline e2e | HIGH | Add full pipeline test |
| No Docker executor integration | MEDIUM | Add test with real Docker |

---

## 11. RISKS

| Risk | Severity | Mitigation |
|------|----------|------------|
| Duplicate scanner systems | HIGH | Remove core/scanner.py |
| VAPTResult bloat | MEDIUM | Separate domain/presentation |
| Legacy code confusion | MEDIUM | Mark deprecated, remove imports |
| Graph underutilization | LOW | Add attack path analysis later |
| No API/GUI integration tests | HIGH | Add integration tests |

---

## 12. RECOMMENDED NEXT MILESTONE

### Recommendation: **Wave 5.5 — Architecture Cleanup**

**Why not Wave 6 (Reporting) first?**

The architecture has accumulated technical debt from rapid wave execution:
1. Duplicate scanner systems create confusion
2. VAPTResult bloat will make reporting harder
3. Legacy code paths need to be removed
4. API/GUI integration tests are missing

**Cleanup tasks:**
1. Remove `core/scanner.py` (update scan_adapter.py)
2. Remove `core/agent_graph.py` from active imports
3. Delete root `app.py`
4. Separate VAPTResult into DomainResult + PresentationResult
5. Add API integration tests
6. Add full pipeline e2e test

**Estimated effort:** 1-2 days

---

## 13. GO / NO-GO DECISION

### GO Criteria:
- [x] Canonical workflow proven
- [x] CLI/API/GUI consistency verified
- [x] Docker observed workflow verified
- [x] Scan ingestion verified
- [x] AI assessment provenance verified
- [x] Safety boundaries verified
- [x] Research core untouched

### NO-GO Criteria:
- [ ] Duplicate scanner systems resolved
- [ ] VAPTResult separation complete
- [ ] Legacy code removed
- [ ] API/GUI integration tests passing

### Decision: **CONDITIONAL GO**

The platform works. All waves are integrated. But technical debt should be cleaned up before adding more features.

---

## 14. AGENT PLAN FOR NEXT MILESTONE

### Agent A: Scanner Deduplication
**Files:** `core/scanner.py`, `decision_engine/adapters/scan_adapter.py`
**Task:** Remove old scanner, update adapter to use new system

### Agent B: VAPTResult Separation
**Files:** `vapt_platform/application.py`, `services/api.py`, `frontend/app.py`
**Task:** Create DomainResult and PresentationResult

### Agent C: Legacy Code Removal
**Files:** `app.py`, `core/agent_graph.py`, tests
**Task:** Remove dead code, update imports

### Agent D: Integration Tests
**Files:** `services/tests/test_api.py`, `tests/test_integration.py`
**Task:** Add API and pipeline e2e tests

---

*Audit completed by Hermes Agent — 2026-09-11*
