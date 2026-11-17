# AI-VAPT Assessment Integrity Forensic & Root-Cause Remediation Report
**Run ID:** `run-14ee778a`  
**Target:** OWASP Juice Shop (`http://127.0.0.1:3000/#/`)  
**Release:** AI-VAPT v1.7.0 RC1  
**Audit Date:** 2026-11-17  
**Engine:** Autonomous Multi-Agent Core (Docker Sandbox)  
**Provider:** Cloud Hosted OpenAI-Compatible (`kaggle-model`, Qwen3-Coder-30B)  

---

## Executive Summary

During Phase D evaluation and regression testing of AI-VAPT v1.7.0 RC1, autonomous assessment run `run-14ee778a` completed against a local OWASP Juice Shop target consuming 43 turns across 16 minutes and 38 seconds, exiting with code 0. Forensic audit of the generated artifacts (`run.json`, `penetration_test_report.md`, `vapt_report_run-14ee778a.html`, `vapt_report_run-14ee778a.pdf`, and SQLite telemetry in `.state/agents.db`) revealed critical assessment integrity defects:

1. **Candidate State Semantic Conflation:** 7 prioritized GAP-1 candidates were marked `VALIDATED` with green badges claiming "Vulnerability Confirmed", despite the assessment discovering **0 confirmed vulnerabilities** (`findings: []`).
2. **False Category Coverage Claims:** The vulnerability category scan matrix reported Software Component Analysis (SCA), SQL Injection, SSRF, SSTI, Client-Side Prototype Pollution, and Code Injection as `PASSED`, despite **0 probes** being executed for those vulnerability families.
3. **GAP-2 Trace Telemetry Bug & Synthetic DAG Loops:** When the candidate queue was exhausted, the state machine logged `[GAP-2 PIVOT] Bounded threshold reached for client-js-attacks... pivoted to None`, and the Web UI graph renderer drew synthetic red pivot loop edges.
4. **Evidence Cross-Contamination:** The Content Security Policy (CSP) candidate bound to Cross-Origin Resource Sharing (CORS) evidence due to loose substring matching on the word `"policy"`, and duplicate curl invocations were counted as distinct independent tool executions.
5. **Conflation of Process Lifecycle with Assessment Completeness:** Consuming 43 of 500 turns was either treated as 100% complete or 0% complete without distinguishing process termination from security objective coverage.

This engineering remediation establishes **empirical assessment integrity**: AI-VAPT now reports strictly and truthfully what it executed and observed. Informational security posture observations are clearly distinguished from verified exploitable vulnerabilities, unexecuted categories are audited as `NOT TESTED`, partially executed categories as `PARTIALLY TESTED`, and all multi-surface exports (JSON, HTML, PDF, Markdown, Web UI) align with zero contradictions.

---

## 1. Baseline Forensic Investigation (`run-14ee778a`)

### 1.1 Execution Environment & Tool Call Inventory
Inspection of `.state/agents.db` revealed 43 total agent messages and 24 function invocations executed inside the Docker container (`ghcr.io/usestrix/strix-sandbox:1.3.0`):

| Tool Name | Invocation Count | Target Endpoints Evaluated | Result Summary |
| :--- | :--- | :--- | :--- |
| `exec_command` (`curl`) | 24 | `http://127.0.0.1:3000/robots.txt` | Disclosed `/ftp` directory path |
| `exec_command` (`curl`) | Shared | `http://127.0.0.1:3000/.well-known/security.txt` | Disclosed security policy & PGP key URL |
| `exec_command` (`curl`) | Shared | `http://127.0.0.1:3000/api-docs/` | Disclosed Swagger UI API specification |
| `exec_command` (`curl`) | Shared | `http://127.0.0.1:3000/` (Headers inspection) | `Access-Control-Allow-Origin: *`, missing CSP |
| `exec_command` (`grep`) | 2 | `main.js`, `vendor.js` (Client bundles) | Search for DOM sinks returned no vulnerabilities |
| `finish_scan` | 1 | Assessment termination | Invoked after candidate queue evaluation |

**Forensic Finding:** Zero active injection payloads, browser DOM manipulations, SQL syntax probes, SSRF redirects, or template expression probes were executed. The autonomous agent focused entirely on passive HTTP reconnaissance and header auditing.

---

## 2. Root Cause Analysis & Technical Breakdowns

