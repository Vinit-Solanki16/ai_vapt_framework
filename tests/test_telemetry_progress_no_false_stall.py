"""Regression: real SDK tool telemetry must prevent a false no-progress stall.

A genuine run on the cloud-hosted endpoint emitted 19 real ``exec_command``
calls, but the SDK logged them only as ``Processing output item
type=function_call`` (never ``Invoking tool``). The worker's stall detector
therefore saw zero productive turns and terminated a healthy scan at 600s.
The engine's ``tool_calls`` telemetry is authoritative for these runs.
"""

from __future__ import annotations

from strix.interface import api


def test_productive_tool_count_uses_telemetry_when_log_lines_absent() -> None:
    """19 real tool executions count as progress without any log lines."""
    run = {
        "tool_calls": [
            {"tool": "exec_command", "started_at": "2026-11-18T05:32:00Z"},
            {"tool": "http_request", "started_at": "2026-11-18T05:33:00Z"},
            {"tool": "exec_command", "started_at": "2026-11-18T05:34:00Z"},
        ]
    }
    assert api.productive_tool_count(run) == 3
    # A stalled run with 3 real tools is not stopped even after 700s.
    assert (
        api.should_stop_for_no_progress(
            elapsed_seconds=700,
            last_progress_seconds=700,
            productively_advanced_turns=api.productive_tool_count(run),
            max_turns=200,
        )
        is False
    )


def test_productive_tool_count_excludes_bookkeeping_tools() -> None:
    """Coverage/finish/report tools never count as progress."""
    run = {
        "tool_calls": [
            {"tool": "record_coverage"},
            {"tool": "update_coverage"},
            {"tool": "finish_scan"},
            {"tool": "agent_finish"},
            {"tool": "create_vulnerability_report"},
        ]
    }
    assert api.productive_tool_count(run) == 0
    assert (
        api.should_stop_for_no_progress(
            elapsed_seconds=700,
            last_progress_seconds=700,
            productively_advanced_turns=api.productive_tool_count(run),
            max_turns=200,
        )
        is True
    )


def test_productive_tool_count_tolerates_real_run_shape() -> None:
    """Real run.json entries may carry only a tool name and timing fields."""
    assert api.productive_tool_count(None) == 0
    assert api.productive_tool_count({}) == 0
    assert (
        api.productive_tool_count(
            {"tool_calls": [{"tool": "exec_command", "duration_ms": 101}, None, "junk"]}
        )
        == 1
    )


def test_engine_failure_status_is_not_relabelled_complete() -> None:
    """An engine that failed stays failed even when a report was harvested."""
    assert api.engine_terminal_failure({"status": "failed"}) == "failed"
    assert api.engine_terminal_failure({"status": "interrupted"}) == "interrupted"
    assert api.engine_terminal_failure({"status": "FAILED"}) == "failed"
    assert api.engine_terminal_failure({"status": "completed"}) is None
    assert api.engine_terminal_failure(None) is None
    assert api.engine_terminal_failure({}) is None
