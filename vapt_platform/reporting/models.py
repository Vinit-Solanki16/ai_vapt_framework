"""Report model for VAPT platform.

Contains all information needed for professional reporting.
Built by ReportBuilder from DomainResult or PersistentRun.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class EvidenceTier(str, Enum):
    """Evidence tier classification."""
    SIMULATED = "SIMULATED"
    OBSERVED_LOCAL = "OBSERVED_LOCAL"
    DOCKER_OBSERVED = "DOCKER_OBSERVED"
    CONTROLLED_VALIDATION = "CONTROLLED_VALIDATION"
    UNKNOWN = "UNKNOWN"


@dataclass
class ReportMetadata:
    """Run metadata for reports."""
    run_id: str = ""
    scenario: str = ""
    mode: str = "simulation"
    final_status: str = "UNKNOWN"
    evidence_tier: str = EvidenceTier.SIMULATED.value
    max_attempts: int = 2
    total_attempts: int = 0
    pivot_count: int = 0
    candidates_processed: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    run_created_at: str = ""
    run_updated_at: str = ""


@dataclass
class CandidateReport:
    """Report-level candidate information."""
    candidate_id: str
    probability: float = 0.0
    quality_rank: str = "PENDING"
    assessed: bool = False
    attempted: bool = False
    execution_outcome: str = ""
    ground_truth: str = ""
    score: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionReport:
    """Report-level execution result."""
    candidate_id: str
    outcome: str
    detail: str = ""
    attempt_number: int = 0


@dataclass
class PivotEvent:
    """Report-level pivot event."""
    event_type: str  # ABANDON, REDIRECT, COMPLETE
    details: str


@dataclass
class ReportModel:
    """Canonical report model.
    
    Contains all information needed to generate reports in any format.
    Built by ReportBuilder from domain state or persisted runs.
    """
    metadata: ReportMetadata = field(default_factory=ReportMetadata)
    
    # Executive summary
    executive_summary: str = ""
    
    # Findings and candidates
    candidates: list[CandidateReport] = field(default_factory=list)
    
    # Execution results
    execution_results: list[ExecutionReport] = field(default_factory=list)
    
    # Decision trace
    decision_trace: list[str] = field(default_factory=list)
    
    # Pivot events
    pivot_events: list[PivotEvent] = field(default_factory=list)
    
    # Per-candidate attempt counts
    attempts_per_candidate: dict[str, int] = field(default_factory=dict)
    
    # Evidence
    evidence_tier: str = EvidenceTier.SIMULATED.value
    evidence_description: str = ""
    safety_notice: str = ""
    
    # Assessment
    assessment: dict[str, Any] = field(default_factory=dict)
    
    # Pipeline summary
    pipeline_summary: dict[str, Any] = field(default_factory=dict)
    
    # Target/scope
    target: Optional[str] = None
    port: int = 8080
    path: str = "/vuln"
    
    # Limitations
    limitations: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "metadata": {
                "run_id": self.metadata.run_id,
                "scenario": self.metadata.scenario,
                "mode": self.metadata.mode,
                "final_status": self.metadata.final_status,
                "evidence_tier": self.metadata.evidence_tier,
                "max_attempts": self.metadata.max_attempts,
                "total_attempts": self.metadata.total_attempts,
                "pivot_count": self.metadata.pivot_count,
                "candidates_processed": self.metadata.candidates_processed,
                "generated_at": self.metadata.generated_at,
                "run_created_at": self.metadata.run_created_at,
                "run_updated_at": self.metadata.run_updated_at,
            },
            "executive_summary": self.executive_summary,
            "candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "probability": c.probability,
                    "quality_rank": c.quality_rank,
                    "assessed": c.assessed,
                    "attempted": c.attempted,
                    "execution_outcome": c.execution_outcome,
                    "ground_truth": c.ground_truth,
                    "score": c.score,
                }
                for c in self.candidates
            ],
            "execution_results": [
                {
                    "candidate_id": e.candidate_id,
                    "outcome": e.outcome,
                    "detail": e.detail,
                    "attempt_number": e.attempt_number,
                }
                for e in self.execution_results
            ],
            "decision_trace": self.decision_trace,
            "pivot_events": [
                {"event_type": p.event_type, "details": p.details}
                for p in self.pivot_events
            ],
            "attempts_per_candidate": self.attempts_per_candidate,
            "evidence_tier": self.evidence_tier,
            "evidence_description": self.evidence_description,
            "safety_notice": self.safety_notice,
            "assessment": self.assessment,
            "pipeline_summary": self.pipeline_summary,
            "target": self.target,
            "port": self.port,
            "path": self.path,
            "limitations": self.limitations,
        }
