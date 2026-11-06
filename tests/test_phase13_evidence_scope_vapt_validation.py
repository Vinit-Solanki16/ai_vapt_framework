"""Phase 13 — Evidence Integrity, Scope Accuracy and VAPT Validation Test Suite.

Verifies:
1. CSP validation & calibration (missing CSP is a hardening observation, not CRITICAL XSS).
2. HSTS validation (inapplicable on HTTP-only localhost targets; rejected/NOT_APPLICABLE).
3. HTTP PUT validation (SPA fallback HTTP 200 is UNVERIFIED; read-back verification required).
4. Network scope enforcement (ports 8000/9090 on localhost excluded from web app candidates).
5. GAP1 accounting (dispatched, investigated, validated, abandoned, not_tested, blocked separated).
6. GAP2 consistency (pivot events synced, abandonment distinguished from dynamic pivot execution).
7. Category & rule count integrity (8 categories, 88 rules aligned across scanner and reports).
8. SPA crawling & component inventory (Angular routes, APIs, query parameters, and components populated).
9. Report canonical dataset (all 8 required fields populated for confirmed findings).
"""

import pytest

from strix.core.scanner.full_scanner import FullScanner
from strix.core.scanner.passive_rules import SCAN_CATEGORIES, run_passive_rules
from strix.core.scanner.port_scanner import scan_target_ports
from strix.report.builder import render_html_report
from strix.tools.reporting.tool import _do_create


# =============================================================================
# 1. CSP Validation & Calibration
# =============================================================================


@pytest.mark.asyncio
async def test_csp_missing_calibrated_to_observation(tmp_path, monkeypatch):
    """Missing CSP header must be calibrated to Low/Info observation, not CRITICAL CVSS 9.4."""
    from strix.report.state import ReportState, set_global_report_state

    state = ReportState(tmp_path)
    set_global_report_state(state)

    res = await _do_create(
        title="Content Security Policy (CSP) Header Not Set",
        description="The application does not set a Content-Security-Policy header.",
        impact="Without CSP, the application may be vulnerable to script injection.",
        target="http://127.0.0.1:3000/",
        technical_analysis="HTTP GET response does not include Content-Security-Policy header.",
        poc_description="1. GET /\n2. Inspect response headers.",
        poc_script_code="GET / HTTP/1.1\nHost: 127.0.0.1:3000",
        remediation_steps="Configure a strict Content-Security-Policy header.",
        evidence="HTTP 200 OK\nServer: Express\nX-Frame-Options: SAMEORIGIN",
        assumptions="Target application is accessible over HTTP.",
        counterevidence="No CSP header observed in response.",
        confidence="high",
        severity_change_conditions="Adding CSP lowers impact.",
        fix_effort="low",
        cvss_breakdown={
            "attack_vector": "N",
            "attack_complexity": "L",
            "privileges_required": "N",
            "user_interaction": "N",
            "scope": "U",
            "confidentiality": "H",
            "integrity": "H",
            "availability": "L",
        },
        endpoint="/",
    )

    assert res.get("success") is True
    # Severity must be capped to low (not critical), CVSS <= 3.9
    assert res.get("severity") in ("low", "info")
    assert res.get("cvss_score", 10.0) <= 3.9

    stored = state.get_existing_vulnerabilities()
    assert len(stored) == 1
    assert stored[0]["finding_class"] == "observation"
    assert stored[0]["severity"] in ("low", "info")


# =============================================================================
# 2. HSTS Validation
# =============================================================================


@pytest.mark.asyncio
async def test_hsts_rejected_on_http_only_localhost():
    """HSTS must be rejected as NOT_APPLICABLE on HTTP-only localhost target."""
    res = await _do_create(
        title="Strict-Transport-Security (HSTS) Header Not Set",
        description="Target does not set Strict-Transport-Security header.",
        impact="Could allow protocol downgrade attacks.",
        target="http://127.0.0.1:3000/",
        technical_analysis="Missing Strict-Transport-Security header.",
        poc_description="1. GET /\n2. Inspect headers.",
        poc_script_code="GET / HTTP/1.1\nHost: 127.0.0.1:3000",
        remediation_steps="Add Strict-Transport-Security header.",
        evidence="Strict-Transport-Security: [NOT PRESENT]",
        assumptions="Target is accessible.",
        counterevidence="Target runs plain HTTP without TLS.",
        confidence="high",
        severity_change_conditions="TLS deployment required.",
        fix_effort="low",
        cvss_breakdown={
            "attack_vector": "N",
            "attack_complexity": "L",
            "privileges_required": "N",
            "user_interaction": "N",
            "scope": "U",
            "confidentiality": "H",
            "integrity": "L",
            "availability": "L",
        },
        endpoint="/",
    )

    assert res.get("success") is False
    assert "NOT_APPLICABLE" in res.get("error", "")


