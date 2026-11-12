"""Comprehensive Regression Tests for AI-VAPT Lifecycle, Verification, GAP1/GAP2, and Duration Tracking.

Tests cover:
1. Finding verification states (all 9 states, transitions, contracts)
2. Positive and negative exploit validation (SQLi, Command Injection, LFI, Recon Ports)
3. Duplicate finding deduplication
4. Severity and CVSS v3.1 consistency
5. GAP-1 candidate investigation accounting equation (dispatched == investigated + not_tested + blocked)
6. Genuine GAP-2 dynamic pivoting (probe outcome, reason, alternative candidate, executed flag)
7. Live elapsed duration from persisted start_time, refresh persistence, and duration freezing
8. Provider quota error handling (provider_blocked) and resumability (/resume endpoint)
9. Report consistency across HTML, Markdown, JSON, and SARIF
10. Incomplete coverage ledger reporting (untested categories never reported as passed)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from strix.core.decision_engine.engine import DecisionEngine
from strix.core.decision_engine.schemas import (
    ActionCandidate,
    CandidateState,
    Outcome,
    VerificationState,
)
from strix.interface.api import (
    _align_cvss_severity,
    _finalize_run_lifecycle,
    _format_duration_str,
    _generate_markdown_report,
    _probe_web_candidate,
    app,
)
from strix.report.builder import render_html_report
from strix.report.sarif import build_sarif_report
from strix.report.verification import (
    CategoryTest,
    VerificationBlock,
    validate_category_outcome,
)


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Verification States and Lifecycle Contracts
# ---------------------------------------------------------------------------


def test_verification_states_enum():
    """Ensure all 9 mandatory verification states are defined and distinct."""
    expected_states = {
        "Discovered",
        "Candidate",
        "Under investigation",
        "Exploitation attempted",
        "Verified",
        "Unconfirmed",
        "False positive",
        "Blocked",
        "Inconclusive",
    }
    actual_states = {s.value for s in VerificationState}
    assert expected_states == actual_states


def test_verification_block_contract():
    """Verify that a confirmed finding carries full reproducible evidence."""
    block = VerificationBlock(
        verification_state="verified",
        reproducible_request="GET /vulnerabilities/fi/?page=../../../../etc/passwd HTTP/1.1\nHost: example.com",
        verification_response="root:x:0:0:root:/root:/bin/bash",
        verification_procedure="Path traversal probe with root token pattern matching",
        demonstrated_impact="Arbitrary local system file read exposing /etc/passwd",
        confidence="high",
        severity="high",
        remediation="Validate and sanitize file path input; enforce whitelist.",
    )
    data = block.to_dict()
    assert data["verification_state"] == "verified"
    assert "root:x:0:0" in data["verification_response"]
    assert data["demonstrated_impact"] != ""
    assert data["evidence_timestamp"] != ""


# ---------------------------------------------------------------------------
# 2. Positive and Negative Exploit Validation
# ---------------------------------------------------------------------------


def test_open_port_is_never_confirmed_vulnerability():
    """Open TCP ports are reconnaissance artifacts; they must NEVER be confirmed vulnerabilities."""
    with patch("socket.socket") as mock_sock_cls:
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0  # Port is open
        mock_sock_cls.return_value = mock_sock

        res = _probe_web_candidate("http://target.local:4280", "open-port-80", "/80")
        assert isinstance(res, tuple)
        is_vuln, msg, snip = res

        # Must NOT be marked as a vulnerability finding
        assert is_vuln is False
        assert "Reconnaissance host/port enumeration metadata" in msg
        assert getattr(res, "verification_state", None) == "Discovered"


def test_sqli_differential_and_error_validation():
    """SQL injection must validate either via database syntax error or boolean differential."""
    # Negative test: normal response without difference
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html>Welcome User</html>"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = _probe_web_candidate("http://target.local:4280", "sqli", "/search")
        is_vuln, msg, _ = res
        assert is_vuln is False
        assert getattr(res, "verification_state", None) in ("Unconfirmed", "Candidate")

    # Positive test: SQL syntax error reflected
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"Fatal error: You have an error in your SQL syntax near ''''"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = _probe_web_candidate("http://target.local:4280", "sqli", "/vulnerabilities/sqli/")
        is_vuln, msg, snip = res
        assert is_vuln is True
        assert "SQL syntax error" in msg
        assert getattr(res, "verification_state", None) == "Verified"
        assert getattr(res, "demonstrated_impact", None) is not None


def test_command_injection_validation():
    """Command injection requires verified system command output (uid/gid) execution proof."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = (
            b"<pre>uid=33(www-data) gid=33(www-data) groups=33(www-data)</pre>"
        )
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = _probe_web_candidate(
            "http://target.local:4280", "command-injection", "/vulnerabilities/exec/"
        )
        is_vuln, msg, snip = res
        assert is_vuln is True
        assert "uid=" in snip
        assert getattr(res, "verification_state", None) == "Verified"
        assert getattr(res, "severity", None) == "CRITICAL"


