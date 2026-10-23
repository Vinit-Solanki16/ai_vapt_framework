# Mid-Semester Prototype Readiness Audit

**Document:** `docs/project_management/MIDSEM_PROTOTYPE_READINESS_AUDIT.md`  
**Repository:** `https://github.com/Vinit-Solanki16/ai_vapt_framework`  
**Working Directory:** `/workspaces/ai_vapt_framework`  
**Base Commit:** `b3e7312` (`fix(scope): treat zero-byte engagement storage as corrupt instead of uninitialized`)  
**Audit Date:** October 22, 2026  
**Status:** COMPLETE  

---

## 1. Executive Summary

This audit assesses the actual runtime, architectural, and test state of the AI VAPT framework for readiness toward a reliable, verifiable mid-semester mentor demonstration. The application investigates pre-execution exploit quality assessment (GAP-1) and threshold-based dynamic failure pivoting (GAP-2).

The framework exhibits robust architectural foundations: the research core (`decision_engine/core/`) remains 100% frozen and byte-identical to `v1.0.1-thesis`, target scope enforcement operates strictly fail-closed, finding normalization accurately segregates actionable vulnerabilities from service discovery, and simulation runs complete end-to-end with dynamic multi-format reporting.

Identified blockers are operational and environmental: Docker lab containers and OWASP Juice Shop are unstarted by default, environment scope variables can desynchronize if launched outside `scripts/start_demo.sh`, Pydantic produces 3 serializer warnings on execution outcome enums, and HTML/Markdown reports omit the Run ID in their metadata headers.

---

## 2. Capabilities Verification Matrix

| # | Capability | Audit State | Verified Evidence & Concrete Findings |
|---|---|---|---|
| 1 | **Application Startup** | **WORKING** | • FastAPI backend (`services.api:app`) imports cleanly with 34 HTTP routes.<br>• Root `/` serves Web SPA (`frontend/web/index.html`, HTTP 200).<br>• Static assets `/css/styles.css` (19.6 KB) and `/js/app.js` (211.5 KB) mounted and served with HTTP 200.<br>• Streamlit Operations Console (`frontend/app.py`) imports without runtime errors.<br>• `scripts/start_demo.sh` correctly resolves venv, loads `.env`, detects Nmap (`7.94SVN`) and Nuclei (`v3.11.1`), and launches Uvicorn. |
| 2 | **Backend/Frontend Connectivity** | **WORKING** | • Web SPA (`app.js`) successfully calls API endpoints (`/health`, `/scenarios`, `/engagements`, `/scanners/status`, `/runs`).<br>• State management binds active run IDs, findings, events, decision traces, and report downloads. |
| 3 | **Authorized Local Lab Execution** | **PARTIAL** | • **Functional:** Simulation mode executes completely via `VAPTApplication.run()`, CLI, and POST `/runs`.<br>• **Implemented:** Loopback socket runner (`prototype/lab_runner.py`) and Docker proxy executor (`prototype/execution_layer.py`) are fully coded.<br>• **Limitation:** In the current Codespace environment, Docker lab containers (`vuln-emulator` at `172.28.0.2` and `vuln-executor` on port 9090) are not built/running, leading to 7 skipped tests in `prototype/tests/test_docker_lab.py`. Local Juice Shop on port 9191 is offline.<br>• **Safety Policy:** Web targets run in explicit assessment-only mode (`WEB_VALIDATION_UNAVAILABLE`, `OBSERVED_LOCAL`) without simulated or fabricated exploits. |
| 4 | **Scanner Execution (Nmap/Nuclei)** | **WORKING** | • Binary discovery verified: Nmap at `/usr/bin/nmap`, Nuclei at `/home/codespace/.local/bin/nuclei`.<br>• Scanners status API (`/scanners/status`) reports availability and version information.<br>• Preflight enforces target reachability before any scanner execution. |
| 5 | **Finding Normalization & Display** | **WORKING** | • `CanonicalFinding` provides deterministic ID computation and standard field normalization.<br>• Scanner registry parses Nmap XML, Nmap JSON, and custom JSON.<br>• Semantic split (`split_findings`) separates actionable vulnerabilities from service discovery (`sun-as-jpda?`, port open records).<br>• CISA KEV and EPSS corpus enrichment executes deterministically. |
| 6 | **GAP-1 Quality Scoring & Ranking** | **WORKING** | • Assess-before-rank ordering verified in `prototype/engine_integration.py`.<br>• Deterministic mode assigns quality ranks (`HIGH`/`MEDIUM`/`LOW`) with `source="deterministic"`.<br>• AI mode with Ollama catches offline service (`http://127.0.0.1:11434`) and records transparent provenance: `fallback=True`, `provider="ollama"`, `model="llama3.2:3b"`, and actionable error message.<br>• AI mode with OpenRouter fails fast on missing keys without concealed fallback. |
| 7 | **GAP-2 Attempts & Pivot Events** | **WORKING** | • Verified on `failure_pivot` scenario: Attempt 1 on `DEMO-WORKER` (`SUCCESS`) advances; Attempts 1 and 2 on `DEMO-DEAD-END` (`FAIL_TIMEOUT`) reach max_attempts=2 and trigger route abandonment.<br>• Total attempts: 3, Pivots: 2, Final Status: `COMPLETED`. Trace reflects real decision engine logs. |
| 8 | **Persistence & Run History** | **WORKING** | • Runs persist to `~/.ai_vapt_framework/runs/` with `index.json`.<br>• REST API `/runs` and `/runs/{run_id}/persisted` serve run histories, finding lists, and decision events. |
| 9 | **Evidence-Tier & Reporting Accuracy** | **PARTIAL** | • Dynamic generation across 4 formats: JSON, HTML, Markdown, TXT.<br>• Evidence tiers (`SIMULATED`, `OBSERVED_LOCAL`, `OBSERVED_EXTERNAL`) and safety notices match execution context without overclaiming.<br>• **Defect:** `Run ID` is displayed in JSON and TXT reports, but omitted from HTML and Markdown metadata tables. |
| 10 | **AI Provider Provenance & Fallback** | **WORKING** | • Clear provenance recorded in `DomainResult.assessment`: provider, model, latency, fallback flag, and reasoning.<br>• Offline Ollama returns explicit fallback notice.<br>• Frontend in-UI credential input passes `X-OpenRouter-API-Key` per-request without persistence. |
| 11 | **Target Scope Enforcement** | **WORKING** | • Local targets strictly restricted to `{"127.0.0.1", "localhost"}` and authorized ports (`AI_VAPT_AUTHORIZED_WEB_PORTS="9191"`).<br>• Unauthorized targets and ports rejected with HTTP 400 before network activity.<br>• External targets require configuration in `VAPT_AUTHORIZED_WEB_SCOPES` and explicit acknowledgement (`target_scope_acknowledged=True`).<br>• Zero-byte storage recovery (`b3e7312`) isolates corrupted storage and defaults to safe local-lab profile. |
| 12 | **Research Core Integrity** | **WORKING** | • Zero diff against `v1.0.1-thesis` across `decision_engine/core/`, `decision_engine/benchmarks/`, `experiments/`, and `docs/thesis/`.<br>• All 12 core tests pass. |