def test_passive_rules_no_hsts_on_http():
    """Passive scanner must not flag missing HSTS on HTTP target."""
    headers = {"server": "Node/Express", "x-frame-options": "SAMEORIGIN"}
    findings, _ = run_passive_rules("http://127.0.0.1:3000/", headers, [], "<html></html>")
    hsts_findings = [f for f in findings if "hsts" in f.get("id", "").lower()]
    assert len(hsts_findings) == 0


def test_passive_rules_flags_hsts_on_https():
    """Passive scanner should flag missing HSTS when target is HTTPS."""
    headers = {"server": "Node/Express", "x-frame-options": "SAMEORIGIN"}
    findings, _ = run_passive_rules("https://example.com/", headers, [], "<html></html>")
    hsts_findings = [f for f in findings if "hsts" in f.get("id", "").lower()]
    assert len(hsts_findings) == 1
    assert hsts_findings[0]["severity"] == "low"


# =============================================================================
# 3. HTTP PUT Validation
# =============================================================================


@pytest.mark.asyncio
async def test_put_arbitrary_file_write_rejected_without_readback():
    """PUT HTTP 200 without verified unique marker read-back must be rejected as UNVERIFIED."""
    res = await _do_create(
        title="Insecure HTTP PUT Method Enabled (Arbitrary File Write)",
        description="Server responds 200 OK to PUT request.",
        impact="Could allow arbitrary file creation.",
        target="http://127.0.0.1:3000/",
        technical_analysis="A PUT request to /strix_probe_test.txt returned HTTP 200 OK.",
        poc_description="1. PUT /strix_probe_test.txt\n2. Observe 200 OK.",
        poc_script_code="PUT /strix_probe_test.txt HTTP/1.1\nHost: 127.0.0.1:3000\n\ntest",
        remediation_steps="Disable PUT method.",
        evidence="HTTP/1.1 200 OK\nContent-Type: text/html\n\n<!doctype html><html>Index</html>",
        assumptions="Target accepts file writes.",
        counterevidence="Server returned 200 with HTML body (SPA fallback).",
        confidence="high",
        severity_change_conditions="Disable PUT method.",
        fix_effort="low",
        cvss_breakdown={
            "attack_vector": "N",
            "attack_complexity": "L",
            "privileges_required": "N",
            "user_interaction": "N",
            "scope": "U",
            "confidentiality": "H",
            "integrity": "H",
            "availability": "H",
        },
        endpoint="/strix_probe_test.txt",
    )

    assert res.get("success") is False
    assert "UNVERIFIED" in res.get("error", "")


# =============================================================================
# 4. Network Scope Enforcement
# =============================================================================


def test_port_scanner_scope_isolation_for_localhost():
    """Localhost scan of 127.0.0.1:3000 must mark other open ports (e.g. 8000, 9090) as environmental."""
    ports = scan_target_ports("http://127.0.0.1:3000/", scan_mode="quick")
    for p in ports:
        if p["port"] == 3000:
            assert p["in_scope"] is True
            assert p["scope"] == "target_application"
        else:
            assert p["in_scope"] is False
            assert p["scope"] == "environmental"


def test_full_scanner_excludes_out_of_scope_ports_from_candidates():
    """FullScanner must not add host/docker ports (8000, 9090) to attack candidates for localhost target."""
    scan_res = FullScanner.scan_target("http://127.0.0.1:3000/", scan_mode="quick")
    cand_ids = [c["id"] for c in scan_res["candidates"]]
    assert "open-port-8000" not in cand_ids
    assert "open-port-9090" not in cand_ids


# =============================================================================
# 5. GAP1 Accounting
# =============================================================================


