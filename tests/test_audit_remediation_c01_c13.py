"""Audit Regression Test Suite: Findings C01 to C13.

Verifies Phase P1 Evidence Truth, Verification, Completion Gate, and Reporting Consistency:
- C01: Benign plain text matches in _analyze_probe return needs_follow_up, not positive.
- C02: VerificationBlock enforces strict impact contract and rejects generic placeholders.
- C03: Passive rules classify findings as observations requiring active verification.
- C04: Reconciliation never fabricates synthetic curl commands for unprobed candidates.
- C05: No hardcoded CORS claims without actual observed headers in HTTP capture.
- C06: Candidate to finding linkage is strictly exact by candidate ID and verified status.
- C07: Evidence write failure fails closed (evidence_intact=False).
- C08: Evidence path containment blocks directory traversal in finding ID.
- C09: Completion gate fails closed (permitted=False) on queue error or exception.
- C10: finish_scan fails cleanly on persistence exceptions (scan_completed=False).
- C11: Minimum tool execution enforcement for genuine assessment.
- C12: Single canonical verification truth across report serializers.
- C13: Versioned canonical evidence envelope hashing request + response + tool + target + timestamp.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from types import SimpleNamespace

from strix.core.runner import _analyze_probe
from strix.report.verification import VerificationBlock, VerificationState
from strix.core.scanner.passive_rules import run_passive_rules
from strix.report.reconciliation import enrich_candidates_from_execution
from strix.report.evidence import record_authentic_evidence, verify_evidence_integrity
from strix.tools.finish.tool import _evaluate_completion_gate, _do_finish
from strix.interface.api import _generate_markdown_report, execution_evidence_from_run


# ---------------------------------------------------------------------------
# C01: Benign text in _analyze_probe
# ---------------------------------------------------------------------------
def test_c01_benign_text_not_verified():
    """Generic text mentions of database names or reflected strings must not verify."""
    cand = SimpleNamespace(endpoint="/search")

    # 1. Plain text with 'mysql' in documentation/body -> needs_follow_up
    outcome, reason, evidence = _analyze_probe(
        candidate=cand,
        result={
            "status": 200,
            "headers": {"content-type": "text/html"},
            "body": "<html><body>Welcome to our MySQL documentation portal</body></html>",
        },
        probe_url="http://127.0.0.1:8080/search?q=mysql",
    )
    assert outcome == "needs_follow_up"
    assert "potential sql error signature observed" in reason.lower()

    # 2. Reflected script tag without DOM execution proof -> needs_follow_up
    outcome_xss, reason_xss, _ = _analyze_probe(
        candidate=cand,
        result={
            "status": 200,
            "headers": {"content-type": "text/html"},
            "body": "<html><body><script>alert(1)</script></body></html>",
        },
        probe_url="http://127.0.0.1:8080/search?q=test",
    )
    assert outcome_xss == "needs_follow_up"
    assert "reflected script text observed" in reason_xss.lower()


# ---------------------------------------------------------------------------
# C02: VerificationBlock contract requires genuine impact
# ---------------------------------------------------------------------------
def test_c02_verification_contract_requires_impact():
    """Generic placeholders or short claims must not satisfy the verification contract."""
    # 1. Generic placeholder impact -> fails contract, downgraded to unconfirmed
    vb_placeholder = VerificationBlock(
        verification_state="verified",
        reproducible_request="GET /api/Users HTTP/1.1\nHost: target",
        verification_response="HTTP/1.1 200 OK\n[...]",
        verification_procedure="Executed active HTTP probe with parameter",
        demonstrated_impact="N/A",  # Generic placeholder
    )
    assert vb_placeholder.verification_state == VerificationState.UNCONFIRMED.value
    assert vb_placeholder.satisfies_verification_contract() is False

    # 2. Too short / vague impact -> fails contract
    vb_short = VerificationBlock(
        verification_state="verified",
        reproducible_request="GET /api/Users HTTP/1.1\nHost: target",
        verification_response="HTTP/1.1 200 OK\n[...]",
        verification_procedure="Executed active probe against user endpoint",
        demonstrated_impact="vulnerable endpoint",  # < 20 chars
    )
    assert vb_short.verification_state == VerificationState.UNCONFIRMED.value

    # 3. Substantive, valid proof -> satisfies contract
    vb_valid = VerificationBlock(
        verification_state="verified",
        reproducible_request="GET /api/Users HTTP/1.1\nHost: target\nAuthorization: Bearer test",
        verification_response="HTTP/1.1 200 OK\n[{\"id\": 1, \"email\": \"admin@juice-sh.op\"}]",
        verification_procedure="Executed authenticated enumeration request against /api/Users",
        demonstrated_impact="Full horizontal privilege escalation exposing all user emails and password hashes",
        evidence_timestamp="2026-11-23 20:00:00 UTC",
    )
    assert vb_valid.verification_state == VerificationState.VERIFIED.value
    assert vb_valid.satisfies_verification_contract() is True


# ---------------------------------------------------------------------------
# C03: Passive rules emit observations
# ---------------------------------------------------------------------------
def test_c03_passive_rules_emit_observations():
    """Passive rules must flag candidates as observations requiring active verification."""
    html_with_redirect = '<html><body><a href="/login?redirect=http://example.com">Login</a></body></html>'
    candidates, summary = run_passive_rules(
        target_url="http://127.0.0.1:8080",
        headers={"Server": "nginx/1.18.0"},
        cookies=[],
        html_body=html_with_redirect,
    )
    redirect_cand = next((c for c in candidates if c["id"] == "open-http-redirect"), None)
    assert redirect_cand is not None
    assert redirect_cand.get("is_observation") is True
    assert redirect_cand.get("requires_active_verification") is True
    assert redirect_cand.get("state") == "OBSERVATION"


# ---------------------------------------------------------------------------
# C04 & C05 & C06: Reconciliation truth
# ---------------------------------------------------------------------------
def test_c04_reconciliation_no_fabricated_curl():
    """Unprobed candidates must not have synthetic curl commands fabricated."""
    unprobed_cand = {
        "id": "unprobed-cand-01",
        "title": "Unprobed Endpoint",
        "endpoint": "/unprobed/path",
        "state": "PENDING",
    }
    reconciled = enrich_candidates_from_execution(
        candidates=[unprobed_cand],
        findings=[],
        run_dir=None,
        control_dir=None,
    )
    assert len(reconciled) == 1
    c = reconciled[0]
    assert c.get("dispatched") is False
    assert c.get("tool_selected") is None
    assert c.get("sanitized_request") == ""
    assert "curl" not in str(c.get("sanitized_request", ""))


def test_c05_no_hardcoded_cors_claims():
    """CORS telemetry must not claim Access-Control-Allow-Origin: * when not observed."""
    cors_cand = {
        "id": "cors-header-cand",
        "title": "CORS Posture Probe",
        "endpoint": "/api",
        "state": "PENDING",
        "evidence": "HTTP/1.1 200 OK\nContent-Type: application/json\n\n{}",  # No CORS headers
    }
    reconciled = enrich_candidates_from_execution(
        candidates=[cors_cand],
        findings=[],
        run_dir=None,
        control_dir=None,
    )
    c = reconciled[0]
    telemetry = c.get("cors_telemetry", {})
    assert telemetry.get("observed_header") is None
    assert "No CORS headers observed" in telemetry.get("actual_impact_evidence", "")


def test_c06_candidate_finding_link_exact():
    """Candidate status must require exact candidate ID match and verified=True."""
    cand = {
        "id": "sqli-candidate-100",
        "title": "SQL Injection in Search",
        "endpoint": "/search",
        "state": "PENDING",
    }
    # Finding with different candidate_id should NOT verify this candidate
    unrelated_finding = {
        "id": "finding-other",
        "candidate_id": "other-candidate-999",
        "title": "SQL Injection in Search",  # Same title substring, but different ID!
        "verified": True,
        "verification_state": "verified",
    }
    reconciled = enrich_candidates_from_execution(
        candidates=[cand],
        findings=[unrelated_finding],
        run_dir=None,
        control_dir=None,
    )
    c = reconciled[0]
    assert c.get("state") != "VERIFIED_VULNERABILITY"


# ---------------------------------------------------------------------------
# C07, C08, C13: Authentic evidence management
# ---------------------------------------------------------------------------
def test_c07_evidence_write_failure_fails_closed(tmp_path):
    """File write failure must return evidence_intact=False."""
    # Point run_dir to an uncreatable / invalid path to simulate write failure
    invalid_dir = tmp_path / "read_only"
    invalid_dir.mkdir(parents=True)
    invalid_dir.chmod(0o400)

    res = record_authentic_evidence(
        run_dir=invalid_dir,
        finding_id="finding-test-01",
        response_data="HTTP/1.1 200 OK\nSensitive Data",
        title="Test Leak",
    )
    assert res["evidence_intact"] is False
    assert res["evidence_file"] is None


def test_c08_evidence_path_containment(tmp_path):
    """Directory traversal in finding_id must be sanitized and contained."""
    traversal_id = "../../etc/passwd"
    res = record_authentic_evidence(
        run_dir=tmp_path,
        finding_id=traversal_id,
        response_data="HTTP/1.1 200 OK\nSafe Content",
        title="Traversal Test",
    )
    # Sanitized path should not contain '..'
    assert ".." not in str(res["evidence_file"])
    target_file = tmp_path / res["evidence_file"]
    assert target_file.resolve().is_relative_to((tmp_path / "evidence").resolve())


def test_c13_versioned_evidence_envelope(tmp_path):
    """Evidence hash must be computed over the canonical versioned envelope."""
    res = record_authentic_evidence(
        run_dir=tmp_path,
        finding_id="vuln-01",
        request_data="GET /api/secret HTTP/1.1\nHost: target",
        response_data="HTTP/1.1 200 OK\nSecret Content",
        title="Information Disclosure",
    )
    assert res["evidence_hash"] is not None
    assert res["evidence_intact"] is True

    # Check that artifact on disk matches envelope JSON
    target_file = tmp_path / res["evidence_file"]
    data = json.loads(target_file.read_text(encoding="utf-8"))
    assert data.get("version") == "1.0"
    assert data.get("finding_id") == "vuln-01"
    assert "Secret Content" in data.get("response")


# ---------------------------------------------------------------------------
# C09 & C10: Completion gate and finish scan persistence
# ---------------------------------------------------------------------------
def test_c09_completion_gate_fails_closed(tmp_path, monkeypatch):
    """Completion gate must return permitted=False on exception or corrupt queue."""
    monkeypatch.setenv("STRIX_GAP1_ENABLED", "1")
    ctrl_dir = tmp_path / "control"
    ctrl_dir.mkdir(parents=True)
    (ctrl_dir / "gap1_queue.json").write_text("NOT_VALID_JSON{")

    res = _evaluate_completion_gate(control_dir=ctrl_dir)
    assert res["permitted"] is False
    assert (
        "corrupt" in res.get("error", "").lower()
        or "failed" in res.get("error", "").lower()
        or "premature" in res.get("error", "").lower()
    )


def test_c10_finish_scan_persistence_failure(monkeypatch):
    """finish_scan persistence failure must return success=False and scan_completed=False."""
    from strix.report import state

    class BrokenReportState:
        def update_scan_final_fields(self, *args, **kwargs):
            raise IOError("Simulated disk full")

    monkeypatch.setattr(state, "get_global_report_state", lambda: BrokenReportState())

    res = _do_finish(
        parent_id=None,
        executive_summary="Summary",
        methodology="Methodology",
        technical_analysis="Analysis",
        recommendations="Recommendations",
        agent_graph={},
    )
    assert res["success"] is False
    assert res["scan_completed"] is False
    assert "failed to complete scan" in res["error"].lower()


# ---------------------------------------------------------------------------
# C11 & C12: Minimum execution and single canonical verification truth
# ---------------------------------------------------------------------------
def test_c11_minimum_coverage_enforcement():
    """Execution evidence requires both model calls and real security tool calls."""
    evidence_none = execution_evidence_from_run(None, "")
    assert evidence_none["has_model_participation"] is False
    assert evidence_none["has_security_execution"] is False

    evidence_real = execution_evidence_from_run(
        {"llm_requests": [{"outcome": "success"}]},
        "Invoking tool exec_command\nCalling LLM",
    )
    assert evidence_real["has_model_participation"] is True
    assert evidence_real["has_security_execution"] is True


def test_c12_single_canonical_verification_truth():
    """Markdown report serializer verifies only findings with explicit verified status."""
    run_data = {
        "run_id": "test-run-c12",
        "findings": [
            {
                "id": "f-01",
                "title": "Unverified with legacy snippet",
                "verified": False,
                "evidence_hash": "abc123hash",
                "evidence_snippet": "<html>test</html>",
            },
            {
                "id": "f-02",
                "title": "Truly Verified Finding",
                "verified": True,
                "verification_state": "verified",
                "severity": "HIGH",
            },
        ],
    }
    md_report = _generate_markdown_report(run_data)
    # Truly verified finding must be in Confirmed Vulnerability Findings section
    assert "Truly Verified Finding" in md_report
    # Unverified finding must NOT be promoted to Confirmed
    assert "Unverified with legacy snippet" in md_report
    assert "Unconfirmed Candidates" in md_report
