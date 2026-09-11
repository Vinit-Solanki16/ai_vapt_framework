"""Report builder for VAPT platform.

Builds ReportModel from:
- DomainResult (immediate execution)
- PersistentRun (persisted execution)
"""
from __future__ import annotations

from typing import Any, Optional

from .models import (
    ReportModel,
    ReportMetadata,
    CandidateReport,
    ExecutionReport,
    PivotEvent,
    EvidenceTier,
)


def _get_evidence_tier(mode: str) -> str:
    """Map execution mode to evidence tier."""
    mode_map = {
        "simulation": EvidenceTier.SIMULATED.value,
        "lab_loopback": EvidenceTier.OBSERVED_LOCAL.value,
        "lab_docker": EvidenceTier.DOCKER_OBSERVED.value,
        "lab": EvidenceTier.DOCKER_OBSERVED.value,
        "real": EvidenceTier.CONTROLLED_VALIDATION.value,
    }
    return mode_map.get(mode.lower(), EvidenceTier.UNKNOWN.value)


def _get_evidence_description(tier: str) -> str:
    """Get human-readable description of evidence tier."""
    descriptions = {
        EvidenceTier.SIMULATED.value: "Outcomes resolved from supplied demo ground truth (labels). No real execution occurred.",
        EvidenceTier.OBSERVED_LOCAL.value: "Outcomes observed from loopback (127.0.0.1) target. No external systems were targeted.",
        EvidenceTier.DOCKER_OBSERVED.value: "Outcomes observed from Docker-isolated vulnerability emulator. No external systems were targeted.",
        EvidenceTier.CONTROLLED_VALIDATION.value: "Outcomes from live target systems. Requires proper authorization.",
    }
    return descriptions.get(tier, "Unknown evidence tier")


def _get_safety_notice(tier: str) -> str:
    """Get safety notice for evidence tier."""
    notices = {
        EvidenceTier.SIMULATED.value: (
            "SIMULATION MODE — Outcomes are resolved from supplied demo ground truth. "
            "No real vulnerabilities were validated."
        ),
        EvidenceTier.OBSERVED_LOCAL.value: (
            "LOOPBACK OBSERVED MODE — Outcomes are from loopback (127.0.0.1) target. "
            "No external systems were targeted."
        ),
        EvidenceTier.DOCKER_OBSERVED.value: (
            "DOCKER OBSERVED MODE — Outcomes are from Docker-isolated emulator responses. "
            "No external systems were targeted."
        ),
        EvidenceTier.CONTROLLED_VALIDATION.value: (
            "REAL MODE — Outcomes are from live systems. "
            "Ensure proper authorization before execution."
        ),
    }
    return notices.get(tier, "Unknown evidence tier")


def _extract_pivot_events(logs: list[str]) -> list[PivotEvent]:
    """Extract pivot events from engine logs."""
    events = []
    for log in logs:
        if "[Pivot]" in log:
            event_type = "UNKNOWN"
            if "Abandoning" in log:
                event_type = "ABANDON"
            elif "Redirected" in log:
                event_type = "REDIRECT"
            elif "All candidates processed" in log:
                event_type = "COMPLETE"
            events.append(PivotEvent(event_type=event_type, details=log.strip()))
    return events


def _count_attempts_per_candidate(results: list[dict]) -> dict[str, int]:
    """Count execution attempts per candidate."""
    counts = {}
    for result in results:
        cid = result.get("candidate_id", "unknown")
        counts[cid] = counts.get(cid, 0) + 1
    return counts


