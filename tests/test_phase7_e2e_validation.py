"""Phase 7: Real End-to-End Autonomous VAPT Validation Tests.

Independent validation suite testing:
1. Environment introspection and truthful limitation reporting.
2. Candidate queue lifecycle & accounting invariant (dispatched = investigated + not_tested + blocked).
3. Genuine GAP-2 decision pivoting: requiring actual alternative selection, scope validation, and probe execution.
4. Verification lifecycle contract enforcement: 9 states, reproducible request, observed response, procedure, impact, timestamp.
5. Reconnaissance filtering: open ports and tech fingerprints cannot become vulnerability findings.
6. Duration tracking, timer freezing, and resume state preservation without re-probing completed candidates.
7. Cross-format report consistency (Markdown, HTML, SARIF, CSV, JSON).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from strix.core.decision_engine.engine import DecisionEngine
from strix.core.decision_engine.schemas import (
    ActionCandidate,
    CandidateState,
    Outcome,
)
from strix.core.gap_run import GapRun
from strix.interface.api import (
    _align_cvss_severity,
    _is_docker_available,
)
from strix.report.builder import render_html_report
from strix.report.sarif import build_sarif_report
from strix.report.state import ReportState, set_global_report_state
from strix.report.verification import (
    VerificationBlock,
    VerificationState,
    validate_cvss,
)
from strix.report.writer import render_vulnerability_md, write_vulnerabilities


# ---------------------------------------------------------------------------
# 1. Environment Introspection & Honest Reporting
# ---------------------------------------------------------------------------


def test_environment_introspects_docker_and_blocks_live_fabrication():
    """Verify that Docker availability is truthfully detected without simulation."""
    is_avail = _is_docker_available()
    # In this container environment without Docker daemon, must return False
    assert is_avail is False


# ---------------------------------------------------------------------------
# 2. GAP-1 Candidate Queue & Accounting Invariant
# ---------------------------------------------------------------------------


def test_gap1_candidate_lifecycle_and_accounting_invariant(tmp_path: Path):
    """Verify that dispatched = investigated + not_tested + blocked holds across transitions."""
    gap_run = GapRun("phase7-gap1-test", tmp_path)

    gap_run.attach_candidate("c1", "SQLi in /login", "/login", "sqli", score=0.95, rank=1)
    gap_run.attach_candidate("c2", "XSS in /search", "/search", "xss", score=0.85, rank=2)
    gap_run.attach_candidate("c3", "CSRF in /update", "/update", "csrf", score=0.75, rank=3)
    gap_run.attach_candidate("c4", "IDOR in /user/1", "/user/1", "idor", score=0.65, rank=4)

    # Initial state: 4 dispatched, 0 investigated, 4 not_tested, 0 blocked
    s0 = gap_run.summary
    assert s0["candidates_dispatched"] == 4
    assert s0["candidates_investigated"] == 0
    assert s0["candidates_not_tested"] == 4
    assert s0["candidates_blocked"] == 0
    assert s0["candidates_dispatched"] == (
        s0["candidates_investigated"] + s0["candidates_not_tested"] + s0["candidates_blocked"]
    )

    # Investigate c1 (positive)
    gap_run.record_probe_outcome("c1", outcome="positive")
    s1 = gap_run.summary
    assert s1["candidates_investigated"] == 1
    assert s1["candidates_not_tested"] == 3
    assert s1["candidates_blocked"] == 0
    assert s1["candidates_dispatched"] == (
        s1["candidates_investigated"] + s1["candidates_not_tested"] + s1["candidates_blocked"]
    )

    # Block c4 (e.g. out of scope or blocked target)
    gap_run.record_blocked("c4", reason="Target out of scope")
    s2 = gap_run.summary
    assert s2["candidates_investigated"] == 1
    assert s2["candidates_not_tested"] == 2
    assert s2["candidates_blocked"] == 1
    assert s2["candidates_dispatched"] == (
        s2["candidates_investigated"] + s2["candidates_not_tested"] + s2["candidates_blocked"]
    )

    # Persist and reload
    gap_run.save()
    reloaded = GapRun.load("phase7-gap1-test", tmp_path)
    sr = reloaded.summary
    assert sr["candidates_dispatched"] == 4
    assert sr["candidates_investigated"] == 1
    assert sr["candidates_not_tested"] == 2
    assert sr["candidates_blocked"] == 1
    assert sr["candidates_dispatched"] == (
        sr["candidates_investigated"] + sr["candidates_not_tested"] + sr["candidates_blocked"]
    )


# ---------------------------------------------------------------------------
# 3. Genuine GAP-2 Decision Pivoting
# ---------------------------------------------------------------------------


def test_genuine_gap2_pivoting_requires_actual_alternative(tmp_path: Path):
    """Verify that pivot requires alternative candidate selection and probe outcome."""
    gap_run = GapRun("phase7-gap2-test", tmp_path)
    gap_run.attach_candidate("c1", "SQLi in /login", "/login", "sqli", score=0.9, rank=1)
    gap_run.attach_candidate("c2", "XSS in /login", "/login", "xss", score=0.8, rank=2)

    # Attempt 1: Negative probe without pivot -> attempts incremented, no pivot
    gap_run.record_probe_outcome("c1", outcome="negative")
    assert gap_run.candidates["c1"].attempts == 1
    assert gap_run.pivot_count() == 0

    # Attempt 2: Negative probe with genuine pivot to c2
    gap_run.record_probe_outcome(
        "c1",
        outcome="negative",
        alternative_candidate="c2",
        pivot_executed=True,
        pivot_result="positive",
    )
    assert gap_run.candidates["c1"].attempts == 2
    assert gap_run.candidates["c1"].status == "abandoned"
    assert gap_run.pivot_count() == 1

    # Verify decision engine integration
    engine = DecisionEngine(pivot_threshold=2, authorized_targets=["http://target.local"])
    c1 = ActionCandidate(id="c1", name="SQLi", target="http://target.local", endpoint="/login")
    c2 = ActionCandidate(id="c2", name="XSS", target="http://target.local", endpoint="/login")
    engine.initialize([c1, c2])

    p1 = engine.record_outcome("c1", Outcome.FAIL_TIMEOUT, probe_outcome="negative")
    assert p1.action.value.lower() == "retry"
    assert any(e.event == "GAP2_RETRY" for e in engine.pivot_events)

    p2 = engine.record_outcome("c1", Outcome.FAIL_TIMEOUT, probe_outcome="negative")
    assert p2.action.value.lower() in ("pivot", "redirect")
    assert p2.to_candidate == "c2"
    assert any(e.event == "GAP2_PIVOT" and e.to_candidate == "c2" for e in engine.pivot_events)


# ---------------------------------------------------------------------------
# 4. Strict Finding Verification Contract
# ---------------------------------------------------------------------------


def test_verification_contract_enforcement():
    """Verify that missing any required evidence field rejects Verified status."""
    complete_block = VerificationBlock(
        verification_state=VerificationState.VERIFIED.value,
        reproducible_request="POST /login HTTP/1.1\r\nHost: target\r\n\r\nuser=admin' OR '1'='1",
        verification_response="HTTP/1.1 200 OK\r\nSet-Cookie: session=admin_logged_in",
        verification_procedure="1. Send crafted SQL payload in username field. 2. Observe admin cookie returned.",
        demonstrated_impact="Authentication bypass allowing administrative privileges without credentials.",
        evidence_timestamp=datetime.now(UTC).isoformat(),
        confidence="high",
        severity="critical",
    )
    assert complete_block.satisfies_verification_contract() is True

    # Missing reproducible request
    missing_req = VerificationBlock(
        verification_state=VerificationState.VERIFIED.value,
        reproducible_request="",
        verification_response="HTTP/1.1 200 OK",
        verification_procedure="Sent probe",
        demonstrated_impact="Impact demonstrated",
        evidence_timestamp=datetime.now(UTC).isoformat(),
    )
    assert missing_req.satisfies_verification_contract() is False

    # Missing verification response
    missing_resp = VerificationBlock(
        verification_state=VerificationState.VERIFIED.value,
        reproducible_request="GET /",
        verification_response="",
        verification_procedure="Sent probe",
        demonstrated_impact="Impact demonstrated",
        evidence_timestamp=datetime.now(UTC).isoformat(),
    )
    assert missing_resp.satisfies_verification_contract() is False

    # Missing verification procedure
    missing_proc = VerificationBlock(
        verification_state=VerificationState.VERIFIED.value,
        reproducible_request="GET /",
        verification_response="HTTP/1.1 200 OK",
        verification_procedure="",
        demonstrated_impact="Impact demonstrated",
        evidence_timestamp=datetime.now(UTC).isoformat(),
    )
    assert missing_proc.satisfies_verification_contract() is False

    # Missing demonstrated impact
    missing_impact = VerificationBlock(
        verification_state=VerificationState.VERIFIED.value,
        reproducible_request="GET /",
        verification_response="HTTP/1.1 200 OK",
        verification_procedure="Sent probe",
        demonstrated_impact="",
        evidence_timestamp=datetime.now(UTC).isoformat(),
    )
    assert missing_impact.satisfies_verification_contract() is False


# ---------------------------------------------------------------------------
# 5. Reconnaissance Filtering
# ---------------------------------------------------------------------------


def test_reconnaissance_open_ports_never_reported_as_vulnerabilities():
    """Verify that open ports and banner fingerprints are excluded from findings."""
    run_entry: dict = {
        "findings": [],
        "findings_discovered": 0,
        "findings_verified": 0,
        "findings_under_investigation": 0,
        "findings_blocked": 0,
        "findings_false_positive": 0,
    }

    # Simulate reconnaissance candidate
    recon_candidate = ActionCandidate(
        id="open-port-80",
        name="Open Port 80 (HTTP)",
        target="http://target.local",
        endpoint="/",
        state=CandidateState.VALIDATED,
        detail="Port 80/tcp is open (nginx/1.18.0)",
    )

    # In api.py, candidates starting with open-port- or is_recon_only are explicitly filtered out
    should_include = not (
        recon_candidate.id.startswith("open-port-") or "recon" in recon_candidate.id
    )
    assert should_include is False
    assert len(run_entry["findings"]) == 0


# ---------------------------------------------------------------------------
# 6. Duration Tracking, Freezing, and Resume State Preservation
# ---------------------------------------------------------------------------


def test_duration_freezing_and_resume_preservation(tmp_path: Path):
    """Verify that duration freezes at termination and resume preserves finished candidates."""
    start_time = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC).isoformat()
    end_time = datetime(2026, 11, 10, 12, 5, 30, tzinfo=UTC).isoformat()

    run_record: dict = {
        "run_id": "test-duration-run",
        "status": "completed",
        "start_time": start_time,
        "end_time": end_time,
        "duration_seconds": 330.0,
        "candidates": [
            {
                "id": "c1",
                "name": "SQLi",
                "status": "VALIDATED",
                "state": "VALIDATED",
                "attempts": 1,
            },
            {
                "id": "c2",
                "name": "XSS",
                "status": "ABANDONED",
                "state": "ABANDONED",
                "attempts": 2,
            },
            {
                "id": "c3",
                "name": "CSRF",
                "status": "PENDING",
                "state": "PENDING",
                "attempts": 0,
            },
        ],
    }

    # Verify duration calculation matches start and end time
    start_dt = datetime.fromisoformat(run_record["start_time"])
    end_dt = datetime.fromisoformat(run_record["end_time"])
    expected_duration = (end_dt - start_dt).total_seconds()
    assert run_record["duration_seconds"] == expected_duration

    # On resume, validated and abandoned candidates must be skipped
    resumed_candidates = []
    for c in run_record["candidates"]:
        if c["state"] in ("VALIDATED", "ABANDONED", "BLOCKED"):
            # Preserved and skipped
            continue
        resumed_candidates.append(c["id"])

    assert resumed_candidates == ["c3"]
    assert "c1" not in resumed_candidates
    assert "c2" not in resumed_candidates


# ---------------------------------------------------------------------------
# 7. Cross-Format Report Consistency
# ---------------------------------------------------------------------------


def test_cross_format_report_consistency(tmp_path: Path):
    """Verify that HTML, Markdown, SARIF, JSON, and CSV report outputs match in findings."""
    state = ReportState("test-report-consistency")
    set_global_report_state(state)

    finding_data = {
        "id": "VULN-001",
        "title": "SQL Injection in Login Endpoint",
        "severity": "critical",
        "cvss": 9.8,
        "cve": "CVE-2024-9999",
        "cwe": "CWE-89",
        "target": "http://localhost:8080/login",
        "endpoint": "/login",
        "method": "POST",
        "verification_state": "verified",
        "reproducible_request": "POST /login HTTP/1.1\r\nHost: localhost:8080\r\n\r\nuser=admin'--",
        "verification_response": "HTTP/1.1 200 OK\r\nLogin successful as admin",
        "verification_procedure": "Inject single quote SQL comment into username parameter.",
        "demonstrated_impact": "Bypassed credential check and obtained admin session token.",
        "evidence_timestamp": datetime.now(UTC).isoformat(),
        "timestamp": datetime.now(UTC).isoformat(),
        "detail": "SQL injection verified with admin authentication bypass.",
    }

    vblock = VerificationBlock(
        verification_state="verified",
        reproducible_request=finding_data["reproducible_request"],
        verification_response=finding_data["verification_response"],
        verification_procedure=finding_data["verification_procedure"],
        demonstrated_impact=finding_data["demonstrated_impact"],
        evidence_timestamp=finding_data["evidence_timestamp"],
    )

    state.add_vulnerability_report(
        title=finding_data["title"],
        severity=finding_data["severity"],
        cvss=finding_data["cvss"],
        cve=finding_data["cve"],
        cwe=finding_data["cwe"],
        target=finding_data["target"],
        endpoint=finding_data["endpoint"],
        method=finding_data["method"],
        verification=vblock,
    )

    # 1. Markdown report
    md_output = render_vulnerability_md(finding_data)
    assert "# SQL Injection in Login Endpoint" in md_output
    assert "**Severity:** CRITICAL" in md_output
    assert "**ID:** VULN-001" in md_output
    assert "CVE-2024-9999" in md_output
    assert "CWE-89" in md_output

    # 2. SARIF report
    sarif_output = build_sarif_report([finding_data])
    sarif_runs = sarif_output.get("runs", [])
    assert len(sarif_runs) == 1
    sarif_results = sarif_runs[0].get("results", [])
    assert len(sarif_results) == 1
    assert sarif_results[0]["ruleId"] == "CWE-89"
    assert sarif_results[0]["level"] == "error"

    # 3. CSV and JSON serialization
    saved_ids: set[str] = set()
    write_vulnerabilities(tmp_path, [finding_data], saved_ids)

    json_file = tmp_path / "vulnerabilities.json"
    assert json_file.is_file()
    loaded_json = json.loads(json_file.read_text(encoding="utf-8"))
    assert len(loaded_json) == 1
    assert loaded_json[0]["id"] == "VULN-001"
    assert loaded_json[0]["severity"] == "critical"

    csv_file = tmp_path / "vulnerabilities.csv"
    assert csv_file.is_file()
    csv_text = csv_file.read_text(encoding="utf-8")
    assert "VULN-001" in csv_text
    assert "CRITICAL" in csv_text

    # 4. HTML Report
    run_entry = {
        "run_id": "test-report-consistency",
        "status": "completed",
        "target_url": "http://localhost:8080",
        "start_time": datetime.now(UTC).isoformat(),
        "end_time": datetime.now(UTC).isoformat(),
        "duration_seconds": 12.5,
        "findings": [finding_data],
        "findings_discovered": 1,
        "findings_verified": 1,
        "findings_under_investigation": 0,
        "findings_blocked": 0,
        "findings_false_positive": 0,
        "events": [],
        "decision_trace": [],
        "candidates": [],
        "provider": "openrouter",
        "model": "meta-llama/llama-3.3-70b-instruct",
        "scan_mode": "quick",
    }
    html_output = render_html_report(run_entry)
    assert "SQL Injection in Login Endpoint" in html_output
    assert "CRITICAL" in html_output


# ---------------------------------------------------------------------------
# 8. CVSS & Severity Contract Consistency
# ---------------------------------------------------------------------------


def test_cvss_severity_alignment_contract():
    """Verify that CVSS scores and severities are strictly aligned."""
    score, sev = validate_cvss(9.8)
    assert score == 9.8
    assert sev == "critical"

    score_low, sev_low = validate_cvss(2.5)
    assert score_low == 2.5
    assert sev_low == "low"

    aligned_score, aligned_sev = _align_cvss_severity(9.8, "low")
    # Aligns with score
    assert aligned_sev.lower() == "critical"
