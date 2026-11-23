# AI-VAPT Framework — Validation Evidence Log

## 1. Execution Environment Fingerprint
- **Audit Date:** 2026-11-23
- **Operating System:** Linux 6.6.137+ x86_64
- **Python Version:** 3.12.14 (`.venv`)
- **Package Manager / Runner:** `uv 0.12.19`
- **Test Framework:** `pytest 9.1.1`
- **Repository Baseline Snapshots:**
  - `ai-vapt-full-application`: `553751d3c9d9555dc9e26b8a5ecb17243349b477`
  - `ai-vapt-release`: `2a278e73653b979df5347049d440357710c343f7`
  - `main`: `271c06473e9e74c4ceec97dc2aea39224908f145`

---

## 2. Hardened Git Branches & Commit Ledger

### 2.1 Full Application Hardening Branch (`fix/ai-vapt-hardening`)
*Created from `ai-vapt-full-application` (`553751d`):*
1. `54c84bd`: `fix(security): resolve audit findings A01-A08 (Phase P0)`
2. `3ff2337`: `fix(reporting): resolve evidence truth, completion gate and verification findings C01-C13 (Phase P1)`
3. `824b522`: `fix(gap): remediate findings B01-B06 for GAP-1 dispatch and GAP-2 verified pivoting`
4. `3b60b3e`: `docs(audit): record verified status and patch hash 824b522 for B01-B06`
5. `26c4937`: `fix(release): remediate findings D01-D05 for CI triggers, governance, and regression tests`
6. `e01f0ab`: `docs(audit): record verified status and patch hash 26c4937 for D01-D05`

### 2.2 Curated Release Candidate Branch (`fix/ai-vapt-release-candidate`)
*Created from `origin/ai-vapt-release` (`2a278e7`):*
1. `2ef280e`: `fix(security): resolve audit findings A01-A08 (Phase P0)`
2. `ec17630`: `fix(reporting): resolve evidence truth, completion gate and verification findings C01-C13 (Phase P1)`
3. `9977574`: `fix(gap): remediate findings B01-B06 for GAP-1 dispatch and GAP-2 verified pivoting`
4. `1eb72c2`: `fix(release): remediate findings D01-D05 for CI triggers, governance, and regression tests`
5. `dc0aa31`: `docs(fixtures): add provenance and sanitization manifest for test fixtures`
6. `8a6500f`: `fix(api): remove duplicate unauthenticated docker cleanup route`

---

## 3. Automated Test Suite Verification

### 3.1 Test Execution Command
```bash
.venv/bin/pytest tests/test_audit_remediation_a01_a08.py \
                 tests/test_audit_remediation_b01_b06.py \
                 tests/test_audit_remediation_c01_c13.py \
                 tests/test_audit_remediation_d01_d05.py \
                 tests/test_interface_api.py
```

### 3.2 Test Results Summary
```text
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/vinit/AI_VAPT/ai_vapt_framework
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.14.1

tests/test_audit_remediation_a01_a08.py ...........                      [ 17%]
tests/test_audit_remediation_b01_b06.py ...............                  [ 41%]
tests/test_audit_remediation_c01_c13.py .............                    [ 61%]
tests/test_audit_remediation_d01_d05.py ......                           [ 71%]
tests/test_interface_api.py ..................                           [100%]

======================== 63 passed, 1 warning in 9.83s =========================
```

---

## 4. Remediation Coverage Matrix by Audit Finding

