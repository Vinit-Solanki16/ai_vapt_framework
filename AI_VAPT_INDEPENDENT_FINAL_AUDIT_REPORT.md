# AI-VAPT — Independent Final Forensic Audit Report (Phase A)

**Auditor Persona**: Senior Security-Platform Architect, Python/FastAPI Engineer, Autonomous-Agent Engineer, Application Security Tester, and Software Quality Auditor  
**Audit Scope**: Entire AI-VAPT Framework repository, source code, test suite, and persisted execution artifacts  
**Target Environment Audited**: `https://pentest-ground.com:4280/` (DVWA Lab) and historical `http://vulnweb.com/`  
**Date of Audit**: 2026-11-16  
**Audit Policy**: Strict Read-Only Audit (Zero code modification, zero git mutation, zero external intrusive scanning)

---

## 1. Executive Summary

This independent forensic audit evaluates the actual implementation status, architectural integrity, and release readiness of the **AI-VAPT** (Autonomous AI Vulnerability Assessment & Penetration Testing) platform.

### High-Level Summary of Findings:
1. **Dual Execution Architecture**:
   - The platform provides two distinct execution engines: **Mode A (Autonomous Multi-Agent Core)** running inside an isolated Docker sandbox (`ghcr.io/usestrix/strix-sandbox:1.3.0`) with authentic LLM tool calling via private/cloud models, and **Mode B (Lightweight Active Scanner)** providing rapid deterministic triage, GAP-2 retry/pivot state transitions, and report generation in-process.
   - Historical runs were forensically classified: `run-767ba9da` ran via the Lightweight Active Scanner (0 LLM turns, 14.8s duration), whereas `run-16c49dbc` ran via the Autonomous Multi-Agent Core (Docker container `47f0a143d814`, Cloud Hosted Qwen3-Coder 30B, 8 LLM turns, 8 sandbox command executions persisted in `agents.db`).
2. **GAP-1 & GAP-2 Dynamic Triage & Pivoting Mechanics**:
   - **GAP-1**: Fully functional pre-execution attack surface analyzer (`strix/core/triage/exploit_assessor.py`). Successfully triages technologies (`PHP_NGINX`, `GENERIC_WEB`), scores exploitability ($P \times S \times U$), and injects prioritized candidate queues into the agent's root instruction prompt via `strix/core/gap_bridge.py`.
   - **GAP-2**: Governs bounded retries up to threshold $k=2$. Candidate abandonment occurs when attempts reach $k=2$.
   - **Investigation of `run-3ef51eab` Discrepancy**: Root cause identified. In `run-3ef51eab`, all candidates were marked `completed` before a second attempt triggered abandonment; because no unattempted candidates remained, `next_candidate` was `None` (`pivot_executed: false`, `result: "Queue exhausted"`). While `strix/interface/api.py` and the UI dashboard correctly reported 0 executed pivots, `strix/report/builder.py` blindly counted all `GAP2_PIVOT` events without checking `pivot_executed`, falsely displaying 3 pivots in HTML reports.
3. **Evidence Integrity & False-Positive Prevention**:
   - The platform enforces a 9-state verification lifecycle (`strix/report/verification.py`).
   - Anti-fabrication rules are strictly enforced for XSS (requires DOM execution proof) and LFI (requires system file extraction). In `run-767ba9da`, only 1 finding (`find-lfi-traversal`) was confirmed (`verified: true`), extracting genuine `/etc/passwd` contents with matching SHA-256 hash `7f7e45ea63...`; the remaining 9 passive findings were correctly maintained as `verified: false` (Unconfirmed).
4. **Category Coverage & Baseline Secure Representation**:
   - A major architectural defect exists in `strix/report/builder.py` and `strix/interface/api.py` (`_reconcile_scan_matrix`): When a scan identifies 0 findings for a category, it defaults the status to `"PASSED (BASELINE SECURE)"` across all 8 scan categories (88 tests), even if those categories were never tested. Zero findings must not be represented as proof of security.
