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
        mode: "simulation" (default), "real", or "lab"
        execute_fn: required for real mode; the domain action runner

    Returns:
        Configured Executor instance

    Raises:
        ValueError: if real mode requested without execute_fn
    """
    if mode not in ("simulation", "real", "lab"):
        raise ValueError(f"Unsupported mode: {mode!r}; expected 'simulation', 'real', or 'lab'")

    if mode == "real" and execute_fn is None:
        raise ValueError("real mode requires an execute_fn (the domain action runner)")

    if mode == "lab":
        raise ValueError("lab mode requires target and port — use create_lab_executor()")

    return Executor(mode=mode, execute_fn=execute_fn)


def create_lab_executor(target: str, port: int, path: str = "/vuln") -> Executor:
    """Create an Executor wired to the Docker vulnerability emulator (OBSERVED mode).

    This is the real-mode executor whose execute_fn performs an HTTP GET to the
    lab emulator and maps the response to an Outcome. It produces OBSERVED (not
    simulated) outcomes — the response is real, not from a label file.

    Args:
        target: IP/hostname of the emulator (must be in LAB_TARGET_ALLOWLIST)
        port: TCP port of the emulator
        path: HTTP path to hit (e.g., /vuln for success, /fail for failure)

    Returns:
        Configured Executor instance in "real" mode

    Raises:
        ValueError: if target is not in the lab allowlist.
    """
    from prototype.lab_runner import run_lab_attempt, _validate_target

    # Validate at construction time (fail-closed: refuse early)
    _validate_target(target)

    def _lab_execute(candidate: ActionCandidate) -> ExecutionResult:
        outcome = run_lab_attempt(target, port, path=path)
        return ExecutionResult(
            candidate_id=candidate.id,
            outcome=outcome,
            request_count=1,
            detail=f"lab-observed(http://{target}:{port}{path})",
        )

    return Executor(mode="real", execute_fn=_lab_execute)


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