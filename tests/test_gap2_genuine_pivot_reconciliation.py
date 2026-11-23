"""Regression tests for truthful GAP-2 pivot counting.

A GAP-2 pivot is genuine only when the selected alternative candidate was
actually executed after the decision. A decision marker, a threshold
counter, or advancing through a pre-sorted queue is not a pivot.
"""

from __future__ import annotations

import json
from pathlib import Path

from strix.core.gap_run import GapRun


def _make_state(tmp_path: Path) -> GapRun:
    state_dir = tmp_path / ".state"
    state_dir.mkdir()
    run = GapRun(run_id="test-pivot", state_dir=state_dir)
    run.attach_candidate("c1", "Candidate 1", "/one", "general", score=0.9, rank=1)
    run.attach_candidate("c2", "Candidate 2", "/two", "general", score=0.8, rank=2)
    return run


def test_decision_marker_alone_is_not_a_pivot(tmp_path: Path) -> None:
    run = _make_state(tmp_path)
    run.record_pivot("c1", "c2", "inconclusive", detail="threshold reached")
    assert run.pivot_count() == 0
    assert run.summary["pivots_executed"] == 0


def test_recorded_alternative_execution_counts_as_pivot(tmp_path: Path) -> None:
    run = _make_state(tmp_path)
    run.record_pivot("c1", "c2", "inconclusive", detail="threshold reached")
    run.record_probe_outcome("c2", outcome="inconclusive", detail="live probe of /two")
    assert run.pivot_count() == 1
    assert run.summary["pivots_executed"] == 1


def test_pivot_with_unexecuted_alternative_does_not_count(tmp_path: Path) -> None:
    run = _make_state(tmp_path)
    run.record_pivot("c1", "c2", "inconclusive", detail="threshold reached")
    run.record_probe_outcome("c1", outcome="inconclusive", detail="retry of /one")
    assert run.pivot_count() == 0


def test_engine_and_persisted_state_counters_agree(tmp_path: Path) -> None:
    run = _make_state(tmp_path)
    run.record_pivot("c1", "c2", "inconclusive", detail="decision only")
    run.record_probe_outcome("c2", outcome="inconclusive", detail="executed alternative")
    persisted = json.loads((tmp_path / ".state" / "gap_state.json").read_text(encoding="utf-8"))
    decisions = [e for e in persisted["decision_trace"] if e.get("type") == "pivot_decision"]
    alternatives = {str(e.get("alternative_candidate")) for e in decisions}
    executed = {str(e.get("candidate_id")) for e in persisted["probe_outcomes"]}
    assert len(alternatives & executed) == 1
    assert run.summary["pivots_executed"] == 1
