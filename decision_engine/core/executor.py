"""Generic execution backend for the decision engine (domain-independent).

Two backends mirror the original VAPT Executor:
  - SIMULATION: resolves outcome from an OPTIONAL ground_truth label on the
    candidate. This is clearly labelled simulation; the pivot engine reacts to
    real signals, just sourced from a curated label rather than a live action.
  - REAL: a pluggable ``execute_fn`` performs the actual domain action and
    returns an ExecutionResult. The engine itself never assumes the action is a
    PoC exploit — it only consumes the returned Outcome. This is how the engine
    stays domain-independent while still supporting observed validation.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from decision_engine.core.schemas import (
    ActionCandidate,
    ExecutionResult,
    Outcome,
)


class Executor:
    def __init__(
        self,
        mode: str = "simulation",
        execute_fn: Optional[Callable[[ActionCandidate], ExecutionResult]] = None,
    ):
        """
        mode:
          "simulation" -> outcome resolved from candidate.ground_truth (if set).
          "real"       -> delegate to execute_fn (must be provided).
        execute_fn: domain action runner returning ExecutionResult (real mode).
        """
        self.mode = mode
        if mode == "real" and execute_fn is None:
            raise ValueError("real mode requires an execute_fn (the domain action runner)")
        self.execute_fn = execute_fn

    def execute(self, candidate: ActionCandidate) -> ExecutionResult:
        candidate.attempted = True
        if self.mode == "simulation":
            outcome = self._outcome_from_label(candidate)
            return ExecutionResult(
                candidate_id=candidate.id,
                outcome=outcome,
                request_count=1,
                detail="simulated(ground_truth)" if candidate.ground_truth else "simulated(no-label)",
            )
        result = self.execute_fn(candidate)  # type: ignore[union-attr]
        if not isinstance(result, ExecutionResult):
            raise TypeError("execute_fn must return an ExecutionResult")
        return result

    @staticmethod
    def _outcome_from_label(candidate: ActionCandidate) -> Outcome:
        return candidate.ground_truth or Outcome.FAIL_TIMEOUT
