"""Tests proving the execution layer uses the existing Executor.

No reimplementation — just thin delegation.
"""

from decision_engine.core.executor import Executor
from decision_engine.core.schemas import Outcome
from decision_engine.core.engine import run_engine

from prototype.execution_layer import (
    create_simulation_executor,
    create_executor,
    simulate_execution,
)


def test_execution_layer_uses_real_executor():
    """Verify that the prototype's executor is the real Executor."""
    from decision_engine.core.executor import Executor as RealExecutor
    e = create_simulation_executor()
    assert isinstance(e, RealExecutor)


def test_create_executor_default_is_simulation():
    """Verify default mode is simulation."""
    e = create_executor()
    assert e.mode == "simulation"


def test_create_simulation_executor_is_simulation():
    """Verify simulation mode is used."""
    e = create_simulation_executor()
    assert e.mode == "simulation"


def test_create_executor_requires_fn_for_real_mode():
    """Verify real mode without execute_fn raises."""
    from decision_engine.core.executor import Executor
    try:
        create_executor(mode="real")
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "execute_fn" in str(e).lower() or "real mode requires" in str(e).lower()


def test_simulate_execution_returns_execution_result():
    """Verify simulate_execution returns a real ExecutionResult."""
    from decision_engine.core.schemas import ActionCandidate, ExecutionResult
    c = ActionCandidate(id="SIM", probability=0.5, ground_truth=Outcome.SUCCESS)
    result = simulate_execution(c)
    assert isinstance(result, ExecutionResult)
    assert result.candidate_id == "SIM"
    assert result.outcome == Outcome.SUCCESS


def test_execution_layer_delegates_to_engine():
    """Verify execution layer does not change engine behaviour —
    delegate to the real run_engine and verify status comes from engine."""
    candidates = [{"id": "EL-1", "probability": 0.9, "ground_truth": "SUCCESS"}]
    state = run_engine(
        candidates,
        assess_fn=None,
        executor=create_simulation_executor(),
        max_attempts=2,
        mode="simulation",
    )
    assert state["status"] in ("SUCCESS", "COMPLETED")


def test_simulation_mode_no_external_calls():
    """Verify simulation mode makes no external calls by checking
    the executor's mode is 'simulation' and the Executor is from the
    decision_engine package."""
    import decision_engine.core.executor as exec_mod
    e = create_simulation_executor()
    assert type(e).__module__.startswith("decision_engine")
    assert e.mode == "simulation"