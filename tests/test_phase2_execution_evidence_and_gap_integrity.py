"""Phase 2 Automated Regression Tests — Execution Lifecycle, Evidence Integrity & GAP Consistency.

Covers all 20 verification criteria:
1. Strix exit code 0 (clean, no findings).
2. Strix exit code 2 (clean completion with findings).
3. Strix exit code 1 (genuine execution failure).
4. Startup recovery of completed runs without falsifying failed runs.
5. Startup recovery preserving failed runs (failed_agent, failed_infrastructure, paused_execution_limit).
6. Resume compatibility with legacy GAP2 events ({"event": "GAP2_PIVOT"}).
7. Resume compatibility with canonical GAP2 events ({"type": "GAP2_PIVOT"}).
8. Resume preserving GAP1 candidates, GAP2 state, and findings.
9. Authentic evidence byte hashing via SHA-256 (record_authentic_evidence).
10. Detection of modified or corrupted evidence artifacts (verify_evidence_integrity).
11. XSS reflected input without DOM execution classified as UNCONFIRMED.
12. LFI PHP include warning without file extraction classified as UNCONFIRMED.
13. PHPInfo configuration disclosure with authentic tables classified as VERIFIED.
14. GAP1 counters derived directly from candidate records.
15. GAP2 pivot counts derived from actual executed pivot events.
16. Segmented duration accounting (active vs wall-clock) across pauses and resumes.
17. Multi-agent turn accounting without ping-pong inflation.
18. Presentation consistency across Dashboard, JSON, HTML, and PDF.
19. State persistence across simulated browser refresh.
20. Read-only idempotency of _load_runs_from_disk across application restarts.
"""

from __future__ import annotations

