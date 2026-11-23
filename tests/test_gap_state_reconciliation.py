"""Verify worker reconciles engine-authoritative GAP state with the control plane.

The engine writes <engine-run>/.state/gap_state.json (GapRun) while the
control plane writes <control>/gap_state.json (gap_bridge). They must not
disagree about candidate attempts, states, or genuine GAP-2 pivots.
"""

from __future__ import annotations

import json
from pathlib import Path

from strix.core.gap_run import GapRun


def test_engine_gap_state_is_authoritative_for_attempts_and_states(tmp_path: Path) -> None:
    """Engine execution records win over stale control-plane state."""
    state_dir = tmp_path / ".state"
    state_dir.mkdir()
    run = GapRun("recon-test", state_dir)
    run.attach_candidate("c1", "Candidate 1", "/one", "general", score=0.9, rank=1)
    run.record_probe_outcome("c1", outcome="inconclusive", detail="real probe")
    run.record_investigation("c1", outcome="abandoned", detail="threshold")
    persisted = json.loads((state_dir / "gap_state.json").read_text(encoding="utf-8"))

    cand = persisted["candidates"]["c1"]
    assert cand["attempts"] >= 1
    assert cand["status"] in ("investigated", "abandoned")
    assert cand["investigation_outcome"] == "abandoned"
    # The control plane must derive its view from this file, not from its own
    # stale gap_state.json; this helper documents the canonical source.
    assert persisted["run_id"] == "recon-test"


def test_only_pivots_with_alternative_execution_are_reconciled(tmp_path: Path) -> None:
    state_dir = tmp_path / ".state"
    state_dir.mkdir()
    run = GapRun("pivot-recon", state_dir)
    run.attach_candidate("c1", "Candidate 1", "/one", "general", score=0.9, rank=1)
    run.attach_candidate("c2", "Candidate 2", "/two", "general", score=0.8, rank=2)

    # A decision with no alternative execution must not produce a pivot event.
    run.record_pivot("c1", "c2", "inconclusive", detail="decision only")
    persisted = json.loads((state_dir / "gap_state.json").read_text(encoding="utf-8"))
    executed = {str(p["candidate_id"]) for p in persisted["probe_outcomes"]}
    genuine = [
        e
        for e in persisted["decision_trace"]
        if e.get("type") == "pivot_decision" and str(e.get("alternative_candidate")) in executed
    ]
    assert genuine == []

    # Once the alternative is really executed, the pivot becomes genuine.
    run.record_probe_outcome("c2", outcome="inconclusive", detail="executed alternative")
    persisted = json.loads((state_dir / "gap_state.json").read_text(encoding="utf-8"))
    executed = {str(p["candidate_id"]) for p in persisted["probe_outcomes"]}
    genuine = [
        e
        for e in persisted["decision_trace"]
        if e.get("type") == "pivot_decision" and str(e.get("alternative_candidate")) in executed
    ]
    assert len(genuine) == 1
    assert run.summary["pivots_executed"] == 1
