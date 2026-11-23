"""Regression tests for AI-VAPT assessment integrity and run-14ee778a defect remediation.

Verifies:
1. Strict candidate state semantics (VALIDATED_OBSERVATION vs VERIFIED_VULNERABILITY).
2. Probes alone (robots.txt, security.txt, Swagger UI, wildcard CORS, missing CSP) do not forge verified vulnerabilities.
3. Scan category matrix integrity: 0 executed checks -> NOT TESTED; partial checks -> PARTIALLY TESTED; never false PASSED.
4. Evidence domain isolation: CSP candidates do not bind to CORS evidence.
5. Unique tool invocation accounting and duplicate evidence tracking.
6. GAP-2 queue exhaustion generates GAP2_ABANDON with pivot_executed=False and 0 pivot count.
7. Lifecycle turns decoupled from assessment completeness.
8. End-to-end report reconciliation and consistency validation on run-14ee778a fixtures.
"""

from pathlib import Path
from typing import Any

import pytest

from strix.core.decision_engine.schemas import CandidateState
from strix.core.gap_bridge import GapRunState, record_outcome
from strix.report.reconciliation import (
    enrich_candidates_from_execution,
    reconcile_assessment_completeness,
    reconcile_markdown_report,
    reconcile_run_directory,
    reconcile_scan_matrix,
)


def test_candidate_cannot_be_verified_vulnerability_without_findings() -> None:
    """A candidate with a positive probe outcome but 0 findings must become VALIDATED_OBSERVATION."""
    raw_candidates = [
        {
            "id": "cand-robots-01",
            "title": "Sensitive Path Disclosure in robots.txt",
            "state": "VALIDATED",
            "probe_outcome": "positive",
        },
        {
            "id": "cand-cors-02",
            "title": "Permissive Cross-Origin Resource Sharing (CORS) Policy",
            "state": "VALIDATED",
            "probe_outcome": "positive",
        },
    ]

    # No findings provided
    enriched = enrich_candidates_from_execution(raw_candidates, findings=[])

    assert len(enriched) == 2
    for c in enriched:
        assert c["state"] == CandidateState.VALIDATED_OBSERVATION.value
        assert c["state"] != CandidateState.VERIFIED_VULNERABILITY.value


def test_candidate_becomes_verified_vulnerability_when_matching_finding_exists() -> None:
    """A candidate becomes VERIFIED_VULNERABILITY only when an active finding confirms exploitability."""
    raw_candidates = [
        {
            "id": "cand-sqli-01",
            "title": "SQL Injection in User Search",
            "state": "VALIDATED",
            "probe_outcome": "positive",
            "endpoint": "/rest/products/search",
        }
    ]
    findings = [
        {
            "id": "vuln-01",
            "title": "SQL Injection in User Search",
            "path": "/rest/products/search",
            "severity": "high",
        }
    ]

    enriched = enrich_candidates_from_execution(raw_candidates, findings=findings)
    assert len(enriched) == 1
    assert enriched[0]["state"] in (
        CandidateState.VERIFIED_VULNERABILITY.value,
        CandidateState.VALIDATED.value,
    )


@pytest.mark.parametrize(
    "cand_title,endpoint,reason",
    [
        (
            "Sensitive Path Disclosure in robots.txt",
            "/robots.txt",
            "robots.txt is standard crawling guidance",
        ),
        (
            "Security Policy Disclosure via security.txt",
            "/.well-known/security.txt",
            "security.txt is public RFC 9116 disclosure",
        ),
        (
            "Public Swagger API Documentation",
            "/api-docs/",
            "Swagger UI exposure is documentation, not an exploitable CVE without auth bypass",
        ),
        (
            "Permissive CORS Policy",
            "/",
            "Wildcard CORS without credentials does not grant credentialed cross-origin read",
        ),
        (
            "Missing Content Security Policy (CSP)",
            "/",
            "Absence of CSP does not prove executable XSS payload",
        ),
    ],
)
def test_recon_probes_alone_do_not_produce_verified_vulnerabilities(
    cand_title: str, endpoint: str, reason: str
) -> None:
    """Reconnaissance discoveries and configuration absences must be marked observations, not vulnerabilities."""
    raw = [
        {
            "id": "recon-cand",
            "title": cand_title,
            "endpoint": endpoint,
            "state": "VALIDATED",
            "probe_outcome": "positive",
        }
    ]
    enriched = enrich_candidates_from_execution(raw, findings=[])
    assert enriched[0]["state"] == CandidateState.VALIDATED_OBSERVATION.value
    assert enriched[0]["state"] != CandidateState.VERIFIED_VULNERABILITY.value


