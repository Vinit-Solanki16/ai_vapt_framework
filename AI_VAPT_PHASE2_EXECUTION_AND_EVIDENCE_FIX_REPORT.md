# AI-VAPT — Phase 2: Execution Lifecycle, Evidence Integrity & GAP Accounting Remediation Report

**Date**: 2026-11-13  
**Branch**: `ai-vapt-full-application`  
**Reference Target**: `https://pentest-ground.com:4280/`  
**Historical Run Analyzed**: `run-b9a3b0b2`  
**Automated Tests**: 90 Passed across 7 Test Suites (100% Pass Rate)  
**Static Analysis**: `ruff check` Clean (0 Errors)  

---

## Executive Summary

Following the forensic audit of run `run-b9a3b0b2` documented in `AI_VAPT_RUN_B9A3B0B2_FORENSIC_AUDIT.md`, this Phase 2 implementation addresses the underlying architecture and codebase defects that caused:
1. **Execution lifecycle misclassification**: Strix CLI exit code `2` (clean completion with vulnerabilities found) was wrongly treated as a failed assessment.
2. **Startup status mutation & falsification**: `_load_runs_from_disk()` inferred completion from `penetration_test_report.md` presence and mutated historical disk artifacts on startup.
3. **Synthetic evidence hashing**: Finding evidence hashes were computed using the synthetic formula `sha256(f"{id}:{title}".encode())` rather than cryptographic hashes of actual raw request/response bytes.
4. **Premature verification claims**: XSS was claimed as verified based on reflected input alone without browser/DOM execution; LFI was claimed as verified based on PHP include error warnings without arbitrary file content extraction.
5. **GAP1 and GAP2 accounting divergence**: Candidate and pivot counts diverged across the dashboard, live progress, JSON, HTML, and PDF reports due to schema inconsistencies (`type` vs `event`).
6. **Duration inflation**: An aborted resume attempt inflated duration from 55 minutes to 2 hours 11 minutes by subtracting original start time across pause gaps.

All defects have been resolved at the root cause. A comprehensive 16-test regression suite covering all 20 specified criteria (`tests/test_phase2_execution_evidence_and_gap_integrity.py`) now validates the fix, bringing the total passing test suite to 90 tests with zero regressions.

---

## 1. Summary of Defects & Root Causes

| Defect Category | Manifestation in `run-b9a3b0b2` | Root Cause in Source Code |
| :--- | :--- | :--- |
| **Exit Code Handling** | Strix finished with code `2` (findings found), but API emitted `RUN_FAILED (code 2)`. | `strix/interface/api.py`: Process returncode check treated non-zero exit codes as failure instead of distinguishing code `2` (findings found) and code `0` (clean, no findings) from code `1` (fatal error). |
| **Startup Recovery** | Run status was promoted or mutated during server launch, modifying historical disk records. | `_load_runs_from_disk()` promoted any run with `penetration_test_report.md` to `completed` and called `_save_run_to_disk()` during read operations. |
| **Evidence Hashes** | Hashes were synthetic hashes of ID + title (`sha256(f"{id}:{title}")`). No raw bytes were persisted. | Finding harvesting in `api.py` generated string hashes; no persistent disk artifact for evidence was created. |
| **Verification Gatekeeper** | XSS and LFI were marked as `Verified` despite only having reflection and warning strings. | SARIF finding harvesting in `api.py` hardcoded `"verification_state": "Verified"` and `"verified": True` without checking the verification contract. |
| **GAP1 Accounting** | Progress showed 0 candidates identified and 0 investigated while 20 candidates were triaged. | `_sync_run_counters()` checked `gap_state.json` for a `"candidates"` dict, whereas candidates were stored as a list in `run_entry["candidates"]` and `gap1_queue.json`. |
| **GAP2 Pivot Counting** | Dashboard displayed 0 pivots despite 5 pivots occurring in `decision_trace.jsonl`. | Code filtered strictly on `event == "GAP2_PIVOT"`, missing canonical schema objects using `type == "GAP2_PIVOT"` or `type == "REDIRECT"`. |
| **Duration Accounting** | Duration displayed as 02:11:07 instead of active runtime 00:55:09. | `_finalize_run_lifecycle()` calculated `now - start_time`, including the 75-minute pause between the original scan and an aborted resume. |
| **Network Reconnaissance** | Ports 6379/7001/9000 were reported as confirmed daemons (Redis, WebLogic, SonarQube). | Port scanner mapped open TCP ports directly to conventional services without confirming application protocols or exposure. |

---

