"""Event models for VAPT platform."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid


class RunState(str, Enum):
    """Canonical run lifecycle states."""
    CREATED = "CREATED"
    INGESTING = "INGESTING"
    NORMALIZING = "NORMALIZING"
    ASSESSING = "ASSESSING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    REPORTING = "REPORTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EventType(str, Enum):
    """Canonical event types."""
    RUN_CREATED = "RUN_CREATED"
    FINDINGS_INGESTED = "FINDINGS_INGESTED"
    FINDINGS_NORMALIZED = "FINDINGS_NORMALIZED"
    CANDIDATES_GENERATED = "CANDIDATES_GENERATED"
    ASSESSMENT_COMPLETED = "ASSESSMENT_COMPLETED"
    DECISION_MADE = "DECISION_MADE"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    ATTEMPT_COMPLETED = "ATTEMPT_COMPLETED"
    PIVOT_OCCURRED = "PIVOT_OCCURRED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    EVIDENCE_CAPTURED = "EVIDENCE_CAPTURED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"


# Valid state transitions
VALID_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.CREATED: {RunState.INGESTING, RunState.FAILED, RunState.CANCELLED},
    RunState.INGESTING: {RunState.NORMALIZING, RunState.FAILED, RunState.CANCELLED},
    RunState.NORMALIZING: {RunState.ASSESSING, RunState.FAILED, RunState.CANCELLED},
    RunState.ASSESSING: {RunState.PLANNING, RunState.FAILED, RunState.CANCELLED},
    RunState.PLANNING: {RunState.EXECUTING, RunState.FAILED, RunState.CANCELLED},
    RunState.EXECUTING: {RunState.VERIFYING, RunState.FAILED, RunState.CANCELLED},
    RunState.VERIFYING: {RunState.REPORTING, RunState.FAILED, RunState.CANCELLED},
    RunState.REPORTING: {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED},
    RunState.COMPLETED: set(),  # Terminal state
    RunState.FAILED: set(),  # Terminal state
    RunState.CANCELLED: set(),  # Terminal state
}


@dataclass
class Event:
    """Immutable event record."""
    run_id: str
    event_type: EventType
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


def is_valid_transition(from_state: RunState, to_state: RunState) -> bool:
    """Check if a state transition is valid."""
    if from_state not in VALID_TRANSITIONS:
        return False
    return to_state in VALID_TRANSITIONS[from_state]
