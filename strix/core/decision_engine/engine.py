"""Core GAP-2 Bounded Dynamic Decision-Pivoting State Machine."""

from __future__ import annotations

import logging

from strix.core.decision_engine.schemas import (
    ActionCandidate,
    CandidateState,
    Outcome,
    PivotAction,
    PivotActionType,
    PivotEvent,
)
from strix.core.decision_engine.trace import DecisionTraceLogger


logger = logging.getLogger("strix.core.decision_engine")


class DecisionEngine:
    """State machine enforcing the bounded retry policy and candidate redirection."""

    def __init__(self, pivot_threshold: int = 2) -> None:
        self.pivot_threshold = max(1, pivot_threshold)
        self.candidates: dict[str, ActionCandidate] = {}
        self.queue: list[str] = []
        self.current_index: int = 0
        self.pivot_events: list[PivotEvent] = []
        self._tracer = DecisionTraceLogger()

    @property
    def decision_trace(self) -> list[str]:
        return self._tracer.get_lines()

    def log(self, prefix: str, message: str) -> None:
        """Append a custom decision trace entry."""
        self._tracer.log(prefix, message)

    @property
    def current_candidate(self) -> ActionCandidate | None:
        if 0 <= self.current_index < len(self.queue):
            cid = self.queue[self.current_index]
            return self.candidates.get(cid)
        return None

    def initialize(self, candidates: list[ActionCandidate]) -> None:
        """Initialize the candidate pool and execution order."""
        self.candidates = {c.id: c for c in candidates}
        self.queue = [c.id for c in candidates]
        self.current_index = 0
        self.pivot_events.append(
            PivotEvent(
                type="INIT",
                reason=f"Initialized decision queue with {len(self.queue)} candidates (threshold k={self.pivot_threshold})",
            )
        )
        self._tracer.log(
            "INIT",
            f"Queue initialized with {len(self.queue)} candidates (threshold k={self.pivot_threshold})",
        )
        if self.current_candidate:
            self.current_candidate.state = CandidateState.ATTEMPTING
            self._tracer.log("DISPATCH", f"Targeting candidate {self.current_candidate.id}")

    def get_next_available_candidate(self) -> ActionCandidate | None:
        """Find the next pending candidate in the queue."""
        for idx in range(self.current_index + 1, len(self.queue)):
            cid = self.queue[idx]
            cand = self.candidates[cid]
            if cand.state == CandidateState.PENDING:
                self.current_index = idx
                cand.state = CandidateState.ATTEMPTING
                return cand
        return None

    def record_outcome(
        self,
        candidate_id: str,
        outcome: Outcome,
        detail: str = "",
    ) -> PivotAction:
        """Record an attempt outcome and evaluate the GAP-2 pivot state machine."""
        cand = self.candidates.get(candidate_id)
        if not cand:
            return PivotAction(
                action=PivotActionType.COMPLETE,
                candidate_id=candidate_id,
                attempt=0,
                max_attempts=self.pivot_threshold,
                reason=f"Candidate {candidate_id} not found in engine",
            )

        cand.attempts += 1
        cand.outcome = outcome
        cand.detail = detail

        # 1. Success -> Advance to next candidate
        if outcome == Outcome.SUCCESS:
            cand.state = CandidateState.VALIDATED
            self._tracer.log(
                "ADVANCE",
                f"Candidate {candidate_id} VALIDATED on attempt {cand.attempts}. Advancing.",
            )
            self.pivot_events.append(
                PivotEvent(
                    type="ADVANCE",
                    candidate_id=candidate_id,
                    attempt=cand.attempts,
                    max_attempts=self.pivot_threshold,
                    reason=f"Validated on attempt {cand.attempts}: {detail}",
                )
            )
            next_cand = self.get_next_available_candidate()
            if next_cand:
                return PivotAction(
                    action=PivotActionType.ADVANCE,
                    candidate_id=candidate_id,
                    attempt=cand.attempts,
                    max_attempts=self.pivot_threshold,
                    to_candidate=next_cand.id,
                    reason="Validated; advanced to next candidate",
                )
            return PivotAction(
                action=PivotActionType.COMPLETE,
                candidate_id=candidate_id,
                attempt=cand.attempts,
                max_attempts=self.pivot_threshold,
                reason="All candidates processed",
            )

        # 2. Failure: Check if attempts reached threshold k
        if cand.attempts >= self.pivot_threshold:
            cand.state = CandidateState.ABANDONED
            self._tracer.log(
                "ABANDON",
                f"Candidate {candidate_id} reached failure threshold {self.pivot_threshold}. Abandoning route.",
            )
            self.pivot_events.append(
                PivotEvent(
                    type="ABANDON",
                    candidate_id=candidate_id,
                    attempt=cand.attempts,
                    max_attempts=self.pivot_threshold,
                    reason=f"Threshold reached ({detail})",
                )
            )

            next_cand = self.get_next_available_candidate()
            if next_cand:
                self._tracer.log(
                    "REDIRECT", f"Redirected execution from {candidate_id} to {next_cand.id}"
                )
                self.pivot_events.append(
                    PivotEvent(
                        type="REDIRECT",
                        candidate_id=candidate_id,
                        to_candidate=next_cand.id,
                        reason=f"Pivoted to {next_cand.id}",
                    )
                )
                return PivotAction(
                    action=PivotActionType.REDIRECT,
                    candidate_id=candidate_id,
                    attempt=cand.attempts,
                    max_attempts=self.pivot_threshold,
                    to_candidate=next_cand.id,
                    reason="Failure threshold reached; pivoted to next candidate",
                )
            self._tracer.log("COMPLETE", "All candidates exhausted after abandonment.")
            self.pivot_events.append(PivotEvent(type="COMPLETE", reason="All candidates exhausted"))
            return PivotAction(
                action=PivotActionType.COMPLETE,
                candidate_id=candidate_id,
                attempt=cand.attempts,
                max_attempts=self.pivot_threshold,
                reason="Queue exhausted",
            )

        # 3. Attempts < k: Retry
        self._tracer.log(
            "RETRY",
            f"Attempt {cand.attempts}/{self.pivot_threshold} on {candidate_id} failed ({outcome.value}). Retrying.",
        )
        return PivotAction(
            action=PivotActionType.RETRY,
            candidate_id=candidate_id,
            attempt=cand.attempts,
            max_attempts=self.pivot_threshold,
            reason=f"Retry attempt {cand.attempts}/{self.pivot_threshold}",
        )
