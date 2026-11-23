"""Regression tests for the real autonomous-assessment stall investigated on run-fd0f5ec4.

The dashboard showed a run stuck at 19/500 turns with 7 GAP-2 "SUCCESS" events
and zero confirmed findings. Evidence in strix_runs/run-fd0f5ec4 showed:

* the web worker and the CLI subprocess share the same run.json path, so their
  records overwrite each other (worker said 1 turn, subprocess log had 19);
* ``record_coverage(outcome='reported')`` was mapped to a GAP-2 positive,
  emitting GAP2_SUCCESS with an empty report_id while vulnerabilities.json
  stayed empty;
* a persisted ``status='running'`` with no live process stayed "running"
  forever after restart, and could be re-launched as a resume.

These tests pin the corrected behaviour. They use no mocked findings or
model responses: they exercise the real functions on temporary run directories.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from strix.core import gap_bridge
from strix.interface import api


@pytest.fixture(autouse=True)
def _clean_bridge(monkeypatch):
    gap_bridge.reset_state()
    for name in (
        gap_bridge.CONTROL_DIR_ENV,
        gap_bridge.QUEUE_ENV,
        gap_bridge.THRESHOLD_ENV,
        gap_bridge.GAP2_ENABLED_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    yield
    gap_bridge.reset_state()


def test_record_coverage_reported_is_not_a_confirmed_positive(tmp_path: Path):
    """A coverage record is an observation, never a confirmed vulnerability.

    GAP-2 success requires a vulnerability report id backed by a real finding.
    'reported' simply means the agent visited/labelled a surface.
    """
    from strix.tools.coverage.tools import _record_impl

    control = tmp_path / "control"
    control.mkdir()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(control))
    monkeypatch.setenv(gap_bridge.GAP2_ENABLED_ENV, "1")
    try:
        result = _record_impl(
            surface="/robots.txt",
            risk_area="robots-txt-exposure",
            outcome="reported",
            evidence="/robots.txt returned 200 with Disallow: /ftp",
            agent_id=None,
            agent_name=None,
        )
        assert result.get("success") is True
        gap2 = result.get("gap2") or {}
        # The candidate was seen, but nothing was proven.
        assert gap2.get("status") != "positive", gap2
        assert gap2.get("status") in ("observed", "inconclusive"), gap2

        trace = control / gap_bridge.TRACE_FILENAME
        events = (
            [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
        )
        assert not any(e.get("event") == "GAP2_SUCCESS" for e in events), events
    finally:
        monkeypatch.undo()


def test_gap2_positive_requires_a_real_report_id(tmp_path: Path):
    """Direct GAP-2 recording refuses 'success' with no report id."""
    control = tmp_path / "control"
    control.mkdir()
    import os

    os.environ[gap_bridge.CONTROL_DIR_ENV] = str(control)
    os.environ[gap_bridge.GAP2_ENABLED_ENV] = "1"
    result = gap_bridge.record_outcome(
        title="SQL injection in login",
        endpoint="/rest/user/login",
        target="http://127.0.0.1:3000/",
        success=True,
        report_id="",
        detail="Agent said the endpoint looks injectable",
    )
    assert result["status"] != "positive", result
    trace = control / gap_bridge.TRACE_FILENAME
    events = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
    assert not any(e.get("event") == "GAP2_SUCCESS" for e in events), events


def test_stale_running_run_without_live_process_is_marked_interrupted(tmp_path: Path, monkeypatch):
    """A persisted 'running' record with no worker/process is not truly running."""
    run_id = "run-stale-test"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    stale = {
        "run_id": run_id,
        "status": "running",
        "start_time": "2026-11-17T11:53:05.170786+00:00",
        "created_at": "2026-11-17T11:53:05.170786+00:00",
        "target_url": "http://127.0.0.1:3000/",
        "execution_mode": "autonomous_multi_agent",
    }
    (run_dir / "run.json").write_text(json.dumps(stale), encoding="utf-8")
    monkeypatch.setattr(api, "runs_base_dir", lambda: tmp_path)
    api._RUNS.clear()

    api._load_runs_from_disk()
    loaded = api._RUNS.get(run_id)
    assert loaded is not None
    assert loaded["status"] != "running", loaded
    assert loaded.get("end_time"), "stale run must have a terminal timestamp"
    assert loaded.get("error"), "stale run must explain why it is not running"


def test_no_progress_detector_distinguishes_real_work_from_bookkeeping():
    """Bookkeeping calls are not progress; real tool calls keep the scan alive."""
    assert api._is_productive_tool("record_coverage") is False
    assert api._is_productive_tool("finish_scan") is False
    assert api._is_productive_tool("http_request") is True
    assert api._is_productive_tool("terminal") is True

    # 19 turns of coverage-only work still count as no progress.
    assert (
        api.should_stop_for_no_progress(
            elapsed_seconds=700,
            last_progress_seconds=700,
            productively_advanced_turns=0,
            max_turns=500,
        )
        is True
    )
    # A scan making real tool calls is not stalled.
    assert (
        api.should_stop_for_no_progress(
            elapsed_seconds=700,
            last_progress_seconds=700,
            productively_advanced_turns=3,
            max_turns=500,
        )
        is False
    )
    # Early in a run, no stall is declared.
    assert (
        api.should_stop_for_no_progress(
            elapsed_seconds=60,
            last_progress_seconds=60,
            productively_advanced_turns=0,
            max_turns=500,
        )
        is False
    )


def test_web_worker_and_cli_subprocess_use_separate_run_json(tmp_path: Path, monkeypatch):
    """The control-plane record must not be overwritten by the worker engine."""
    from strix.core.paths import run_dir_for

    web_run_id = "run-control-plane"
    engine_name = api._engine_run_name(web_run_id)
    assert engine_name != web_run_id
    monkeypatch.setattr(api, "PROJECT_ROOT", tmp_path)
    assert run_dir_for(engine_name).name == engine_name
    assert run_dir_for(engine_name) != run_dir_for(web_run_id)