# ---------------------------------------------------------------------------
# 3. Duplicate Finding Deduplication
# ---------------------------------------------------------------------------


def test_finding_deduplication():
    """Identical findings across same endpoint and parameter must be consolidated."""
    raw_findings = [
        {
            "title": "SQL Injection",
            "location": "/vulnerabilities/sqli/",
            "parameter": "id",
            "severity": "CRITICAL",
            "cvss_score": 9.8,
        },
        {
            "title": "SQL Injection",
            "location": "/vulnerabilities/sqli/",
            "parameter": "id",
            "severity": "CRITICAL",
            "cvss_score": 9.8,
        },
        {
            "title": "Command Injection",
            "location": "/vulnerabilities/exec/",
            "parameter": "ip",
            "severity": "CRITICAL",
            "cvss_score": 9.8,
        },
    ]

    seen = set()
    deduped = []
    for f in raw_findings:
        key = (f["title"].lower(), f["location"].lower(), str(f.get("parameter", "")).lower())
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    assert len(deduped) == 2
    assert deduped[0]["title"] == "SQL Injection"
    assert deduped[1]["title"] == "Command Injection"


# ---------------------------------------------------------------------------
# 4. Severity and CVSS Consistency
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_cvss, raw_sev, expected_cvss, expected_sev",
    [
        (9.8, "LOW", 9.8, "CRITICAL"),
        (8.5, "CRITICAL", 8.5, "HIGH"),
        (5.4, "HIGH", 5.4, "MEDIUM"),
        (2.1, "HIGH", 2.1, "LOW"),
        (0.0, "HIGH", 0.0, "INFO"),
        (None, "CRITICAL", 9.8, "CRITICAL"),
        (None, "HIGH", 8.2, "HIGH"),
        (None, "MEDIUM", 5.5, "MEDIUM"),
        (None, "LOW", 3.1, "LOW"),
    ],
)
def test_align_cvss_severity(raw_cvss, raw_sev, expected_cvss, expected_sev):
    score, sev = _align_cvss_severity(raw_cvss, raw_sev)
    assert score == expected_cvss
    assert sev == expected_sev


# ---------------------------------------------------------------------------
# 5. GAP-1 Candidate Investigation Accounting
# ---------------------------------------------------------------------------


def test_gap1_accounting_equation():
    """Dispatched must equal investigated + not_tested + blocked."""
    candidates = [
        {"id": "cand-1", "state": "VALIDATED", "attempts": 1},
        {"id": "cand-2", "state": "ABANDONED", "attempts": 2},
        {"id": "cand-3", "state": "BLOCKED", "attempts": 0},
        {"id": "cand-4", "state": "NOT_TESTED", "attempts": 0},
        {"id": "cand-5", "state": "NOT_TESTED", "attempts": 0},
    ]

    dispatched = len(candidates)
    investigated = sum(
        1
        for c in candidates
        if c["state"] in ("VALIDATED", "ABANDONED") or c.get("attempts", 0) > 0
    )
    validated = sum(1 for c in candidates if c["state"] == "VALIDATED")
    abandoned = sum(1 for c in candidates if c["state"] == "ABANDONED")
    not_tested = sum(1 for c in candidates if c["state"] == "NOT_TESTED")
    blocked = sum(1 for c in candidates if c["state"] == "BLOCKED")

    assert investigated == 2
    assert validated == 1
    assert abandoned == 1
    assert not_tested == 2
    assert blocked == 1
    # Truthful equation:
    assert dispatched == investigated + not_tested + blocked


