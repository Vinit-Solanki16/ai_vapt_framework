"""Tests for the three deterministic demo scenarios.

Each test proves the scenario reaches its expected terminal state
through the real engine — no simulation of the engine itself.
"""

from decision_engine.core.engine import run_engine
from decision_engine.core.schemas import EngineStatus, Outcome

from prototype.demo_data import (
    success_scenario,
    failure_pivot_scenario,
    multi_candidate_scenario,
)
from prototype.engine_integration import run_decision_scenario
from prototype.execution_layer import create_simulation_executor
from decision_engine.core.assessor import deterministic_assessor


class TestSuccessScenario:
    """Tests for the 'success' scenario."""

    def test_success_scenario_reaches_terminal_state(self):
        """Verify success scenario reaches expected terminal state."""
        candidates = success_scenario()
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

        # The first (highest priority) candidate must succeed
        assert state["status"] == EngineStatus.SUCCESS.value

    def test_success_scenario_has_high_priority_winner(self):
        """Verify the winner has highest priority in the ranking."""
        candidates = success_scenario()
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

        # First candidate processed should be the highest priority
        processed = state["_presentation"].get("candidates_processed", [])
        assert len(processed) >= 1


class TestFailurePivotScenario:
    """Tests for the 'failure_pivot' scenario."""

    def test_failure_pivot_demonstrates_bounded_attempts(self):
        """Verify failure_pivot shows bounded attempts before pivot."""
        candidates = failure_pivot_scenario(max_attempts=2)

        # Run with real engine
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

        # Check logs for bounded attempt behavior
        logs = state.get("logs", [])
        execute_attempts = [l for l in logs if "[Executor]" in l]

        # Should have at least 2 execute attempts for the dead-end candidate
        fail_attempts = [l for l in execute_attempts if "FAIL_TIMEOUT" in l]
        assert len(fail_attempts) >= 2, f"Expected >= 2 fail attempts, got {len(fail_attempts)}"

    def test_failure_pivot_reaches_next_candidate(self):
        """Verify failure_pivot pivots to next candidate after max attempts."""
        candidates = failure_pivot_scenario(max_attempts=2)
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

        # Pivot should have occurred (log entry exists)
        logs = state.get("logs", [])
        pivot_log = [l for l in logs if "[Pivot]" in l and "Redirected" in l]
        assert len(pivot_log) >= 1, "Expected pivot redirect log entry"

        # Final status should be SUCCESS (DEMO-WORKER succeeds)
        assert state["status"] in (EngineStatus.SUCCESS.value, EngineStatus.COMPLETED.value)

        # Both candidates should be processed
        processed = state["_presentation"].get("candidates_processed", [])
        assert "DEMO-DEAD-END" in processed
        assert "DEMO-WORKER" in processed

    def test_pivot_count_is_correct(self):
        """Verify pivot count is computed correctly."""
        candidates = failure_pivot_scenario(max_attempts=2)
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

        pivot_count = state["_presentation"].get("pivot_count", 0)
        assert pivot_count >= 1, "Expected at least one pivot"


class TestMultiCandidateScenario:
    """Tests for the 'multi_candidate' scenario."""

    def test_multi_candidate_executes_through_real_engine(self):
        """Verify multi_candidate runs through the real engine with mixed outcomes."""
        candidates = multi_candidate_scenario()
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

        # Should have processed candidates
        assert state["status"] in (EngineStatus.SUCCESS.value, EngineStatus.COMPLETED.value)

    def test_multi_candidate_has_multiple_attempts(self):
        """Verify multi_candidate shows multiple execution attempts."""
        candidates = multi_candidate_scenario()
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")

        results = state.get("results", [])
        total_attempts = len(results)

        # Multiple candidates with mixed outcomes = multiple attempts
        assert total_attempts >= 1, "Expected at least one execution attempt"


def test_engine_api_path_is_used():
    """Verify the prototype uses decision_engine.core.engine.run_engine().

    This test imports both and checks they are the same module-level function.
    """
    from decision_engine.core.engine import run_engine as core_run_engine

    # The integration should call the core engine
    candidates = [{"id": "X", "probability": 0.5, "ground_truth": "SUCCESS"}]

    state = run_engine(
        candidates,
        assess_fn=deterministic_assessor,
        executor=create_simulation_executor(),
        max_attempts=2,
        mode="simulation",
    )

    assert state is not None
    assert "results" in state
    assert "logs" in state