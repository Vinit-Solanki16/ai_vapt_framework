"""Tests for GAP-2 Bounded Dynamic Decision-Pivoting Engine."""

from __future__ import annotations

from strix.core.decision_engine.engine import DecisionEngine
from strix.core.decision_engine.schemas import (
    ActionCandidate,
    CandidateState,
    Outcome,
    PivotActionType,
)


def test_initialization():
    """Verify queue initialization and initial state."""
    engine = DecisionEngine(pivot_threshold=2)
    c1 = ActionCandidate(id="c1", probability=0.9)
    c2 = ActionCandidate(id="c2", probability=0.8)

    engine.initialize([c1, c2])
    assert engine.current_candidate is not None
    assert engine.current_candidate.id == "c1"
    assert engine.current_candidate.state == CandidateState.ATTEMPTING


def test_validation_advances():
    """Verify successful outcome validates candidate and advances queue."""
    engine = DecisionEngine(pivot_threshold=2)
    c1 = ActionCandidate(id="c1", probability=0.9)
    c2 = ActionCandidate(id="c2", probability=0.8)
    engine.initialize([c1, c2])

    action = engine.record_outcome("c1", Outcome.SUCCESS, detail="Confirmed PoC")
    assert action.action == PivotActionType.ADVANCE
    assert action.to_candidate == "c2"
    assert engine.candidates["c1"].state == CandidateState.VALIDATED
    assert engine.current_candidate.id == "c2"


def test_failure_pivots_at_threshold():
    """Verify candidate is abandoned and redirected at threshold k=2."""
    engine = DecisionEngine(pivot_threshold=2)
    c1 = ActionCandidate(id="c1", probability=0.9)
    c2 = ActionCandidate(id="c2", probability=0.8)
    engine.initialize([c1, c2])

    # Attempt 1 -> Retry
    action1 = engine.record_outcome("c1", Outcome.FAIL_TIMEOUT)
    assert action1.action == PivotActionType.RETRY
    assert engine.candidates["c1"].attempts == 1

    # Attempt 2 -> Threshold reached, Pivot to c2
    action2 = engine.record_outcome("c1", Outcome.FAIL_TIMEOUT)
    assert action2.action == PivotActionType.REDIRECT
    assert action2.to_candidate == "c2"
    assert engine.candidates["c1"].state == CandidateState.ABANDONED
    assert engine.current_candidate.id == "c2"


def test_exhaustion_completes():
    """Verify engine signals COMPLETE when all candidates are processed."""
    engine = DecisionEngine(pivot_threshold=1)
    c1 = ActionCandidate(id="c1", probability=0.9)
    engine.initialize([c1])

    action = engine.record_outcome("c1", Outcome.FAIL_TIMEOUT)
    assert action.action == PivotActionType.COMPLETE
    assert engine.candidates["c1"].state == CandidateState.ABANDONED