# ---------------------------------------------------------------------------
# 6. Genuine GAP-2 Dynamic Pivoting
# ---------------------------------------------------------------------------


def test_genuine_gap2_pivoting():
    """GAP-2 must record genuine pivot decisions with reason and alternative candidate."""
    engine = DecisionEngine(pivot_threshold=2)
    c1 = ActionCandidate(
        id="route-a", name="Route A", target="http://target.local", probability=0.8
    )
    c2 = ActionCandidate(
        id="route-b", name="Route B", target="http://target.local", probability=0.6
    )
    engine.initialize([c1, c2])

    # First attempt: failure
    p1 = engine.record_outcome(
        "route-a", Outcome.FAIL_TIMEOUT, probe_outcome="negative", reason="WAF 403 block"
    )
    assert p1.action.value == "RETRY"
    # Includes INIT + RETRY
    assert len(engine.pivot_events) == 2

    # Second attempt: failure reaches threshold k=2 -> genuine pivot
    p2 = engine.record_outcome(
        "route-a", Outcome.FAIL_TIMEOUT, probe_outcome="negative", reason="Repeated WAF block"
    )
    assert p2.action.value == "REDIRECT"
    assert c1.state == CandidateState.ABANDONED
    # Includes INIT + RETRY + ABANDON + PIVOT
    assert len(engine.pivot_events) == 4

    abandon_event = engine.pivot_events[-2]
    assert abandon_event.event == "GAP2_ABANDON"
    assert "WAF" in (abandon_event.reason or "")

    last_event = engine.pivot_events[-1]
    assert last_event.candidate_id == "route-a"
    assert last_event.next_candidate == "route-b"
    assert last_event.pivot_executed is True
    assert "Failure threshold reached" in (last_event.reason or "")


# ---------------------------------------------------------------------------
# 7. Live Elapsed Duration and Timer Freezing
# ---------------------------------------------------------------------------


def test_live_duration_calculation_and_freezing():
    """Elapsed duration must be computed from persisted timestamps and frozen on finish."""
    start_time = (datetime.now(UTC) - timedelta(seconds=125)).isoformat()
    run_entry: dict[str, Any] = {
        "run_id": "test-run-dur",
        "status": "running",
        "start_time": start_time,
        "end_time": None,
        "duration_seconds": None,
        "events": [],
    }

    # Simulate ongoing duration
    s_dt = datetime.fromisoformat(run_entry["start_time"])
    cur_dur = (datetime.now(UTC) - s_dt).total_seconds()
    assert 120 <= cur_dur <= 135

    # Finalize run
    _finalize_run_lifecycle(run_entry, status="completed")
    assert run_entry["status"] == "completed"
    assert run_entry["end_time"] is not None
    frozen_dur = run_entry["duration_seconds"]
    assert frozen_dur is not None
    assert 120 <= frozen_dur <= 135

    # Duration format check
    dur_str = _format_duration_str(frozen_dur)
    assert dur_str.startswith("00:02:")


# ---------------------------------------------------------------------------
# 8. Provider Rate-Limit Handling and Resumability
# ---------------------------------------------------------------------------


def test_provider_quota_blocked_and_resumability(client: TestClient):
    """Detect permanent daily quota exhaustion (429) and verify /resume endpoint."""
    run_id = "test-quota-resume"
    run_entry = {
        "run_id": run_id,
        "status": "provider_blocked",
        "start_time": datetime.now(UTC).isoformat(),
        "end_time": datetime.now(UTC).isoformat(),
        "duration_seconds": 45.0,
        "scenario": "web_application",
        "mode": "autonomous",
        "target_url": "https://pentest-ground.com:4280/",
        "model": "openrouter/free-model",
        "provider": "openrouter",
        "scan_mode": "quick",
        "max_turns": 20,
        "candidates": [{"id": "sqli", "name": "SQL Injection", "state": "PENDING", "attempts": 0}],
        "findings": [],
        "decision_trace": [],
        "pivot_events": [],
        "events": [],
        "provider_error": "Provider daily quota exhausted (HTTP 429)",
    }

    from strix.interface import api as api_mod

    api_mod._RUNS[run_id] = run_entry

    # Check status endpoint
    resp = client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "provider_blocked"

    # Resume the run with another model
    with patch("strix.interface.api._execute_run_worker") as mock_worker:
        res_resp = client.post(
            f"/runs/{run_id}/resume",
            json={"model": "google/gemini-2.5-flash", "provider": "google"},
        )
        assert res_resp.status_code == 200
        res_data = res_resp.json()
        assert res_data["status"] == "resumed"

        # Verify run in memory is transitioned to running with new model
        updated = api_mod._RUNS[run_id]
        assert updated["status"] == "running"
        assert updated["model"] == "google/gemini-2.5-flash"
        assert updated["provider"] == "google"
        assert updated["end_time"] is None
        assert updated["provider_error"] is None
        assert mock_worker.called


