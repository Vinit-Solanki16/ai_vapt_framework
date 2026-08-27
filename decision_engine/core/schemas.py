"""Domain-independent schemas for the General Autonomous Decision & Pivot Engine.

These are a deliberate COPY + REFACTOR of the original VAPT-specific
``core/schemas.py``. Everything here is domain-agnostic: an "action candidate"
is any task the engine might attempt (a PoC exploit is just one example).

The decision engine operates ONLY on these types. The VAPT domain is attached
later via ``decision_engine/adapters/vapt_adapter.py``.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class QualityRank(str, Enum):
    """Pre-execution usability / quality of a candidate action (Gap-1 output)."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


QUALITY_WEIGHT = {QualityRank.HIGH: 1.0, QualityRank.MEDIUM: 0.6, QualityRank.LOW: 0.3}


class EngineStatus(str, Enum):
    ASSESSING = "ASSESSING"
    TESTING = "TESTING"
    SUCCESS = "SUCCESS"
    PIVOT = "PIVOT"
    COMPLETED = "COMPLETED"


class Outcome(str, Enum):
    """Generic execution outcome. Mirrors VAPT ExecutionOutcome in spirit."""

    SUCCESS = "SUCCESS"          # validated / worked
    FAIL_TIMEOUT = "FAIL_TIMEOUT"
    FAIL_SYNTAX = "FAIL_SYNTAX"
    FAIL_DEPENDENCY = "FAIL_DEPENDENCY"
    FAIL_NO_TARGET = "FAIL_NO_TARGET"
    SKIPPED = "SKIPPED"         # skipped for safety / low quality


class ExecutionResult(BaseModel):
    candidate_id: str
    outcome: Outcome
    request_count: int = 0
    detail: str = ""


class ActionCandidate(BaseModel):
    """A single candidate action for the engine to (optionally) attempt.

    Fields:
      id            - stable identifier (e.g. a CVE, or any task key)
      probability   - real-world probability signal in 0..1 (e.g. EPSS)
      quality_rank  - pre-execution usability (Gap-1); filled by assessor
      assessed      - whether the assessor has run
      attempted     - whether execution was attempted
      execution_outcome - observed/ground-truth outcome
      ground_truth  - OPTIONAL ground-truth label used ONLY by simulation backend
    """

    id: str = Field(default="UNKNOWN", description="Stable candidate identifier.")
    probability: float = 0.0
    quality_rank: Optional[QualityRank] = None
    assessed: bool = False
    attempted: bool = False
    execution_outcome: Optional[Outcome] = None
    # simulation-only ground truth (never trusted by a real observed backend)
    ground_truth: Optional[Outcome] = None

    def priority_score(self) -> float:
        """priority = probability * (0.5 + 0.5 * quality).

        Mirrors the VAPT priority_score formula; domain-independent so the
        engine's ordering logic is demonstrably not CVE-specific.
        """
        u = QUALITY_WEIGHT[self.quality_rank] if self.quality_rank else 0.0
        return round(self.probability * (0.5 + 0.5 * u), 4)


def candidate_from_dict(d: dict) -> ActionCandidate:
    c = ActionCandidate(
        id=d.get("id") or "UNKNOWN",
        probability=float(d.get("probability", 0.0)),
        ground_truth=Outcome(d["ground_truth"]) if d.get("ground_truth") else None,
    )
    return c


def candidates_from_state(raw) -> List["ActionCandidate"]:
    out = []
    for d in raw:
        if isinstance(d, ActionCandidate):
            out.append(d)
        else:
            out.append(ActionCandidate(**d))
    return out