| ID | Title / Subsystem | Verification Test | Status |
|---|---|---|---|
| **A01** | Central operator auth / RBAC / CSRF | `test_a01_unauthenticated_api_rejected_when_auth_required` | **PASSED (100%)** |
| **A02** | Target scope validation against engagement record | `test_a02_unauthorized_external_target_rejected` | **PASSED (100%)** |
| **A03** | Cloud provider TLS certificate verification | `test_a03_provider_tls_verification` | **PASSED (100%)** |
| **A04** | Scanner HTTP transport default verified TLS | `test_a04_scanner_ssl_context_defaults` | **PASSED (100%)** |
| **A05** | Per-run subprocess environment credential isolation | `test_a05_runtime_credentials_isolation` | **PASSED (100%)** |
| **A06** | Target token sanitized from `--instruction` argv | `test_a06_target_token_not_in_instruction` | **PASSED (100%)** |
| **A07** | Target redirect boundary and metadata SSRF protection | `test_a07_redirect_out_of_scope_blocked` | **PASSED (100%)** |
| **A08** | Custom provider endpoint scheme and SSRF validation | `test_a08_custom_provider_ssrf_blocked` | **PASSED (100%)** |
| **B01** | Honest heuristic/model scoring provenance | `test_b01_heuristic_scorer_provenance` | **PASSED (100%)** |
| **B02** | Discovery order vs ranked queue order preservation | `test_b02_discovery_order_and_ranking_changed` | **PASSED (100%)** |
| **B03** | Candidate ticket scheduler priority enforcement | `test_b03_scheduler_priority_dispatch` | **PASSED (100%)** |
| **B04** | GAP-2 separate PIVOT_DECIDED and PIVOT_VERIFIED | `test_b04_decision_engine_sets_pivot_executed_false_at_decision_time` | **PASSED (100%)** |
| **B05** | Missing native GAP state fails closed (unverified) | `test_b05_missing_native_gap_state_does_not_infer_execution` | **PASSED (100%)** |
| **B06** | Native pivot count requires linked tool execution ID | `test_b06_gap_run_rejects_caller_supplied_flag_without_tool_id` | **PASSED (100%)** |
| **C01** | Benign GET text (mysql, <script>) produces candidate only | `test_c01_benign_text_not_verified` | **PASSED (100%)** |
| **C02** | VerificationBlock rejects generic text placeholders | `test_c02_verification_contract_requires_impact` | **PASSED (100%)** |
| **C03** | Passive rule findings emitted as observations | `test_c03_passive_rules_emit_observations` | **PASSED (100%)** |
| **C04** | Reconciliation eliminates synthetic curl and false dispatch | `test_c04_reconciliation_no_fabricated_curl` | **PASSED (100%)** |
| **C05** | Reconciliation eliminates hardcoded CORS claims | `test_c05_no_hardcoded_cors_claims` | **PASSED (100%)** |
| **C06** | Finding state links strictly by candidate ID | `test_c06_candidate_finding_link_exact` | **PASSED (100%)** |
| **C07** | Evidence file write failure fails closed (`intact: False`) | `test_c07_evidence_write_failure_fails_closed` | **PASSED (100%)** |
| **C08** | Evidence file paths sanitized against directory traversal | `test_c08_evidence_path_containment` | **PASSED (100%)** |
| **C09** | Completion gate fails closed on corrupt/missing queue | `test_c09_completion_gate_fails_closed` | **PASSED (100%)** |
| **C10** | `finish_scan` returns unsuccessful on persistence failure | `test_c10_finish_scan_persistence_failure` | **PASSED (100%)** |
| **C11** | Minimum execution threshold enforces security tools | `test_c11_minimum_coverage_enforcement` | **PASSED (100%)** |
| **C12** | Single canonical verification state (no legacy hash promote)| `test_c12_single_canonical_verification_truth` | **PASSED (100%)** |
| **C13** | Canonical versioned evidence envelope (v1.0) | `test_c13_versioned_evidence_envelope` | **PASSED (100%)** |
| **D01** | SPA decision graph matches findings strictly by candidate ID| `test_d01_unrelated_findings_do_not_validate_candidate` | **PASSED (100%)** |
| **D02** | SVG renderer uses DOM APIs without inline onclick sinks | `test_d02_svg_renderer_avoids_inline_onclick` | **PASSED (100%)** |
| **D03** | Docker cleanup preserves running containers by default | `test_d03_running_sandboxes_preserved_by_default` | **PASSED (100%)** |
| **D04** | CI workflow includes push triggers for all active branches | `test_d04_ci_workflow_branch_triggers` | **PASSED (100%)** |
| **D05** | Version alignment and secret-free fixtures verified | `test_d05_release_metadata_alignment` | **PASSED (100%)** |