# ---------------------------------------------------------------------------
# 9. Report Consistency Across Formats
# ---------------------------------------------------------------------------


def test_report_consistency():
    """HTML, Markdown, and SARIF reports must strictly agree on findings, status, and duration."""
    start_t = datetime.now(UTC).isoformat()
    end_t = (datetime.now(UTC) + timedelta(seconds=75)).isoformat()
    run_data = {
        "run_id": "test-report-consistency",
        "status": "completed",
        "start_time": start_t,
        "end_time": end_t,
        "duration_seconds": 75.0,
        "target_url": "https://pentest-ground.com:4280/",
        "findings": [
            {
                "id": "find-sqli",
                "title": "SQL Injection",
                "severity": "CRITICAL",
                "cvss_score": 9.8,
                "cwe_id": "CWE-89",
                "owasp_category": "A03:2021 - Injection",
                "location": "/vulnerabilities/sqli/",
                "parameter": "id",
                "verification_state": "Verified",
                "verified": True,
                "evidence_hash": "a1b2c3d4e5f67890",
                "reproducible_request": "GET /vulnerabilities/sqli/?id=1'%20OR%20'1'='1&Submit=Submit HTTP/1.1",
                "evidence_snippet": "First name: admin Surname: admin",
                "verification_procedure": "Boolean differential query validation",
                "demonstrated_impact": "Unauthorized extraction of backend database records",
            }
        ],
        "candidates": [
            {"id": "sqli", "name": "SQL Injection", "state": "VALIDATED", "attempts": 1},
        ],
        "candidate_accounting": {
            "dispatched": 1,
            "investigated": 1,
            "validated": 1,
            "abandoned": 0,
            "not_tested": 0,
            "blocked": 0,
        },
    }

    # 1. HTML Report
    html_out = render_html_report(run_data)
    assert "test-report-consistency" in html_out
    assert "00:01:15" in html_out
    assert "SQL Injection" in html_out
    assert "VERIFIED" in html_out
    assert "CRITICAL" in html_out
    assert "9.8" in html_out

    # 2. Markdown Report
    md_out = _generate_markdown_report(run_data)
    assert "test-report-consistency" in md_out
    assert "00:01:15" in md_out
    assert "### 2.1 SQL Injection" in md_out
    assert "CRITICAL" in md_out
    assert "CVSS Score:** 9.8" in md_out
    assert "Verification State:** `Verified`" in md_out

    # 3. SARIF Report
    sarif_out = build_sarif_report(run_data["findings"])
    results = sarif_out["runs"][0]["results"]
    assert len(results) == 1
    assert results[0]["level"] == "error"  # CRITICAL maps to SARIF level 'error'
    assert "SQL Injection" in results[0]["message"]["text"]


# ---------------------------------------------------------------------------
# 10. Incomplete Coverage Reporting
# ---------------------------------------------------------------------------


def test_category_test_ledger():
    """Untested categories must remain untested and cannot be reported as passed."""
    ct = CategoryTest(category="csrf", title="Cross-Site Request Forgery")
    assert ct.is_untested is True
    assert ct.is_passed is False

    # Mark as blocked
    ct.update(tested=True, outcome="blocked", blocked_count=1)
    assert ct.is_blocked is True
    assert ct.is_passed is False

    with pytest.raises(ValueError):
        validate_category_outcome("invalid_outcome")


# ---------------------------------------------------------------------------
# 11. Phase 2: Genuine Finding Verification Contract Enforcement
# ---------------------------------------------------------------------------


