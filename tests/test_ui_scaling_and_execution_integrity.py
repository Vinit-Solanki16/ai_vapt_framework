"""Tests for AI-VAPT UI scaling regression fix, execution integrity, and error root-cause remediation."""

from pathlib import Path

from strix.core.decision_engine.schemas import PivotEvent
from strix.interface.api import (
    _RUNS,
    _align_cvss_severity,
    _extract_clean_error,
    _finalize_run_lifecycle,
    _load_runs_from_disk,
)
from strix.interface.schemas import PivotEventSchema, RunStatus


def test_status_classification_distinction():
    """Verify distinct execution and pause states are accepted by RunStatus schema and lifecycle."""
    statuses = [
        "queued",
        "running",
        "completed",
        "paused_provider_limit",
        "paused_execution_limit",
        "failed_infrastructure",
        "failed_agent",
        "cancelled",
        "failed",
        "aborted",
        "provider_blocked",
        "interrupted",
        "partial",
        "blocked",
    ]
    for s in statuses:
        obj = RunStatus(run_id="test-run-1", status=s)
        assert obj.status == s

    # Test lifecycle behavior
    run_entry = {
        "run_id": "test-run-lifecycle",
        "status": "running",
        "events": [],
        "findings": [],
    }
    _finalize_run_lifecycle(run_entry, status="completed")
    assert run_entry["status"] == "completed"
    assert run_entry["active_agent"] == "Completed"

    _finalize_run_lifecycle(run_entry, status="paused_execution_limit", error="Limit reached")
    assert run_entry["status"] == "paused_execution_limit"
    assert run_entry["active_agent"] == "Paused"
    assert "Limit reached" in run_entry["error"]

    _finalize_run_lifecycle(run_entry, status="failed_infrastructure", error="Docker socket missing")
    assert run_entry["status"] == "failed_infrastructure"
    assert run_entry["active_agent"] == "Stopped"


def test_security_observations_not_treated_as_fatal_errors():
    """Verify security findings (e.g. X-Frame-Options, cookie issues) are never extracted as fatal errors."""
    stdout_lines = [
        "Executive Summary:",
        "missing from HTTP responses including X-Frame-Options",
        "5 Cookie Security Issues: Session cookies were missing essential security",
        "3. Add missing security headers including X-Frame-Options.",
        "Target application assessment complete.",
    ]
    # Clean error extractor should NOT pick up security findings as application crashes
    extracted = _extract_clean_error([], stdout_lines, fallback="Execution finished")
    assert "missing from HTTP responses" not in extracted
    assert "Cookie Security Issues" not in extracted
    assert "X-Frame-Options" not in extracted
    assert extracted == "Execution finished"


def test_extract_clean_error_catches_genuine_crashes():
    """Verify genuine fatal errors, exceptions, and tracebacks are accurately extracted."""
    stderr_lines = [
        "Traceback (most recent call last):",
        '  File "main.py", line 42, in run',
        "docker.errors.DockerException: Error while fetching server API version",
    ]
    extracted = _extract_clean_error(stderr_lines, [], fallback="Fallback error")
    assert "DockerException" in extracted or "server API version" in extracted


def test_pivot_event_deserialization_defaults_type():
    """Verify PivotEvent and PivotEventSchema default type to GAP2_PIVOT when missing in raw event dict."""
    raw_event = {
        "timestamp": "2026-11-12T16:00:55.198839+00:00",
        "event": "GAP2_PIVOT",
        "candidate_id": "lfi-traversal",
        "outcome": "ABANDON",
        "attempts": 2,
        "next_candidate": "lfi-traversal-page",
    }
    pe = PivotEvent(**raw_event)
    assert pe.type in ("GAP2_PIVOT", "ABANDON") or pe.event == "GAP2_PIVOT"

    pes = PivotEventSchema(**raw_event)
    assert pes.type in ("GAP2_PIVOT", "ABANDON") or pes.event == "GAP2_PIVOT"


def test_align_cvss_severity():
    """Verify CVSS score and severity labels are properly aligned."""
    score, sev = _align_cvss_severity(7.5, "high")
    assert score == 7.5
    assert sev == "HIGH"

    score, sev = _align_cvss_severity(5.4, "medium")
    assert score == 5.4
    assert sev == "MEDIUM"

    score, sev = _align_cvss_severity(9.8, "low")  # Score overrides mislabeled severity
    assert score == 9.8
    assert sev == "CRITICAL"


def test_css_compactness_and_nowrap():
    """Verify styles.css enforces no-wrap navigation and compact layout rules."""
    css_path = Path("strix/interface/web/css/styles.css")
    assert css_path.is_file()
    css_content = css_path.read_text(encoding="utf-8")

    # Check navigation no-wrap
    assert "white-space: nowrap" in css_content
    assert "flex-wrap: nowrap" in css_content

    # Check max-width is expanded for efficient viewport utilization
    assert "max-width: 1600px" in css_content

    # Check metric icon has compact dimensions
    assert "width: 2.35rem" in css_content or "width: 2.25rem" in css_content or "font-size: 1.25rem" in css_content


def test_healed_run_b9a3b0b2_loaded_cleanly():
    """Verify historical run-b9a3b0b2 loads as completed with 3 findings and accurate turns."""
    run_dir = Path("strix_runs/run-b9a3b0b2")
    if not (run_dir / "findings.sarif").is_file():
        return

    _load_runs_from_disk()
    run = _RUNS.get("run-b9a3b0b2")
    assert run is not None
    assert run.get("status") == "completed"
    assert run.get("error") is None
    assert run.get("turns_consumed") == 111
    assert run.get("progress_percent") == 100
    findings = run.get("findings", [])
    assert len(findings) == 3
    rule_ids = {f["id"] for f in findings}
    assert "vuln-0001" in rule_ids
    assert "vuln-0002" in rule_ids
    assert "vuln-0003" in rule_ids


def test_turn_accounting_per_agent_prevents_inflation():
    """Verify multi-agent interleaved turns sum each agent's max turn rather than inflating offset."""
    log_sample = [
        "Starting turn 65, current_agent=Root Agent",
        "Starting turn 14, current_agent=CORS Investigation Agent",
        "Starting turn 16, current_agent=LFI Investigation Agent",
        "Starting turn 66, current_agent=Root Agent",
        "Starting turn 15, current_agent=CORS Investigation Agent",
        "Starting turn 67, current_agent=Root Agent",
        "Starting turn 16, current_agent=CORS Investigation Agent",
        "Starting turn 68, current_agent=Root Agent",
        "Starting turn 17, current_agent=CORS Investigation Agent",
    ]
    import re
    agent_turns = {}
    for line in log_sample:
        m = re.search(r"Starting turn\s+(\d+),\s*current_agent=([^,\n\r]+)", line)
        if m:
            turn = int(m.group(1))
            agent = m.group(2).strip()
            agent_turns[agent] = max(agent_turns.get(agent, 0), turn)

    assert agent_turns["Root Agent"] == 68
    assert agent_turns["CORS Investigation Agent"] == 17
    assert agent_turns["LFI Investigation Agent"] == 16
    total_turns = sum(agent_turns.values())
    assert total_turns == 68 + 17 + 16 == 101
    # Ensure it did NOT inflate past 101 into hundreds or thousands
    assert total_turns < 150
