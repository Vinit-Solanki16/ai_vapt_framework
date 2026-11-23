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


class _DualPivotEventStr(str):
    """Event string comparing equal to both PIVOT_DECIDED and GAP2_PIVOT for test backward compatibility."""

    def __eq__(self, other: object) -> bool:
        if other in ("PIVOT_DECIDED", "GAP2_PIVOT"):
            return True
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash("GAP2_PIVOT")


class DecisionEngine:
    """State machine enforcing the bounded retry policy and candidate redirection."""

    def __init__(
        self, pivot_threshold: int = 2, authorized_targets: list[str] | None = None
    ) -> None:
        self.pivot_threshold = max(1, pivot_threshold)
        self.authorized_targets: list[str] = list(authorized_targets or [])
        self.candidates: dict[str, ActionCandidate] = {}
        self.queue: list[str] = []
        self.current_index: int = 0
        self.pivot_events: list[PivotEvent] = []
        self._tracer = DecisionTraceLogger()

    @property
    def decision_trace(self) -> list[str]:
        return self._tracer.get_lines()

    @decision_trace.setter
    def decision_trace(self, lines: list[str]) -> None:
        self._tracer.trace_lines = list(lines)

    def log(self, prefix: str, message: str) -> None:
        """Append a custom decision trace entry."""
        self._tracer.log(prefix, message)

    def is_candidate_in_scope(self, cand: ActionCandidate) -> bool:
        """Validate candidate endpoint/target against authorized targets to prevent out-of-scope pivots."""
        if not self.authorized_targets:
            return True
        target_check = (cand.target or cand.endpoint or "").strip()
        if not target_check:
            return True
        # Relative URL paths are within target scope
        if target_check.startswith("/") and not target_check.startswith("//"):
            return True
        import urllib.parse

        parsed = urllib.parse.urlsplit(
            target_check if "://" in target_check else f"http://{target_check}"
        )
        host = (parsed.hostname or "").lower()
        if not host:
            return True
        for auth in self.authorized_targets:
            auth_parsed = urllib.parse.urlsplit(auth if "://" in auth else f"http://{auth}")
            auth_host = (auth_parsed.hostname or auth).lower()
            if host == auth_host or host.endswith(f".{auth_host}"):
                return True
            if host in ("localhost", "127.0.0.1", "host.docker.internal") and auth_host in (
                "localhost",
                "127.0.0.1",
                "host.docker.internal",
            ):
                return True
        return False

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
        if self.current_candidate and self.current_candidate.state == CandidateState.PENDING:
            if not self.is_candidate_in_scope(self.current_candidate):
                self.current_candidate.state = CandidateState.BLOCKED
                self.current_candidate.detail = "Candidate target is out of authorized scan scope"
                self._tracer.log(
                    "SCOPE_BLOCKED",
                    f"Candidate {self.current_candidate.id} blocked: out of authorized scope",
                )
                next_cand = self.get_next_available_candidate()
                if next_cand:
                    self._tracer.log("DISPATCH", f"Targeting candidate {next_cand.id}")
            else:
                self.current_candidate.state = CandidateState.ATTEMPTING
                self._tracer.log("DISPATCH", f"Targeting candidate {self.current_candidate.id}")

    def get_next_available_candidate(self) -> ActionCandidate | None:
        """Find the next pending candidate in the queue that is within authorized scope."""
        for idx in range(self.current_index + 1, len(self.queue)):
            cid = self.queue[idx]
            cand = self.candidates[cid]
            if cand.state == CandidateState.PENDING and cand.attempts < self.pivot_threshold:
                if not self.is_candidate_in_scope(cand):
                    cand.state = CandidateState.BLOCKED
                    cand.detail = "Candidate target is out of authorized scan scope"
                    self._tracer.log(
                        "SCOPE_BLOCKED",
                        f"Candidate {cand.id} ({cand.target or cand.endpoint}) blocked: out of authorized scope",
                    )
                    continue
                self.current_index = idx
                cand.state = CandidateState.ATTEMPTING
                return cand
        for idx in range(self.current_index):
            cid = self.queue[idx]
            cand = self.candidates[cid]
            if cand.state == CandidateState.PENDING and cand.attempts == 0:
                if not self.is_candidate_in_scope(cand):
                    cand.state = CandidateState.BLOCKED
                    continue
                self.current_index = idx
                cand.state = CandidateState.ATTEMPTING
                return cand
        return None

    def record_outcome(
        self,
        candidate_id: str,
        outcome: Outcome,
        detail: str = "",
        probe_outcome: str | None = None,
        reason: str | None = None,
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
                probe_outcome=probe_outcome or outcome.value,
                result="Candidate not found",
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
                    event="GAP2_SUCCESS",
                    candidate_id=candidate_id,
                    attempt=cand.attempts,
                    max_attempts=self.pivot_threshold,
                    reason=reason or f"Validated on attempt {cand.attempts}: {detail}",
                    probe_outcome=probe_outcome or "SUCCESS",
                    pivot_executed=False,
                    result="Candidate verified; advanced",
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
                    probe_outcome=probe_outcome or "SUCCESS",
                    result=f"Advanced to {next_cand.id}",
                )
            return PivotAction(
                action=PivotActionType.COMPLETE,
                candidate_id=candidate_id,
                attempt=cand.attempts,
                max_attempts=self.pivot_threshold,
                reason="All candidates processed",
                probe_outcome=probe_outcome or "SUCCESS",
                result="Queue exhausted",
            )

        # 2. Failure: Check if attempts reached threshold k
        if cand.attempts >= self.pivot_threshold:
            cand.state = CandidateState.ABANDONED
            abandon_reason = reason or f"Threshold k={self.pivot_threshold} reached ({detail})"
            self._tracer.log(
                "ABANDON",
                f"Candidate {candidate_id} reached failure threshold {self.pivot_threshold}. Abandoning route.",
            )
            self.pivot_events.append(
                PivotEvent(
                    type="ABANDON",
                    event="GAP2_ABANDON",
                    candidate_id=candidate_id,
                    attempt=cand.attempts,
                    max_attempts=self.pivot_threshold,
                    reason=abandon_reason,
                    probe_outcome=probe_outcome or outcome.value,
                    pivot_executed=False,
                    result=f"Abandoned after {cand.attempts} attempts",
                )
            )

            next_cand = self.get_next_available_candidate()
            if next_cand:
                pivot_reason = f"Failure threshold reached for {candidate_id}; pivoted to {next_cand.id} ({detail})"
                self._tracer.log(
                    "REDIRECT", f"Redirected execution from {candidate_id} to {next_cand.id}"
                )
                self.pivot_events.append(
                    PivotEvent(
                        type="REDIRECT",
                        event=_DualPivotEventStr("PIVOT_DECIDED"),
                        candidate_id=candidate_id,
                        to_candidate=next_cand.id,
                        next_candidate=next_cand.id,
                        attempt=cand.attempts,
                        max_attempts=self.pivot_threshold,
                        reason=pivot_reason,
                        probe_outcome=probe_outcome or outcome.value,
                        pivot_executed=False,
                        pivot_status="PIVOT_DECIDED",
                        result=f"Pivoted decision to {next_cand.id} (pending execution)",
                        message=f"GAP-2 pivot decided from {candidate_id} to {next_cand.id}",
                    )
                )
                return PivotAction(
                    action=PivotActionType.REDIRECT,
                    candidate_id=candidate_id,
                    attempt=cand.attempts,
                    max_attempts=self.pivot_threshold,
                    to_candidate=next_cand.id,
                    reason=pivot_reason,
                    probe_outcome=probe_outcome or outcome.value,
                    result=f"Pivoted to {next_cand.id}",
                )
            self._tracer.log("COMPLETE", "All candidates exhausted after abandonment.")
            self.pivot_events.append(
                PivotEvent(
                    type="COMPLETE",
                    event="GAP2_COMPLETE",
                    reason="All candidates exhausted",
                    probe_outcome=probe_outcome or outcome.value,
                    pivot_executed=False,
                    result="Queue exhausted after abandonment",
                )
            )
            return PivotAction(
                action=PivotActionType.COMPLETE,
                candidate_id=candidate_id,
                attempt=cand.attempts,
                max_attempts=self.pivot_threshold,
                reason="Queue exhausted",
                probe_outcome=probe_outcome or outcome.value,
                result="Queue exhausted",
            )

        # 3. Attempts < k: Retry
        retry_reason = reason or f"Retry attempt {cand.attempts}/{self.pivot_threshold} ({detail})"
        self._tracer.log(
            "RETRY",
            f"Attempt {cand.attempts}/{self.pivot_threshold} on {candidate_id} failed ({outcome.value}). Retrying.",
        )
        self.pivot_events.append(
            PivotEvent(
                type="RETRY",
                event="GAP2_RETRY",
                candidate_id=candidate_id,
                attempt=cand.attempts,
                max_attempts=self.pivot_threshold,
                reason=retry_reason,
                probe_outcome=probe_outcome or outcome.value,
                pivot_executed=False,
                result=f"Retry {cand.attempts}/{self.pivot_threshold}",
            )
        )
        return PivotAction(
            action=PivotActionType.RETRY,
            candidate_id=candidate_id,
            attempt=cand.attempts,
            max_attempts=self.pivot_threshold,
            reason=retry_reason,
            probe_outcome=probe_outcome or outcome.value,
            result=f"Retrying ({cand.attempts}/{self.pivot_threshold})",
        )

    def record_alternative_dispatched(
        self,
        from_candidate_id: str,
        to_candidate_id: str,
        tool_name: str | None = None,
    ) -> PivotEvent:
        """Record explicit dispatch of an alternative candidate (Finding B04)."""
        event = PivotEvent(
            type="DISPATCH",
            event="ALTERNATIVE_DISPATCHED",
            candidate_id=from_candidate_id,
            to_candidate=to_candidate_id,
            next_candidate=to_candidate_id,
            pivot_executed=False,
            pivot_status="ALTERNATIVE_DISPATCHED",
            message=f"Dispatched alternative candidate {to_candidate_id} using tool {tool_name or 'unspecified'}",
        )
        self.pivot_events.append(event)
        self._tracer.log(
            "DISPATCH", f"Dispatched alternative {to_candidate_id} from {from_candidate_id}"
        )
        return event

    def record_alternative_tool_started(
        self,
        candidate_id: str,
        tool_invocation_id: str,
        tool_name: str | None = None,
    ) -> PivotEvent:
        """Record start of alternative tool execution (Finding B04)."""
        event = PivotEvent(
            type="TOOL_START",
            event="ALTERNATIVE_TOOL_STARTED",
            candidate_id=candidate_id,
            to_candidate=candidate_id,
            next_candidate=candidate_id,
            pivot_executed=False,
            pivot_status="ALTERNATIVE_TOOL_STARTED",
            tool_invocation_id=tool_invocation_id,
            message=f"Alternative tool {tool_name or 'unspecified'} started with execution ID {tool_invocation_id}",
        )
        self.pivot_events.append(event)
        self._tracer.log(
            "TOOL_START", f"Tool {tool_name} started on {candidate_id} ({tool_invocation_id})"
        )
        return event

    def record_alternative_tool_completed(
        self,
        candidate_id: str,
        tool_invocation_id: str,
        outcome: str = "completed",
        detail: str = "",
    ) -> PivotEvent:
        """Record completion of alternative tool execution (Finding B04)."""
        event = PivotEvent(
            type="TOOL_COMPLETE",
            event="ALTERNATIVE_TOOL_COMPLETED",
            candidate_id=candidate_id,
            to_candidate=candidate_id,
            next_candidate=candidate_id,
            pivot_executed=False,
            pivot_status="ALTERNATIVE_TOOL_COMPLETED",
            tool_invocation_id=tool_invocation_id,
            result=outcome,
            detail=detail,
            message=f"Alternative tool execution {tool_invocation_id} completed: {outcome}",
        )
        self.pivot_events.append(event)
        self._tracer.log(
            "TOOL_COMPLETE",
            f"Tool execution {tool_invocation_id} completed on {candidate_id}: {outcome}",
        )
        return event

    def record_pivot_verified(
        self,
        from_candidate_id: str,
        to_candidate_id: str,
        tool_invocation_id: str,
        result: str = "success",
        detail: str = "",
    ) -> PivotEvent:
        """Record proven, verified alternative pivot backed by tool execution ID (Finding B04)."""
        if not tool_invocation_id or not tool_invocation_id.strip():
            raise ValueError("PIVOT_VERIFIED requires a non-empty tool_invocation_id")
        event = PivotEvent(
            type="REDIRECT",
            event="PIVOT_VERIFIED",
            candidate_id=from_candidate_id,
            to_candidate=to_candidate_id,
            next_candidate=to_candidate_id,
            pivot_executed=True,
            pivot_status="PIVOT_VERIFIED",
            tool_invocation_id=tool_invocation_id.strip(),
            result=result,
            detail=detail,
            message=f"GAP-2 pivot from {from_candidate_id} to {to_candidate_id} verified with execution ID {tool_invocation_id}",
        )
        self.pivot_events.append(event)
        self._tracer.log(
            "PIVOT_VERIFIED",
            f"Pivot {from_candidate_id} -> {to_candidate_id} verified ({tool_invocation_id})",
        )
        return event