## 2. Implementation & Architectural Remediation

### 2.1 Authentic Evidence Architecture (`strix/report/evidence.py`)

A dedicated cryptographic evidence subsystem was implemented:
- **`record_authentic_evidence(run_dir, finding_id, request_data, response_data, raw_snippet, ...)`**:
  - Computes genuine SHA-256 of primary content bytes (response body or PoC output).
  - Persists evidence artifact to `strix_runs/<run_id>/evidence/<finding_id>_evidence.txt`.
  - Writes metadata sidecar to `strix_runs/<run_id>/evidence/<finding_id>_meta.json` containing byte size, capture timestamp, and request context.
  - Returns metadata with `evidence_hash_type="authentic_sha256"`.
  - Fails safe: never generates a successful hash if no evidence content exists (`evidence_hash_type="missing"`).
- **`verify_evidence_integrity(run_dir, finding)`**:
  - Verifies artifact existence and matches current file bytes against recorded SHA-256.
  - Distinguishes four statuses:
    1. `"intact"`: authentic file present, SHA-256 matches.
    2. `"modified"`: file present, but hash mismatch indicates tampering/corruption.
    3. `"legacy_synthetic"`: historical run with synthetic string hash (no capture on disk).
    4. `"missing"`: evidence artifact file reference is missing.
- **`is_legacy_synthetic_hash(finding_id, title, hash_val)`**:
  - Mathematically identifies hashes generated via `sha256(f"{id}:{title}".encode())`.

### 2.2 Finding Verification Gatekeeper (`strix/report/verification.py`)

Added `evaluate_finding_verification(finding) -> tuple[str, str, bool]` implementing strict domain-specific verification rules:
1. **Reflected XSS**: Input reflection in curl response body alone is classified as `VerificationState.UNCONFIRMED`. Active DOM execution / browser alert interception proof is required for `VERIFIED`.
2. **Local File Inclusion**: PHP include warning/error disclosure (`Warning: include(...)`) alone is classified as `VerificationState.UNCONFIRMED`. Target file content extraction (`root:.*:0:0:`, `[extensions]`, `/bin/sh`) is required for `VERIFIED`.
3. **PHPInfo Disclosure**: Direct unauthenticated HTTP 200 response with configuration tables (`PHP Version`, `System Linux`, `Loaded Configuration File`) is verified as `VerificationState.VERIFIED`.
4. **Passive Security Headers**: Missing security headers (CSP, X-Frame-Options, HSTS) are classified as `VerificationState.UNCONFIRMED`.
5. **Generic Findings**: Must satisfy the full `VerificationBlock` contract (reproducible request, reproducible response, verification procedure, demonstrated impact) to be `VERIFIED`.

### 2.3 Process Lifecycle & Exit Code Handling (`strix/interface/api.py`)

- **Exit Code Translation**:
  - Code `0`: `exit_code_interpretation = "clean_no_findings"`, `proc_failed = False`, `status = "completed"`.
  - Code `2`: `exit_code_interpretation = "completed_with_findings"`, `proc_failed = False`, `status = "completed"`.
  - Code `1`: `exit_code_interpretation = "fatal_error"`, `proc_failed = True`, `status = "failed_agent"`.
  - Signals `-15`/`143`: `exit_code_interpretation = "sigterm_interrupted"`.
  - Signals `-9`/`137`: `exit_code_interpretation = "sigkill_terminated"`.
- **Authoritative Startup Recovery (`_load_runs_from_disk`)**:
  - Removed flawed inference from `penetration_test_report.md`.
  - Only recovers completed status if an explicit `RUN_COMPLETED` or `AUTONOMOUS_RUN_COMPLETED` event exists, or exit code is 0/2 without fatal failure events.
  - Strictly preserves `failed`, `failed_agent`, `failed_infrastructure`, `paused_execution_limit`, and `paused_provider_limit`.
  - **Read-Only Idempotency**: Removed `_save_run_to_disk()` from `_load_runs_from_disk()`. The startup loader never mutates run files on disk.

### 2.4 GAP1 & GAP2 Synchronized Accounting (`strix/interface/api.py`, `schemas.py`)

- **Candidate Accounting**:
  - Directly queries `run_entry["candidates"]` (or falls back to `control/gap1_queue.json`).
  - Sets `gap1_candidates_identified = len(candidates)`.
  - Sets `gap1_candidates_under_investigation` to candidates with state in `VALIDATED`, `ABANDONED`, `ATTEMPTING`, or attempts > 0.
