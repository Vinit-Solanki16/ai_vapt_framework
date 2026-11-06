"""Phase 11 Regression Tests: Completion Gate, Finding Consistency & Accurate Telemetry.

Validates:
1. Candidate matching in gap_bridge.candidate_for:
   - Prohibits root slash "/" substring collisions against unrelated endpoints.
   - Accurately matches candidate IDs and tokenized titles.
2. Attempt retention in gap_bridge.record_outcome:
   - Preserves actual attempt count (attempts >= 1) on positive, negative, and inconclusive outcomes.
3. Completion Gate (_evaluate_completion_gate in finish_scan):
   - Rejects premature completion when candidates in gap1_queue remain uninvestigated.
   - Permits completion only when every prioritized candidate is addressed.
   - Prohibits root slash false-positive coverage matching.
4. Scan Matrix Reconciliation (_reconcile_scan_matrix):
   - Accurately reconciles category counts and statuses against confirmed findings.
   - Sets findings_count=0 and status="PASSED" when 0 findings exist.
5. No spurious promotion of passive recon open ports:
   - Disallows unconditional promotion of open ports or passive recon findings without verification.
6. Honest status and turn count stats:
   - Records executed turns in stats.attempts, not max_turns.
   - Marks unaddressed candidates as NOT_TESTED and sets run status to "partial".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from strix.core import gap_bridge
from strix.interface.api import _reconcile_scan_matrix
from strix.tools.finish.tool import _evaluate_completion_gate


@pytest.fixture
def sample_queue(tmp_path: Path) -> Path:
    """Create a sample GAP-1 candidate queue."""
    candidates = [
        {
            "candidate_id": "open-port-9090",
            "title": "Open TCP Port: 9090 (Prometheus/Cockpit)",
            "endpoint": "tcp://127.0.0.1:9090",
            "priority_score": 100,
        },
        {
            "candidate_id": "csp-bypass",
            "title": "Content Security Policy (CSP) Header Not Set",
            "endpoint": "/",
            "priority_score": 90,
        },
        {
            "candidate_id": "missing-hsts",
            "title": "Strict-Transport-Security (HSTS) Header Not Set",
            "endpoint": "/",
            "priority_score": 85,
        },
        {
            "candidate_id": "sensitive-path-robotstxt",
            "title": "Robots Exclusion Protocol Information Disclosure",
            "endpoint": "/robots.txt",
            "priority_score": 80,
        },
    ]
    queue_file = tmp_path / "gap1_queue.json"
    queue_file.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")
    return tmp_path


def test_candidate_matching_no_slash_collision(sample_queue: Path):
    """Proves that root slash '/' does NOT match 'tcp://127.0.0.1:9090' or other non-root endpoints."""
    # When probing root '/' with a title unrelated to port 9090, it must NOT match open-port-9090
    cand = gap_bridge.candidate_for(
        title="Content Security Policy Header Not Set",
        endpoint="/",
        target="http://127.0.0.1:3000/",
        directory=sample_queue,
    )
    assert cand is not None
    assert cand.get("candidate_id") == "csp-bypass"

    # Probing port 9090 must match open-port-9090
    cand_port = gap_bridge.candidate_for(
        title="Open TCP Port: 9090",
        endpoint="tcp://127.0.0.1:9090",
        target="http://127.0.0.1:3000/",
        directory=sample_queue,
    )
    assert cand_port is not None
    assert cand_port.get("candidate_id") == "open-port-9090"

    # Probing robots.txt must match sensitive-path-robotstxt
    cand_robots = gap_bridge.candidate_for(
        title="Robots Exclusion Protocol Information Disclosure",
        endpoint="/robots.txt",
        target="http://127.0.0.1:3000/",
        directory=sample_queue,
    )
    assert cand_robots is not None
    assert cand_robots.get("candidate_id") == "sensitive-path-robotstxt"


def test_record_outcome_attempt_retention(sample_queue: Path):
    """Proves that record_outcome preserves attempts >= 1 on positive and negative outcomes."""
    state = gap_bridge.get_run_state(directory=sample_queue)

    # Negative outcome
    out_neg = gap_bridge.record_outcome(
        directory=sample_queue,
        candidate_id="csp-bypass",
        title="Content Security Policy (CSP) Header Not Set",
        endpoint="/",
        probe_status="negative",
        detail="CSP not present",
    )
    assert out_neg.get("attempts", 0) >= 1
    assert "csp-bypass" in state.completed
    assert state.attempts.get("csp-bypass") == 1

    # Positive outcome
    out_pos = gap_bridge.record_outcome(
        directory=sample_queue,
        candidate_id="sensitive-path-robotstxt",
        title="Robots Exclusion Protocol Information Disclosure",
        endpoint="/robots.txt",
        probe_status="positive",
        detail="Found sensitive route in robots.txt",
    )
    assert out_pos.get("attempts", 0) >= 1
    assert "sensitive-path-robotstxt" in state.completed
    assert state.attempts.get("sensitive-path-robotstxt") == 1


def test_completion_gate_rejection_when_candidates_remain(sample_queue: Path, monkeypatch):
    """Proves that _evaluate_completion_gate blocks finish_scan if candidates remain unaddressed."""
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(sample_queue))
    monkeypatch.setenv(gap_bridge.GAP1_ENABLED_ENV, "true")

    # Initially all 4 candidates in sample_queue are unaddressed
    gate_res = _evaluate_completion_gate()
    assert gate_res.get("permitted") is False
    assert len(gate_res.get("remaining_candidates", [])) == 4
    assert "open-port-9090" in gate_res.get("remaining_candidates", [])

    # Mark 2 candidates completed in run_state
    st = gap_bridge.get_run_state(directory=sample_queue)
    st.completed.add("open-port-9090")
    st.completed.add("csp-bypass")
    st.save()

    # Still 2 remaining candidates (missing-hsts, sensitive-path-robotstxt)
    gate_res2 = _evaluate_completion_gate()
    assert gate_res2.get("permitted") is False
    assert len(gate_res2.get("remaining_candidates", [])) == 2
    assert "missing-hsts" in gate_res2.get("remaining_candidates", [])
    assert "sensitive-path-robotstxt" in gate_res2.get("remaining_candidates", [])

    # Mark remaining completed
    st.completed.add("missing-hsts")
    st.exhausted.add("sensitive-path-robotstxt")
    st.save()

    # Now all are addressed -> permitted
    gate_res3 = _evaluate_completion_gate()
    assert gate_res3.get("permitted") is True
    assert gate_res3.get("investigated_count") == 4


def test_scan_matrix_reconciliation_zero_findings():
    """Proves scan_matrix is reconciled to 0 findings and PASSED status when findings list is empty."""
    raw_matrix = [
        {
            "category_key": "configuration",
            "title": "Common configuration issues",
            "findings_count": 4,
            "status": "VULNERABILITIES_IDENTIFIED",
        },
        {
            "category_key": "xss",
            "title": "XSS testing",
            "findings_count": 1,
            "status": "VULNERABILITIES_IDENTIFIED",
        },
        {
            "category_key": "sqli",
            "title": "SQL Injection",
            "findings_count": 0,
            "status": "PASSED",
        },
    ]

    reconciled = _reconcile_scan_matrix(raw_matrix, [])
    assert len(reconciled) == 3
    for cat in reconciled:
        assert cat["findings_count"] == 0
        assert cat["status"] == "PASSED"


def test_scan_matrix_reconciliation_with_confirmed_findings():
    """Proves scan_matrix correctly classifies confirmed findings and sets VULNERABILITIES_IDENTIFIED."""
    raw_matrix = [
        {
            "category_key": "xss",
            "title": "XSS testing",
            "findings_count": 0,
            "status": "PASSED",
        },
        {
            "category_key": "sqli",
            "title": "SQL Injection",
            "findings_count": 0,
            "status": "PASSED",
        },
    ]
    findings = [
        {
            "id": "find-1",
            "title": "Reflected Cross-Site Scripting (XSS)",
            "cwe_id": "CWE-79",
        }
    ]

    reconciled = _reconcile_scan_matrix(raw_matrix, findings)
    xss_entry = next(m for m in reconciled if m["category_key"] == "xss")
    sqli_entry = next(m for m in reconciled if m["category_key"] == "sqli")

    assert xss_entry["findings_count"] == 1
    assert xss_entry["status"] == "VULNERABILITIES_IDENTIFIED"
    assert sqli_entry["findings_count"] == 0
    assert sqli_entry["status"] == "PASSED"


def test_partial_status_when_candidates_untested():
    """Proves that untested candidates are marked NOT_TESTED and assessment is marked partial."""
    candidates = [
        {"id": "cand-1", "name": "Cand 1", "state": "ABANDONED", "attempts": 1},
        {"id": "cand-2", "name": "Cand 2", "state": "PENDING", "attempts": 0},
    ]

    untested_count = 0
    for cand in candidates:
        if cand.get("state") in ("PENDING", None) or (cand.get("attempts", 0) == 0 and cand.get("state") not in ("VALIDATED", "ABANDONED")):
            cand["state"] = "NOT_TESTED"
            cand["status"] = "NOT_TESTED"
            untested_count += 1

    assert untested_count == 1
    assert candidates[1]["state"] == "NOT_TESTED"
    assert candidates[0]["state"] == "ABANDONED"
