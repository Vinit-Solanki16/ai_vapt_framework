"""Schemas and state models for the GAP-2 Decision Engine."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class CandidateState(str, Enum):
    DISCOVERED = "DISCOVERED"
    CANDIDATE = "CANDIDATE"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    PROBE_EXECUTED = "PROBE_EXECUTED"
    VALIDATED_OBSERVATION = "VALIDATED_OBSERVATION"
    EXPLOITATION_ATTEMPTED = "EXPLOITATION_ATTEMPTED"
    VERIFIED_VULNERABILITY = "VERIFIED_VULNERABILITY"
    RULED_OUT = "RULED_OUT"
    RULED_OUT_WITH_EVIDENCE = "RULED_OUT_WITH_EVIDENCE"
    ABANDONED = "ABANDONED"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    NOT_TESTED = "NOT_TESTED"
    # Backwards compatibility aliases
    IDENTIFIED = "IDENTIFIED"
    DISPATCHED = "DISPATCHED"
    PENDING = "PENDING"
    ATTEMPTING = "ATTEMPTING"
    VALIDATED = "VALIDATED"


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
    model_config = ConfigDict(extra="allow")

    timestamp: str = Field(default_factory=_utc_now)
    type: str = "GAP2_PIVOT"  # INIT, ADVANCE, REDIRECT, ABANDON, COMPLETE, GAP2_PIVOT
    event: str | None = None
    candidate_id: str | None = None
    attempt: int | None = None
    max_attempts: int | None = None
    reason: str | None = None
    to_candidate: str | None = None
    next_candidate: str | None = None
    probe_outcome: str | None = None
    pivot_executed: bool = False
    pivot_status: str | None = None
    tool_invocation_id: str | None = None
    result: str | None = None
    message: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_gap2_event(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Backward compatibility: populate type if only event exists, and vice-versa
            if "type" not in data and "event" in data:
                data["type"] = data.get("event") or "GAP2_PIVOT"
            if "event" not in data and "type" in data:
                data["event"] = data.get("type") or "GAP2_PIVOT"
            if "to_candidate" not in data and "next_candidate" in data:
                data["to_candidate"] = data["next_candidate"]
            if "next_candidate" not in data and "to_candidate" in data:
                data["next_candidate"] = data["to_candidate"]
        return data


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
    # Probe & Execution Audit Fields
    tool_selected: str | None = None
    tool_invocation_id: str | None = None
    sanitized_request: str | None = None
    tool_result: str | None = None
    http_status: int | None = None
    evidence_reference: str | None = None
    verification_contract: str | None = None
    verification_result: str | None = None
    retry_eligibility: bool = False
    state_transition_reason: str | None = None
    dispatched_at: str | None = None
    agent_assignment: str | None = None