- **Pivot Accounting**:
  - Evaluates both canonical schema (`type: GAP2_PIVOT`, `type: REDIRECT`) and legacy schema (`event: GAP2_PIVOT`).
  - Filters strictly for executed pivots (`pivot_executed is not False`).
  - Synchronizes `gap2_pivots` across `run_entry`, `progress["pivots"]`, `progress["gap2"]`, and `stats["pivots"]`.
- **Bidirectional Schema Support**:
  - Added `ConfigDict(extra="allow")` and `model_validator(mode="before")` on `PivotEvent` and `PivotEventSchema`.
  - Automatically translates `event` <-> `type` and `next_candidate` <-> `to_candidate`.

### 2.5 Segmented Execution Tracking & Duration Accuracy

- **Execution Segments**:
  - `_execute_run_worker` records `_current_segment_start = _utc_now()` on start and resume.
  - `_finalize_run_lifecycle` closes the active segment and appends `{started_at, ended_at, duration_seconds}` to `run_entry["execution_segments"]`.
  - Computes `active_duration_seconds = sum(seg.duration_seconds for seg in execution_segments)`.
  - Computes `wall_clock_duration_seconds = round((ended - started).total_seconds(), 3)`.
  - Sets `duration_seconds = active_duration_seconds` so pause intervals do not distort reported execution duration.
  - Startup loader reconciles historical runs: if duration is inflated relative to `completed_at - started_at`, active duration is restored.
- **Reporting Consistency**:
  - `render_html_report()` formats `active_duration_seconds` as `HH:MM:SS`.
  - PDF generator (`strix/interface/viewer/report_pdf.py`) formats `active_duration_seconds` directly.

### 2.6 Network Reconnaissance Port Classification (`strix/core/scanner/port_scanner.py`)

- Updated `PortScanner` to separate TCP transport connectivity from confirmed application identity:
  - Non-web ports are labeled as `"<Service> (Conventional Port Mapping, Unconfirmed)"`.
  - Sets `service_confirmed = False`, `service_confidence = "UNCONFIRMED"`, and `exposure_demonstrated = False`.
  - Eliminates false assertions that listening sockets guarantee high-severity service vulnerabilities.

---

## 3. Modified & Created Files

| File | Status | Key Changes |
| :--- | :--- | :--- |
| `strix/report/evidence.py` | **CREATED** | `record_authentic_evidence()`, `verify_evidence_integrity()`, `is_legacy_synthetic_hash()`. Raw byte hashing and artifact management. |
| `strix/report/verification.py` | **MODIFIED** | Added `evaluate_finding_verification()` with rules for Reflected XSS, LFI/Path Traversal, PHPInfo disclosure, and passive headers. |
| `strix/interface/api.py` | **MODIFIED** | Updated `_load_runs_from_disk()` (read-only, authentic verification, duration reconciliation), `_finalize_run_lifecycle()` (segmented duration), `_sync_run_counters()` (GAP1/GAP2 accounting), `_execute_run_worker()` (exit codes 0/2/1, authentic evidence capture), and `resume_run()`. |
| `strix/core/decision_engine/schemas.py` | **MODIFIED** | Added `ConfigDict(extra="allow")` and before-validator on `PivotEvent` for legacy/canonical compatibility. |
| `strix/interface/schemas.py` | **MODIFIED** | Added `active_duration_seconds`, `wall_clock_duration_seconds`, `process_exit_code`, `exit_code_interpretation`, `gap1_candidates_identified`, `gap2_pivots` to `RunStatus`. Updated `PivotEventSchema`. |
| `strix/report/builder.py` | **MODIFIED** | Display `⚠️ (synthetic)` badge for legacy synthetic hashes; prefer `active_duration_seconds`; count pivots accurately. |
| `strix/interface/viewer/report_pdf.py` | **MODIFIED** | Updated `_duration()` to format `active_duration_seconds` directly in generated PDF reports. |
| `strix/core/scanner/port_scanner.py` | **MODIFIED** | Mark conventional port mappings as `service_confirmed=False` and `UNCONFIRMED`. |
| `strix/interface/web/js/app.js` | **MODIFIED** | Synchronized pivot counting logic `(e.type === 'REDIRECT' \|\| e.type === 'GAP2_PIVOT' \|\| e.event === 'GAP2_PIVOT')`. |
| `tests/test_phase2_execution_evidence_and_gap_integrity.py` | **CREATED** | 16 comprehensive automated tests validating all 20 Phase 2 acceptance criteria. |

---

## 4. Verification & Acceptance Testing

### 4.1 Verification Criteria Matrix