### Defect 1: Disconnect Between 7 "VALIDATED" Candidates and 0 Confirmed Findings
- **Root Cause:** In `strix/core/gap_bridge.py` and `strix/interface/api.py`, when the LLM agent called `record_probe_result(..., outcome="positive")`, the system mapped `outcome == "positive"` directly to `CandidateState.VALIDATED` with badge `VALIDATED (Vulnerability Confirmed)`.
- **Engineering Reality:** Discovering that `/robots.txt` exists, that `/.well-known/security.txt` is public (RFC 9116), that Swagger UI documentation is visible, that CORS allows `*` (without credentials), or that CSP is omitted are **security posture observations**. None of these demonstrate an exploitable compromise without an accompanying exploit finding.
- **Remediation:**
  - Expanded `CandidateState` in `strix/core/decision_engine/schemas.py` and `strix/interface/schemas.py` to include `VALIDATED_OBSERVATION` alongside `VERIFIED_VULNERABILITY`.
  - In `strix/report/reconciliation.py` (`enrich_candidates_from_execution`), candidates are strictly validated:
    - If `findings` contains a confirmed exploitable finding matching the candidate, the state is `VERIFIED_VULNERABILITY` (or `VALIDATED`).
    - If `findings` is empty, the candidate is mapped to `VALIDATED_OBSERVATION` with badge `ℹ OBSERVATION` (cyan) and description: *"Factual security posture observation validated; exploit impact unproven."*

### Defect 2: Vulnerability Category Scan Matrix False "PASSED"
- **Root Cause:** In `strix/core/scanner/full_scanner.py` and `strix/report/reconciliation.py`, `SCAN_CATEGORIES` defined `test_count` as the number of *configured* checks (e.g. 14 for SQLi, 8 for SSRF, 6 for Prototype Pollution). When 0 findings were reported, `full_scanner.py` initialized categories as `executed_checks = cat_meta["test_count"]` and `status = "PASSED"`.
- **Engineering Reality:** Claiming SQLi, SSRF, SSTI, Prototype Pollution, and Code Injection "PASSED" when 0 tests were executed is a severe false-negative assurance bug.
- **Remediation:**
  - Decoupled `configured_checks` from `executed_checks`. Configured rules are never counted as executed checks.
  - Initialized unexecuted categories in `FullScanner` with `executed_checks = 0` and `status = "NOT TESTED"`.
  - Enforced deterministic category status rules in `reconcile_scan_matrix`:
    - `cnt > 0` $\rightarrow$ `VULNERABILITIES_IDENTIFIED`
    - `executed_checks == 0` $\rightarrow$ `NOT TESTED`
    - `0 < executed_checks < configured_checks` $\rightarrow$ `PARTIALLY TESTED`
    - `executed_checks >= configured_checks` AND 0 findings $\rightarrow$ `PASSED`
  - In `run-14ee778a`, Version SCA (3/12) and Configuration (4/22) are truthfully reported as `PARTIALLY TESTED`. All remaining categories are audited as `NOT TESTED`.

### Defect 3: GAP-2 Pivot Trace Wording Bug & Synthetic Loop Edges
- **Root Cause:** When `client-js-attacks` reached attempt 2 of threshold 2, the candidate queue was exhausted (`next_entry = None`). `gap_bridge.py` logged event `GAP2_PIVOT` with `next_candidate = None`, and `api.py` printed:
  `[GAP-2 PIVOT] Bounded threshold reached for client-js-attacks (2/2 attempts); pivoted to None`.
  In `strix/interface/web/js/app.js`, the DAG renderer drew a red pivot line from index `i` to `i + 1` blindly, creating a synthetic loop edge back into the same candidate.
- **Remediation:**
  - In `strix/core/gap_bridge.py` (lines 584-600), when the retry threshold is reached and the queue is exhausted, the state machine logs event `GAP2_ABANDON` with `pivot_executed = False` and clear message:
    `"GAP2 threshold reached for client-js-attacks. Candidate abandoned. Queue exhausted. No alternative path executed. Pivot count: 0."`
  - In `strix/interface/web/js/app.js`, dynamic pivot edges are only drawn if `pivotEvt.pivot_executed === true` AND `next_candidate` exists in the rendered nodes.
  - In `strix/interface/viewer/report_pdf.py` and `strix/report/builder.py`, GAP-2 accounting reports `0 executed pivots`.

### Defect 4: Evidence Cross-Contamination and Shared Invocations
- **Root Cause:** In `strix/report/reconciliation.py`, fuzzy word matching used `any(w in c_risk for w in title.split() if len(w) > 4)`. For candidate `csp-bypass` ("Content Security Policy (CSP) Header Not Set"), the word `"policy"` (length 6) matched the CORS coverage entry ("Permissive Cross-Origin Resource Sharing (CORS) Policy"), attaching CORS headers to the CSP candidate. Furthermore, multiple candidates evaluated output from the same underlying `curl` command.
- **Remediation:**
  - Implemented strict domain-specific matching in `enrich_candidates_from_execution`:
    - CSP candidates reject coverage entries containing `"cors"` unless `"csp"` or `"content-security-policy"` is explicitly present.
    - CORS candidates reject coverage entries containing `"csp"` or `"content-security-policy"`.
  - Added duplicate evidence tracking: candidates sharing an underlying tool invocation record `duplicate_invocation_of` and are accounted under `candidate_accounting.duplicate_evidence_associations` (2 in `run-14ee778a`), while unique tool invocations are tracked under `candidate_accounting.unique_tool_invocations` (6 in `run-14ee778a`).

