# AI-VAPT Assessment Integrity Regression & Visual Inspection Report
**Target Release:** AI-VAPT v1.7.0 RC1  
**Audit Scope:** Defect Remediation Regression, Multi-Surface Consistency & PDF Visual Inspection  
**Audit Date:** 2026-11-17  
**Test Harness:** Pytest 9.1.1 (Python 3.12.14)  
**Static Analysis:** Ruff 0.8.x, Mypy 1.13.0, Bandit 1.8.x  
**Visual PDF Inspection:** `pypdfium2` High-DPI Page Rendering  

---

## 1. Executive Summary

This report documents the comprehensive regression testing and visual audit conducted following the remediation of assessment integrity defects in AI-VAPT v1.7.0 RC1. All tests and verification passes confirm that:

1. **62 of 62 targeted regression tests** passed with 0 failures and 0 warnings.
2. **Static code analysis** (Ruff, Mypy, Bandit) completed cleanly with zero unresolved defects or security issues.
3. **Visual PDF inspection** via `pypdfium2` confirmed a clean 3-page layout with zero overlapping tables, zero text clipping, zero orphan headers, and truthful scan matrix and candidate tables.
4. **Multi-surface consistency audit** verified that JSON, Markdown, HTML, PDF, and Web UI representations report identical figures without contradictions.

---

## 2. Automated Test Suite Execution

### 2.1 Test Execution Matrix

| Test Suite File | Tests Count | Status | Execution Time | Coverage Area |
| :--- | :--- | :--- | :--- | :--- |
| `tests/test_assessment_integrity_run_14ee778a_remediation.py` | 16 | **16 PASSED** | 6.99s | Candidate observation semantics, evidence isolation, scan matrix audit, queue exhaustion, PDF reconciliation. |
| `tests/test_autonomous_execution_gap_remediation.py` | 24 | **24 PASSED** | 4.12s | Controlled fixtures for run-8ae38b46, distinct candidate states, inconclusive & blocked probe tracking. |
| `tests/test_phase11_completion_gate_and_finding_consistency.py` | 6 | **6 PASSED** | 1.84s | Candidate matching without root slash collision, attempt retention, completion gate rejection. |
| `tests/test_gap2_pivoting.py` | 4 | **4 PASSED** | 0.95s | GAP-2 bounded retry state machine ($k=2$), threshold transitions, and exhaustion completion. |
| `tests/test_gap_bridge.py` | 12 | **12 PASSED** | 1.48s | GAP-1 queue ranking, task prompt injection, outcome recording, and guidance text formatting. |
| **Total Focused Regression Gate** | **62** | **62 PASSED** | **8.18s** | **100% Pass Rate** |

### 2.2 Detailed Coverage of Remediation Tests (`test_assessment_integrity_run_14ee778a_remediation.py`)

1. `test_candidate_cannot_be_verified_vulnerability_without_findings`: Asserts candidates with positive probe outcomes become `VALIDATED_OBSERVATION` when findings count is 0.
2. `test_candidate_becomes_verified_vulnerability_when_matching_finding_exists`: Confirms `VERIFIED_VULNERABILITY` is assigned only when an active finding confirms exploitability.
3. `test_recon_probes_alone_do_not_produce_verified_vulnerabilities` (5 test variants): Evaluates robots.txt, security.txt, Swagger UI, wildcard CORS, and missing CSP. All 5 are verified as observations.
4. `test_scan_matrix_unexecuted_categories_strictly_not_tested`: Verifies unexecuted checks produce `NOT TESTED (0 executed)`.
5. `test_scan_matrix_partially_tested_categories_cannot_be_passed`: Verifies partially tested checks produce `PARTIALLY TESTED`.
6. `test_scan_matrix_passed_only_when_fully_executed_and_clean`: Verifies `PASSED` requires `executed >= configured` and 0 findings.
7. `test_evidence_domain_isolation_prevents_csp_cors_cross_contamination`: Verifies CSP candidates reject CORS coverage records.
8. `test_duplicate_tool_invocations_tracked_truthfully`: Verifies shared tool executions record duplicate evidence associations without inflating unique invocations (6 unique tool invocations across 8 candidate evaluations).
9. `test_gap2_queue_exhaustion_produces_abandon_event_without_synthetic_pivot`: Verifies queue exhaustion emits `GAP2_ABANDON` with `pivot_executed=False` and 0 pivot count.
10. `test_lifecycle_turns_decoupled_from_vulnerability_completeness`: Verifies 43/500 turns used is decoupled from 25.0% category coverage and 0 confirmed findings.
11. `test_markdown_report_sanitization_removes_unsupported_critical_claims`: Verifies markdown executive summary and technical analysis severity labels are converted from critical/high to observation.
12. `test_reconcile_run_directory_run_14ee778a_produces_zero_validation_errors`: Validates end-to-end artifact reconciliation on `strix_runs/run-14ee778a/`.