5. **Quality & Test Assurance**:
   - The test suite comprises **2,858 passing tests** (1 skipped, 3 xfailed) across unit, API, and mock suites. Ruff linting is clean (0 errors). Mypy passes on 178 source files, but `strix.interface.api` is deliberately excluded from type checking in `pyproject.toml`.

---

## 2. Actual Repository and Git State

| Git Attribute | Current Value / Observed State |
|---|---|
| **Working Directory** | `/home/vinit/AI_VAPT/ai_vapt_framework` |
| **Current Branch** | `ai-vapt-full-application` |
| **Tracking Remote** | `origin/ai-vapt-full-application` |
| **HEAD Commit** | `f8b58a2` (*"feat: complete AI-VAPT portability, remote Docker runtime, multi-provider AI, and GAP1/GAP2 integration"*, 2026-11-12) |
| **Divergence from Main** | `ai-vapt-full-application` is ahead of `origin/main` (`271c064`) by 73 changed files (+16,312 / -476 lines) representing full application implementation. |
| **Uncommitted Modifications** | **21 files modified** in working tree (+5,780 / -1,109 lines), including `api.py` (+1,865 lines), `app.js` (+2,761 lines), `index.html` (+583 lines), `provider_validation.py` (+689 lines), `verification.py` (+184 lines). |
| **Untracked Files** | **14 audit/remediation reports**, `screenshots/` directory (5 PNGs), 2 untracked source modules (`strix/core/runtime_credentials.py`, `strix/report/evidence.py`), and 7 untracked test files (`tests/test_cloud_hosted_qwen3_validation.py`, etc.). |
| **Remediation Status** | Phase 1–8.1 remediation tasks have been implemented in code and verified via unit tests, but remain uncommitted to preserve working tree stability. |

---

## 3. Architecture and Execution Flow

The platform execution flow was traced across 14 lifecycle stages:

```
[Web UI (app.js)] 
       │ (1. POST /runs)
       ▼
[FastAPI Router (api.py)] ──► (2. Preflight Validation & Docker Check)
       │
       ├─► (3. Run Persistence: run.json & SQLite in strix_runs/<run_id>/)
       ├─► (4. Provider/Model Resolution: runtime_credentials.py & router.py)
       │
       ▼
[_execute_run_worker (Background Task)]
       │
       ├─► (7. Reconnaissance: FullScanner, port_scanner.py, spider.py)
       │
       ├─► (8. GAP-1 Triage: exploit_assessor.py -> gap1_queue.json)
       │
       ├─► If Mode == "autonomous" ──► (5 & 6. Strix Multi-Agent in Docker Sandbox)
       │                                     │
       │                                     ├─► (10. Tool Exec: exec_command inside strix-sandbox)
       │                                     ├─► (9. GAP-2 Bounded Pivoting: gap_bridge.py / k=2)
       │                                     └─► (11. Finding Verification: outcome_tool.py)
       │
       └─► If Mode == "lightweight" ──► (In-Process Python Asynchronous Scanner)
                                             │
                                             ├─► (9. Deterministic GAP-2 DAG & Retry Loop)
                                             └─► (11. evaluate_finding_verification)
       │
       ▼
[Post-Processing & Ledger Sync]
       │
       ├─► (12. Evidence Hashing & Artifact Persistence: evidence.py / SHA-256)
       ├─► (13. Multi-Format Report Builder: builder.py, report_pdf.py, sarif.py)
       └─► (14. Lifecycle Finalization: status=completed | paused_execution_limit)
```

### Component Analysis:
* **Implemented vs Mocked**:
  - Full scanner, port scanner, spider, GAP-1 triage, GAP-2 bridge, LiteLLM router, runtime credentials, evidence ledger, report builders (HTML, PDF, JSON, SARIF), and frontend dashboard are **fully implemented**.
  - Local unit tests heavily mock Docker and LiteLLM calls to guarantee deterministic offline execution.
