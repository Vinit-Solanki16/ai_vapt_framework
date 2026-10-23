# Mid-Semester Prototype Readiness Audit & Post-Implementation Review

**Document:** `docs/project_management/MIDSEM_PROTOTYPE_READINESS_AUDIT.md`<br>
**Repository:** `https://github.com/Vinit-Solanki16/ai_vapt_framework`<br>
**Working Directory:** `/workspaces/ai_vapt_framework`<br>
**Feature Branch:** `fix/midsem-review-reconciliation` (based on `feature/midsem-prototype-readiness`)<br>
**Base Commit:** `b3e7312` (`fix(scope): treat zero-byte engagement storage as corrupt instead of uninitialized`)<br>
**Audit & Review Date:** October 23, 2026<br>
**Status:** RECONCILED & POST-IMPLEMENTATION VERIFIED

---

## 1. Executive Summary

This audit reconciles the runtime, architectural, test, and documentation state of the AI VAPT framework for the upcoming mid-semester demonstration. The framework investigates pre-execution exploit quality assessment (GAP-1) and threshold-based dynamic failure pivoting (GAP-2).

Following the implementation of prioritized blockers, all 3 pre-existing Pydantic serialization warnings have been completely eliminated, Run IDs are consistently surfaced across all 4 report formats (JSON, HTML, Markdown, TXT), environment configuration auto-loads cleanly via a zero-dependency loader with strict test-runner isolation, and Docker lab management scripts (`start_lab.sh`, `stop_lab.sh`) provide a deterministic path for live container testing.

All frozen research components (`decision_engine/core/`, `decision_engine/benchmarks/`, `decision_engine/tests/`, `experiments/`, `docs/thesis/`) remain 100% byte-identical to baseline tag `v1.0.1-thesis`. The platform is fully operational in simulation mode, and all live lab limitations are transparently documented.

---

## 2. Verification Evidence Tiers

To ensure scientific honesty and prevent overclaiming, findings are categorized into four explicit evidence tiers:

- **Tier 1 — Verified by Automated Tests:** Code paths exercised and asserted by automated pytest suites.
- **Tier 2 — Verified by Running API & CLI Workflows:** Code paths executed against active Uvicorn daemon, curl requests, TestClient, or direct CLI execution.
- **Tier 3 — Functionally Integrated but Awaiting Human Browser Walkthrough:** Web SPA UI components and state bindings that are structurally tested via REST API endpoints and asset delivery, but require operator interactive browser dry-run.
- **Tier 4 — Not Verified Due to Environment Constraints:** Capabilities dependent on live external services (e.g. Docker lab containers unstarted by default; paid hosted LLM providers without active API keys).

---

## 3. Capabilities Verification Matrix

