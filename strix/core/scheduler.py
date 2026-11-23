"""Candidate ticket dispatch scheduler for GAP-1 prioritization.

Enforces candidate-specific dispatch authorization based on priority rank,
records discovery order vs ranked order, and blocks unranked candidate execution
unless an authorized, logged override is provided (Finding B03).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SchedulingViolationError(Exception):
    """Raised when an agent attempts unranked candidate dispatch without an authorized override."""


@dataclass
class CandidateTicket:
    """Authorization ticket for executing a candidate vulnerability assessment."""

    ticket_id: str
    candidate_id: str
    dispatch_priority: int
    dispatched_order: int | None = None
    status: str = "ISSUED"  # ISSUED, DISPATCHED, COMPLETED, OVERRIDDEN, BLOCKED
    override_reason: str | None = None
    issued_at: str = field(default_factory=_utc_now)
    dispatched_at: str | None = None
    completed_at: str | None = None
    tool_invocation_ids: list[str] = field(default_factory=list)
    outcome: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "candidate_id": self.candidate_id,
            "dispatch_priority": self.dispatch_priority,
            "dispatched_order": self.dispatched_order,
            "status": self.status,
            "override_reason": self.override_reason,
            "issued_at": self.issued_at,
            "dispatched_at": self.dispatched_at,
            "completed_at": self.completed_at,
            "tool_invocation_ids": list(self.tool_invocation_ids),
            "outcome": self.outcome,
        }


class CandidateScheduler:
    """Scheduler that manages priority-governed candidate dispatch."""

    def __init__(
        self, run_id: str = "run-default", queue: list[dict[str, Any]] | None = None
    ) -> None:
        self.run_id = run_id
        self.tickets: dict[str, CandidateTicket] = {}
        self.tickets_by_candidate: dict[str, CandidateTicket] = {}
        self.dispatch_sequence: list[str] = []
        self.original_order: list[str] = []
        self.ranked_order: list[str] = []
        self.ranking_changed: bool = False
        self._next_dispatched_order = 1

        if queue:
            self.initialize(queue)

    def initialize(self, queue: list[dict[str, Any]]) -> None:
        """Initialize tickets from candidate queue, tracking discovery vs ranked order."""
        # Preserve discovery order if indicated, otherwise order in the input list
        sorted_by_discovery = sorted(
            queue,
            key=lambda c: c.get("discovery_order", c.get("priority_rank", 0)),
        )
        self.original_order = [
            str(c.get("id") or c.get("candidate_id")) for c in sorted_by_discovery
        ]
        self.ranked_order = [str(c.get("id") or c.get("candidate_id")) for c in queue]
        self.ranking_changed = self.original_order != self.ranked_order

        self.tickets.clear()
        self.tickets_by_candidate.clear()
        self.dispatch_sequence.clear()
        self._next_dispatched_order = 1

        run_prefix = self.run_id.replace("run-", "")[:8]
        for idx, cand in enumerate(queue, 1):
            cid = str(cand.get("id") or cand.get("candidate_id"))
            tid = f"TICKET-{run_prefix}-{idx:03d}"
            ticket = CandidateTicket(
                ticket_id=tid,
                candidate_id=cid,
                dispatch_priority=cand.get("priority_rank", idx),
                status="ISSUED",
            )
            self.tickets[tid] = ticket
            self.tickets_by_candidate[cid] = ticket

    def dispatch_next(self) -> CandidateTicket | None:
        """Dispatch the highest priority pending candidate ticket."""
        pending_tickets = [t for t in self.tickets.values() if t.status in ("ISSUED", "PENDING")]
        if not pending_tickets:
            return None

        # Sort by dispatch priority
        pending_tickets.sort(key=lambda t: t.dispatch_priority)
        next_ticket = pending_tickets[0]

        next_ticket.status = "DISPATCHED"
        next_ticket.dispatched_order = self._next_dispatched_order
        self._next_dispatched_order += 1
        next_ticket.dispatched_at = _utc_now()
        self.dispatch_sequence.append(next_ticket.candidate_id)
        return next_ticket

    def authorize_dispatch(
        self,
        candidate_id: str,
        override_reason: str | None = None,
    ) -> tuple[bool, CandidateTicket | None, str]:
        """Authorize dispatch for a specific candidate.

        Enforces priority order. If a higher priority candidate has not been
        dispatched or completed, requires an explicit, non-empty override reason.
        """
        ticket = self.tickets_by_candidate.get(candidate_id)
        if ticket is None:
            return False, None, f"Unknown candidate '{candidate_id}'; no ticket issued."

        if ticket.status in ("COMPLETED", "DISPATCHED"):
            return True, ticket, f"Candidate already {ticket.status.lower()}."

        # Find higher priority tickets that are still pending
        higher_priority_pending = [
            t
            for t in self.tickets.values()
            if t.dispatch_priority < ticket.dispatch_priority and t.status in ("ISSUED", "PENDING")
        ]

        if higher_priority_pending:
            if not override_reason or not override_reason.strip():
                highest_pending = min(higher_priority_pending, key=lambda t: t.dispatch_priority)
                reason_msg = (
                    f"Unranked dispatch rejected: higher priority candidate "
                    f"'{highest_pending.candidate_id}' (rank {highest_pending.dispatch_priority}) "
                    f"is pending and no authorized override reason was provided."
                )
                ticket.status = "BLOCKED"
                return False, None, reason_msg

            # Authorized override
            ticket.status = "OVERRIDDEN"
            ticket.override_reason = override_reason.strip()
            ticket.dispatched_order = self._next_dispatched_order
            self._next_dispatched_order += 1
            ticket.dispatched_at = _utc_now()
            self.dispatch_sequence.append(ticket.candidate_id)
            return True, ticket, f"Authorized priority override: {override_reason.strip()}"

        # Standard priority dispatch
        ticket.status = "DISPATCHED"
        ticket.dispatched_order = self._next_dispatched_order
        self._next_dispatched_order += 1
        ticket.dispatched_at = _utc_now()
        self.dispatch_sequence.append(ticket.candidate_id)
        return True, ticket, "Authorized according to priority rank."

    def record_tool_invocation(
        self, candidate_id_or_ticket_id: str, tool_invocation_id: str
    ) -> bool:
        """Bind an executed security tool invocation ID to the candidate's ticket."""
        ticket = self.tickets.get(candidate_id_or_ticket_id)
        if ticket is None:
            ticket = self.tickets_by_candidate.get(candidate_id_or_ticket_id)
        if ticket is not None and tool_invocation_id:
            ticket.tool_invocation_ids.append(tool_invocation_id)
            return True
        return False

    def complete_ticket(
        self,
        candidate_id_or_ticket_id: str,
        outcome: str = "completed",
    ) -> bool:
        """Mark a candidate ticket completed."""
        ticket = self.tickets.get(candidate_id_or_ticket_id)
        if ticket is None:
            ticket = self.tickets_by_candidate.get(candidate_id_or_ticket_id)
        if ticket is not None:
            ticket.status = "COMPLETED"
            ticket.outcome = outcome
            ticket.completed_at = _utc_now()
            return True
        return False

    def audit_trail(self) -> dict[str, Any]:
        """Return the complete scheduler audit trail."""
        return {
            "run_id": self.run_id,
            "original_order": list(self.original_order),
            "ranked_order": list(self.ranked_order),
            "ranking_changed": self.ranking_changed,
            "dispatch_sequence": list(self.dispatch_sequence),
            "tickets": [t.to_dict() for t in self.tickets.values()],
            "overrides": [
                t.to_dict() for t in self.tickets.values() if t.override_reason is not None
            ],
        }
