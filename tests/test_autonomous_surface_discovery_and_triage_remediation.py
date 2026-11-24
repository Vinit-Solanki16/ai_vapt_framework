"""Regression and integrity test suite for autonomous surface discovery,
GAP-1 candidate triage, active parameter fuzzing, and status synchronization.
"""

from __future__ import annotations

import json
import socket
import urllib.parse
from pathlib import Path

import pytest

from strix.core.scanner.active_fuzzer import ActiveFuzzer
from strix.core.scanner.crawler import WebSpider
from strix.core.triage.exploit_assessor import run_gap1_triage
from strix.interface.schemas import RunStatus
from strix.report.reconciliation import reconcile_all


def _is_target_live(url: str = "http://127.0.0.1:3000") -> bool:
    """Check if the authorized target is actively accepting connections."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def test_web_spider_discovers_spa_routes_and_disallowed_paths():
    """Verify WebSpider discovers API routes from script bundles and robots.txt."""
    if not _is_target_live("http://127.0.0.1:3000"):
        pytest.skip(
            "Authorized local target http://127.0.0.1:3000 is not reachable (live lab offline)"
        )

    spider = WebSpider("http://127.0.0.1:3000", scan_mode="quick")
    res = spider.crawl()

    assert res["visited_count"] >= 1
    discovered = set(res["discovered_paths"])
    api_endpoints = set(res["api_endpoints"])

    # Disallowed sensitive path from robots.txt
    assert "/ftp" in discovered

    # Discovered routes and API endpoints from main.js
    assert "/rest/user/login" in discovered or "/rest/user/login" in api_endpoints
    assert "/rest/products/search" in discovered or any("search" in ep for ep in api_endpoints)

    # Discovered query parameters
    assert "/rest/products/search" in res["parameters"] or "/" in res["parameters"]
    assert len(res["forms"]) >= 1


def test_active_fuzzer_discovers_sensitive_ftp_and_sqli():
    """Verify ActiveFuzzer discovers /ftp directory listing and SQL injection."""
    if not _is_target_live("http://127.0.0.1:3000"):
        pytest.skip(
            "Authorized local target http://127.0.0.1:3000 is not reachable (live lab offline)"
        )

    fuzzer = ActiveFuzzer("http://127.0.0.1:3000", scan_mode="quick")
    path_findings = fuzzer.probe_paths()

    # /ftp directory listing
    ftp_finding = next(
        (f for f in path_findings if f["endpoint"] == "/ftp" or "ftp" in f["id"]), None
    )
    assert ftp_finding is not None
    assert ftp_finding["category"] == "info_disclosure"
    assert ftp_finding["severity"] == "high"

    # Fuzzing on search endpoint
    params = {"/rest/products/search": ["q"]}
    forms = [
        {
            "action": "/rest/user/login",
            "method": "POST",
            "fields": [
                {"name": "email", "type": "email"},
                {"name": "password", "type": "password"},
            ],
        }
    ]
    fuzz_findings = fuzzer.fuzz_parameters(params, forms)

    fuzz_ids = [f["id"] for f in fuzz_findings]
    assert any("sqli" in fid for fid in fuzz_ids)
    assert "sqli-login-bypass" in fuzz_ids or "sqli-error-q" in fuzz_ids


def test_run_gap1_triage_produces_full_attack_surface():
    """Verify run_gap1_triage produces realistic, prioritized candidate queue."""
    if not _is_target_live("http://127.0.0.1:3000"):
        pytest.skip(
            "Authorized local target http://127.0.0.1:3000 is not reachable (live lab offline)"
        )

    candidates = run_gap1_triage(
        target_url="http://127.0.0.1:3000",
        scan_mode="quick",
    )

    c_ids = [c["id"] if isinstance(c, dict) else c.id for c in candidates]
    c_endpoints = [c["endpoint"] if isinstance(c, dict) else c.endpoint for c in candidates]

    # Verify key attack vectors are present
    assert any("sqli" in cid for cid in c_ids)
    assert any("ftp" in cid for cid in c_ids)
    assert any("basket" in cid for cid in c_ids)
    assert any("user" in cid for cid in c_ids)
    assert any("mainjs" in cid for cid in c_ids)

    # Verify score ranking: SQLi login should have higher score than passive header checks
    sqli_cands = [c for c in candidates if "sqli" in (c["id"] if isinstance(c, dict) else c.id)]
    header_cands = [c for c in candidates if "header" in (c["id"] if isinstance(c, dict) else c.id)]

    if sqli_cands and header_cands:
        sqli_score = (
            sqli_cands[0]["composite_score"]
            if isinstance(sqli_cands[0], dict)
            else sqli_cands[0].composite_score
        )
        header_score = (
            header_cands[0]["composite_score"]
            if isinstance(header_cands[0], dict)
            else header_cands[0].composite_score
        )
        assert sqli_score > header_score


def test_run_status_schema_supports_stopped_and_dict_traces():
    """Verify RunStatus validates stopped status and structured decision traces."""
    run_payload = {
        "run_id": "test-run-stopped-1",
        "status": "stopped",
        "decision_trace": [
            "Initializing scan...",
            {"type": "candidate_added", "candidate_id": "sqli-login", "score": 0.99},
            {"type": "GAP2_PIVOT", "from": "c1", "to": "c2"},
        ],
        "candidates": [],
        "findings": [],
    }

    # Should validate without throwing ValidationError
    status_obj = RunStatus(**run_payload)
    assert status_obj.status == "stopped"
    assert len(status_obj.decision_trace) == 3
    assert isinstance(status_obj.decision_trace[1], dict)


def test_run_fd0f5ec4_reconciliation_validates_cleanly():
    """Verify run-fd0f5ec4 deserializes cleanly via RunStatus without HTTP 500."""
    fixture_file = Path(__file__).resolve().parent / "fixtures" / "run-fd0f5ec4" / "run.json"
    run_file = fixture_file if fixture_file.is_file() else Path("strix_runs/run-fd0f5ec4/run.json")
    if run_file.is_file():
        run_data = json.loads(run_file.read_text(encoding="utf-8"))
        reconciled = reconcile_all(run_data, run_dir=run_file.parent)
        status_obj = RunStatus(**reconciled)
        assert status_obj.run_id == "run-fd0f5ec4"
        assert status_obj.status == "stopped"