import hashlib
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from strix.core.decision_engine.schemas import PivotEvent
from strix.interface.api import (
    _RUNS,
    _finalize_run_lifecycle,
    _load_runs_from_disk,
    _sync_run_counters,
    app,
)
from strix.interface.schemas import PivotEventSchema
from strix.interface.viewer.report_pdf import _duration
from strix.report.builder import render_html_report
from strix.report.evidence import (
    is_legacy_synthetic_hash,
    record_authentic_evidence,
    verify_evidence_integrity,
)
from strix.report.verification import (
    VerificationState,
    evaluate_finding_verification,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def temp_run_dir(tmp_path):
    run_dir = tmp_path / f"test-run-{uuid.uuid4().hex[:6]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


# ===========================================================================
# 1. Strix exit code 0 (clean, no findings)
# ===========================================================================
def test_criterion_1_exit_code_0_clean_no_findings():
    run_data = {
        "run_id": "run-exit-0",
        "status": "running",
        "findings": [],
        "events": [],
    }
    _finalize_run_lifecycle(run_data, status="completed")
    assert run_data["status"] == "completed"
    assert run_data.get("active_agent") == "Completed"
    assert run_data["events"][-1]["event"] == "RUN_COMPLETED"


# ===========================================================================
# 2. Strix exit code 2 (clean completion with findings)
# ===========================================================================
def test_criterion_2_exit_code_2_completed_with_findings():
    run_data = {
        "run_id": "run-exit-2",
        "status": "running",
        "findings": [{"id": "vuln-1", "title": "PHPInfo", "verification_state": "verified"}],
        "events": [],
    }
    _finalize_run_lifecycle(run_data, status="completed_with_findings")
    assert run_data["status"] == "completed_with_findings"
    assert run_data.get("active_agent") == "Completed"
    assert run_data["events"][-1]["event"] == "RUN_COMPLETED_WITH_FINDINGS"


# ===========================================================================
# 3. Genuine execution failure (exit code 1)
# ===========================================================================
def test_criterion_3_exit_code_1_fatal_error():
    run_data = {
        "run_id": "run-exit-1",
        "status": "running",
        "events": [],
    }
    err_msg = "Scanner encountered a fatal execution error (exit code 1)"
    _finalize_run_lifecycle(run_data, status="failed_agent", error=err_msg)
    assert run_data["status"] == "failed_agent"
    assert run_data["error"] == err_msg
    assert run_data["active_agent"] == "Stopped"
    assert run_data["events"][-1]["event"] == "RUN_FAILED_AGENT"


# ===========================================================================
# 4 & 5. Startup recovery logic without falsifying failed runs
# ===========================================================================
def test_criterion_4_and_5_startup_recovery(tmp_path, monkeypatch):
    base = tmp_path / "strix_runs"
    base.mkdir()
    monkeypatch.setattr("strix.interface.api.runs_base_dir", lambda: base)

    # Run A: completed run with RUN_COMPLETED event
    run_a = base / "run-completed-ok"
    run_a.mkdir()
    (run_a / "run.json").write_text(
        json.dumps({
            "run_id": "run-completed-ok",
            "status": "completed",
            "events": [{"event": "RUN_COMPLETED"}],
        }),
        encoding="utf-8",
    )

    # Run B: failed run with report file present (must NOT be promoted to completed)
    run_b = base / "run-failed-with-report"
    run_b.mkdir()
    (run_b / "penetration_test_report.md").write_text("# Report", encoding="utf-8")
    (run_b / "run.json").write_text(
        json.dumps({
            "run_id": "run-failed-with-report",
            "status": "failed_agent",
            "exit_code": 1,
            "error": "Syntax error in target prompt",
            "events": [{"event": "RUN_FAILED_AGENT"}],
        }),
        encoding="utf-8",
    )

    # Run C: paused execution limit (must preserve paused status)
    run_c = base / "run-paused-limit"
    run_c.mkdir()
    (run_c / "run.json").write_text(
        json.dumps({
            "run_id": "run-paused-limit",
            "status": "paused_execution_limit",
            "events": [{"event": "RUN_PAUSED_EXECUTION_LIMIT"}],
        }),
        encoding="utf-8",
    )

    _load_runs_from_disk()

    assert _RUNS["run-completed-ok"]["status"] == "completed"
    assert _RUNS["run-failed-with-report"]["status"] == "failed_agent"
    assert _RUNS["run-paused-limit"]["status"] == "paused_execution_limit"


# ===========================================================================
# 6 & 7. Resume compatibility with legacy and canonical GAP2 events
# ===========================================================================
def test_criterion_6_and_7_legacy_and_canonical_gap2_events():
    # Legacy schema with event: GAP2_PIVOT
    legacy_raw = {
        "event": "GAP2_PIVOT",
        "candidate_id": "cand-1",
        "next_candidate": "cand-2",
        "reason": "Threshold reached",
    }
    p1 = PivotEvent(**legacy_raw)
    assert p1.type == "GAP2_PIVOT"
    assert p1.candidate_id == "cand-1"
    assert p1.to_candidate == "cand-2"

    p1_schema = PivotEventSchema(**legacy_raw)
    assert p1_schema.type == "GAP2_PIVOT"
    assert p1_schema.next_candidate == "cand-2"

    # Canonical schema with type: GAP2_PIVOT
    canonical_raw = {
        "type": "GAP2_PIVOT",
        "candidate_id": "cand-2",
        "to_candidate": "cand-3",
        "reason": "Adaptive redirect",
    }
    p2 = PivotEvent(**canonical_raw)
    assert p2.type == "GAP2_PIVOT"
    assert p2.to_candidate == "cand-3"

    p2_schema = PivotEventSchema(**canonical_raw)
    assert p2_schema.type == "GAP2_PIVOT"
    assert p2_schema.to_candidate == "cand-3"


# ===========================================================================
# 8. Resume preserving candidates, GAP2 state, and findings
# ===========================================================================
@pytest.mark.asyncio
async def test_criterion_8_resume_preserves_state(client):
    run_id = f"test-resume-{uuid.uuid4().hex[:6]}"
    _RUNS[run_id] = {
        "run_id": run_id,
        "status": "paused_provider_limit",
        "provider": "openrouter",
        "model": "auto",
        "candidates": [{"id": "c1", "name": "Candidate 1", "state": "VALIDATED", "attempts": 1}],
        "pivot_events": [{"type": "GAP2_PIVOT", "candidate_id": "c1", "to_candidate": "c2"}],
        "findings": [{"id": "v1", "title": "PHPInfo", "verification_state": "verified"}],
        "events": [],
        "execution_segments": [{"started_at": "2026-11-12T10:00:00+00:00", "ended_at": "2026-11-12T10:30:00+00:00", "duration_seconds": 1800.0}],
    }

    res = client.post(f"/runs/{run_id}/resume", json={"model": "deepseek/deepseek-chat"})
    assert res.status_code == 200
    updated = _RUNS[run_id]
    assert updated["model"] == "deepseek/deepseek-chat"
    assert len(updated["candidates"]) == 1
    assert updated["candidates"][0]["state"] == "VALIDATED"
    assert len(updated["findings"]) == 1
    assert len(updated["pivot_events"]) == 1
    assert any(e.get("event") == "RUN_RESUMED" for e in updated["events"])


# ===========================================================================
# 9 & 10. Authentic evidence byte hashing & tampering detection
# ===========================================================================
def test_criterion_9_and_10_evidence_hashing_and_tampering(temp_run_dir):
    finding_id = "vuln-auth-test"
    req_bytes = "GET /index.php?page=test HTTP/1.1\r\nHost: target\r\n\r\n"
    resp_bytes = "<html><body>Target Response Content</body></html>"

    # Record genuine evidence
    ev_meta = record_authentic_evidence(
        run_dir=temp_run_dir,
        finding_id=finding_id,
        request_data=req_bytes,
        response_data=resp_bytes,
        title="Test Vuln",
    )
    expected_hash = hashlib.sha256(resp_bytes.encode("utf-8")).hexdigest()
    assert ev_meta["evidence_hash"] == expected_hash
    assert ev_meta["evidence_hash_type"] == "authentic_sha256"
    assert ev_meta["evidence_intact"] is True

    # Verify integrity (intact)
    finding_record = {
        "id": finding_id,
        "title": "Test Vuln",
        "evidence_hash": expected_hash,
        "evidence_file": ev_meta["evidence_file"],
    }
    v_res = verify_evidence_integrity(temp_run_dir, finding_record)
    assert v_res["status"] == "intact"
    assert v_res["evidence_intact"] is True

    # Tamper with evidence artifact on disk
    ev_file = temp_run_dir / ev_meta["evidence_file"]
    ev_file.write_text("TAMPERED CONTENT", encoding="utf-8")

    # Verify tampering is detected
    v_tampered = verify_evidence_integrity(temp_run_dir, finding_record)
    assert v_tampered["status"] == "modified"
    assert v_tampered["evidence_intact"] is False

    # Verify legacy synthetic hash detection
    legacy_hash = hashlib.sha256(f"{finding_id}:Test Vuln".encode()).hexdigest()
    assert is_legacy_synthetic_hash(finding_id, "Test Vuln", legacy_hash) is True
    legacy_finding = {
        "id": finding_id,
        "title": "Test Vuln",
        "evidence_hash": legacy_hash,
    }
    v_legacy = verify_evidence_integrity(temp_run_dir, legacy_finding)
    assert v_legacy["status"] == "legacy_synthetic"
    assert v_legacy["evidence_intact"] is False


# ===========================================================================
# 11, 12, 13. Finding verification state enforcement (XSS, LFI, PHPInfo)
# ===========================================================================
def test_criterion_11_xss_reflection_unconfirmed():
    finding = {
        "id": "vuln-xss",
        "title": "Reflected Cross-Site Scripting (name)",
        "reproducible_request": "GET /vulnerabilities/xss_r/?name=%3Cscript%3Ealert(1)%3C/script%3E HTTP/1.1",
        "reproducible_response": "Hello <script>alert(1)</script>",
        "verification_procedure": "curl -s 'http://pentest-ground.com:4280/vulnerabilities/xss_r/?name=%3Cscript%3Ealert(1)%3C/script%3E'",
        "demonstrated_impact": "Script tag reflected in response",
    }
    state, reason, verified = evaluate_finding_verification(finding)
    assert state == VerificationState.UNCONFIRMED.value
    assert verified is False
    assert "client-side script execution was not verified" in reason


def test_criterion_12_lfi_warning_unconfirmed():
    finding = {
        "id": "vuln-lfi",
        "title": "Path Traversal / Local File Inclusion (page)",
        "reproducible_request": "GET /vulnerabilities/fi/?page=../../../../etc/passwd HTTP/1.1",
        "reproducible_response": "Warning: include(../../../../etc/passwd): Failed to open stream: No such file or directory in /var/www/html/vulnerabilities/fi/index.php on line 36",
        "verification_procedure": "curl -s 'http://pentest-ground.com:4280/vulnerabilities/fi/?page=../../../../etc/passwd'",
        "demonstrated_impact": "PHP include warning displayed",
    }
    state, reason, verified = evaluate_finding_verification(finding)
    assert state == VerificationState.UNCONFIRMED.value
    assert verified is False
    assert "arbitrary file content extraction was not demonstrated" in reason


def test_criterion_13_phpinfo_disclosure_verified():
    finding = {
        "id": "vuln-phpinfo",
        "title": "PHPInfo Diagnostic Configuration Disclosure",
        "reproducible_request": "GET /phpinfo.php HTTP/1.1",
        "reproducible_response": '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"><html><head><title>phpinfo()</title></head><body><h1>PHP Version 7.4.3</h1><table><tr><td>System Linux</td></tr></table></body></html>',
        "verification_procedure": "curl -s 'http://pentest-ground.com:4280/phpinfo.php'",
        "demonstrated_impact": "Direct unauthenticated access exposes PHP configuration tables",
    }
    state, reason, verified = evaluate_finding_verification(finding)
    assert state == VerificationState.VERIFIED.value
    assert verified is True
    assert "configuration and environment diagnostic tables" in reason


# ===========================================================================
# 14 & 15. GAP1 and GAP2 counter accounting
# ===========================================================================
def test_criterion_14_and_15_gap1_and_gap2_counter_derivation():
    run_entry = {
        "run_id": "test-gap-counts",
        "candidates": [
            {"id": "c1", "state": "VALIDATED", "attempts": 1},
            {"id": "c2", "state": "ABANDONED", "attempts": 3},
            {"id": "c3", "state": "ATTEMPTING", "attempts": 1},
            {"id": "c4", "state": "PENDING", "attempts": 0},
        ],
        "pivot_events": [
            {"type": "GAP2_PIVOT", "candidate_id": "c2", "to_candidate": "c3", "pivot_executed": True},
            {"type": "GAP2_PIVOT", "candidate_id": "c3", "to_candidate": "c4", "pivot_executed": False},  # not executed
            {"event": "GAP2_PIVOT", "candidate_id": "c1", "next_candidate": "c2"},  # executed legacy
        ],
        "findings": [],
        "progress": {},
        "stats": {},
    }

    _sync_run_counters(run_entry)

    # GAP1: 4 identified, 3 investigated (c1 validated, c2 abandoned, c3 attempting)
    assert run_entry["gap1_candidates_identified"] == 4
    assert run_entry["gap1_candidates_under_investigation"] == 3
    assert run_entry["progress"]["gap1"]["identified"] == 4
    assert run_entry["progress"]["gap1"]["investigated"] == 3

    # GAP2: exactly 2 executed pivots (1 true, 1 legacy, 1 skipped)
    assert run_entry["gap2_pivots"] == 2
    assert run_entry["pivots"] == 2
    assert run_entry["progress"]["gap2"]["pivots"] == 2
    assert run_entry["stats"]["pivots"] == 2


# ===========================================================================
# 16. Segmented duration accounting (active vs wall-clock)
# ===========================================================================
def test_criterion_16_segmented_duration_accounting():
    start_time = "2026-11-12T10:00:00+00:00"
    pause_time = "2026-11-12T10:30:00+00:00"
    resume_time = "2026-11-12T12:00:00+00:00"  # 1.5 hr pause
    end_time = "2026-11-12T12:25:00+00:00"

    run_entry = {
        "run_id": "test-segmented-dur",
        "start_time": start_time,
        "started_at": start_time,
        "_current_segment_start": resume_time,
        "execution_segments": [
            {
                "started_at": start_time,
                "ended_at": pause_time,
                "duration_seconds": 1800.0,  # 30 mins active
            }
        ],
        "findings": [],
        "events": [],
    }

    # Finalize segment 2 (25 mins active)
    # Mock _utc_now to end_time
    import strix.interface.api as api_mod
    orig_utc_now = api_mod._utc_now
    api_mod._utc_now = lambda: end_time
    try:
        _finalize_run_lifecycle(run_entry, status="completed")
    finally:
        api_mod._utc_now = orig_utc_now

    assert len(run_entry["execution_segments"]) == 2
    assert run_entry["execution_segments"][1]["duration_seconds"] == 1500.0  # 25 mins
    # Active duration is 30m + 25m = 55m = 3300s
    assert run_entry["active_duration_seconds"] == 3300.0
    assert run_entry["duration_seconds"] == 3300.0
    # Wall clock duration is 10:00 to 12:25 = 2h 25m = 8700s
    assert run_entry["wall_clock_duration_seconds"] == 8700.0


# ===========================================================================
# 17. Multi-agent turn accounting
# ===========================================================================
def test_criterion_17_multi_agent_turn_accounting(tmp_path, monkeypatch):
    base = tmp_path / "strix_runs"
    base.mkdir()
    monkeypatch.setattr("strix.interface.api.runs_base_dir", lambda: base)

    run_dir = base / "run-turn-test"
    run_dir.mkdir()
    log_content = (
        "Starting turn 1, current_agent=Root Agent\n"
        "Starting turn 2, current_agent=Root Agent\n"
        "Starting turn 1, current_agent=Subagent Recon\n"
        "Starting turn 2, current_agent=Subagent Recon\n"
        "Starting turn 3, current_agent=Subagent Recon\n"
    )
    (run_dir / "strix.log").write_text(log_content, encoding="utf-8")
    (run_dir / "run.json").write_text(
        json.dumps({
            "run_id": "run-turn-test",
            "status": "completed",
            "max_turns": 100,
            "turns_consumed": 999,  # Inflated by ping-pong
        }),
        encoding="utf-8",
    )

    _load_runs_from_disk()
    # True turns: max(Root Agent) = 2, max(Subagent Recon) = 3 -> sum = 5
    assert _RUNS["run-turn-test"]["turns_consumed"] == 5


# ===========================================================================
# 18. Dashboard, JSON, HTML, PDF count and format consistency
# ===========================================================================
def test_criterion_18_presentation_consistency():
    run_entry = {
        "run_id": "run-pres-cons",
        "target_url": "https://pentest-ground.com:4280/",
        "status": "completed",
        "active_duration_seconds": 3309.0,
        "duration_seconds": 3309.0,
        "start_time": "2026-11-12T15:23:31+00:00",
        "end_time": "2026-11-12T16:18:40+00:00",
        "candidates": [
            {"id": "c1", "name": "Candidate 1", "state": "VALIDATED", "attempts": 1},
            {"id": "c2", "name": "Candidate 2", "state": "NOT_TESTED", "attempts": 0},
        ],
        "pivot_events": [
            {"type": "GAP2_PIVOT", "candidate_id": "c1", "to_candidate": "c2", "pivot_executed": True}
        ],
        "findings": [
            {
                "id": "vuln-0001",
                "title": "PHPInfo Diagnostic Disclosure",
                "severity": "LOW",
                "cvss_score": 5.3,
                "verification_state": "verified",
                "verified": True,
                "evidence_hash": "a" * 64,
                "reproducible_request": "GET /phpinfo.php HTTP/1.1",
                "reproducible_response": "PHP Version 7.4",
            }
        ],
        "events": [],
    }
    _sync_run_counters(run_entry)

    # 1. Synchronized state
    assert run_entry["gap1_candidates_identified"] == 2
    assert run_entry["gap2_pivots"] == 1
    assert run_entry["findings_verified"] == 1

    # 2. HTML report rendering
    html_out = render_html_report(run_entry)
    assert "PHPInfo Diagnostic Disclosure" in html_out
    assert "00:55:09" in html_out  # 3309s formatted as HH:MM:SS

    # 3. PDF duration formatting
    pdf_dur = _duration(run_entry["start_time"], run_entry["end_time"], run_entry["active_duration_seconds"])
    assert pdf_dur == "55m 9s"


# ===========================================================================
# 19. State persistence across simulated browser refresh
# ===========================================================================
def test_criterion_19_browser_refresh_persistence(client):
    run_id = f"test-refresh-{uuid.uuid4().hex[:6]}"
    _RUNS[run_id] = {
        "run_id": run_id,
        "target_url": "https://pentest-ground.com:4280/",
        "status": "completed",
        "active_duration_seconds": 3309.0,
        "duration_seconds": 3309.0,
        "gap1_candidates_identified": 20,
        "gap2_pivots": 5,
        "findings": [{"id": "v1", "title": "PHPInfo", "verification_state": "verified"}],
        "events": [],
    }

    # Simulate 3 consecutive GET requests (like browser refresh)
    for _ in range(3):
        res = client.get(f"/runs/{run_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "completed"
        assert body["duration_seconds"] == 3309.0
        assert body["gap1_candidates_identified"] == 20
        assert body["gap2_pivots"] == 5


# ===========================================================================
# 20. Read-only idempotency of _load_runs_from_disk across app restarts
# ===========================================================================
def test_criterion_20_load_runs_idempotent_no_disk_mutation(tmp_path, monkeypatch):
    base = tmp_path / "strix_runs"
    base.mkdir()
    monkeypatch.setattr("strix.interface.api.runs_base_dir", lambda: base)

    run_dir = base / "run-idempotency-test"
    run_dir.mkdir()
    run_json = run_dir / "run.json"
    initial_content = json.dumps({
        "run_id": "run-idempotency-test",
        "status": "completed",
        "events": [{"event": "RUN_COMPLETED"}],
    }, indent=2)
    run_json.write_text(initial_content, encoding="utf-8")
    initial_mtime = run_json.stat().st_mtime_ns

    # Call _load_runs_from_disk multiple times (simulating server restarts)
    _load_runs_from_disk()
    _load_runs_from_disk()
    _load_runs_from_disk()

    # Verify run.json was NOT mutated on disk
    assert run_json.read_text(encoding="utf-8") == initial_content
    assert run_json.stat().st_mtime_ns == initial_mtime