---

## 3. Static Code Analysis & Security Scans

### 3.1 Ruff Lint & Formatting Check
```bash
.venv/bin/python -m ruff check strix/report/reconciliation.py strix/core/decision_engine/schemas.py strix/core/gap_bridge.py tests/test_assessment_integrity_run_14ee778a_remediation.py
```
- **Result:** `All checks passed!` (0 errors across 4 files).

### 3.2 Mypy Static Type Checking
```bash
.venv/bin/python -m mypy strix/report/reconciliation.py strix/core/decision_engine/schemas.py tests/test_assessment_integrity_run_14ee778a_remediation.py
```
- **Result:** `Success: no issues found in 3 source files`. Strict type annotations maintained.

### 3.3 Bandit Security Code Audit
```bash
.venv/bin/python -m bandit -r strix/report/reconciliation.py strix/core/decision_engine/schemas.py -ll -ii
```
- **Result:**
  - Scanned: 876 lines of code.
  - High Severity: 0
  - Medium Severity: 0
  - Undefined: 0
  - Conclusion: `No issues identified.`

---

## 4. Visual PDF Report Inspection (`vapt_report_run-14ee778a.pdf`)

Using the virtual environment's `pypdfium2` rendering engine, the generated PDF report (`strix_runs/run-14ee778a/vapt_report_run-14ee778a.pdf`, size 5,644 bytes) was rendered at 2.0x DPI scale into high-resolution PNG images in `screenshots/pdf_inspection_run_14ee778a/`:

- `page_1.png` (1191 × 1684 px)
- `page_2.png` (1191 × 1684 px)
- `page_3.png` (1191 × 1684 px)

### 4.1 Page-by-Page Forensic Layout Breakdown

#### Page 1: Cover & Metadata Header
- **Branding:** Dark themed header banner with AI-VAPT logo typography (`AI-VAPT PENETRATION TEST REPORT`).
- **Target URL:** `http://127.0.0.1:3000/#/` (untruncated, properly wrapped).
- **Assessment Metadata Grid:**
  - Run Name: `run-14ee778a`
  - Scan Mode: `deep`
  - Status: `completed`
  - Started: `2026-11-17 07:35 UTC`
  - Completed: `2026-11-17 07:52 UTC`
  - Duration: `16m 38s`
  - Classification: `CONFIDENTIAL`
- **Visual Quality:** Crisp font rendering, precise margins (20mm left/right, 22mm top, 24mm bottom). Zero clipping.

#### Page 2: Executive Summary, Scan Matrix & Port Inventory
- **Executive Severity Grid:**
  - `0 CRITICAL` | `0 HIGH` | `0 MEDIUM` | `0 LOW`
  - Subtitle: *"0 total confirmed findings across this assessment."*
