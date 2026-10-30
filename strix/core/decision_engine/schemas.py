"""Schemas and state models for the GAP-2 Decision Engine."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    to_candidate: Optional[str] = None
    reason: Optional[str] = None


class PivotEvent(BaseModel):
    timestamp: str = Field(default_factory=_utc_now)
    type: str  # INIT, ADVANCE, REDIRECT, ABANDON, COMPLETE
    candidate_id: Optional[str] = None
    attempt: Optional[int] = None
    max_attempts: Optional[int] = None
    reason: Optional[str] = None
    to_candidate: Optional[str] = None


class ActionCandidate(BaseModel):
    id: str
    name: str = ""
    target: str = ""
    probability: float = 0.5
    severity: str = "medium"
    state: CandidateState = CandidateState.PENDING
    attempts: int = 0
    max_attempts: int = 2
    outcome: Optional[Outcome] = None
    evidence_hash: Optional[str] = None
    detail: str = ""