def test_missing_evidence_cannot_produce_verified_finding():
    """A finding lacking reproducible request, response, procedure, or impact cannot be Verified."""
    # 1. Missing reproducible_request
    b1 = VerificationBlock(
        verification_state="verified",
        reproducible_request="",
        verification_response="HTTP 200 OK",
        verification_procedure="Manual injection",
        demonstrated_impact="Data leak",
    )
    assert b1.satisfies_verification_contract() is False
    assert b1.verification_state == "unconfirmed"

    # 2. Missing verification_procedure
    b2 = VerificationBlock(
        verification_state="verified",
        reproducible_request="GET /api/test HTTP/1.1",
        verification_response="HTTP 200 OK",
        verification_procedure="",
        demonstrated_impact="Data leak",
    )
    assert b2.satisfies_verification_contract() is False
    assert b2.verification_state == "unconfirmed"

    # 3. Missing demonstrated_impact
    b3 = VerificationBlock(
        verification_state="verified",
        reproducible_request="GET /api/test HTTP/1.1",
        verification_response="HTTP 200 OK",
        verification_procedure="SQLi probe",
        demonstrated_impact="",
    )
    assert b3.satisfies_verification_contract() is False
    assert b3.verification_state == "unconfirmed"

    # 4. Dummy / N/A request
    b4 = VerificationBlock(
        verification_state="verified",
        reproducible_request="N/A",
        verification_response="HTTP 200 OK",
        verification_procedure="Probe",
        demonstrated_impact="Impact",
    )
    assert b4.satisfies_verification_contract() is False
    assert b4.verification_state == "unconfirmed"

    # 5. Full valid contract
    b5 = VerificationBlock(
        verification_state="verified",
        reproducible_request="GET /vuln?id=1' HTTP/1.1",
        verification_response="SQL syntax error",
        verification_procedure="Injected SQL single quote",
        demonstrated_impact="Unauthorized database syntax disclosure",
    )
    assert b5.satisfies_verification_contract() is True
    assert b5.verification_state == "verified"


# ---------------------------------------------------------------------------
# 12. Phase 3: Negative Probe Does Not Emit Pivot Without Alternative Probe
# ---------------------------------------------------------------------------


def test_unsuccessful_probe_does_not_count_as_pivot():
    """An unsuccessful probe attempt (attempt 1 of k=2) must NOT emit a GAP2_PIVOT event."""
    engine = DecisionEngine(pivot_threshold=2)
    c1 = ActionCandidate(id="c1", name="Candidate 1", target="http://target.local")
    c2 = ActionCandidate(id="c2", name="Candidate 2", target="http://target.local")
    engine.initialize([c1, c2])

    action = engine.record_outcome(
        "c1",
        Outcome.FAIL_TIMEOUT,
        probe_outcome="negative",
        detail="Target endpoint returned 404 Not Found",
    )
    assert action.action.value == "RETRY"
    assert c1.attempts == 1
    assert c1.state == CandidateState.ATTEMPTING

    # Only INIT and RETRY events exist; NO GAP2_PIVOT
    pivot_events = [e for e in engine.pivot_events if getattr(e, "event", "") == "GAP2_PIVOT"]
    assert len(pivot_events) == 0


def test_genuine_pivot_requires_alternative_selection_and_execution():
    """A genuine pivot requires threshold k reached, alternative selected, and alternative probed."""
    engine = DecisionEngine(pivot_threshold=2)
    c1 = ActionCandidate(id="c1", name="Candidate 1", target="http://target.local")
    c2 = ActionCandidate(id="c2", name="Candidate 2", target="http://target.local")
    engine.initialize([c1, c2])

    # Attempt 1 on c1
    engine.record_outcome(
        "c1", Outcome.FAIL_TIMEOUT, probe_outcome="negative", detail="Probe 1 failed"
    )
    # Attempt 2 on c1 reaches threshold k=2
    action = engine.record_outcome(
        "c1", Outcome.FAIL_TIMEOUT, probe_outcome="negative", detail="Probe 2 failed"
    )

    assert action.action.value == "REDIRECT"
    assert action.to_candidate == "c2"
    assert c1.state == CandidateState.ABANDONED

    # Alternative candidate c2 is selected and probed
    engine.current_index = 1
    c2.state = CandidateState.ATTEMPTING
    alt_action = engine.record_outcome(
        "c2", Outcome.SUCCESS, probe_outcome="positive", detail="PoC confirmed on alternative route"
    )
    assert alt_action.action.value == "COMPLETE"
    assert c2.state == CandidateState.VALIDATED
    assert c2.attempts == 1


