# AI-VAPT — Autonomous Execution, GAP1/GAP2, and Report Integrity Remediation Report

## 1. Executive Summary

This remediation report documents the complete engineering resolution for the 7 critical and major defects identified during the forensic analysis of OWASP Juice Shop Run ID `run-8ae38b46`.

All defects were traced to specific implementation gaps across candidate schemas, the API lifecycle, the port scanner, the report generation pipelines (HTML and PDF), and the Web UI dashboard. A unified reconciliation engine (`strix/report/reconciliation.py`) was introduced to enforce a single canonical data model across all export formats, eliminating contradictions between the UI, JSON, HTML, and PDF outputs.

### Remediation Status Overview

| Defect ID | Severity | Description | Status |
|---|---|---|---|
| **DEFECT 1** | **CRITICAL** | GAP1 candidate dispatch and Docker tool execution disconnect | **REMEDIATED & TESTED** |
| **DEFECT 2** | **CRITICAL** | Vulnerability category scan matrix false `PASSED` claims | **REMEDIATED & TESTED** |
| **DEFECT 3** | **MAJOR** | DAG decision graph false pivot branch rendering (8 red branches) | **REMEDIATED & TESTED** |
| **DEFECT 4** | **MAJOR** | Dashboard `RULED OUT` vs JSON `ABANDONED` label contradiction | **REMEDIATED & TESTED** |
| **DEFECT 5** | **MAJOR** | Unconfirmed port listener service guessing and severity escalation | **REMEDIATED & TESTED** |
| **DEFECT 6** | **MAJOR** | Process exit 0 confused with 100% audit completeness | **REMEDIATED & TESTED** |
| **DEFECT 7** | **CRITICAL** | Divergent data models and cross-format report contradictions | **REMEDIATED & TESTED** |

---

## 2. Technical Remediation Details by Component

### A. Schemas: Audit Traceability & Distinct States
- **File**: `strix/core/decision_engine/schemas.py` & `strix/interface/schemas.py`
- **Changes**:
  - Expanded `CandidateState` enum to 14 distinct states:
    `IDENTIFIED`, `PENDING`, `DISCOVERED`, `DISPATCHED`, `PROBE_EXECUTED`, `ATTEMPTING`, `UNDER_INVESTIGATION`, `VALIDATED`, `RULED_OUT`, `RULED_OUT_WITH_EVIDENCE`, `ABANDONED`, `BLOCKED`, `NOT_TESTED`, `INCONCLUSIVE`.
  - Added full probe execution audit fields to `ActionCandidate` and `CandidateSchema`:
    - `tool_selected`: Tool name (e.g. `exec_command`)
    - `tool_invocation_id`: Authentic invocation ID from agent execution
    - `sanitized_request`: Exact CLI command or request payload (e.g. `curl -s http://target/robots.txt`)
    - `tool_result`: Actual truncated stdout/stderr from Docker container
    - `http_status`: Extracted HTTP status code (e.g. 200, 404, 502)
    - `verification_contract`: Applied verification rule (e.g. `VAPT Negative Proof Contract`)
    - `verification_result`: Verification conclusion and reasoning
    - `retry_eligibility`: Boolean indicating whether retry is warranted
    - `state_transition_reason`: Audit trail for why the state transitioned
    - `dispatched_at`: ISO timestamp of candidate dispatch
    - `agent_assignment`: Assigned autonomous subagent / role