- **Execution Telemetry Callout:**
  - `RUN LIFECYCLE`: *"Run process completed — 43 of 500 turns used."*
  - `PROBES EXECUTED`: *"8 concrete tool probe executions recorded"*
  - `GAP-1 CANDIDATES`: *"8 identified | 8 investigated (7 validated observations, 0 verified vulnerabilities, 1 abandoned)"*
  - `GAP-2 ADAPTIVE PIVOTS`: *"0 executed (No adaptive pivots were executed during this assessment)"*
- **Vulnerability Category Scan Matrix:**
  | Category | Executed / Configured | Findings | Audit Status |
  | :--- | :--- | :--- | :--- |
  | Version-based vulnerability detection | 3 executed (12 configured) | 0 finding(s) | `PARTIALLY TESTED` |
  | Common configuration issues | 4 executed (22 configured) | 0 finding(s) | `PARTIALLY TESTED` |
  | XSS testing using real browsers | 0 executed (8 configured) | 0 finding(s) | `NOT TESTED` |
  | SQL Injection | 0 executed (14 configured) | 0 finding(s) | `NOT TESTED` |
  | Server-Side Request Forgery (SSRF) | 0 executed (8 configured) | 0 finding(s) | `NOT TESTED` |
  | Server-Side Template Injection | 0 executed (8 configured) | 0 finding(s) | `NOT TESTED` |
  | Client-Side Prototype Pollution | 0 executed (6 configured) | 0 finding(s) | `NOT TESTED` |
  | Python, Javascript, PHP Code Injection | 0 executed (10 configured) | 0 finding(s) | `NOT TESTED` |
- **Port & Environmental Scope Inventory:**
  - Port 3000/TCP: `HTTP Web Service`, Scope: `Target Scope`, Confidence: `CONFIRMED`
  - Port 8000/TCP: `Unfingerprinted TCP Listener`, Scope: `Environmental`, Confidence: `UNCONFIRMED`
  - Port 9090/TCP: `Unfingerprinted TCP Listener`, Scope: `Environmental`, Confidence: `UNCONFIRMED`
- **Pagination Footer:** `Page 2 of 3`. No overlapping text with table borders.

#### Page 3: Findings Section
- **Section Heading:** `Findings`
- **Body Text:** *"No findings were recorded for this run."*
- **Pagination Footer:** `Page 3 of 3`.
- **Layout Verdict:** Zero orphan rows or orphan section headers. Page budget strictly adhered to 3 pages.

---

## 5. Multi-Surface Audit Alignment

All five reporting surfaces for `run-14ee778a` are now completely synchronized:

| Surface | Confirmed Findings | GAP-1 Observations | GAP-2 Pivots | Category Matrix Status |
| :--- | :--- | :--- | :--- | :--- |
| **REST API (`/runs/{id}`)** | 0 | 7 Validated Observations, 1 Abandoned | 0 | 6 NOT TESTED, 2 PARTIALLY TESTED |
| **JSON (`run.json`)** | `[]` (0 count) | `validated_observations: 7`, `verified_vulnerabilities: 0` | 0 | Truthful `executed_checks` & statuses |
| **Markdown (`penetration_test_report.md`)** | 0 | 7 Observations listed as `(Observation)` | 0 | Reconciled narrative, zero critical claims |
| **HTML (`vapt_report_run-14ee778a.html`)** | 0 | 7 Cyan `OBSERVATION` badges | 0 | Clean tables, 0 executed pivots |
| **PDF (`vapt_report_run-14ee778a.pdf`)** | 0 | `(7 validated observations, 0 verified vulnerabilities)` | 0 | Clean 3-page layout, zero false PASSED |
| **Web Console UI (DAG / Tables)** | 0 | Cyan `ℹ OBSERVATION` node badges | 0 | No synthetic red loop edges |

---

## 6. Regression Gate Verdict

**FINAL REGRESSION VERDICT: PASS (100% Verified).**  
All identified assessment integrity defects have been remediated, verified with targeted and suite-level unit/integration tests, visually audited via PDF rendering, and reconciled across all export formats.
