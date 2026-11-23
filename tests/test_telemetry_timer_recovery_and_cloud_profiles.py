"""Comprehensive regression tests for AI-VAPT telemetry, wall-clock timer,
run recovery, cumulative turn tracking, verification states, and cloud hosted profiles.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from strix.interface.api import (
    _RUNS,
    _finalize_run_lifecycle,
    _sync_run_counters,
    app,
    count_findings_by_verification_state,
)


@pytest.fixture
def client():
    return TestClient(app)


# ============================================================================
# 1. Started At and Elapsed Wall-Clock Timer
# ============================================================================


def test_started_at_presence_and_utc_format(client):
    """started_at must be an authoritative UTC ISO string in run state and API."""
    run_id = "test-timer-run-001"
    start_ts = datetime.now(UTC).isoformat()
    _RUNS[run_id] = {
        "run_id": run_id,
        "status": "running",
        "start_time": start_ts,
        "started_at": start_ts,
        "scenario": "web_assessment",
        "mode": "autonomous",
        "target_url": "https://example.com",
        "provider": "openrouter",
        "model": "deepseek/deepseek-chat",
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
    }

    res = client.get(f"/runs/{run_id}")
    assert res.status_code == 200
    data = res.json()

    assert "started_at" in data
    assert data["started_at"] is not None
    assert "T" in data["started_at"]
    # Verify parseable ISO UTC datetime
    parsed = datetime.fromisoformat(data["started_at"])
    assert parsed.tzinfo is not None

    # Check elapsed_seconds is positive and calculated from wall clock
    assert "elapsed_seconds" in data
    assert data["elapsed_seconds"] >= 0.0


def test_elapsed_timer_frozen_on_completion(client):
    """When a run completes, aborts, or fails, duration and elapsed_seconds must freeze."""
    run_id = "test-timer-run-completed"
    t_start = (datetime.now(UTC) - timedelta(seconds=125)).isoformat()
    t_end = datetime.now(UTC).isoformat()

    run_entry = {
        "run_id": run_id,
        "status": "running",
        "start_time": t_start,
        "started_at": t_start,
        "scenario": "web_assessment",
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
    }
    _RUNS[run_id] = run_entry

    _finalize_run_lifecycle(run_entry, status="completed")
    assert run_entry["status"] == "completed"
    assert run_entry["duration_seconds"] is not None
    assert 120 <= run_entry["duration_seconds"] <= 130
    assert run_entry["elapsed_seconds"] == run_entry["duration_seconds"]

    res = client.get(f"/runs/{run_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert data["duration_seconds"] == run_entry["duration_seconds"]
    assert data["elapsed_seconds"] == run_entry["elapsed_seconds"]


# ============================================================================
# 2. Findings by Verification State Breakdown
# ============================================================================


def test_verification_states_all_categories_present():
    """All 9 verification state categories must be calculated without nulls."""
    sample_findings = [
        {"id": "v1", "title": "SQLi", "verification": {"verification_state": "verified"}},
        {"id": "v2", "title": "XSS", "verification": {"verification_state": "candidate"}},
        {
            "id": "v3",
            "title": "CSRF",
            "verification": {"verification_state": "under_investigation"},
        },
        {
            "id": "v4",
            "title": "SSRF",
            "verification": {"verification_state": "exploitation_attempted"},
        },
        {"id": "v5", "title": "IDOR", "verification": {"verification_state": "unconfirmed"}},
        {
            "id": "v6",
            "title": "Info Disclosure",
            "verification": {"verification_state": "false_positive"},
        },
        {"id": "v7", "title": "Rate Limit", "verification": {"verification_state": "blocked"}},
        {"id": "v8", "title": "CORS", "verification": {"verification_state": "inconclusive"}},
        {"id": "v9", "title": "RCE", "verification": {"verification_state": "discovered"}},
    ]
    counts = count_findings_by_verification_state(sample_findings)
    assert counts["discovered"] == 1
    assert counts["candidate"] == 1
    assert counts["under_investigation"] == 1
    assert counts["exploitation_attempted"] == 1
    assert counts["verified"] == 1
    assert counts["unconfirmed"] == 1
    assert counts["false_positive"] == 1
    assert counts["blocked"] == 1
    assert counts["inconclusive"] == 1


def test_sync_run_counters_populates_verification_states(client):
    """_sync_run_counters must populate verification_states and findings_summary."""
    run_id = "test-sync-counters-run"
    now_iso = datetime.now(UTC).isoformat()
    run_entry = {
        "run_id": run_id,
        "status": "running",
        "start_time": now_iso,
        "started_at": now_iso,
        "findings": [
            {
                "id": "v1",
                "title": "Confirmed SQLi",
                "verified": True,
                "verification": {"verification_state": "verified"},
            },
        ],
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
    }
    _RUNS[run_id] = run_entry
    _sync_run_counters(run_entry)

    assert "verification_states" in run_entry
    assert run_entry["verification_states"]["verified"] == 1
    assert run_entry["findings_summary"]["verified"] == 1

    res = client.get(f"/runs/{run_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["verification_states"] is not None
    assert data["verification_states"]["verified"] == 1
    assert data["findings_summary"] is not None


# ============================================================================
# 3. Active Agent and Task Telemetry
# ============================================================================


def test_active_agent_and_task_telemetry(client):
    """Active Agent and Active Task must reflect real execution state."""
    run_id = "test-agent-telemetry-run"
    now_iso = datetime.now(UTC).isoformat()
    _RUNS[run_id] = {
        "run_id": run_id,
        "status": "running",
        "start_time": now_iso,
        "started_at": now_iso,
        "active_agent": "Web Reconnaissance Specialist",
        "active_task": "Invoking tool: probe_endpoint",
        "last_progress_at": now_iso,
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
    }

    res = client.get(f"/runs/{run_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["active_agent"] == "Web Reconnaissance Specialist"
    assert data["active_task"] == "Invoking tool: probe_endpoint"
    assert data["last_progress_at"] is not None


# ============================================================================
# 4. Cumulative Turn Extraction Across Continuations
# ============================================================================


def test_cumulative_turns_tracking():
    """When Strix forces continuation, turns must not freeze at turn 73."""
    # Simulate turn log lines across two continuation phases
    simulated_lines = [
        "Starting turn 1, current_agent=Root Agent",
        "Starting turn 2, current_agent=Root Agent",
        "Starting turn 73, current_agent=Root Agent",
        "forcing tool continuation (1/500)",
        "Starting turn 1, current_agent=Root Agent",
        "Starting turn 2, current_agent=Root Agent",
        "Starting turn 56, current_agent=Root Agent",
    ]

    current_turn = 1
    turn_offset = 0
    prev_strix_turn = 0

    for line in simulated_lines:
        m = re.search(r"Starting turn\s+(\d+)", line, re.I)
        if m:
            t_val = int(m.group(1))
            if t_val < prev_strix_turn:
                turn_offset += prev_strix_turn
            prev_strix_turn = t_val
            current_turn = turn_offset + t_val

    # 73 + 56 = 129 cumulative turns
    assert current_turn == 129
    assert turn_offset == 73


# ============================================================================
# 5. Live Event Streaming and Monotonic Sequence IDs
# ============================================================================


def test_stream_run_events_monotonic_sequence(client):
    """GET /runs/{run_id}/stream must output monotonic event IDs and initial state."""
    run_id = "test-stream-run"
    now_iso = datetime.now(UTC).isoformat()
    _RUNS[run_id] = {
        "run_id": run_id,
        "status": "completed",
        "start_time": now_iso,
        "started_at": now_iso,
        "progress": {"percent": 100, "phase": "Assessment Complete", "current": 50, "total": 50},
        "decision_trace": ["Log 1", "Log 2"],
        "events": [],
        "pivot_events": [],
        "candidates": [],
        "findings": [],
    }

    with client.stream("GET", f"/runs/{run_id}/stream") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        lines = []
        for line in response.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 8:
                break

        full_stream = "\n".join(lines)
        assert "id: 1" in full_stream
        assert "event: state" in full_stream


# ============================================================================
# 6. Cloud Hosted Profiles CRUD & Activation
# ============================================================================


def test_cloud_hosted_profile_crud_and_activation(client, tmp_path):
    """Cloud Hosted profiles can be created, retrieved, activated, and deleted."""
    cfg_file = tmp_path / "cli-config.json"
    with patch("strix.interface.api.CLI_CONFIG_FILE", cfg_file):
        # 1. Create a profile
        create_payload = {
            "name": "Kaggle Dedicated GPU",
            "api_base": "https://llm-gateway.example.com/v1",
            "api_key": "test-key-12345",
            "model": "kaggle-model",
            "model_alias": "Qwen 2.5 72B Kaggle",
            "context_window": 131072,
            "max_output_tokens": 4096,
            "timeout": 300,
            "streaming": True,
            "is_active": True,
        }
        res = client.post("/providers/cloud_hosted/profiles", json=create_payload)
        assert res.status_code == 200
        saved = res.json()
        assert saved["name"] == "Kaggle Dedicated GPU"
        assert saved["has_api_key"] is True
        prof_id = saved["id"]

        # 2. List profiles
        res_list = client.get("/providers/cloud_hosted/profiles")
        assert res_list.status_code == 200
        profiles = res_list.json()
        assert len(profiles) >= 1
        assert any(p["id"] == prof_id for p in profiles)

        # 3. Activate profile
        res_act = client.post(f"/providers/cloud_hosted/profiles/{prof_id}/activate")
        assert res_act.status_code == 200
        assert res_act.json()["is_active"] is True

        # 4. Delete profile
        res_del = client.delete(f"/providers/cloud_hosted/profiles/{prof_id}")
        assert res_del.status_code == 200


# ============================================================================
# 7. Frontend DOM Element Bindings and UX Integrity
# ============================================================================


def test_frontend_dom_elements_exist_in_html():
    """All required DOM IDs for live telemetry and cloud hosted controls must exist in index.html."""
    html_path = Path("strix/interface/web/index.html")
    assert html_path.is_file()
    html = html_path.read_text(encoding="utf-8")

    required_ids = [
        # Live facts card
        "metric-started",
        "metric-elapsed",
        "metric-active-agent",
        "metric-active-task",
        # Findings verification states
        "fe-discovered",
        "fe-candidate",
        "fe-under-investigation",
        "fe-exploitation",
        "fe-verified",
        "fe-unconfirmed",
        "fe-fp",
        "fe-blocked",
        "fe-inc",
        # Cloud hosted profile controls
        "cloud-empty-state",
        "cloud-active-profile-section",
        "cloud-profile-select-main",
        "btn-cloud-new-profile-inline",
        "btn-cloud-edit-profile-inline",
        "btn-cloud-delete-profile-inline",
        "btn-open-cloud-profile-modal",
        "cloud-profile-endpoint-text",
        "cloud-profile-auth-status",
        "btn-test-cloud-profile",
        "cloud-model-search",
        "cloud-discovered-model-select",
        "cloud-manual-model-input",
    ]

    for elem_id in required_ids:
        assert f'id="{elem_id}"' in html, f"Missing DOM element id: {elem_id}"


def test_frontend_app_js_binds_and_handles_telemetry():
    """app.js must bind telemetry elements and implement timer and recovery routines."""
    js_path = Path("strix/interface/web/js/app.js")
    assert js_path.is_file()
    js = js_path.read_text(encoding="utf-8")

    assert "elements.metricStarted" in js
    assert "elements.metricElapsed" in js
    assert "elements.metricActiveAgent" in js
    assert "elements.metricActiveTask" in js
    assert "elements.feDiscovered" in js
    assert "elements.feVerified" in js
    assert "startElapsedTimer" in js
    assert "updateRunFactsAndTelemetry" in js
    assert "recoverActiveAssessmentOnLoad" in js
    assert "localStorage.getItem('activeRunId')" in js


# ============================================================================
# 8. Run Isolation and State Separation
# ============================================================================


def test_run_isolation_timer_and_telemetry(client):
    """Multiple concurrent runs must maintain strictly isolated timers and state."""
    start_a = (datetime.now(UTC) - timedelta(seconds=100)).isoformat()
    start_b = (datetime.now(UTC) - timedelta(seconds=20)).isoformat()

    _RUNS["run-iso-A"] = {
        "run_id": "run-iso-A",
        "status": "running",
        "start_time": start_a,
        "started_at": start_a,
        "active_agent": "Agent Alpha",
        "active_task": "Task Alpha",
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [{"id": "c1", "state": "PENDING"}],
        "findings": [{"id": "f1", "title": "Vuln A", "verified": True}],
    }
    _RUNS["run-iso-B"] = {
        "run_id": "run-iso-B",
        "status": "running",
        "start_time": start_b,
        "started_at": start_b,
        "active_agent": "Agent Beta",
        "active_task": "Task Beta",
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
        "candidates": [{"id": "c2", "state": "ATTEMPTING"}],
        "findings": [],
    }

    res_a = client.get("/runs/run-iso-A").json()
    res_b = client.get("/runs/run-iso-B").json()

    assert res_a["active_agent"] == "Agent Alpha"
    assert res_b["active_agent"] == "Agent Beta"
    assert res_a["elapsed_seconds"] >= 95
    assert res_b["elapsed_seconds"] <= 30
    assert len(res_a["candidates"]) == 1
    assert res_a["candidates"][0]["id"] == "c1"
    assert len(res_b["candidates"]) == 1
    assert res_b["candidates"][0]["id"] == "c2"


# ============================================================================
# 9. Assessment Resume Preserves Historical Data
# ============================================================================


def test_resume_preserves_historical_findings(client):
    """Resuming a paused or failed run preserves existing findings, candidates, and logs."""
    run_id = "test-resume-preservation"
    now_iso = datetime.now(UTC).isoformat()
    _RUNS[run_id] = {
        "run_id": run_id,
        "status": "provider_blocked",
        "start_time": now_iso,
        "started_at": now_iso,
        "provider": "openrouter",
        "model": "deepseek/deepseek-chat",
        "findings": [
            {"id": "vuln-preserved-1", "title": "Preserved Vulnerability", "verified": True}
        ],
        "candidates": [{"id": "cand-1", "state": "VALIDATED", "attempts": 1}],
        "events": [],
        "decision_trace": ["Log 1 before resume"],
        "pivot_events": [],
    }

    resume_payload = {
        "provider": "anthropic",
        "model": "claude-3-5-sonnet-20241022",
        "api_key": "sk-ant-test-key",
    }
    with patch("strix.interface.api._execute_run_worker"):
        res = client.post(f"/runs/{run_id}/resume", json=resume_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "resumed"

    updated_run = _RUNS[run_id]
    assert updated_run["status"] == "running"
    assert updated_run["provider"] == "anthropic"
    assert updated_run["model"] == "claude-3-5-sonnet-20241022"
    # Preserved data
    assert len(updated_run["findings"]) == 1
    assert updated_run["findings"][0]["id"] == "vuln-preserved-1"
    assert len(updated_run["candidates"]) == 1


# ============================================================================
# 10. Separation of GAP-1 Candidate Counts vs Confirmed Findings
# ============================================================================


def test_no_fabrication_between_candidates_and_findings(client):
    """GAP-1 candidates and confirmed findings must remain strictly distinct."""
    run_id = "test-cand-vs-findings"
    now_iso = datetime.now(UTC).isoformat()
    _RUNS[run_id] = {
        "run_id": run_id,
        "status": "running",
        "start_time": now_iso,
        "started_at": now_iso,
        "candidates": [
            {"id": "c1", "name": "Candidate 1", "state": "PENDING"},
            {"id": "c2", "name": "Candidate 2", "state": "ATTEMPTING"},
            {"id": "c3", "name": "Candidate 3", "state": "ABANDONED"},
        ],
        "findings": [],  # 0 verified findings
        "events": [],
        "decision_trace": [],
        "pivot_events": [],
    }

    res = client.get(f"/runs/{run_id}").json()
    assert len(res["candidates"]) == 3
    assert len(res["findings"]) == 0
    assert res["verification_states"]["verified"] == 0
