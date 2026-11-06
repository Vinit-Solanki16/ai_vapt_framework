"""Schemas and state models for the GAP-2 Decision Engine."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class CandidateState(str, Enum):
    PENDING = "PENDING"
    ATTEMPTING = "ATTEMPTING"
    VALIDATED = "VALIDATED"
    ABANDONED = "ABANDONED"


class Outcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAIL_TIMEOUT = "FAIL_TIMEOUT"
    FAIL_BLOCKED = "FAIL_BLOCKED"
    FAIL_ERROR = "FAIL_ERROR"


class PivotActionType(str, Enum):
    RETRY = "RETRY"
    ADVANCE = "ADVANCE"
    REDIRECT = "REDIRECT"
    COMPLETE = "COMPLETE"


class PivotAction(BaseModel):
    action: PivotActionType
    candidate_id: str
    attempt: int
    max_attempts: int
    to_candidate: str | None = None
    reason: str | None = None


class PivotEvent(BaseModel):
    timestamp: str = Field(default_factory=_utc_now)
    type: str  # INIT, ADVANCE, REDIRECT, ABANDON, COMPLETE
    candidate_id: str | None = None
    attempt: int | None = None
    max_attempts: int | None = None
    reason: str | None = None
    to_candidate: str | None = None


class ActionCandidate(BaseModel):
    id: str
    name: str = ""
    target: str = ""
    probability: float = 0.5
    severity: str = "medium"
    state: CandidateState = CandidateState.PENDING
    attempts: int = 0
    max_attempts: int = 2
    outcome: Outcome | None = None
    evidence_hash: str | None = None
    detail: str = ""