| # | Capability | Audit State | Evidence Tier | Verified Evidence & Concrete Findings |
|---|---|---|---|---|
| 1 | **Application Startup** | **WORKING** | Tier 1 & 2 | • FastAPI backend (`services.api:app`) imports cleanly with 34 HTTP routes.<br>• Root `/` serves Web SPA (`frontend/web/index.html`, HTTP 200).<br>• Static assets `/css/styles.css` (19.6 KB) and `/js/app.js` (211.5 KB) mounted and served with HTTP 200.<br>• Streamlit Operations Console (`frontend/app.py`) imports without runtime errors.<br>• `scripts/start_demo.sh` automatically detects `.venv`, loads `.env`, checks tools, and launches Uvicorn. |
| 2 | **Backend/Frontend Connectivity** | **WORKING** | Tier 2 & 3 | • Web SPA (`app.js`) successfully queries `/health`, `/scenarios`, `/engagements`, `/scanners/status`, and `/runs`.<br>• State management binds active run IDs, findings, events, decision traces, and report downloads. |
| 3 | **Authorized Local Lab Execution** | **PARTIAL** | Tier 1 & 4 | • **Verified (Tier 1 & 2):** Simulation mode executes completely via `VAPTApplication.run()`, CLI, and POST `/runs`. Loopback socket runner (`prototype/lab_runner.py`) and Docker proxy executor (`prototype/execution_layer.py`) are fully implemented.<br>• **Not Verified (Tier 4):** Live Docker lab containers (`vuln-emulator` at `172.28.0.2:8080` and `vuln-executor` on port 9090) are offline by default in Codespaces, leading to 7 skipped tests in `prototype/tests/test_docker_lab.py`. Local Juice Shop (`9191`) is offline.<br>• **Safety Policy:** Web targets run in explicit assessment-only mode (`WEB_VALIDATION_UNAVAILABLE`, `OBSERVED_LOCAL`) without simulated or fabricated exploits. |
| 4 | **Scanner Execution (Nmap/Nuclei)** | **WORKING** | Tier 1 & 2 | • Binary discovery verified: Nmap at `/usr/bin/nmap` (`7.94SVN`), Nuclei at `/home/codespace/.local/bin/nuclei` (`v3.11.1`).<br>• Scanners status API (`/scanners/status`) reports availability and version information.<br>• Target preflight enforces reachability before invoking any scanner binary. |
| 5 | **Finding Normalization & Display** | **WORKING** | Tier 1 & 2 | • `CanonicalFinding` provides deterministic ID computation and standard field normalization.<br>• Scanner registry parses Nmap XML, Nmap JSON, and custom JSON.<br>• Semantic split (`split_findings`) separates actionable vulnerabilities from service discovery (`sun-as-jpda?`, port open records).<br>• CISA KEV and EPSS corpus enrichment executes deterministically. |
| 6 | **GAP-1 Quality Scoring & Ranking** | **WORKING** | Tier 1 & 2 | • Assess-before-rank ordering verified in `prototype/engine_integration.py`.<br>• Deterministic mode assigns quality ranks (`HIGH`/`MEDIUM`/`LOW`) with `source="deterministic"`.<br>• AI mode with Ollama catches offline service (`http://127.0.0.1:11434`) and records transparent provenance: `fallback=True`, `provider="ollama"`, `model="llama3.2:3b"`, and actionable error message.<br>• AI mode with OpenRouter fails fast on missing keys without concealed fallback. |
| 7 | **GAP-2 Attempts & Pivot Events** | **WORKING** | Tier 1 & 2 | • Verified on `failure_pivot` scenario: Attempt 1 on `DEMO-WORKER` (`SUCCESS`) advances; Attempts 1 and 2 on `DEMO-DEAD-END` (`FAIL_TIMEOUT`) reach max_attempts=2 and trigger route abandonment.<br>• Total attempts: 3, Pivots: 2, Final Status: `COMPLETED`. Trace reflects real decision engine logs. |
| 8 | **Persistence & Run History** | **WORKING** | Tier 1 & 2 | • Runs persist to `~/.ai_vapt_framework/runs/` with `index.json`.<br>• REST API `/runs` and `/runs/{run_id}/persisted` serve run histories, finding lists, and decision events. |
| 9 | **Evidence-Tier & Reporting Accuracy** | **WORKING** | Tier 1 & 2 | • Dynamic generation across 4 formats: JSON, HTML, Markdown, TXT.<br>• Evidence tiers (`SIMULATED`, `OBSERVED_LOCAL`, `OBSERVED_EXTERNAL`) and safety notices match execution context without overclaiming.<br>• **Resolved:** `Run ID` is now rendered consistently across JSON, HTML, Markdown, and TXT headers (asserted by `test_all_renderers_include_run_id`). |
| 10 | **AI Provider Provenance & Fallback** | **WORKING** | Tier 1 & 2 | • Clear provenance recorded in `DomainResult.assessment`: provider, model, latency, fallback flag, and reasoning.<br>• Offline Ollama returns explicit fallback notice.<br>• Frontend in-UI credential input passes `X-OpenRouter-API-Key` per-request without persistence. |
| 11 | **Target Scope Enforcement** | **WORKING** | Tier 1 & 2 | • Local targets strictly restricted to `{"127.0.0.1", "localhost"}` and authorized ports (`AI_VAPT_AUTHORIZED_WEB_PORTS="9191"`).<br>• Unauthorized targets and ports rejected with HTTP 400 before network activity.<br>• External targets require configuration in `VAPT_AUTHORIZED_WEB_SCOPES` and explicit acknowledgement (`target_scope_acknowledged=True`).<br>• Zero-byte storage recovery (`b3e7312`) isolates corrupted storage and defaults to safe local-lab profile. |
| 12 | **Research Core Integrity** | **WORKING** | Tier 1 | • Zero diff against `v1.0.1-thesis` across `decision_engine/core/`, `decision_engine/benchmarks/`, `decision_engine/tests/`, `experiments/`, and `docs/thesis/`.<br>• `core/exploit_assessor.py` diff reflects approved opt-in OpenRouter provider commit `6040429`.<br>• All 12 core tests pass. |

---

## 4. Status of Prioritized Demonstration Blockers

1. **[RESOLVED] Scope Environment Variable Loading Desynchronization:**
   - *Resolution:* Implemented `vapt_platform/env_loader.py` and invoked at top-level initialization in `services/api.py`. It uses `setdefault` semantics, never overwrites existing variables, and skips during pytest test runs (both collection and execution) to protect unit-test isolation. Covered by `tests/test_env_loader.py`.
2. **[RESOLVED] Pydantic Serializer Warnings:**
   - *Resolution:* Coerced string outcomes to `Outcome` enum before Pydantic model serialization in `vapt_platform/application.py`, and handled `.value` attribute extraction safely in `prototype/report_generator.py`. All 3 warnings completely silenced (0 warnings in pytest).
3. **[RESOLVED] Missing Run ID in Report Renderers:**
   - *Resolution:* Added `Run ID` to header metadata in `HTMLRenderer`, `MarkdownRenderer`, and `TXTRenderer` in `vapt_platform/reporting/renderers.py`. Verified by `tests/test_reporting.py::test_all_renderers_include_run_id`.
4. **[RESOLVED] Docker Lab Orchestration & Preflight:**
   - *Resolution:* Created `scripts/start_lab.sh` and `scripts/stop_lab.sh` with working directory anchoring and readiness polling on `http://localhost:9090/health`. Updated `scripts/start_demo.sh` to reference the new lab script.
5. **[RESOLVED] Operational Clarity Between Frontends:**
   - *Resolution:* Updated `README.md` and `docs/project_management/MENTOR_DEMO_COMPREHENSIVE_GUIDE.md` to designate `./scripts/start_demo.sh` (FastAPI Web SPA on port 8000) as the primary operations console.

---

## 5. Test Suite Verification Metrics

- **Total Collected Tests:** 1019
- **Passing Tests:** 1012
- **Skipped Tests (7):**
  - `prototype/tests/test_docker_lab.py:80`: Docker lab not available
  - `prototype/tests/test_docker_lab.py:90`: Docker lab not available
  - `prototype/tests/test_docker_lab.py:99`: Docker lab not available
  - `prototype/tests/test_docker_lab.py:108`: Docker lab not available
  - `prototype/tests/test_docker_lab.py:124`: Docker lab not available
  - `prototype/tests/test_docker_lab.py:132`: Docker lab not available
  - `prototype/tests/test_docker_lab.py:141`: Docker lab not available
- **Failures:** 0
- **Warnings:** 0
- **Execution Time:** ~10-18s