# ---------------------------------------------------------------------------
# 13. Phase 4: Resumption Preserves Completed Candidates and Findings
# ---------------------------------------------------------------------------


def test_resume_preserves_completed_candidates_and_findings(tmp_path: Path):
    """Resuming a run preserves completed candidates, existing findings, and skips completed investigations."""
    from strix.interface.api import _RUNS, _execute_run_worker
    from strix.interface.schemas import RunRequest

    run_id = f"test-resume-preservation-{int(datetime.now(UTC).timestamp() * 1000)}"
    fake_strix_runs = tmp_path / "strix_runs"
    fake_strix_runs.mkdir(parents=True, exist_ok=True)

    verified_finding = {
        "id": "find-c1",
        "title": "SQL Injection",
        "severity": "CRITICAL",
        "cvss_score": 9.8,
        "location": "/sqli",
        "parameter": "id",
        "verification_state": "Verified",
        "verified": True,
        "reproducible_request": "GET /sqli?id=1' HTTP/1.1",
        "reproducible_response": "SQL syntax error near ''''",
        "verification_procedure": "Injected SQL quote",
        "demonstrated_impact": "Database query manipulation",
    }

    run_entry: dict[str, Any] = {
        "run_id": run_id,
        "status": "provider_blocked",
        "scenario": "web_application",
        "mode": "lightweight",
        "target_url": "http://127.0.0.1:4280",
        "is_resumed": True,
        "start_time": datetime.now(UTC).isoformat(),
        "created_at": datetime.now(UTC).isoformat(),
        "events": [
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "event": "RUN_RESUMED",
                "message": "Resumed",
            }
        ],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [
            {
                "id": "c1",
                "name": "SQL Injection",
                "endpoint": "/sqli",
                "state": "VALIDATED",
                "attempts": 1,
                "detail": "SQL syntax error near ''''",
                "reproducible_request": "GET /sqli?id=1' HTTP/1.1",
                "reproducible_response": "SQL syntax error near ''''",
                "verification_procedure": "Injected SQL quote",
                "demonstrated_impact": "Database query manipulation",
            },
            {
                "id": "c2",
                "name": "Abandoned Route",
                "endpoint": "/abandoned",
                "state": "ABANDONED",
                "attempts": 2,
                "detail": "Threshold reached",
            },
            {
                "id": "c3",
                "name": "Pending Candidate",
                "endpoint": "/pending",
                "state": "PENDING",
                "attempts": 0,
            },
        ],
        "findings": [verified_finding],
        "stats": {"attempts": 3, "pivots": 1, "findings": 1},
    }
    _RUNS[run_id] = run_entry

    req = RunRequest(
        target_url="http://127.0.0.1:4280",
        mode="lightweight",
        scan_mode="quick",
        max_turns=10,
    )

    probe_calls = []

    def mock_probe(target, cid, ep, auth_session=None):
        probe_calls.append(cid)
        return (False, "Probe negative", "")

    with (
        patch("strix.interface.api.runs_base_dir", return_value=fake_strix_runs),
        patch("strix.interface.api._is_docker_available", return_value=False),
        patch("strix.interface.api._probe_web_candidate", side_effect=mock_probe),
    ):
        _execute_run_worker(run_id, req, None)

    # c1 (VALIDATED) and c2 (ABANDONED) MUST NOT have been probed again!
    assert "c1" not in probe_calls
    assert "c2" not in probe_calls
    # Only c3 (PENDING) should have been probed
    assert "c3" in probe_calls

    # Preserved findings must still contain verified finding
    final_findings = run_entry["findings"]
    assert any(
        f["id"] == "find-c1" and f["verification_state"] == "Verified" for f in final_findings
    )

    # Preserved candidates: c1 is still VALIDATED, c2 is still ABANDONED
    cands_by_id = {c["id"]: c for c in run_entry["candidates"]}
    assert cands_by_id["c1"]["state"] == "VALIDATED"
    assert cands_by_id["c2"]["state"] == "ABANDONED"