* **Duplicated Sources of Truth**:
  - Pivot calculation: `api.py` checks `p_exec is not False`, whereas `builder.py` counts any `GAP2_PIVOT` event.
  - Duration calculation: `api.py` tracks active duration segments (`active_duration_seconds`), while older artifacts only record wall-clock `duration_seconds`.

---

## 4. GAP-1 Audit (Attack Surface Triage)

### Implementation Audit:
* **Triage Generation**: `strix/core/triage/exploit_assessor.py` (`run_gap1_triage`) inspects HTTP headers, technology markers, and open ports.
* **Ranking Model**: Ranks candidates using composite usability scoring:
  $$\text{Composite Score} = P(\text{Exploitability}) \times S(\text{Severity}) \times U(\text{Usability})$$
* **Agent Root Injection**: `strix/core/gap_bridge.py` (`gap1_instruction_block`) formats the top candidates into markdown instructions injected directly into the Root Agent's system prompt.
* **Persistence**: Serialized to `strix_runs/<run_id>/control/gap1_queue.json`.

### Forensic Artifact Verification:
* In `run-16c49dbc` (Autonomous Multi-Agent Core): 15 candidates generated for `PHP_NGINX`. The Root Agent immediately prioritized and probed `/robots.txt`, open port 6379, and `/vulnerabilities/fi/?page=...`, proving that GAP-1 directly steers agent tool selection.
* In `run-767ba9da` (Lightweight Active Scanner): 15 candidates were evaluated in sequence, generating 4 failure pivots when metadata probes failed.
* **Verdict**: **VERIFIED**. GAP-1 is not cosmetic; it alters the agent's prompt, tool invocation targets, and execution ordering.

---

## 5. GAP-2 Audit (Bounded Dynamic Pivoting)

### Implementation Audit:
* **State Manager**: `strix/core/gap_bridge.py` (`GapRunState`) maintains `attempts` ($c_i$), `exhausted` set, and `completed` set in `strix_runs/<run_id>/control/gap_state.json`.
* **Bounded Threshold**: Governed by `STRIX_GAP2_THRESHOLD` (default $k=2$).
* **Event Logging**: Every attempt logs `GAP2_ATTEMPT` to `strix_runs/<run_id>/control/decision_trace.jsonl`. When $c_i \ge k$, the candidate transitions to `ABANDONED`, logging `GAP2_PIVOT`.

### Resolution of Historical Inconsistency (`run-3ef51eab`):
The reported discrepancy in `run-3ef51eab` was forensically verified:
1. `run-3ef51eab/control/decision_trace.jsonl` contains 3 `GAP2_PIVOT` events:
   - `candidate_id: "missing-anti-clickjacking"`, `outcome: "ABANDON"`, `attempts: 2`, `threshold: 2`, `next_candidate: null`, `pivot_executed: false`, `result: "Queue exhausted"`.
   - `candidate_id: "cors-misconfiguration"`, `outcome: "ABANDON"`, `attempts: 2`, `next_candidate: null`, `pivot_executed: false`.
   - `candidate_id: "missing-security-headers"`, `outcome: "ABANDON"`, `attempts: 2`, `next_candidate: null`, `pivot_executed: false`.
2. **Why was `pivot_executed` False?** Prior to these events (at 10:48–10:49 UTC), the agent had recorded coverage for all candidates, placing all 4 queue items in `st.completed`. When attempt 2 failed, `next_candidate()` had no remaining candidates to select.
3. **Discrepancy Cause**:
   - `strix/interface/api.py` (lines 1075–1077) correctly filters for `p_exec is not False`. Since `pivot_executed == False`, `api.py` reported `gap2_pivots: 0`. The dashboard showed `0`.
   - `strix/report/builder.py` (lines 137–141) counts all `GAP2_PIVOT` events regardless of `pivot_executed`, displaying `3 pivots` in the HTML report.