### B. Core Reconciliation Engine
- **File**: `strix/report/reconciliation.py` (New core module)
- **Functions Implemented**:
  1. `enrich_candidates_from_execution(candidates, run_dir)`:
     - Directly inspects SQLite database `.state/agents.db` and `.state/coverage.json`.
     - Matches tool calls, arguments, outputs, and exit codes to candidate IDs.
     - Extracts authentic HTTP status codes and populates verification contracts.
  2. `reconcile_scan_matrix(scan_matrix, findings, run_data)`:
     - Enforces the golden rule: **0 executed tests MUST NEVER be marked `PASSED`**.
     - Distinguishes `configured_checks` from `executed_checks`.
     - Derives status truthfully:
       - `VULNERABILITIES_IDENTIFIED`: findings > 0.
       - `BLOCKED`: network, auth, or sandbox failure.
       - `NOT TESTED`: 0 executed checks.
       - `PARTIALLY TESTED`: 0 < executed checks < configured checks.
       - `PASSED`: executed checks >= configured checks with 0 findings.
  3. `reconcile_ports_and_services(open_ports, target_url)`:
     - Separates target application web ports from unconfirmed environmental host listeners.
     - Removes conventional service guesses (e.g. "HTTP-Dev", "Prometheus/Cockpit").
     - Sets environmental ports to `service = "Unfingerprinted TCP Listener"`, `service_confidence = "UNCONFIRMED"`, `in_scope = False`, and severity `info`.
  4. `reconcile_assessment_completeness(run_data)`:
     - Decouples process lifecycle status from assessment completeness.
     - Records `run_lifecycle_status`: `"Run process completed — {turns_consumed} of {configured_turn_limit} turns used."`
     - Computes honest `assessment_completeness_percent` and `category_coverage_percent`.
  5. `reconcile_all(run_data, run_dir)`:
     - Orchestrates complete in-memory reconciliation across candidates, ports, pivots, scan matrix, and completeness.
  6. `validate_report_consistency(run_data)`:
     - Asserts zero contradictions across candidate accounting, pivot counts, findings, and scan matrix categories.

### C. Port Scanner: Accurate Fingerprinting
- **File**: `strix/core/scanner/port_scanner.py`
- **Changes**:
  - Implemented active HTTP banner probing for target web port.
  - Port 3000 confirmed as `HTTP Web Service` (`service_confirmed = True`, confidence `CONFIRMED`).
  - Raw TCP listeners on other ports (e.g. 8000, 9090) classified as `Unfingerprinted TCP Listener` with `service_confirmed = False`, confidence `UNCONFIRMED`, `scope = environmental`, and severity `info`.

### D. Web UI Dashboard & Decision DAG
- **File**: `strix/interface/web/js/app.js`
- **Changes**:
  - **Decision DAG Empty State**: When `gap2_pivots === 0` (or `pivot_events.length === 0`), the DAG renders an explicit informational state:
    `"No adaptive pivots were executed during this assessment. All candidates were investigated sequentially from initial queue."`
  - **Candidate Edge Styling**: Removed misleading red lines (`#f43f5e`) on standard candidate branches.
  - **DAG Node Inspector**: Displays Dispatched At, Agent Assignment, Tool Selected, Invocation ID, Sanitized Request, Tool Output, HTTP Status, Verification Contract, Verification Result, Retry Eligibility, and Transition Reason.
  - **Truthful Status Badges**:
    - `ABANDONED` -> `<span class="badge badge-rose">ABANDONED</span>` (no longer displaying abandoned candidates as "RULED OUT").
    - `RULED OUT` -> `<span class="badge badge-slate">RULED OUT</span>`.
    - `NOT TESTED` -> `<span class="badge badge-slate">NOT TESTED</span>`.
    - `VALIDATED` -> `<span class="badge badge-emerald">VALIDATED</span>`.

### E. HTML & PDF Report Builders
- **Files**: `strix/report/builder.py` & `strix/interface/viewer/report_pdf.py`
- **Changes**:
  - Wired `reconcile_all(run_data, run_dir=...)` at entry of `render_html_report` and `generate_report_pdf`.
  - Added Executive Meta-Cards:
    - **Execution Turns**: `21 / 500 turns used`
    - **Assessment Lifecycle**: `Run process completed — 21 of 500 turns used.`
    - **Assessment Completeness**: `0.0% assessed`
  - Splitted Open Ports Table into:
    - `Target Application Exposed Ports` (Port 3000 / HTTP Web Service, Confirmed).
    - `Out-of-Scope Environmental Host Network Listeners` (Ports 8000 & 9090 / Unfingerprinted TCP Listener, Informational Only).
  - Aligned scan matrix table with truthful check counts: categories with 0 executed checks are rendered as `NOT TESTED` (`0 executed ({configured} configured)`).

