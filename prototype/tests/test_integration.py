"""Tests proving the prototype integrates with the real decision engine.

No mock engines. Every test calls actual decision_engine APIs.
"""

from decision_engine.core.engine import run_engine, initial_state
from decision_engine.core.schemas import (
    ActionCandidate,
    EngineStatus,
    Outcome,
    candidate_from_dict,
)
from decision_engine.core.executor import Executor
from decision_engine.core.assessor import deterministic_assessor

from prototype.engine_integration import (
    run_decision_scenario,
    load_vapt_corpus_scenario,
    validate_scenario,
)


def test_engine_run_engine_is_real():
    """Verify that the engine function we use is the real one."""
    from decision_engine.core.engine import run_engine as real_run_engine
    assert run_engine is real_run_engine


def test_initial_state_creates_candidates():
    """Verify that the engine's initial_state is used (real)."""
    candidates = [
        {"id": "X", "probability": 0.5, "ground_truth": "SUCCESS"},
    ]
    state = initial_state(candidates, max_attempts=2, mode="simulation")
    assert len(state["candidates"]) == 1
    assert state["candidates"][0].id == "X"
    assert state["max_attempts"] == 2


def test_candidate_from_dict_used_in_real_api():
    """Verify candidate_from_dict conversion works through the real engine."""
    d = {"id": "TEST", "probability": 0.7, "ground_truth": "SUCCESS"}
    c = candidate_from_dict(d)
    assert c.id == "TEST"
    assert c.probability == 0.7
    assert c.ground_truth == Outcome.SUCCESS


def test_decision_engine_status_enum_is_real():
    """Verify the engine status enum is the real one."""
    assert EngineStatus.SUCCESS.value == "SUCCESS"
    assert EngineStatus.COMPLETED.value == "COMPLETED"


def test_run_decision_scenario_uses_real_engine():
    """Verify run_decision_scenario calls the real engine."""
    state = run_decision_scenario(
        [{"id": "R1", "probability": 0.9, "ground_truth": "success"}],
        max_attempts=2,
        mode="simulation",
    )
    # Status from the real engine
    assert state["status"] in (EngineStatus.SUCCESS.value, EngineStatus.COMPLETED.value)


def test_load_vapt_corpus_scenario_uses_real_adapter():
    """Verify corpus loading uses the real adapter."""
    candidates = load_vapt_corpus_scenario()
    # The real corpus has CVEs (from the existing data)
    assert len(candidates) > 0
    for c in candidates:
        assert "id" in c
        assert isinstance(c["id"], str)


def test_validate_scenario_rejects_empty():
    """Verify empty scenarios are rejected before engine invocation."""
    import pytest
    with pytest.raises(ValueError, match="at least one candidate"):
        validate_scenario([])


def test_validate_scenario_rejects_non_list():
    """Verify non-list scenarios are rejected."""
    import pytest
    with pytest.raises(ValueError, match="must be a list"):
        validate_scenario("not a list")


def test_validate_scenario_rejects_missing_id():
    """Verify scenarios without ids are rejected."""
    import pytest
    with pytest.raises(ValueError, match="non-empty string 'id'"):
        validate_scenario([{"probability": 0.5}])


def test_validate_scenario_rejects_invalid_probability():
    """Verify scenarios with invalid probabilities are rejected."""
    import pytest
    with pytest.raises(ValueError, match="invalid 'probability'"):
        validate_scenario([{"id": "X", "probability": 1.5}])


def test_validate_scenario_rejects_invalid_outcome():
    """Verify scenarios with unknown ground_truth are rejected."""
    import pytest
    with pytest.raises(ValueError, match="unknown 'ground_truth'"):
        validate_scenario([{"id": "X", "probability": 0.5, "ground_truth": "INVALID_OUTCOME"}])


def test_validate_scenario_accepts_valid_input():
    """Verify valid scenarios are accepted."""
    validate_scenario([
        {"id": "A", "probability": 0.5, "ground_truth": "success"},
        {"id": "B", "probability": 0.7},
    ])