4. **Semantics Delineation**:
   - **Retry**: An unconfirmed probe on candidate $i$ where $c_i < k$.
   - **Abandonment**: Candidate $i$ reaches $c_i \ge k$ and is moved to `exhausted`.
   - **Pivot Decision**: Engine evaluates whether candidate $i+1$ exists.
   - **Executed Pivot**: A subsequent candidate $j$ is actively selected and dispatched.
   - **Successful Redirection**: The dispatched candidate $j$ is probed and reaches a terminal state.

---

## 6. Target Discovery and Reconnaissance Audit

### Implementation Audit:
* Target discovery is implemented in `strix/core/scanner/full_scanner.py` and `strix/core/scanner/spider.py`.
* **Port Scanner**: Tests 22 TCP ports (`strix/core/scanner/port_scanner.py`) including HTTP (80, 443, 8080), databases (3306, 5432, 6379, 27017), and management services (22, 23).
* **Spidering**: Extracts HTML anchors (`<a href>`), forms (`<form action>`), and inputs (`<input name>`).

### Investigation of VulnWeb Assessment (`vulnweb.com` vs `rest.vulnweb.com`):
* In `run-3ef51eab`, `http://vulnweb.com/` was assessed. The target returned HTTP 502 Bad Gateway on all requests.
* Consequently, `spider_stats` recorded: `visited_count: 1`, `discovered_paths: ['/']`, `forms_count: 0`, `parameters_count: 0`.
* **Scope Limitation Found**: In `strix/interface/schemas.py`, `ScanCreateRequest` defines a single string field: `target_url: str | None`. It **does not support an array of authorized hostnames or subdomains**. When assessing `vulnweb.com`, the operator cannot supply `rest.vulnweb.com` or `testphp.vulnweb.com` as part of the authorized scope.
* **Verdict**: **PARTIALLY VERIFIED**. Discovery works on single target URLs, but multi-domain / subdomain scope configuration is not exposed in the API.

---

## 7. Finding and Evidence Integrity Audit

### Lifecycle & Verification State Machine:
* Implemented in `strix/report/verification.py` across 9 states:
  $$\text{Discovered} \to \text{Candidate} \to \text{Under Investigation} \to \text{Exploitation Attempted} \to \begin{cases} \text{Verified} \\ \text{Unconfirmed} \\ \text{False Positive} \\ \text{Blocked} \\ \text{Inconclusive} \end{cases}$$
* Enforces `evaluate_finding_verification()`:
  - **Reflected XSS**: Reflected strings without DOM alert execution $\to$ `UNCONFIRMED`.
  - **LFI / Path Traversal**: PHP include warnings without extracted `/etc/passwd` or file contents $\to$ `UNCONFIRMED`.
  - **Diagnostic / PHPInfo**: Full configuration dump $\to$ `VERIFIED`.

### Evidence Storage & Cryptographic Hashing:
* Implemented in `strix/report/evidence.py`:
  - Authentic evidence saved to `strix_runs/<run_id>/evidence/<finding_id>_evidence.txt`.
  - SHA-256 computed over raw evidence bytes.
  - Detects and flags legacy synthetic hashes (`sha256(id:title)`).
* In `run-767ba9da`:
  - `find-lfi-traversal`: `GET /vulnerabilities/fi/?page=../../../../../../etc/passwd` extracted `/etc/passwd`. SHA-256 hash `7f7e45ea63295744d6fc5e472d1fdfe43b686026a4acf1a213a6966b1e4affcd` matches evidence file byte digest exactly.
  - Findings 2–10: All 9 passive observations are marked `verified: false`.
* **Verdict**: **VERIFIED**. The evidence hashing and state machine prevent unconfirmed observations from being claimed as verified exploits.

---

## 8. Reporting and Telemetry Audit

