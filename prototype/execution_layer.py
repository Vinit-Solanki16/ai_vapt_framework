"""Execution abstraction layer for the prototype.

This module provides a thin abstraction over the real engine Executor.
It does NOT reimplement engine logic — it delegates to the existing Executor.

Default mode: simulation
- Outcomes are resolved from candidate.ground_truth labels.
- No external network access is performed.
- No Nmap, Nuclei, or exploitation is executed.
"""

from typing import Optional, Callable

from decision_engine.core.executor import Executor
from decision_engine.core.schemas import ActionCandidate, ExecutionResult


def create_simulation_executor() -> Executor:
    """Create an Executor in simulation mode.

    Outcomes are resolved from the candidate's ground_truth field.
    This is deterministic and makes no external calls.
    """
    return Executor(mode="simulation")


def create_executor(
    mode: str = "simulation",
    execute_fn: Optional[Callable[[ActionCandidate], ExecutionResult]] = None,
) -> Executor:
    """Factory for Executor instances.

    Args:
        mode: "simulation" (default) or "real"
        execute_fn: required for real mode; the domain action runner

    Returns:
        Configured Executor instance

    Raises:
        ValueError: if real mode requested without execute_fn
    """
    if mode not in ("simulation", "real"):
        raise ValueError(f"Unsupported mode: {mode!r}; expected 'simulation' or 'real'")

    if mode == "real" and execute_fn is None:
        raise ValueError("real mode requires an execute_fn (the domain action runner)")

    return Executor(mode=mode, execute_fn=execute_fn)


def simulate_execution(candidate: ActionCandidate) -> ExecutionResult:
    """Simulate executing a single candidate.

    This is a convenience function that uses the simulation Executor
    without explicit state management.

    Args:
        candidate: The candidate to "execute"

    Returns:
        ExecutionResult with outcome from ground_truth
    """
    executor = create_simulation_executor()
    return executor.execute(candidate)