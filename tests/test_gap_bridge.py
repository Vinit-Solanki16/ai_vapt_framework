"""GAP-1 queue injection and GAP-2 pivot bridge tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from strix.core import gap_bridge
from strix.core.inputs import build_root_task
from strix.tools.reporting.tool import _attach_gap2


@pytest.fixture(autouse=True)
def _clean_bridge(monkeypatch):
    gap_bridge.reset_state()
    monkeypatch.delenv(gap_bridge.CONTROL_DIR_ENV, raising=False)
    monkeypatch.delenv(gap_bridge.QUEUE_ENV, raising=False)
    monkeypatch.delenv(gap_bridge.THRESHOLD_ENV, raising=False)
    yield
    gap_bridge.reset_state()


def _write_queue(tmp_path: Path, *, ranked=None):
    control = tmp_path / "control"
    control.mkdir()
    candidates = ranked or [
        {
            "candidate_id": "c2",
            "gap1_rank": 1,
            "title": "Second",
            "endpoint": "/second",
            "method": "GET",
            "quality_rank": "high",
            "priority_score": 0.8,
        },
        {
            "candidate_id": "c1",
            "gap1_rank": 2,
            "title": "First",
            "endpoint": "/first",
            "method": "POST",
            "quality_rank": "low",
            "priority_score": 0.2,
        },
    ]
    (control / "gap1_queue.json").write_text(
        json.dumps(
            {
                "original_order": ["c1", "c2"],
                "ranked_order": [c["candidate_id"] for c in candidates],
                "ranking_changed": True,
                "candidates": candidates,
            }
        ),
        encoding="utf-8",
    )
    return control


def test_gap1_block_orders_candidates_by_rank(tmp_path, monkeypatch):
    control = _write_queue(tmp_path)
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(control))
    block = gap_bridge.gap1_instruction_block()
    assert block.index("[c2] Second") < block.index("[c1] First")
    assert "Work through them in this exact order" in block
    trace = (control / "decision_trace.jsonl").read_text(encoding="utf-8")
    event = json.loads(trace.splitlines()[0])
    assert event["event"] == "GAP1_ROOT_TASK_INJECTED"
    assert event["ranked_order"] == ["c2", "c1"]
    assert event["ranking_changed"] is True


def test_build_root_task_injects_gap1_block(tmp_path, monkeypatch):
    control = _write_queue(tmp_path)
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(control))
    task = build_root_task(
        {
            "targets": [
                {
                    "type": "web_application",
                    "details": {"target_url": "http://host.docker.internal:9191"},
                }
            ],
            "user_instructions": "",
        }
    )
    assert "AI_VAPT GAP-1 prioritized candidate queue" in task
    assert "http://host.docker.internal:9191" in task


def test_build_root_task_without_control_dir_is_unchanged():
    task = build_root_task(
        {
            "targets": [
                {"type": "web_application", "details": {"target_url": "http://example.test"}}
            ]
        }
    )
    assert "AI_VAPT GAP-1" not in task


def test_gap2_failure_pivots_at_threshold(tmp_path, monkeypatch):
    control = _write_queue(tmp_path)
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(control))
    monkeypatch.setenv(gap_bridge.THRESHOLD_ENV, "2")
    first = gap_bridge.record_outcome(
        title="Second", endpoint="/second", success=False, detail="no signal"
    )
    assert first["attempts"] == 1
    assert first["pivot"] is False
    second = gap_bridge.record_outcome(
        title="Second", endpoint="/second", success=False, detail="still no signal"
    )
    assert second["attempts"] == 2
    assert second["pivot"] is True
    assert second["next_candidate"]["candidate_id"] == "c1"
    guidance = gap_bridge.guidance_text(second)
    assert "PIVOT" in guidance and "c1" not in guidance
    assert "First" in guidance
    trace = (control / "decision_trace.jsonl").read_text(encoding="utf-8")
    assert "GAP2_PIVOT" in trace


def test_gap2_success_completes_candidate(tmp_path, monkeypatch):
    control = _write_queue(tmp_path)
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(control))
    outcome = gap_bridge.record_outcome(
        title="Second",
        endpoint="/second",
        success=True,
        detail="confirmed",
        report_id="report-1",
    )
    assert outcome["pivot"] is False
    assert outcome["candidate_id"] == "c2"
    assert outcome["next_candidate"]["candidate_id"] == "c1"


def test_candidate_matching_prefers_endpoint_over_title(tmp_path, monkeypatch):
    control = _write_queue(tmp_path)
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(control))
    assert gap_bridge.candidate_id_for("Unrelated", "/second", "") == "c2"


def test_invalid_threshold_falls_back(tmp_path, monkeypatch):
    control = _write_queue(tmp_path)
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(control))
    monkeypatch.setenv(gap_bridge.THRESHOLD_ENV, "not-a-number")
    assert gap_bridge.threshold() == gap_bridge.DEFAULT_THRESHOLD


def test_attach_gap2_returns_pivot_guidance(tmp_path, monkeypatch):
    control = _write_queue(tmp_path)
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(control))
    monkeypatch.setenv(gap_bridge.THRESHOLD_ENV, "1")
    result = _attach_gap2(
        {"success": False, "error": "no PoC"},
        title="Second",
        endpoint="/second",
        target="http://host.docker.internal:9191",
        success=False,
        detail="verification failed",
    )
    assert result["gap2"]["pivot"] is True
    assert "pivot_guidance" in result
    assert "Abandon this route" in result["pivot_guidance"]


def test_attach_gap2_noop_without_bridge():
    result = _attach_gap2(
        {"success": False},
        title="x",
        endpoint="/x",
        target="http://example.test",
        success=False,
    )
    assert result == {"success": False}


def test_next_candidate_skips_exhausted(tmp_path, monkeypatch):
    control = _write_queue(tmp_path)
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(control))
    monkeypatch.setenv(gap_bridge.THRESHOLD_ENV, "1")
    gap_bridge.record_outcome(title="Second", endpoint="/second", success=False)
    assert gap_bridge.next_candidate()["candidate_id"] == "c1"


def test_gap1_can_be_disabled(tmp_path, monkeypatch):
    control = _write_queue(tmp_path)
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(control))
    monkeypatch.setenv(gap_bridge.GAP1_ENABLED_ENV, "0")
    assert gap_bridge.gap1_instruction_block() == ""


def test_gap2_can_be_disabled(tmp_path, monkeypatch):
    control = _write_queue(tmp_path)
    monkeypatch.setenv(gap_bridge.CONTROL_DIR_ENV, str(control))
    monkeypatch.setenv(gap_bridge.GAP2_ENABLED_ENV, "0")
    result = _attach_gap2(
        {"success": False},
        title="Second",
        endpoint="/second",
        target="http://example.test",
        success=False,
    )
    assert result == {"success": False}