---

## 3. Prioritized Demonstration Blockers

1. **[P0] Scope Environment Variable Loading Desynchronization:**
   - *Problem:* When Uvicorn is launched directly without `source .env`, `VAPT_AUTHORIZED_WEB_SCOPES` is empty in `os.environ`, causing valid external scope preflights to fail.
   - *Fix:* Add automatic `.env` discovery in `services/api.py` and `vapt_platform/web_target.py` via `python-dotenv`.
2. **[P0] Offline Live Lab Target Default State:**
   - *Problem:* Demonstration of live HTTP exploit attempts requires the Docker lab emulator (`172.28.0.2:8080`) or local Juice Shop (`9191`), which are unstarted by default.
   - *Fix:* Provide a dedicated preflight and startup helper (`scripts/start_lab.sh` or enhanced `scripts/start_demo.sh`) and clear simulation-mode fallback instructions.
3. **[P1] Pydantic Serializer Warnings:**
   - *Problem:* Full test runs produce 3 UserWarnings regarding `PydanticSerializationUnexpectedValue` for `execution_outcome='SUCCESS'`.
   - *Fix:* Update `ExecutionResultSchema` in `services/schemas.py` to accept string/Outcome enum values cleanly.
4. **[P1] Missing Run ID in Report Renderers:**
   - *Problem:* `HTMLRenderer` and `MarkdownRenderer` omit `Run ID` from their metadata tables, weakening traceability between UI and exported reports.
   - *Fix:* Add `Run ID` to report metadata tables in `vapt_platform/reporting/renderers.py`.
5. **[P2] Operational Clarity Between Frontends:**
   - *Problem:* The repository has both FastAPI Web SPA (port 8000) and Streamlit (port 8501).
   - *Fix:* Designate the Web SPA as the primary operations console in documentation and guides.

---

## 4. Test Suite Baseline

- **Total Collected:** 1014 tests
- **Passing:** 1007
- **Skipped:** 7 (all in `prototype/tests/test_docker_lab.py` due to offline Docker lab container)
- **Failures:** 0
- **Warnings:** 3 (Pydantic enum serializer)
