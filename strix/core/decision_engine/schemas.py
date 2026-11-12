"""Schemas and state models for the GAP-2 Decision Engine."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class CandidateState(str, Enum):
    PENDING = "PENDING"
    DISCOVERED = "DISCOVERED"
    ATTEMPTING = "ATTEMPTING"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    VALIDATED = "VALIDATED"
    ABANDONED = "ABANDONED"
    BLOCKED = "BLOCKED"
    NOT_TESTED = "NOT_TESTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class VerificationState(str, Enum):
    DISCOVERED = "Discovered"
    CANDIDATE = "Candidate"
    UNDER_INVESTIGATION = "Under investigation"
    EXPLOITATION_ATTEMPTED = "Exploitation attempted"
    VERIFIED = "Verified"
    UNCONFIRMED = "Unconfirmed"
    FALSE_POSITIVE = "False positive"
    BLOCKED = "Blocked"
    INCONCLUSIVE = "Inconclusive"


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
    probe_outcome: str | None = None
    result: str | None = None


class PivotEvent(BaseModel):
    timestamp: str = Field(default_factory=_utc_now)
    type: str  # INIT, ADVANCE, REDIRECT, ABANDON, COMPLETE, GAP2_PIVOT
    event: str | None = None
    candidate_id: str | None = None
    attempt: int | None = None
    max_attempts: int | None = None
    reason: str | None = None
    to_candidate: str | None = None
    next_candidate: str | None = None
    probe_outcome: str | None = None
    pivot_executed: bool = True
    result: str | None = None
    message: str | None = None


class ActionCandidate(BaseModel):
    id: str
    name: str = ""
    target: str = ""
    endpoint: str = "/"
    parameter: str | None = None
    probability: float = 0.5
    severity: str = "medium"
    cvss_score: float = 5.0
    cwe_id: str = "CWE-200"
    state: CandidateState = CandidateState.PENDING
    verification_state: VerificationState = VerificationState.CANDIDATE
    attempts: int = 0
    max_attempts: int = 2
    outcome: Outcome | None = None
    evidence_hash: str | None = None
    detail: str = ""
    reproducible_request: str | None = None
    reproducible_response: str | None = None
    verification_procedure: str | None = None
    demonstrated_impact: str | None = None
    timestamp: str | None = None