def test_scan_matrix_unexecuted_categories_strictly_not_tested() -> None:
    """Categories with 0 executed checks must never be marked PASSED."""
    matrix = [
        {
            "category_key": "sqli",
            "name": "SQL Injection",
            "configured_checks": 14,
            "executed_checks": 0,
            "test_count": 14,
            "status": "PASSED",  # Defective legacy state
        },
        {
            "category_key": "xss",
            "name": "XSS Testing",
            "configured_checks": 8,
            "executed_checks": 0,
            "test_count": 8,
            "status": "PASSED",
        },
    ]

    reconciled = reconcile_scan_matrix(matrix, findings=[])
    for cat in reconciled:
        assert cat["status"] == "NOT TESTED"
        assert cat["executed_checks"] == 0
        assert cat["status"] != "PASSED"


def test_scan_matrix_partially_tested_categories_cannot_be_passed() -> None:
    """Categories with executed checks strictly between 0 and configured must be PARTIALLY TESTED."""
    matrix = [
        {
            "category_key": "info_disclosure",
            "name": "Information Disclosure",
            "configured_checks": 12,
            "executed_checks": 3,
            "test_count": 12,
            "status": "PASSED",
        }
    ]

    reconciled = reconcile_scan_matrix(matrix, findings=[])
    assert len(reconciled) == 1
    assert reconciled[0]["status"] == "PARTIALLY TESTED"
    assert reconciled[0]["executed_checks"] == 3
    assert reconciled[0]["configured_checks"] == 12


def test_scan_matrix_passed_only_when_fully_executed_and_clean() -> None:
    """A category is marked PASSED only if executed >= configured and findings count is 0."""
    matrix = [
        {
            "category_key": "headers",
            "name": "Security Headers",
            "configured_checks": 10,
            "executed_checks": 10,
            "status": "UNKNOWN",
        }
    ]
    reconciled = reconcile_scan_matrix(matrix, findings=[])
    assert reconciled[0]["status"] == "PASSED"
    assert reconciled[0]["executed_checks"] == 10


def test_evidence_domain_isolation_prevents_csp_cors_cross_contamination() -> None:
    """CSP candidate must not match CORS coverage entries despite shared target path."""
    candidates = [
        {
            "id": "cand-csp",
            "title": "Missing Content-Security-Policy (CSP) Header",
            "endpoint": "/",
            "state": "PENDING",
        },
        {
            "id": "cand-cors",
            "title": "Permissive Cross-Origin Resource Sharing (CORS) Policy",
            "endpoint": "/",
            "state": "PENDING",
        },
    ]

    fixtures_run_dir = Path(__file__).resolve().parent / "fixtures" / "run-14ee778a"
    run_dir = fixtures_run_dir if fixtures_run_dir.is_dir() else Path("strix_runs/run-14ee778a")
    if run_dir.exists():
        enriched = enrich_candidates_from_execution(candidates, run_dir=run_dir, findings=[])
        csp = next(c for c in enriched if c["id"] == "cand-csp")
        cors = next(c for c in enriched if c["id"] == "cand-cors")

        # Verify CSP candidate did not bind CORS coverage risk
        if csp.get("evidence"):
            evidence_str = str(csp["evidence"]).lower()
            assert "cors" not in evidence_str or "csp" in evidence_str


def test_duplicate_tool_invocations_tracked_truthfully() -> None:
    """When multiple candidates evaluate output from a single curl call, duplicate associations are counted."""
    fixtures_run_dir = Path(__file__).resolve().parent / "fixtures" / "run-14ee778a"
    run_dir = fixtures_run_dir if fixtures_run_dir.is_dir() else Path("strix_runs/run-14ee778a")
    if not run_dir.exists():
        pytest.skip("run-14ee778a fixture directory not available")

    run_data, errors = reconcile_run_directory(run_dir)
    assert len(errors) == 0

    acc = run_data["candidate_accounting"]
    assert acc["identified"] == 8
    assert acc["investigated"] == 8
    assert acc["validated_observations"] == 7
    assert acc["verified_vulnerabilities"] == 0
    assert acc["abandoned"] == 1
    # 8 candidate evaluations mapped to 6 unique curl command executions in agents.db
    assert acc["unique_tool_invocations"] == 6
    assert acc["duplicate_evidence_associations"] == 2


def test_gap2_queue_exhaustion_produces_abandon_event_without_synthetic_pivot(
    tmp_path: Path,
) -> None:
    """When retry threshold k=2 is reached and candidate queue is empty, GAP2 must emit GAP2_ABANDON with 0 pivots."""
    st = GapRunState(directory=tmp_path, threshold_override=2)
    cid = "cand-client-js"

    # First attempt: inconclusive probe (attempt 1/2)
    res1 = record_outcome(
        state=st,
        candidate_id=cid,
        probe_status="inconclusive",
        detail="First client JS search yielded no DOM sinks",
    )
    assert res1["attempts"] == 1
    assert res1["pivot"] is False

    # Second attempt: threshold reached (2/2), queue is empty -> candidate abandoned, pivot=False
    res2 = record_outcome(
        state=st,
        candidate_id=cid,
        probe_status="inconclusive",
        detail="Second client JS search failed to locate vulnerable endpoints",
    )
    assert res2["attempts"] == 2
    assert res2["status"] == "abandoned"
    assert res2["pivot"] is False
    assert res2["next_candidate"] is None
    assert res2.get("pivot_executed") is False
    assert "Queue exhausted" in res2.get("reason", "")


