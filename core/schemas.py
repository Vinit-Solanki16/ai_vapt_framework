"""Shared Pydantic schemas and enums for the AI VAPT Framework.

Centralising these fixes two real bugs from the prototype:
1. `usability_rank` was a loose `str`, which allowed the LLM to return
   garbage like "}" (seen during testing). It is now a constrained `Literal`.
2. The agent status / pivot signals are now explicitly typed enums so the
   LangGraph router cannot drift into an undefined state.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class UsabilityRank(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AgentStatus(str, Enum):
    ASSESSING = "ASSESSING"
    TESTING = "TESTING"
    SUCCESS = "SUCCESS"
    PIVOT = "PIVOT"
    COMPLETED = "COMPLETED"


# ---------------------------------------------------------------------------
# Exploit quality scoring matrix (Phase 1, Task 1.3)
# ---------------------------------------------------------------------------
class ExploitAssessment(BaseModel):
    """Structured output contract enforced on the LLM.

    The schema mirrors the literature gap identified by Lu et al. (2024) on
    PoC quality: we grade concrete, operational factors rather than a single
    vague reliability number.
    """

    exploit_found: bool = Field(
        description="Whether usable public exploit code was located for the CVE."
    )
    syntax_valid: bool = Field(
        description="Does the code parse / appear syntactically valid (no obvious errors)."
    )
    os_dependencies: str = Field(
        description="List of non-default OS/runtime dependencies required (e.g. 'paramiko', 'root')."
    )
    privileges_required: Literal["none", "user", "root"] = Field(
        description="Execution privilege level the exploit needs to succeed."
    )
    network_noise: Literal["low", "medium", "high"] = Field(
        description="Detectability/stealth cost: how loud the exploit is on the wire."
    )
    complexity_score: int = Field(
        ge=1, le=10,
        description="Operational complexity from 1 (trivial) to 10 (extremely complex).",
    )
    prerequisites_met: bool = Field(
        description="Whether standard execution prerequisites are satisfied in this environment."
    )
    usability_rank: UsabilityRank = Field(
        description="Aggregate usability: HIGH, MEDIUM, or LOW based on reliability and effort."
    )
    reasoning: str = Field(
        description="Short concise justification for the assigned scores."
    )


# ---------------------------------------------------------------------------
# Execution outcome (replaces the hardcoded execution_success = False)
# ---------------------------------------------------------------------------
class ExecutionOutcome(str, Enum):
    SUCCESS = "SUCCESS"          # exploitable, validated
    FAIL_TIMEOUT = "FAIL_TIMEOUT"
    FAIL_SYNTAX = "FAIL_SYNTAX"
    FAIL_DEPENDENCY = "FAIL_DEPENDENCY"
    FAIL_NO_TARGET = "FAIL_NO_TARGET"
    SKIPPED = "SKIPPED"         # skipped for safety / low rank


class ExecutionResult(BaseModel):
    cve: str
    outcome: ExecutionOutcome
    request_count: int = 0
    detail: str = ""


# ---------------------------------------------------------------------------
# Finding enrichment passed between modules
# ---------------------------------------------------------------------------
class Finding(BaseModel):
    cve: str = Field(default="UNKNOWN-CVE", description="CVE identifier, or a derived key if none present in the scan.")
    port: Optional[int] = None
    service: Optional[str] = None
    description: Optional[str] = None
    epss_score: float = 0.0
    # populated later by the assessor / executor
    usability_rank: Optional[UsabilityRank] = None
    assessed: bool = False
    executed: bool = False
    execution_outcome: Optional[ExecutionOutcome] = None

    def priority_score(self) -> float:
        """Combine real-world probability (EPSS) with usability.

        EPSS is 0..1. Usability contributes 0..1 (HIGH=1, MEDIUM=0.6, LOW=0.3).
        Used to order the agent's attack path (Deng et al. Type-B pivot).
        """
        u = {UsabilityRank.HIGH: 1.0, UsabilityRank.MEDIUM: 0.6, UsabilityRank.LOW: 0.3}.get(
            self.usability_rank, 0.0
        )
        return round(self.epss_score * (0.5 + 0.5 * u), 4)


def finding_from_dict(d: dict) -> Finding:
    cve = d.get("cve") or "UNKNOWN-CVE"
    return Finding(
        cve=cve,
        port=d.get("port"),
        service=d.get("service"),
        description=d.get("description"),
        epss_score=float(d.get("epss_score", 0.0)),
    )


def findings_from_state(raw) -> List["Finding"]:
    """Rebuild Finding objects from a persisted state list (dicts OR Findings)."""
    out = []
    for d in raw:
        if isinstance(d, Finding):
            out.append(d)
        else:
            out.append(Finding(**d))
    return out
