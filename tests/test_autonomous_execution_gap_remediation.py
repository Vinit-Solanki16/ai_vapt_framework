"""Regression test suite for Autonomous Execution, GAP1/GAP2 tracking, and Report Integrity Remediation.

Fixture: OWASP Juice Shop Run ID run-8ae38b46.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from strix.core.decision_engine.schemas import CandidateState
from strix.interface.viewer.report_pdf import generate_report_pdf
from strix.report.builder import render_html_report
from strix.report.reconciliation import (
    enrich_candidates_from_execution,
    reconcile_all,
    reconcile_assessment_completeness,
    reconcile_ports_and_services,
    reconcile_scan_matrix,
    validate_report_consistency,
)


_LOCAL_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "run-8ae38b46"
_RUNS_FIXTURE = Path(__file__).resolve().parent.parent / "strix_runs" / "run-8ae38b46"
FIXTURE_DIR = _LOCAL_FIXTURE if _LOCAL_FIXTURE.is_dir() else _RUNS_FIXTURE


@pytest.fixture
def run_8ae38b46_data() -> dict[str, Any]:
    """Load the raw or reconciled run-8ae38b46 run.json fixture."""
    run_file = FIXTURE_DIR / "run.json"
    if not run_file.is_file():
        pytest.skip(f"Fixture run.json missing at {run_file}")
    return json.loads(run_file.read_text(encoding="utf-8"))


class TestAutonomousExecutionAndGapRemediation:
    """Test suite covering the 7 defects and 17 regression requirements."""

    def test_01_candidate_dispatch_reaches_agent_context(self, run_8ae38b46_data: dict[str, Any]):
        """Requirement 1: Candidate dispatch reaches agent context."""
        candidates = run_8ae38b46_data.get("candidates", [])
        assert len(candidates) == 8
        for cand in candidates:
            assert cand.get("dispatched") is True
            assert cand.get("agent_assignment") is not None
            assert cand.get("dispatched_at") is not None

    def test_02_candidate_tool_invocation_persisted(self, run_8ae38b46_data: dict[str, Any]):
        """Requirement 2: Candidate-specific tool invocation is persisted with tool name, invocation ID, request, and result."""
        candidates = run_8ae38b46_data.get("candidates", [])
        for cand in candidates:
            assert cand.get("tool_selected") is not None, (
                f"Candidate {cand['id']} missing tool_selected"
            )
            assert cand.get("tool_invocation_id") is not None, (
                f"Candidate {cand['id']} missing tool_invocation_id"
            )
            assert cand.get("sanitized_request") is not None, (
                f"Candidate {cand['id']} missing sanitized_request"
            )
            assert cand.get("tool_result") is not None, (
                f"Candidate {cand['id']} missing tool_result"
            )
            assert len(cand["tool_invocation_id"]) >= 8

    def test_03_tool_results_map_to_candidate_ids(self, run_8ae38b46_data: dict[str, Any]):
        """Requirement 3: Tool results map to candidate IDs without loss or misattribution."""
        candidates = enrich_candidates_from_execution(
            run_8ae38b46_data.get("candidates", []),
            FIXTURE_DIR,
        )
        assert len(candidates) == 8
        c_robots = next(c for c in candidates if c["id"] == "sensitive-path-robotstxt")
        assert "robots.txt" in c_robots["sanitized_request"]
        assert c_robots["http_status"] == 200

        c_sec = next(c for c in candidates if c["id"] == "sensitive-path-wellknownsecuritytxt")
        assert "security.txt" in c_sec["sanitized_request"]

    def test_04_verification_contracts_execute_on_real_tool_results(
        self, run_8ae38b46_data: dict[str, Any]
    ):
        """Requirement 4: Verification contracts execute on real tool results."""
        candidates = run_8ae38b46_data.get("candidates", [])
        for cand in candidates:
            contract = cand.get("verification_contract")
            v_res = cand.get("verification_result")
            assert contract is not None, f"Candidate {cand['id']} missing verification_contract"
            assert v_res is not None, f"Candidate {cand['id']} missing verification_result"
            assert "Proof Contract" in contract

    def test_05_retry_limits_count_actual_attempts(self, run_8ae38b46_data: dict[str, Any]):
        """Requirement 5: Retry limits count actual attempts, not speculative attempts."""
        candidates = run_8ae38b46_data.get("candidates", [])
        for cand in candidates:
            assert cand.get("attempts") == 1
            assert cand.get("max_attempts") == 2
            # Since probe was conclusive negative, retry eligibility is False
            assert cand.get("retry_eligibility") is False

    def test_06_abandonment_does_not_become_ruled_out_distinct_states(
        self, run_8ae38b46_data: dict[str, Any]
    ):
        """Requirement 6: Distinct states are supported without flattening or confusion."""
        # Ensure CandidateState enum supports all required distinct states
        expected_states = {
            "IDENTIFIED",
            "DISPATCHED",
            "PROBE_EXECUTED",
            "UNDER_INVESTIGATION",
            "VALIDATED",
            "RULED_OUT",
            "RULED_OUT_WITH_EVIDENCE",
            "ABANDONED",
            "BLOCKED",
            "INCONCLUSIVE",
            "NOT_TESTED",
        }
        enum_names = {s.name for s in CandidateState}
        assert expected_states.issubset(enum_names)

        # In run-8ae38b46, all 8 candidates are strictly ABANDONED in data model
        candidates = run_8ae38b46_data.get("candidates", [])
        for cand in candidates:
            assert cand.get("state") == "ABANDONED"
            assert cand.get("status") == "ABANDONED"

    def test_07_zero_findings_does_not_imply_passed(self):
        """Requirement 7: Zero findings does not imply PASSED."""
        scan_matrix = [
            {
                "category_key": "version_sca",
                "test_count": 12,
                "configured_checks": 12,
                "executed_checks": 0,
            },
            {
                "category_key": "configuration",
                "test_count": 22,
                "configured_checks": 22,
                "executed_checks": 0,
            },
        ]
        reconciled = reconcile_scan_matrix(scan_matrix, findings=[], run_data={})
        for item in reconciled:
            assert item["status"] == "NOT TESTED"
            assert item["executed_checks"] == 0
            assert item["status"] != "PASSED"

    def test_08_category_status_uses_actual_execution_records(self):
        """Requirement 8: Category status uses actual execution records."""
        scan_matrix = [
            {
                "category_key": "sqli",
                "test_count": 14,
                "configured_checks": 14,
                "executed_checks": 0,
            },
            {"category_key": "xss", "test_count": 8, "configured_checks": 8, "executed_checks": 4},
            {"category_key": "ssrf", "test_count": 8, "configured_checks": 8, "executed_checks": 8},
        ]
        reconciled = reconcile_scan_matrix(scan_matrix, findings=[], run_data={})
        by_key = {item["category_key"]: item for item in reconciled}
        assert by_key["sqli"]["status"] == "NOT TESTED"
        assert by_key["xss"]["status"] == "PARTIALLY TESTED"
        assert by_key["ssrf"]["status"] == "PASSED"

    def test_09_candidate_branches_do_not_become_gap2_pivots(
        self, run_8ae38b46_data: dict[str, Any]
    ):
        """Requirement 9: Candidate branches do not become GAP2 pivots."""
        reconciled = reconcile_all(run_8ae38b46_data, run_dir=FIXTURE_DIR)
        assert reconciled.get("pivots") == 0
        assert reconciled.get("gap2_pivots") == 0
        assert len(reconciled.get("pivot_events", [])) == 0

    def test_10_gap2_pivots_require_actual_alternative_execution(self):
        """Requirement 10: GAP2 pivots require actual alternative execution."""
        mock_run = {
            "pivots": 5,  # Claimed 5 pivots
            "pivot_events": [
                {"event": "CANDIDATE_BRANCH", "candidate_id": "c1"},  # Not a real pivot
                {"type": "REDIRECT", "candidate_id": "c2", "pivot_executed": False},  # Not executed
            ],
            "candidates": [],
            "findings": [],
        }
        reconciled = reconcile_all(mock_run)
        assert reconciled["pivots"] == 0
        assert reconciled["gap2_pivots"] == 0

        # With a real executed pivot:
        mock_run_with_real_pivot = {
            "pivots": 0,
            "pivot_events": [
                {
                    "type": "GAP2_PIVOT",
                    "candidate_id": "c1",
                    "next_candidate": "c2",
                    "pivot_executed": True,
                },
            ],
            "candidates": [],
            "findings": [],
        }
        reconciled2 = reconcile_all(mock_run_with_real_pivot)
        assert reconciled2["pivots"] == 1
        assert reconciled2["gap2_pivots"] == 1

    def test_11_unconfirmed_ports_do_not_receive_fabricated_identities(self):
        """Requirement 11: Unconfirmed ports do not receive fabricated service identities."""
        raw_ports = [
            {"port": 3000, "state": "open"},
            {"port": 8000, "state": "open"},
            {"port": 9090, "state": "open"},
        ]
        target_ports, env_ports = reconcile_ports_and_services(raw_ports, "http://127.0.0.1:3000")
        assert len(target_ports) == 1
        assert target_ports[0]["port"] == 3000
        assert target_ports[0]["service"] == "HTTP Web Service"
        assert target_ports[0]["service_confirmed"] is True

        assert len(env_ports) == 2
        for ep in env_ports:
            assert ep["service"] == "Unfingerprinted TCP Listener"
            assert ep["service_confirmed"] is False
            assert ep["service_confidence"] == "UNCONFIRMED"
            assert "Conventional Guess Only" in ep["conventional_service"]

    def test_12_out_of_scope_ports_remain_environmental(self):
        """Requirement 12: Out-of-scope ports remain environmental and do not escalate severity."""
        raw_ports = [
            {"port": 8000, "state": "open", "severity": "medium"},
            {"port": 9090, "state": "open", "severity": "high"},
        ]
        target_ports, env_ports = reconcile_ports_and_services(raw_ports, "http://127.0.0.1:3000")
        assert len(target_ports) == 0
        for ep in env_ports:
            assert ep["in_scope"] is False
            assert ep["scope"] == "environmental"
            assert ep["severity"] == "info"

    def test_13_turns_consumed_not_represented_as_full_turn_limit(
        self, run_8ae38b46_data: dict[str, Any]
    ):
        """Requirement 13: 21/500 turns is not represented as 500 turns completed."""
        reconciled = reconcile_assessment_completeness(run_8ae38b46_data)
        assert reconciled["turns_consumed"] == 21
        assert reconciled["configured_turn_limit"] == 500
        assert "21 of 500 turns used" in reconciled["run_lifecycle_status"]
        assert reconciled["assessment_completeness_percent"] == 0.0

    def test_14_dashboard_json_html_pdf_reconcile_with_zero_contradictions(
        self, run_8ae38b46_data: dict[str, Any]
    ):
        """Requirement 14: Dashboard, JSON, HTML, and PDF counts reconcile with zero contradictions."""
        reconciled = reconcile_all(run_8ae38b46_data, run_dir=FIXTURE_DIR)
        errors = validate_report_consistency(reconciled)
        assert len(errors) == 0, f"Consistency validation failed: {errors}"

        # Generate HTML and ensure zero contradictions
        html_out = render_html_report(reconciled)
        assert "Run process completed — 21 of 500 turns used" in html_out
        assert "ABANDONED" in html_out
        assert "NOT TESTED" in html_out
        assert "Unfingerprinted TCP Listener" in html_out

        # Generate PDF and ensure it compiles cleanly
        pdf_bytes = generate_report_pdf(FIXTURE_DIR)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 2000

    def test_15_no_synthetic_evidence_generated(self, run_8ae38b46_data: dict[str, Any]):
        """Requirement 15: No synthetic evidence is generated (DEF-04 integrity)."""
        findings = run_8ae38b46_data.get("findings", [])
        assert len(findings) == 0
        # If any findings were present, they must have real sha256 evidence
        for f in findings:
            assert not f.get("synthetic_evidence")
            assert f.get("evidence_hash") is not None

    def test_16_successful_process_exit_with_incomplete_objectives(
        self, run_8ae38b46_data: dict[str, Any]
    ):
        """Requirement 16: Successful process exit with incomplete objectives is represented accurately."""
        assert run_8ae38b46_data.get("status") == "completed"
        # Exit code 0 does not mean 100% complete audit coverage
        assert run_8ae38b46_data.get("assessment_completeness_percent") == 0.0
        assert run_8ae38b46_data.get("category_coverage_percent") == 0.0

    def test_17_exact_verification_of_run_8ae38b46_fixture(self, run_8ae38b46_data: dict[str, Any]):
        """Requirement 17: Exact verification of run-8ae38b46 fixture.

        Expected:
        - 8 candidates identified
        - 8 candidates dispatched
        - 8 candidates investigated
        - 8 candidates abandoned
        - 0 candidates validated
        - 0 pivots executed
        - 0 findings confirmed
        - Scan matrix: 0 executed checks, all 8 categories NOT TESTED
        - Ports: 3000 confirmed, 8000 and 9090 unconfirmed environmental
        """
        reconciled = reconcile_all(run_8ae38b46_data, run_dir=FIXTURE_DIR)

        acct = reconciled.get("candidate_accounting", {})
        assert acct.get("identified") == 8
        assert acct.get("dispatched") == 8
        assert acct.get("investigated") == 8
        assert acct.get("abandoned") == 8
        assert acct.get("validated") == 0
        assert acct.get("ruled_out") == 0
        assert acct.get("not_tested") == 0
        assert acct.get("blocked") == 0

        assert reconciled.get("pivots") == 0
        assert reconciled.get("gap2_pivots") == 0
        assert len(reconciled.get("findings", [])) == 0

        # Scan matrix
        scan_matrix = reconciled.get("scan_matrix", [])
        assert len(scan_matrix) == 8
        for cat in scan_matrix:
            assert cat.get("status") in ("NOT TESTED", "PARTIALLY TESTED")
            assert cat.get("status") != "PASSED"

        # Open ports
        open_ports = reconciled.get("open_ports", [])
        assert len(open_ports) == 3
        p3000 = next(p for p in open_ports if p["port"] == 3000)
        assert p3000["service"] == "HTTP Web Service"
        assert p3000["service_confirmed"] is True
        assert p3000["scope"] == "target_application"

        p8000 = next(p for p in open_ports if p["port"] == 8000)
        assert p8000["service"] == "Unfingerprinted TCP Listener"
        assert p8000["service_confirmed"] is False
        assert p8000["scope"] == "environmental"
        assert p8000["severity"] == "info"

        p9090 = next(p for p in open_ports if p["port"] == 9090)
        assert p9090["service"] == "Unfingerprinted TCP Listener"
        assert p9090["service_confirmed"] is False
        assert p9090["scope"] == "environmental"
        assert p9090["severity"] == "info"

    def test_18_probe_and_unique_invocation_accounting(self, run_8ae38b46_data: dict[str, Any]):
        """Requirement 18: Shared invocation IDs do not inflate unique invocation count."""
        reconciled = reconcile_all(run_8ae38b46_data, run_dir=FIXTURE_DIR)
        probe_acct = reconciled.get("probe_accounting", {})
        assert probe_acct.get("candidates_identified") == 8
        assert probe_acct.get("candidates_dispatched") == 8
        assert probe_acct.get("candidates_with_actual_probes") == 8
        assert probe_acct.get("candidate_to_probe_associations") == 8
        # In run-8ae38b46, 8 candidates map to 6 distinct tool invocation IDs
        assert probe_acct.get("unique_tool_invocations") == 6
        assert probe_acct.get("verification_checks_executed") == 8
        assert probe_acct.get("abandoned_candidates") == 8
        assert probe_acct.get("validated_candidates") == 0

    def test_19_cors_verification_telemetry_semantics(self, run_8ae38b46_data: dict[str, Any]):
        """Requirement 19: CORS observation records header, credentials, data access, and untested aspects."""
        candidates = run_8ae38b46_data.get("candidates", [])
        cors_cand = next(c for c in candidates if "cors" in c.get("id", ""))
        assert "cors_telemetry" in cors_cand
        telemetry = cors_cand["cors_telemetry"]
        assert "Access-Control-Allow-Origin: *" in telemetry["observed_header"]
        assert telemetry["credentials_supported"] is False
        assert telemetry["sensitive_authenticated_data_accessible"] is False
        assert telemetry["browser_behavior_tested"] is True
        assert len(telemetry["actual_impact_evidence"]) > 10
        assert len(telemetry["untested_aspects"]) > 10

    def test_20_controlled_fixture_inconclusive_then_resolved(self):
        """Controlled fixture: Candidate whose first probe is inconclusive and second resolves it."""
        mock_candidates = [
            {
                "id": "cand-sqli",
                "category": "sqli",
                "state": "ATTEMPTING",
                "attempts": 1,
                "max_attempts": 2,
                "retry_eligibility": True,
                "detail": "needs_follow_up after ambiguous response length",
            }
        ]
        mock_run = {
            "run_id": "test-inconclusive-resolve",
            "candidates": mock_candidates,
            "findings": [],
            "scan_matrix": [{"category_key": "sqli", "test_count": 14}],
        }
        rec1 = reconcile_all(mock_run)
        sqli_matrix1 = next(m for m in rec1["scan_matrix"] if m["category_key"] == "sqli")
        assert sqli_matrix1["status"] == "INCONCLUSIVE"
        assert rec1["candidates"][0]["retry_eligibility"] is True

        # Now simulate attempt 2 resolving to VALIDATED
        rec1["candidates"][0]["attempts"] = 2
        rec1["candidates"][0]["state"] = "VALIDATED"
        rec1["candidates"][0]["retry_eligibility"] = False
        rec1["findings"] = [{"id": "v1", "category": "sqli", "title": "SQL Injection confirmed"}]
        rec2 = reconcile_all(rec1)
        sqli_matrix2 = next(m for m in rec2["scan_matrix"] if m["category_key"] == "sqli")
        assert sqli_matrix2["status"] == "VULNERABILITIES_IDENTIFIED"
        assert rec2["candidates"][0]["state"] in ("VALIDATED", "VERIFIED_VULNERABILITY")

    def test_21_controlled_fixture_candidate_probe_blocked(self):
        """Controlled fixture: Candidate whose probe is blocked by network / 502."""
        mock_run = {
            "run_id": "test-blocked",
            "candidates": [
                {
                    "id": "cand-ssrf",
                    "category": "ssrf",
                    "state": "ABANDONED",
                    "attempts": 1,
                    "max_attempts": 2,
                    "detail": "Connection refused / 502 Bad Gateway from upstream target",
                }
            ],
            "findings": [],
            "scan_matrix": [{"category_key": "ssrf", "test_count": 8}],
        }
        reconciled = reconcile_all(mock_run)
        ssrf_matrix = next(m for m in reconciled["scan_matrix"] if m["category_key"] == "ssrf")
        assert ssrf_matrix["status"] == "BLOCKED"

    def test_22_controlled_fixture_candidate_ruled_out_with_evidence(self):
        """Controlled fixture: Candidate conclusively ruled out with evidence."""
        mock_run = {
            "run_id": "test-ruled-out",
            "candidates": [
                {
                    "id": "cand-robots",
                    "category": "configuration",
                    "state": "RULED_OUT",
                    "attempts": 1,
                    "max_attempts": 2,
                    "tool_selected": "exec_command",
                    "tool_invocation_id": "call-123",
                    "sanitized_request": "curl -s http://target/robots.txt",
                    "tool_result": "Disallow: /ftp",
                    "http_status": 200,
                    "verification_contract": "VAPT Negative Proof Contract",
                    "verification_result": "RULED OUT with evidence: Only /ftp disallowed",
                }
            ],
            "findings": [],
            "scan_matrix": [{"category_key": "configuration", "test_count": 22}],
        }
        reconciled = reconcile_all(mock_run)
        cand = reconciled["candidates"][0]
        assert cand["state"] == "RULED_OUT"
        assert cand["verification_contract"] == "VAPT Negative Proof Contract"
        assert cand["retry_eligibility"] is False

    def test_23_controlled_fixture_adaptive_pivot_execution(self):
        """Controlled fixture: Candidate requiring an actual adaptive alternative."""
        mock_run = {
            "run_id": "test-pivot-exec",
            "candidates": [
                {
                    "id": "cand-primary",
                    "category": "sqli",
                    "state": "ABANDONED",
                    "attempts": 2,
                    "max_attempts": 2,
                },
                {
                    "id": "cand-pivot-alt",
                    "category": "sqli",
                    "state": "VALIDATED",
                    "attempts": 1,
                    "max_attempts": 2,
                },
            ],
            "pivot_events": [
                {
                    "type": "GAP2_PIVOT",
                    "candidate_id": "cand-primary",
                    "next_candidate": "cand-pivot-alt",
                    "reason": "Primary endpoint hardened with WAF; pivoted to secondary parameter",
                    "pivot_executed": True,
                }
            ],
            "findings": [{"id": "v1", "category": "sqli", "title": "SQLi on secondary parameter"}],
            "scan_matrix": [{"category_key": "sqli", "test_count": 14}],
        }
        reconciled = reconcile_all(mock_run)
        assert reconciled["pivots"] == 1
        assert reconciled["gap2_pivots"] == 1
        sqli_matrix = next(m for m in reconciled["scan_matrix"] if m["category_key"] == "sqli")
        assert sqli_matrix["status"] == "VULNERABILITIES_IDENTIFIED"

    def test_24_controlled_fixture_incomplete_and_unresolved_run(self):
        """Controlled fixture: Run that stops early with untested categories."""
        mock_run = {
            "run_id": "test-early-stop",
            "status": "completed",
            "turns_consumed": 21,
            "configured_turn_limit": 500,
            "candidates": [
                {"id": "c1", "state": "ABANDONED", "attempts": 1, "max_attempts": 2},
            ],
            "findings": [],
            "scan_matrix": [
                {
                    "category_key": "xss",
                    "test_count": 8,
                    "configured_checks": 8,
                    "executed_checks": 0,
                },
                {
                    "category_key": "sqli",
                    "test_count": 14,
                    "configured_checks": 14,
                    "executed_checks": 0,
                },
            ],
        }
        reconciled = reconcile_all(mock_run)
        assert "21 of 500 turns used" in reconciled["run_lifecycle_status"]
        assert reconciled["assessment_completeness_percent"] == 0.0
        for cat in reconciled["scan_matrix"]:
            assert cat["status"] == "NOT TESTED"
            assert cat["executed_checks"] == 0