### Consistency Across Subsystems:
* `run.json`, `findings.sarif`, SQLite `agents.db`, and the Web API maintain consistent finding counts and states.
* **Telemetry**: Elapsed timer freezes upon run completion or pause limit; no runaway timer drift occurs.

### Critical Reporting Defect (Category Matrix False Assurance):
* In `strix/report/builder.py` (lines 488, 501, 1110) and `strix/interface/api.py` (`_reconcile_scan_matrix`):
  ```python
  m_status = (
      '<span class="badge badge-amber">FINDINGS IDENTIFIED</span>'
      if m_count > 0
      else '<span class="badge badge-emerald">PASSED (BASELINE SECURE)</span>'
  )
  ```
* When an assessment runs in Quick mode or evaluates only 1–2 categories, the remaining categories have `findings_count == 0`.
* The report renders: `<span class="badge badge-emerald">PASSED (BASELINE SECURE)</span>` and claims *"Comprehensive multi-layer audit coverage across 8 core VAPT test categories (88 total tests)"*.
* **Verdict**: **FAILED**. The system fails to distinguish `NOT TESTED`, `BLOCKED`, and `INCONCLUSIVE` in the HTML category matrix, misrepresenting untested categories as secure.

---

## 9. Provider and Model Audit

Every supported provider was audited against implementation and test evidence:

| Provider Name | Verification Status | Exact Classification Label | Notes / Operational Boundaries |
|---|---|---|---|
| **OpenRouter** | Production Integrated | `Implemented`, `Mock-tested`, `API-validated` | Preflight `/v1/auth/key` validation implemented. Free model auto-formatting (`format_openrouter_model`). Requires valid API key for live execution. |
| **OpenAI** | Production Integrated | `Implemented`, `Mock-tested`, `API-validated` | Routes `gpt-4o`, `gpt-4o-mini`. Validated in mock suites. |
| **Anthropic** | Production Integrated | `Implemented`, `Mock-tested`, `API-validated` | Claude 3.5 Sonnet routing implemented. Key validation verified via `validate_anthropic_credential`. |
| **Google Gemini** | Production Integrated | `Implemented`, `Mock-tested`, `API-validated` | Gemini 2.0 Flash routing via Google Generative AI API. Verified in mock suites. |
| **Ollama (Local)** | Local Ready | `Implemented`, `Mock-tested`, `API-validated`, `Live-inference-tested` | Local daemon integration (`http://127.0.0.1:11434`), tag discovery (`/api/tags`). Tested with `qwen2.5:1.5b`. |
| **Custom OpenAI-Compatible** | Production Integrated | `Implemented`, `Mock-tested`, `API-validated` | Arbitrary remote endpoint routing (`/v1`), base URL, custom model IDs. Validated via `validate_openai_compatible_endpoint`. |
| **Cloud Hosted (Qwen3-Coder)** | **Primary Validated Engine** | `Implemented`, `Mock-tested`, `API-validated`, `Live-inference-tested`, `Live-tool-calling-tested`, `Autonomous-execution-tested` | Active Quick Tunnel profile (`[temporary Cloudflare tunnel endpoint]/v1`), model `kaggle-model-deep`, context 131,072. Validated end-to-end in `run-95c0f177`, `run-9b2446ec`, and `run-16c49dbc`. |

* **Guardrails Verified**:
  - No silent provider fallback: Unknown providers raise HTTP 400.
  - Credential redaction: API keys are masked in API responses and never written to disk or logs.
  - In-memory precedence: Frontend keys take precedence over absent/placeholder `.env` keys.

---

## 10. Frontend Audit