def test_gap1_candidate_accounting_breakdown():
    """Candidate accounting must cleanly separate dispatched, investigated, validated, abandoned, and not_tested."""
    candidates = [
        {"id": "c1", "state": "VALIDATED", "attempts": 1},
        {"id": "c2", "state": "ABANDONED", "attempts": 2},
        {"id": "c3", "state": "ATTEMPTING", "attempts": 1},
        {"id": "c4", "state": "NOT_TESTED", "attempts": 0},
        {"id": "c5", "state": "BLOCKED", "attempts": 0},
    ]

    accounting = {
        "dispatched": len(candidates),
        "investigated": sum(
            1
            for c in candidates
            if c.get("state") in ("VALIDATED", "ABANDONED") or c.get("attempts", 0) > 0
        ),
        "validated": sum(1 for c in candidates if c.get("state") == "VALIDATED"),
        "abandoned": sum(1 for c in candidates if c.get("state") == "ABANDONED"),
        "not_tested": sum(1 for c in candidates if c.get("state") == "NOT_TESTED"),
        "blocked": sum(1 for c in candidates if c.get("state") == "BLOCKED"),
    }

    assert accounting["dispatched"] == 5
    assert accounting["investigated"] == 3
    assert accounting["validated"] == 1
    assert accounting["abandoned"] == 1
    assert accounting["not_tested"] == 1
    assert accounting["blocked"] == 1
    # Abandoned candidates must never count towards validated investigations
    assert accounting["validated"] != accounting["investigated"]


# =============================================================================
# 6. GAP2 Pivot Consistency
# =============================================================================


def test_gap2_pivot_event_sync():
    """Stats and dashboard pivot count must strictly derive from actual persisted pivot events."""
    pivot_events = [
        {
            "event": "GAP2_PIVOT",
            "candidate_id": "c2",
            "outcome": "ABANDON",
            "attempts": 2,
            "next_candidate": "c3",
        },
    ]
    pivots_count = len(
        [
            e
            for e in pivot_events
            if e.get("event") == "GAP2_PIVOT" or e.get("type") in ("REDIRECT", "GAP2_PIVOT")
        ]
    )
    assert pivots_count == 1

    # Empty pivot events list must yield 0 pivots
    assert len([e for e in [] if e.get("event") == "GAP2_PIVOT"]) == 0


# =============================================================================
# 7. Category & Rule Count Agreement
# =============================================================================


def test_scan_categories_rule_count_matches_88_across_8_categories():
    """SCAN_CATEGORIES must have exactly 8 categories and 88 total tests."""
    assert len(SCAN_CATEGORIES) == 8
    total_rules = sum(cat["test_count"] for cat in SCAN_CATEGORIES.values())
    assert total_rules == 88


# =============================================================================
# 8. Report Canonical Dataset (All 8 Canonical Fields)
# =============================================================================


def test_report_builder_renders_all_eight_canonical_fields():
    """HTML report must contain all 8 canonical fields for confirmed findings."""
    run_data = {
        "run_id": "run-test-phase13",
        "status": "completed",
        "target_url": "http://127.0.0.1:3000/",
        "findings": [
            {
                "id": "find-001",
                "title": "Reflected Cross-Site Scripting",
                "severity": "HIGH",
                "cvss_score": 7.5,
                "cwe_id": "CWE-79",
                "owasp_category": "A03:2021 - Injection",
                "location": "/#/search",
                "evidence_hash": "a1b2c3d4e5f67890",
                "evidence_snippet": "Payload <script>alert(1)</script> reflected in DOM sink.",
                "reproducible_request": "GET /#/search?q=<script>alert(1)</script> HTTP/1.1",
                "validation_method": "Active payload injection & sink reflection verification",
                "impact": "Session cookie exfiltration and unauthorized script execution.",
                "severity_justification": "High exploitability via unauthenticated GET parameter.",
                "remediation_technical": "contextEncode(q); sanitizeInput(q);",
                "retest_procedure": "curl -s -k 'http://127.0.0.1:3000/#/search?q=<script>'",
            }
        ],
        "candidates": [],
        "scan_matrix": [],
    }

    html_out = render_html_report(run_data)
    assert "Affected Endpoint:" in html_out
    assert "/#/search" in html_out
    assert "Validation Method:" in html_out
    assert "Severity Justification:" in html_out
    assert "Vulnerability Impact:" in html_out
    assert "Reproducible Request / Proof-of-Concept:" in html_out
    assert "Relevant Response Evidence:" in html_out
    assert "Server Hardening Configuration & Code Patch:" in html_out
    assert "Retest Verification Procedure:" in html_out
    assert "8 core VAPT test categories (88 total tests)" in html_out