class ReportBuilder:
    """Builds ReportModel from domain state or persisted runs."""

    def from_domain_result(
        self,
        domain: Any,
        request: Any = None,
        pipeline_summary: dict[str, Any] | None = None,
    ) -> ReportModel:
        """Build report from DomainResult.
        
        Args:
            domain: DomainResult from VAPTApplication.run()
            request: Optional VAPTRequest for context
            pipeline_summary: Optional pipeline summary data
            
        Returns:
            ReportModel ready for rendering
        """
        evidence_tier = _get_evidence_tier(domain.mode)
        
        # Build candidates
        candidates = []
        for c in domain.candidates:
            candidates.append(CandidateReport(
                candidate_id=c.get("id", "?"),
                probability=c.get("probability", 0.0),
                quality_rank=c.get("quality_rank", "PENDING") or "PENDING",
                assessed=c.get("assessed", False),
                attempted=c.get("attempted", False),
                execution_outcome=c.get("execution_outcome", "") or "",
                ground_truth=c.get("ground_truth", "") or "",
                score=c.get("_score", {}),
            ))
        
        # Build execution results
        execution_results = []
        for i, r in enumerate(domain.execution_results):
            execution_results.append(ExecutionReport(
                candidate_id=r.get("candidate_id", "?"),
                outcome=r.get("outcome", "?"),
                detail=r.get("detail", ""),
                attempt_number=i + 1,
            ))
        
        # Build metadata
        metadata = ReportMetadata(
            run_id=domain.run_id,
            scenario=domain.scenario,
            mode=domain.mode,
            final_status=domain.final_status,
            evidence_tier=evidence_tier,
            max_attempts=request.max_attempts if request else 2,
            total_attempts=domain.total_attempts,
            pivot_count=domain.pivot_count,
            candidates_processed=domain.candidates_processed,
        )
        
        # Build report
        report = ReportModel(
            metadata=metadata,
            executive_summary=self._build_executive_summary(domain, evidence_tier),
            candidates=candidates,
            execution_results=execution_results,
            decision_trace=domain.decision_trace,
            pivot_events=_extract_pivot_events(domain.decision_trace),
            attempts_per_candidate=_count_attempts_per_candidate(domain.execution_results),
            evidence_tier=evidence_tier,
            evidence_description=_get_evidence_description(evidence_tier),
            safety_notice=_get_safety_notice(evidence_tier),
            assessment=domain.assessment,
            pipeline_summary=pipeline_summary or {},
            target=request.target if request else None,
            port=request.port if request else 8080,
            path=request.path if request else "/vuln",
            limitations=self._build_limitations(evidence_tier),
        )
        
        return report

    def from_persisted_run(self, run: Any) -> ReportModel:
        """Build report from PersistentRun.
        
        Args:
            run: PersistentRun from RunRepository
            
        Returns:
            ReportModel ready for rendering
        """
        evidence_tier = _get_evidence_tier(run.mode)
        
        # Build candidates
        candidates = []
        for c in run.candidates:
            candidates.append(CandidateReport(
                candidate_id=c.get("id", "?"),
                probability=c.get("probability", 0.0),
                quality_rank=c.get("quality_rank", "PENDING") or "PENDING",
                assessed=c.get("assessed", False),
                attempted=c.get("attempted", False),
                execution_outcome=c.get("execution_outcome", "") or "",
                ground_truth=c.get("ground_truth", "") or "",
                score=c.get("_score", {}),
            ))
        
        # Build execution results
        execution_results = []
        for i, r in enumerate(run.execution_results):
            execution_results.append(ExecutionReport(
                candidate_id=r.get("candidate_id", "?"),
                outcome=r.get("outcome", "?"),
                detail=r.get("detail", ""),
                attempt_number=i + 1,
            ))
        
        # Build metadata
        metadata = ReportMetadata(
            run_id=run.run_id,
            scenario=run.scenario,
            mode=run.mode,
            final_status=run.final_status,
            evidence_tier=evidence_tier,
            max_attempts=run.max_attempts,
            total_attempts=run.total_attempts,
            pivot_count=run.pivot_count,
            candidates_processed=run.candidates_processed,
            run_created_at=run.created_at,
            run_updated_at=run.updated_at,
        )
        
        # Build report
        report = ReportModel(
            metadata=metadata,
            executive_summary=self._build_executive_summary_from_run(run, evidence_tier),
            candidates=candidates,
            execution_results=execution_results,
            decision_trace=run.decision_trace,
            pivot_events=_extract_pivot_events(run.decision_trace),
            attempts_per_candidate=_count_attempts_per_candidate(run.execution_results),
            evidence_tier=evidence_tier,
            evidence_description=_get_evidence_description(evidence_tier),
            safety_notice=run.safety_notice or _get_safety_notice(evidence_tier),
            assessment=run.assessment,
            pipeline_summary=run.pipeline_summary,
            target=run.target,
            port=run.port,
            path=run.path,
            limitations=self._build_limitations(evidence_tier),
        )
        
        return report

    def _build_executive_summary(self, domain: Any, evidence_tier: str) -> str:
        """Build executive summary from domain result."""
        parts = []
        
        parts.append(f"Scenario '{domain.scenario}' completed with status: {domain.final_status}.")
        parts.append(f"Evidence tier: {evidence_tier}.")
        
        if domain.total_attempts > 0:
            parts.append(f"Total execution attempts: {domain.total_attempts}.")
        
        if domain.pivot_count > 0:
            parts.append(f"Pivot events: {domain.pivot_count}.")
        
        if domain.candidates_processed:
            parts.append(f"Candidates processed: {len(domain.candidates_processed)}.")
        
        return " ".join(parts)

    def _build_executive_summary_from_run(self, run: Any, evidence_tier: str) -> str:
        """Build executive summary from persisted run."""
        parts = []
        
        parts.append(f"Scenario '{run.scenario}' completed with status: {run.final_status}.")
        parts.append(f"Evidence tier: {evidence_tier}.")
        
        if run.total_attempts > 0:
            parts.append(f"Total execution attempts: {run.total_attempts}.")
        
        if run.pivot_count > 0:
            parts.append(f"Pivot events: {run.pivot_count}.")
        
        if run.candidates_processed:
            parts.append(f"Candidates processed: {len(run.candidates_processed)}.")
        
        return " ".join(parts)

    def _build_limitations(self, evidence_tier: str) -> list[str]:
        """Build limitations list based on evidence tier."""
        limitations = []
        
        if evidence_tier == EvidenceTier.SIMULATED.value:
            limitations.append("This run used simulated outcomes from ground-truth labels.")
            limitations.append("No real vulnerabilities were validated.")
            limitations.append("Results demonstrate workflow behavior, not real-world effectiveness.")
        elif evidence_tier == EvidenceTier.OBSERVED_LOCAL.value:
            limitations.append("This run used loopback (127.0.0.1) targets only.")
            limitations.append("No external systems were targeted.")
        elif evidence_tier == EvidenceTier.DOCKER_OBSERVED.value:
            limitations.append("This run used Docker-isolated emulator targets.")
            limitations.append("No external systems were targeted.")
            limitations.append("Emulator responses may not represent real-world behavior.")
        elif evidence_tier == EvidenceTier.CONTROLLED_VALIDATION.value:
            limitations.append("This run targeted live systems.")
            limitations.append("Results are specific to the authorized target scope.")
        
        limitations.append("This is a research prototype, not a production tool.")
        
        return limitations