* **File Location**: `strix/interface/web/` (`index.html`, `js/app.js`, `css/styles.css`).
* **Views Verified**:
  - `New Assessment`: Target preflight check, IP resolution (`178.79.134.182`), engine selection (Autonomous Multi-Agent Core vs Lightweight Active Scanner), turn limits, authorization checkbox.
  - `Active Assessment`: Real-time SSE telemetry, active agent status, elapsed timer, GAP-1 prioritization queue, live GAP-2 DAG visualizer, verification state counters.
  - `History`: 8-column historical runs ledger with filter controls, duration, findings count, and resume action.
  - `Reports`: Findings table, cryptographic proof hashes, ReportLab PDF, JSON, SARIF 2.1.0 download.
  - `AI Models (Settings)`: Dynamic profile creation, activation, deletion, model discovery (`/providers/*/models`), and test verification.
* **Control Fidelity**: All buttons and form inputs are bound to real backend API routes in `app.js`. No dummy or disconnected action handlers exist.

---

## 11. Setup and Portability Audit

* **Shell Scripts**:
  - `setup.sh`: Detects Linux, WSL2, Codespaces, and macOS; checks Python 3.12+, `uv`, Docker, and sandbox image `ghcr.io/usestrix/strix-sandbox:1.3.0`.
  - `start.sh`: Starts FastAPI via Uvicorn in background or foreground; tracks PID in `.ai_vapt.pid`.
  - `stop.sh`: Gracefully terminates Uvicorn process; preserves all run artifacts and database files.
* **System Endpoints**:
  - Health: `GET /health` and `GET /system/health` return status, Docker availability, and active run ID.
  - Readiness: `GET /system/readiness` and `GET /diagnostics/readiness` inspect provider keys, Docker runtime, and disk storage.

---

## 12. Test Results

The non-destructive local test suite was executed:

| Test Metric | Result |
|---|---|
| **Command Executed** | `uv run pytest tests/ -q` |
| **Total Tests Collected** | 2,862 |
| **Passed** | **2,858** |
| **Failed** | **0** |
| **Skipped** | 1 (`test_docker_client_devices.py` - host specific) |
| **Expected Failures (xfail)** | 3 (known upstream upstream edge cases) |
| **Warnings** | 108 (benign Starlette `httpx` deprecation and Pydantic field notices) |
| **Execution Time** | 326.99s (05:26) |
| **Test Types** | Unit tests, mock provider tests, FastAPI contract tests, integration lifecycle tests |
| **Static Checks** | `uv run ruff check .` $\to$ **All checks passed!**; `uv run bandit` $\to$ **0 issues identified**; `uv run mypy strix/` $\to$ **Success (178 files)**. |

---

## 13. Critical Defects

### DEF-01: False Security Assurance in Report Category Matrix (Untested Categories Marked PASSED)
* **Severity**: **CRITICAL**
* **Source File & Function**: `strix/report/builder.py` (`build_html_report`, lines 488, 501, 1110) & `strix/interface/api.py` (`_reconcile_scan_matrix`, lines 559–568).
* **Evidence Observed**: If `findings_count == 0`, status is unconditionally rendered as `<span class="badge badge-emerald">PASSED (BASELINE SECURE)</span>`, accompanied by the text: *"Comprehensive multi-layer audit coverage across 8 core VAPT test categories (88 total tests)"*.
* **Reproduction**: Run a Quick assessment (`max_turns: 8`) testing only LFI. The resulting HTML report marks SSRF, SSTI, SQLi, and Prototype Pollution as "PASSED (BASELINE SECURE)".
* **Impact**: Misleads clients and evaluators by presenting untested security categories as verified secure, violating fundamental penetration testing standards.
* **Recommended Correction**: Update `_reconcile_scan_matrix()` and `builder.py` to check whether test rules for each category were actively dispatched. If not dispatched, display `NOT TESTED` in neutral gray.

---

## 14. Major Defects