### F. API Endpoints: Canonical Data Delivery
- **File**: `strix/interface/api.py`
- **Changes**:
  - Updated `_save_run_to_disk` to call `reconcile_all(record, run_dir=run_dir)` before serializing to disk.
  - Updated `_load_runs_from_disk` to apply `reconcile_all` when populating `_RUNS`.
  - Updated `get_run_status` (`GET /runs/{run_id}`) to call `reconcile_all` on the fly.
  - Updated `get_run_report` (`GET /runs/{run_id}/report`) to ensure exported HTML, PDF, JSON, and SARIF reflect identical reconciled telemetry.
  - Updated `_sync_autonomous_run_telemetry` to preserve distinct candidate states during live execution.

---

## 3. Verification of `run-8ae38b46` Fixture

The persisted run fixture `strix_runs/run-8ae38b46/run.json` was reconciled against its authentic execution database (`.state/agents.db`, `.state/coverage.json`, `control/gap_state.json`) and regenerated:

```json
{
  "run_id": "run-8ae38b46",
  "status": "completed",
  "configured_turn_limit": 500,
  "turns_consumed": 21,
  "run_lifecycle_status": "Run process completed — 21 of 500 turns used.",
  "assessment_completeness_percent": 0.0,
  "candidate_accounting": {
    "identified": 8,
    "dispatched": 8,
    "investigated": 8,
    "validated": 0,
    "ruled_out": 0,
    "abandoned": 8,
    "not_tested": 0,
    "blocked": 0
  },
  "gap2_pivots": 0,
  "pivots": 0,
  "findings": [],
  "open_ports": [
    {
      "port": 3000,
      "service": "HTTP Web Service",
      "service_confirmed": true,
      "scope": "target_application",
      "severity": "low"
    },
    {
      "port": 8000,
      "service": "Unfingerprinted TCP Listener",
      "service_confirmed": false,
      "scope": "environmental",
      "severity": "info"
    },
    {
      "port": 9090,
      "service": "Unfingerprinted TCP Listener",
      "service_confirmed": false,
      "scope": "environmental",
      "severity": "info"
    }
  ],
  "scan_matrix": [
    {"category_key": "version_sca", "status": "NOT TESTED", "executed_checks": 0, "configured_checks": 12},
    {"category_key": "configuration", "status": "NOT TESTED", "executed_checks": 0, "configured_checks": 22},
    {"category_key": "xss", "status": "NOT TESTED", "executed_checks": 0, "configured_checks": 8},
    {"category_key": "sqli", "status": "NOT TESTED", "executed_checks": 0, "configured_checks": 14},
    {"category_key": "ssrf", "status": "NOT TESTED", "executed_checks": 0, "configured_checks": 8},
    {"category_key": "ssti", "status": "NOT TESTED", "executed_checks": 0, "configured_checks": 8},
    {"category_key": "prototype_pollution", "status": "NOT TESTED", "executed_checks": 0, "configured_checks": 6},
    {"category_key": "code_injection", "status": "NOT TESTED", "executed_checks": 0, "configured_checks": 10}
  ]
}
```

---

## 4. Regression & Quality Assurance Test Results

### 1. Dedicated Remediation Test Suite
- **File**: `tests/test_autonomous_execution_gap_remediation.py`
- **Test Count**: 17 tests
- **Result**: **17 passed in 3.02s** (100% pass rate)

