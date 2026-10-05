"""Persistent run model."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class RunStatus(str, Enum):
    """Status of a VAPT run."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class PersistentRun:
    """A persisted VAPT run.

    Contains all domain-level execution state needed to reconstruct
    a completed run. Presentation-specific data is reconstructable
    from this state.
    """
    run_id: str
    scenario: str
    mode: str
    status: str = RunStatus.PENDING.value
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Execution state
    final_status: str = "UNKNOWN"
    candidates: list[dict] = field(default_factory=list)
    execution_results: list[dict] = field(default_factory=list)
    decision_trace: list[str] = field(default_factory=list)
    total_attempts: int = 0
    pivot_count: int = 0
    candidates_processed: list[str] = field(default_factory=list)
    evidence_tier: str = "SIMULATED"
    assessment: dict[str, Any] = field(default_factory=dict)
    safety_notice: str = ""
    
    # Request context
    target: Optional[str] = None
    port: int = 8080
    path: str = "/vuln"
    max_attempts: int = 2
    assessor_mode: str = "deterministic"
    assessor_provider: str = "ollama"

    # Web-target assessment context (Phase 32; absent for older runs)
    target_url: Optional[str] = None
    assessment_type: str = "scenario"
    
    # Pipeline summary
    pipeline_summary: dict[str, Any] = field(default_factory=dict)
    scored_candidates: list[dict] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "run_id": self.run_id,
            "scenario": self.scenario,
            "mode": self.mode,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "final_status": self.final_status,
            "candidates": self.candidates,
            "execution_results": self.execution_results,
            "decision_trace": self.decision_trace,
            "total_attempts": self.total_attempts,
            "pivot_count": self.pivot_count,
            "candidates_processed": self.candidates_processed,
            "evidence_tier": self.evidence_tier,
            "assessment": self.assessment,
            "safety_notice": self.safety_notice,
            "target": self.target,
            "port": self.port,
            "path": self.path,
            "max_attempts": self.max_attempts,
            "assessor_mode": self.assessor_mode,
            "assessor_provider": self.assessor_provider,
            "target_url": self.target_url,
            "assessment_type": self.assessment_type,
            "pipeline_summary": self.pipeline_summary,
            "scored_candidates": self.scored_candidates,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersistentRun":
        """Deserialize from dictionary."""
        return cls(
            run_id=data.get("run_id", ""),
            scenario=data.get("scenario", ""),
            mode=data.get("mode", "simulation"),
            status=data.get("status", RunStatus.PENDING.value),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            final_status=data.get("final_status", "UNKNOWN"),
            candidates=data.get("candidates", []),
            execution_results=data.get("execution_results", []),
            decision_trace=data.get("decision_trace", []),
            total_attempts=data.get("total_attempts", 0),
            pivot_count=data.get("pivot_count", 0),
            candidates_processed=data.get("candidates_processed", []),
            evidence_tier=data.get("evidence_tier", "SIMULATED"),
            assessment=data.get("assessment", {}),
            safety_notice=data.get("safety_notice", ""),
            target=data.get("target"),
            port=data.get("port", 8080),
            path=data.get("path", "/vuln"),
            max_attempts=data.get("max_attempts", 2),
            assessor_mode=data.get("assessor_mode", "deterministic"),
            assessor_provider=data.get("assessor_provider", "ollama"),
            target_url=data.get("target_url"),
            assessment_type=data.get("assessment_type", "scenario"),
            pipeline_summary=data.get("pipeline_summary", {}),
            scored_candidates=data.get("scored_candidates", []),
        )