### DEF-02: GAP-2 Pivot Metric Discrepancy Between HTML Reports and Dashboard
* **Severity**: **MAJOR**
* **Source File & Function**: `strix/report/builder.py` (lines 137–141) vs `strix/interface/api.py` (lines 1075–1077).
* **Evidence Observed**: In `run-3ef51eab`, `pivot_events` had 3 records with `pivot_executed: false` and `next_candidate: null` (queue exhausted). `api.py` and the dashboard reported 0 pivots, but `builder.py` counted all 3 events and displayed `3 pivots` in the HTML report.
* **Reproduction**: Inspect `strix_runs/run-3ef51eab/run.json` (`gap2_pivots: 0`) and compare against `builder.py` HTML output (`total_pivots: 3`).
* **Impact**: Contradictory metrics across reports and UI dashboard undermine confidence in reporting accuracy.
* **Recommended Correction**: In `builder.py` line 137, enforce the exact filter used in `api.py`:
  ```python
  total_pivots = len([
      e for e in pivot_events
      if (e.get("type") in ("REDIRECT", "GAP2_PIVOT") or e.get("event") == "GAP2_PIVOT")
      and e.get("pivot_executed", True) is not False
  ])
  ```

### DEF-03: Single Target URL Scope Restriction (No Multi-Host / Subdomain Scope Configuration)
* **Severity**: **MAJOR**
* **Source File & Function**: `strix/interface/schemas.py` (`ScanCreateRequest`, line 35).
* **Evidence Observed**: `ScanCreateRequest` only accepts `target_url: str | None`. It provides no field to declare additional in-scope hostnames or API subdomains (e.g., `rest.vulnweb.com`).
* **Reproduction**: Inspect `schemas.py` and UI form fields. When assessing `vulnweb.com`, the agent cannot be instructed to assess related subdomains without violating strict host boundaries.
* **Impact**: Prevents testing modern distributed web applications with split frontend/API domains.
* **Recommended Correction**: Add `additional_authorized_hosts: list[str] = Field(default_factory=list)` to `ScanCreateRequest` and pass them to `build_scope_context()` in `strix/core/inputs.py`.

---

## 15. Minor Defects

### DEF-04: Synthetic Request and Response Strings in Report Mitigation Cards
* **Severity**: **MINOR**
* **Source File & Function**: `strix/report/builder.py` (lines 305–318).
* **Evidence Observed**: If a finding record lacks `reproducible_request` or `evidence_snippet`, `builder.py` synthesizes: `GET {location} HTTP/1.1\nHost: {target_clean}` and `"Response confirmed vulnerable behavior."`.
* **Impact**: Displays artificial request/response text in reports when authentic network exchanges were not captured.
* **Recommended Correction**: Display `"No raw HTTP exchange captured"` rather than generating synthetic request/response templates.

### DEF-05: Mypy Type Checking Ignores `strix.interface.api`
* **Severity**: **MINOR**
* **Source File & Function**: `pyproject.toml` (lines 213–216).
* **Evidence Observed**: `[[tool.mypy.overrides]] module = ["strix.interface.api", "strix.interface.web_cli"] ignore_errors = true`.
* **Impact**: The largest module in the codebase (6,620 lines) is exempt from static type checking, increasing risk of runtime `AttributeError` or `KeyError` regressions.
* **Recommended Correction**: Progressively annotate `api.py` and remove the ignore override.

---

## 16. Unverified Functionality

| Subsystem / Feature | Audit Status | Forensic Reason / Limitation |
|---|---|---|
| **Multi-Agent Peer Swarm Coordination** | **PARTIALLY VERIFIED** | Strix Root Agent sub-delegation to tools is verified; autonomous peer-to-peer negotiation between multiple reasoning LLM agents is bounded by turn budgets and provider inference latency. |
| **Deep Protocol Fuzzing (Binary / Custom Protocols)** | **PARTIALLY VERIFIED** | High-level web payloads (LFI traversal, SQLi, command injection) are functional; protocol-level binary fuzzing is agent prompt-driven rather than an independent specialized fuzzing engine. |
| **External Live Cloud Model Continuous Stress** | **PARTIALLY VERIFIED** | Cloud Hosted Qwen3-Coder tested up to 24 turns; prolonged 500+ turn autonomous assessments over public tunnels remain untested due to Cloudflare Quick Tunnel ephemerality. |