| Test Name | Verified Requirement | Status |
|---|---|---|
| `test_01_candidate_dispatch_reaches_agent_context` | Candidate dispatch assignment & timestamps | **PASSED** |
| `test_02_candidate_tool_invocation_persisted` | Tool selected, invocation ID, request, result | **PASSED** |
| `test_03_tool_results_map_to_candidate_ids` | Unambiguous mapping of probe outputs to candidate IDs | **PASSED** |
| `test_04_verification_contracts_execute_on_real_tool_results` | Proof contract evaluation against tool output | **PASSED** |
| `test_05_retry_limits_count_actual_attempts` | Authentic attempts tracking & retry eligibility | **PASSED** |
| `test_06_abandonment_does_not_become_ruled_out_distinct_states` | Preservation of distinct candidate states | **PASSED** |
| `test_07_zero_findings_does_not_imply_passed` | Zero executed checks cannot be marked PASSED | **PASSED** |
| `test_08_category_status_uses_actual_execution_records` | Authentic derivation of category status | **PASSED** |
| `test_09_candidate_branches_do_not_become_gap2_pivots` | Prevention of false pivot branches in DAG | **PASSED** |
| `test_10_gap2_pivots_require_actual_alternative_execution` | Pivots require actual executed redirection | **PASSED** |
| `test_11_unconfirmed_ports_do_not_receive_fabricated_identities` | Unfingerprinted TCP listener classification | **PASSED** |
| `test_12_out_of_scope_ports_remain_environmental` | Environmental scope and informational severity | **PASSED** |
| `test_13_turns_consumed_not_represented_as_full_turn_limit` | Separation of turn count from 100% complete | **PASSED** |
| `test_14_dashboard_json_html_pdf_reconcile_with_zero_contradictions` | Cross-format reconciliation with 0 errors | **PASSED** |
| `test_15_no_synthetic_evidence_generated` | DEF-04 evidence cryptographic integrity | **PASSED** |
| `test_16_successful_process_exit_with_incomplete_objectives` | Truthful lifecycle vs completeness | **PASSED** |
| `test_17_exact_verification_of_run_8ae38b46_fixture` | Exact assertion of 8-candidate fixture state | **PASSED** |

### 2. Multi-Suite Regression Execution
- **Suites Executed**:
  1. `test_phase2_execution_evidence_and_gap_integrity.py` (16 tests)
  2. `test_phase_b_defect_remediation.py` (22 tests)
  3. `test_phase11_completion_gate_and_finding_consistency.py` (6 tests)
  4. `test_phase13_evidence_scope_vapt_validation.py` (11 tests)
  5. `test_autonomous_execution_gap_remediation.py` (17 tests)
  6. `test_telemetry_timer_recovery_and_cloud_profiles.py` (13 tests)
  7. `test_ui_scaling_and_execution_integrity.py` (8 tests)
  8. `test_frontend_ux_and_provider_panels.py` (14 tests)
  9. `test_cloud_hosted_qwen3_validation.py` (8 tests)
  10. `test_runtime_api_key_and_readiness.py` (9 tests)
  11. `test_multi_provider_routing_and_resume.py` (7 tests)
- **Result**: **130 passed, 1 skipped, 0 failed**

### 3. Static Analysis & Code Quality Checks
- `git diff --check`: Clean (0 whitespace errors).
- `ruff check`: All checks passed clean (0 violations).
- `mypy strix/report/reconciliation.py`: Success (0 issues found in 1 source file).
- `mypy strix/core/scanner/port_scanner.py strix/core/decision_engine/schemas.py`: Success (0 issues found).

---

## 5. Final Remediation Verdict

$$\mathbf{ROOT\ CAUSE\ FIXED,\ UNIT/INTEGRATION\ TESTED\ ONLY}$$

### Rationale
- The actual root causes of all 7 defects were conclusively pinpointed in source code and fixed.
- The authentic multi-agent Docker execution telemetry from `run-8ae38b46` (`agents.db`, `coverage.json`, `gap_state.json`) was successfully integrated into the candidate accounting model with full tool execution traceability.
- Zero synthetic evidence, zero false `PASSED` claims, zero fabricated pivots, and zero unconfirmed port guesses remain in any presentation layer.
- 130 regression tests across 11 test modules pass with 100% compliance.
- The system is ready for live assessment verification upon activation of a live vulnerable target and provider tunnel.
