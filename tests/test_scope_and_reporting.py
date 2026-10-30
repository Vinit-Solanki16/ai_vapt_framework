"""Tests for Scope Gatekeeper, Cryptographic Evidence, and Audit Reporting."""
from __future__ import annotations

import hashlib
import pytest

from strix.core.safety.scope_validator import validate_web_target
from strix.report.builder import render_html_report
from strix.tools.validators.base import BaseValidator


def test_scope_validator_loopback_allowed():
    """Verify local loopback is authorized."""
    res = validate_web_target("http://127.0.0.1:8000/app")
    assert res.authorized is True
    assert res.in_scope is True


def test_scope_validator_metadata_blocked():
    """Verify cloud metadata endpoint (169.254.169.254) is unconditionally rejected."""
    res = validate_web_target("http://169.254.169.254/latest/meta-data/")
    assert res.authorized is False
    assert "REJECTED" in res.authorization_status


def test_cryptographic_evidence_hash():
    """Verify SHA-256 evidence hashing."""
    val = BaseValidator()
    raw = b"HTTP/1.1 200 OK\r\nServer: Apache\r\n\r\nPHP Version 8.1.2"
    expected = hashlib.sha256(raw).hexdigest()
    assert val.compute_evidence_hash(raw) == expected
    assert len(expected) == 64


def test_report_builder_html_rendering():
    """Verify HTML audit report generator includes required sections."""
    sample_run = {
        "run_id": "run-test1234",
        "status": "completed",
        "mode": "simulation",
        "target_url": "http://127.0.0.1:8080",
        "findings": [
            {
                "id": "find-1",
                "title": "PHPInfo Diagnostic Exposure",
                "severity": "medium",
                "cvss_score": 5.3,
                "evidence_hash": hashlib.sha256(b"sample-evidence").hexdigest(),
            }
        ],
        "decision_trace": ["[INIT] Started", "[ADVANCE] finding-1 validated"],
        "pivot_events": [],
    }

    html = render_html_report(sample_run)
    assert "<!DOCTYPE html>" in html
    assert "run-test1234" in html
    assert "PHPInfo Diagnostic Exposure" in html
    assert "A01:2021" in html
    assert "SHA-256 Proof Hash" in html
    assert "Server Hardening Configuration" in html


def test_report_builder_xss_payload_escaped():
    """Verify XSS payloads in findings and retest procedures are strictly HTML-escaped."""
    xss_run = {
        "run_id": "run-xss",
        "status": "completed",
        "mode": "web",
        "target_url": "https://pentest-ground.com:4280",
        "findings": [
            {
                "id": "find-xss",
                "title": "Reflected Cross-Site Scripting <script>alert(1)</script>",
                "severity": "high",
                "cvss_score": 6.1,
                "retest_procedure": 'curl -s "https://target/?q=<script>alert(1)</script>"',
                "evidence_hash": hashlib.sha256(b"xss").hexdigest(),
            }
        ],
        "decision_trace": ["[DISPATCH] Injected <script>alert(1)</script> probe"],
        "pivot_events": [],
    }

    html = render_html_report(xss_run)
    # The literal script tags must NEVER appear unescaped in executable form
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    # Check print-friendly CSS is present
    assert "@media print" in html
    assert "break-inside: avoid" in html