---

## 17. Recommended Remediation Order

1. **Fix HTML Report Category Matrix (DEF-01)**:
   - In `strix/report/builder.py` and `_reconcile_scan_matrix()`, replace unconditional `"PASSED"` with `"NOT TESTED"` for categories where zero active probe rules were executed.
2. **Align Pivot Accounting in Builder (DEF-02)**:
   - Update `builder.py` lines 137–141 to filter out events where `pivot_executed == False`.
3. **Remove Synthetic Request/Response Strings (DEF-04)**:
   - In `builder.py`, replace fallback `GET /` and `Response confirmed vulnerable behavior` with explicit notice: `[No HTTP exchange captured]`.
4. **Extend Scan Request Scope to Multi-Host (DEF-03)**:
   - Add `additional_authorized_hosts` to `ScanCreateRequest` in `schemas.py` and wire it to `strix/core/inputs.py`.
5. **Enable Mypy Type Checking on API (DEF-05)**:
   - Resolve untyped variables in `strix/interface/api.py` and remove `ignore_errors = true` from `pyproject.toml`.

---

## 18. Audit Categorization Breakdown

* **VERIFIED**:
  - Docker sandbox isolation and loopback rewriting (`localhost` $\to$ `host.docker.internal`).
  - Strix autonomous agent execution with authentic tool calling (`run-16c49dbc`).
  - GAP-1 attack surface triage and dynamic prompt injection.
  - GAP-2 bounded retry state machine ($k=2$) and candidate abandonment.
  - 9-state finding verification lifecycle and cryptographic SHA-256 evidence hashing.
  - Telemetry timer freeze upon completion / turn budget pause.
  - Web UI dashboard, historical runs ledger, and multi-format report exports (PDF, JSON, SARIF).
  - 2,858 passing deterministic regression tests.
* **PARTIALLY VERIFIED**:
  - Target discovery: Works on single target URLs, but lacks multi-hostname scope configuration.
  - Cloud Hosted Qwen3-Coder: Verified for controlled turn budgets; ephemeral tunnel URLs require manual re-configuration upon rotation.
* **FAILED**:
  - Scan category matrix in HTML reports: Incorrectly labels untested categories as `"PASSED (BASELINE SECURE)"`.
  - Report pivot accounting: HTML generator counts abandoned candidates as executed pivots when queue is exhausted.
* **BLOCKED**:
  - Autonomous multi-agent execution on hosts without a running Docker daemon (cleanly detected and reported by API).
* **NOT TESTED**:
  - Intrusive external exploitation against unauthorized internet targets (strictly forbidden by audit rules).

---

## 19. Final Verdict

### Chosen Verdict:
$$\mathbf{B.\; Ready\; for\; controlled\; academic\; demonstration,\; but\; not\; public\; release.}$$

### Justification:
1. **Academic Demonstration Readiness**:
   - The platform conclusively proves its core research contribution: Autonomous penetration testing with Guided Attack Planning (GAP-1) and Bounded Dynamic Decision-Pivoting (GAP-2).
   - Both execution engines (**Mode A: Autonomous Multi-Agent Core with Docker and Qwen3-Coder**; **Mode B: Lightweight Active Scanner**) are functional, reproducible, and forensically documented (`run-16c49dbc` and `run-767ba9da`).
   - The system satisfies rigorous evidence authenticity: findings require genuine exploit proof, and 2,858 regression tests pass cleanly.
2. **Public Release Ineligibility**:
   - The platform cannot be released to the general public because its reporting subsystem falsely presents untested categories as "PASSED (BASELINE SECURE)", which creates severe liability in production security audits.
   - The HTML report builder contains metric inconsistencies regarding pivot counts and synthetic request fallbacks.
   - Target scope definition is currently limited to single hostnames.
   - Once DEF-01 and DEF-02 are remediated, the platform will satisfy production commercial standards.
