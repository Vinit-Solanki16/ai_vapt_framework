"""Regression: worker finding sync must carry the engine's verification state.

A confirmed SQLi finding had all five evidence fields and the engine's
verification block said ``verified``, but the dashboard showed ``unconfirmed``:
the worker built ``finding_item`` without ``verification_state``, so
``evaluate_finding_verification`` saw the default and downgraded it.
"""

from __future__ import annotations

from strix.report.verification import evaluate_finding_verification


def test_verification_state_from_engine_block_is_preserved() -> None:
    """A fully evidenced finding with engine state 'verified' stays verified."""
    finding = {
        "title": "SQL Injection Authentication Bypass in /rest/user/login",
        "verification_state": "verified",
        "reproducible_request": "POST /rest/user/login ... email=' OR 1=1--",
        "reproducible_response": "HTTP/1.1 200 {\"authentication\":{\"token\":\"...\"}}",
        "verification_procedure": "baseline 401 then injection payload returned admin token",
        "demonstrated_impact": "Authentication bypass to admin@juice-sh.op",
        "evidence_timestamp": "2026-11-18 07:08:00 UTC",
    }
    state, _reason, verified = evaluate_finding_verification(finding)
    assert verified is True
    assert state == "verified"


def test_missing_verification_state_still_downgrades() -> None:
    """The gate is not weakened: no engine state means no confirmation."""
    finding = {
        "title": "SQL Injection Authentication Bypass in /rest/user/login",
        "verification_state": "",
        "reproducible_request": "POST /rest/user/login ...",
        "reproducible_response": "HTTP 200 with token",
        "verification_procedure": "payload sent",
        "demonstrated_impact": "auth bypass",
        "evidence_timestamp": "2026-11-18 07:08:00 UTC",
    }
    state, _reason, verified = evaluate_finding_verification(finding)
    assert verified is False
    assert state != "verified"