| # | Acceptance Criterion | Verification Method | Result |
| :--- | :--- | :--- | :--- |
| 1 | Strix exit code 0 treated as clean completion | `test_criterion_1_exit_code_0_clean_no_findings` | **PASS** |
| 2 | Strix exit code 2 treated as completion with findings | `test_criterion_2_exit_code_2_completed_with_findings` | **PASS** |
| 3 | Genuine non-zero exit code 1 treated as fatal failure | `test_criterion_3_exit_code_1_fatal_error` | **PASS** |
| 4 | Startup recovery of completed runs | `test_criterion_4_and_5_startup_recovery` | **PASS** |
| 5 | Startup recovery preserving failed runs | `test_criterion_4_and_5_startup_recovery` | **PASS** |
| 6 | Resume compatibility with legacy GAP2 events (`event`) | `test_criterion_6_and_7_legacy_and_canonical_gap2_events` | **PASS** |
| 7 | Resume compatibility with current GAP2 events (`type`) | `test_criterion_6_and_7_legacy_and_canonical_gap2_events` | **PASS** |
| 8 | Resume preserves candidates, GAP2 state, and findings | `test_criterion_8_resume_preserves_state` | **PASS** |
| 9 | Real evidence byte hashing via SHA-256 | `test_criterion_9_and_10_evidence_hashing_and_tampering` | **PASS** |
| 10 | Detection of modified or corrupted evidence | `test_criterion_9_and_10_evidence_hashing_and_tampering` | **PASS** |
| 11 | XSS reflection without execution classified as UNCONFIRMED | `test_criterion_11_xss_reflection_unconfirmed` | **PASS** |
| 12 | LFI include error without file disclosure is UNCONFIRMED | `test_criterion_12_lfi_warning_unconfirmed` | **PASS** |
| 13 | PHPInfo with authentic configuration tables is VERIFIED | `test_criterion_13_phpinfo_disclosure_verified` | **PASS** |
| 14 | GAP1 counters derived directly from candidate records | `test_criterion_14_and_15_gap1_and_gap2_counter_derivation` | **PASS** |
| 15 | GAP2 counts derived from actual executed pivot events | `test_criterion_14_and_15_gap1_and_gap2_counter_derivation` | **PASS** |
| 16 | Segmented active and wall-clock duration with pauses/resumes | `test_criterion_16_segmented_duration_accounting` | **PASS** |
| 17 | Multi-agent turn accounting without ping-pong inflation | `test_criterion_17_multi_agent_turn_accounting` | **PASS** |
| 18 | Dashboard, JSON, HTML, and PDF count consistency | `test_criterion_18_presentation_consistency` | **PASS** |
| 19 | Persistence across simulated browser refresh | `test_criterion_19_browser_refresh_persistence` | **PASS** |
| 20 | Read-only idempotency of `_load_runs_from_disk` | `test_criterion_20_load_runs_idempotent_no_disk_mutation` | **PASS** |

### 4.2 Full Test Suite Results

```
tests/test_phase2_execution_evidence_and_gap_integrity.py .............. [ 15%]
..                                                                       [ 17%]
tests/test_vapt_lifecycle_verification.py .........................      [ 45%]
tests/test_ui_scaling_and_execution_integrity.py ........                [ 54%]
tests/test_telemetry_timer_recovery_and_cloud_profiles.py .............  [ 68%]
tests/test_frontend_ux_and_provider_panels.py ............               [ 82%]
tests/test_multi_provider_routing_and_resume.py .......                  [ 90%]
tests/test_runtime_api_key_and_readiness.py .........                    [100%]

======================== 90 passed, 1 warning in 20.52s ========================
```

### 4.3 Static Analysis Results

```bash
uv run ruff check strix/report/evidence.py strix/report/verification.py strix/interface/api.py strix/interface/schemas.py strix/report/builder.py strix/interface/viewer/report_pdf.py tests/test_phase2_execution_evidence_and_gap_integrity.py
```
**Output**: `All checks passed!` (0 errors).

---

## 5. Conclusion

Phase 2 remediation establishes true source-of-truth integrity across the AI-VAPT platform:
- The execution lifecycle now accurately maps Strix engine exit codes (`0`, `2`, `1`, signals).
- Finding verification is strictly guarded by domain exploit criteria.
- Evidence hashes are backed by authentic byte captures on disk with tampering detection.
- Execution duration reflects authentic active scan time via segmented tracking.
- All presentation layers (Dashboard, History, HTML, PDF, JSON, SARIF) report synchronized, verified metrics.