### Defect 5: Decoupling Process Lifecycle from Assessment Completeness
- **Root Cause:** The console progress bar previously bound to turns consumed (e.g. 43 / 500 = 8.6%), while reports claimed 100% completion or 0% completeness.
- **Remediation:**
  - Established distinct schema metrics in `strix/report/reconciliation.py` (`reconcile_assessment_completeness`):
    - `execution_lifecycle`: `"Run process completed — 43 of 500 turns used."`
    - `candidate_completion_percent`: 100.0% (8 of 8 candidates investigated).
    - `category_coverage_percent`: 25.0% (2 of 8 categories tested: 3/12 version checks, 4/22 configuration checks).
    - `assessment_completeness_percent`: 87.5% (7 validated observations + 0 ruled out of 8 candidates).
    - `findings_discovered`: 0.

---

## 3. Source Code Modification Summary

| File Path | Lines Modified | Description of Modification |
| :--- | :--- | :--- |
| `strix/core/decision_engine/schemas.py` | 16-36 | Expanded `CandidateState` with `VALIDATED_OBSERVATION`, `VERIFIED_VULNERABILITY`, and backwards-compatible aliases (`DISPATCHED`, `IDENTIFIED`). |
| `strix/interface/schemas.py` | 185-235 | Synchronized `CandidateSchema.state` documentation and allowed enum literals. |
| `strix/core/gap_bridge.py` | 560-622 | Emits `GAP2_ABANDON` with `pivot_executed=False` on queue exhaustion; returns `status="abandoned"` and `pivot=False`. |
| `strix/core/scanner/full_scanner.py` | 188-215 | Initializes unexecuted categories to `executed_checks=0` and `status="NOT TESTED"`. |
| `strix/report/reconciliation.py` | 35-320, 324-460, 519-766, 767-893 | Implemented strict domain evidence matching, scan matrix execution auditing, lifecycle decoupling, `reconcile_markdown_report`, and `reconcile_run_directory`. |
| `strix/report/builder.py` | 480-515, 1314-1319 | Added cyan `OBSERVATION` badge rendering and exported `build_executive_html_report` / `build_html_report` aliases. |
| `strix/interface/viewer/report_pdf.py` | 620-750 | PDF overview displays `(X validated observations, 0 verified vulnerabilities, Y abandoned)` and truthful category scan matrix. |
| `strix/interface/web/js/app.js` | 890-940, 1120-1160 | DAG nodes display cyan badge for `VALIDATED_OBSERVATION` and suppress synthetic pivot edges when `pivot_executed` is false. |
| `strix/interface/api.py` | 4264-4380 | Synchronized real-time telemetry streaming and candidate state persistence with validated observation semantics. |

---

## 4. Multi-Surface Output Verification (`run-14ee778a`)

Reconciled artifacts were regenerated and validated on disk in `strix_runs/run-14ee778a/`:

1. **`run.json`:**
   - `findings_discovered`: 0, `findings`: `[]`
   - `pivots`: 0, `gap2_pivots`: 0
   - `candidate_accounting`: 8 identified, 8 investigated, 7 validated observations, 0 verified vulnerabilities, 1 abandoned, 6 unique tool invocations, 2 duplicate evidence associations.
   - `category_coverage_percent`: 25.0%
   - `execution_lifecycle`: `"Run process completed — 43 of 500 turns used."`
2. **`penetration_test_report.md`:**
   - Executive summary sanitized: *"0 confirmed vulnerabilities were identified. 7 security observations were validated regarding information disclosure endpoints and defensive header posture. No active exploitable conditions or vulnerabilities were confirmed."*
   - Technical analysis severity labels converted from `(Critical)` / `(High)` to `(Observation)`.
3. **`vapt_report_run-14ee778a.html`:**
   - Rendered 7 cyan `OBSERVATION` badges, 1 rose `ABANDONED` badge, 0 `VULNERABILITY` badges.
   - Scan matrix displays 6 `NOT TESTED` categories and 2 `PARTIALLY TESTED` categories.
4. **`vapt_report_run-14ee778a.pdf`:**
   - Rendered to 3 pages via ReportLab and verified via `pypdfium2`.
   - Page 1: Metadata, target URL, scan mode (`deep`), duration (`16m 38s`).
   - Page 2: Severity summary (0 Critical, 0 High, 0 Medium, 0 Low), probe accounting, category scan matrix, port scope inventory.
   - Page 3: Findings section: *"No findings were recorded for this run."*
5. **Consistency Validator:** `validate_report_consistency(run_data)` returned **0 errors**.

---

## 5. Conclusion

The assessment integrity defects observed in `run-14ee778a` have been resolved at root cause. AI-VAPT v1.7.0 RC1 now provides cryptographically and empirically honest reports: reconnaissance discoveries and unexploited headers are never exaggerated into vulnerabilities, unexecuted attack categories are never claimed as passed, and the autonomous state machine logs only verified operational pivots.