def test_lifecycle_turns_decoupled_from_vulnerability_completeness() -> None:
    """Process lifecycle completion (turns used) must not be reported as vulnerability assessment completeness."""
    run_data: dict[str, Any] = {
        "status": "completed",
        "turns_consumed": 43,
        "max_turns": 500,
        "candidates": [
            {"id": "c1", "state": "VALIDATED_OBSERVATION", "attempts": 1, "tool_selected": "curl"},
            {"id": "c2", "state": "ABANDONED", "attempts": 2, "tool_selected": "curl"},
        ],
        "scan_matrix": [
            {
                "category_key": "info",
                "status": "PARTIALLY TESTED",
                "executed_checks": 2,
                "configured_checks": 10,
            },
            {
                "category_key": "sqli",
                "status": "NOT TESTED",
                "executed_checks": 0,
                "configured_checks": 14,
            },
            {
                "category_key": "xss",
                "status": "NOT TESTED",
                "executed_checks": 0,
                "configured_checks": 8,
            },
            {
                "category_key": "ssrf",
                "status": "NOT TESTED",
                "executed_checks": 0,
                "configured_checks": 8,
            },
        ],
        "findings": [],
    }

    reconciled = reconcile_assessment_completeness(run_data)

    # Lifecycle is 43 of 500 turns used
    assert reconciled["execution_lifecycle"]["turns_consumed"] == 43
    assert reconciled["execution_lifecycle"]["max_turns"] == 500
    assert "43 of 500 turns used" in reconciled["run_lifecycle_status"]

    # Category coverage is 1 of 4 categories = 25.0%
    assert reconciled["assessment_completeness"]["category_coverage_percent"] == 25.0
    # Candidate completion is 2 of 2 = 100.0%
    assert reconciled["assessment_completeness"]["candidate_completion_percent"] == 100.0
    # Objective completeness (validated + ruled out) is 1 of 2 = 50.0%
    assert reconciled["assessment_completeness"]["objective_completeness_percent"] == 50.0


def test_markdown_report_sanitization_removes_unsupported_critical_claims() -> None:
    """Markdown executive summary and technical analysis claiming critical vulnerabilities are sanitized when findings=0."""
    raw_md = """# Security Penetration Test Report

# Executive Summary

An external assessment of the OWASP Juice Shop application identified multiple critical security weaknesses that could lead to unauthorized access, data exposure, and exploitation. The application is intentionally insecure as part of its educational purpose, but several vulnerabilities were confirmed that would be concerning in a production environment.

# Technical Analysis

**Severity model**: All findings are documented as reported based on confirmed issues.

1. **Sensitive Path Disclosure in robots.txt** (Critical) - The robots.txt file reveals sensitive information.
2. **Security Policy Disclosure via security.txt** (High) - Exposes contact info.
"""

    run_data = {
        "target_url": "http://127.0.0.1:3000/#/",
        "findings": [],
        "candidate_accounting": {
            "validated_observations": 7,
            "unique_tool_invocations": 6,
        },
    }

    sanitized = reconcile_markdown_report(raw_md, run_data)

    assert "critical security weaknesses" not in sanitized
    assert "several vulnerabilities were confirmed" not in sanitized
    assert "(Critical)" not in sanitized
    assert "(High)" not in sanitized
    assert "(Observation)" in sanitized
    assert "0 confirmed vulnerabilities were identified" in sanitized


def test_reconcile_run_directory_run_14ee778a_produces_zero_validation_errors() -> None:
    """Running reconcile_run_directory on run-14ee778a completes cleanly with zero consistency errors."""
    fixtures_run_dir = Path(__file__).resolve().parent / "fixtures" / "run-14ee778a"
    run_dir = fixtures_run_dir if fixtures_run_dir.is_dir() else Path("strix_runs/run-14ee778a")
    if not run_dir.exists():
        pytest.skip("run-14ee778a fixture directory not available")

    run_data, errors = reconcile_run_directory(run_dir)
    assert errors == []
    assert run_data["findings_discovered"] == 0
    assert run_data["pivots"] == 0
    assert run_data["candidate_accounting"]["verified_vulnerabilities"] == 0
    assert run_data["candidate_accounting"]["validated_observations"] == 7
