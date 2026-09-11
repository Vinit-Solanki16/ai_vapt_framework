"""Unified VAPT application workflow service.

This is the single canonical workflow that CLI, API, and GUI must use.
It orchestrates the full pipeline from finding ingestion to report generation.

Architecture:
    CLI / API / GUI
           ↓
    VAPTApplication.run(request)
           ↓
    Finding Ingestion → Normalization → Candidate Generation
           ↓
    AI Assessment (pluggable)
           ↓
    Decision Engine (research core)
           ↓
    Safety-controlled Executor
           ↓
    Verification + Evidence
           ↓
    Report

No interface should implement its own copy of this workflow.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from decision_engine.core.schemas import ActionCandidate, Outcome


# ---------------------------------------------------------------------------
# Request / Result Models
# ---------------------------------------------------------------------------

@dataclass
class VAPTRequest:
    """Unified request model for the VAPT workflow.

    Fields:
        scenario: Scenario name (e.g., "failure_pivot", "docker_pivot")
        mode: Execution mode ("simulation" or "lab")
        target: Lab target IP (required for lab mode)
        port: Lab target port (default: 8080)
        path: Default lab target path (default: "/vuln")
        assessor_mode: Assessment mode ("deterministic" or "ai")
        assessor_provider: AI provider ("ollama" or "openai")
        assessor_api_key: OpenAI API key (optional)
        max_attempts: Pivot threshold (default: 2)
        scan_file: Path to scan file (optional, overrides scenario)
    """
    scenario: str = "failure_pivot"
    mode: str = "simulation"
    target: Optional[str] = None
    port: int = 8080
    path: str = "/vuln"
    assessor_mode: str = "deterministic"
    assessor_provider: str = "ollama"
    assessor_api_key: Optional[str] = None
    max_attempts: int = 2
    scan_file: Optional[str] = None


@dataclass
class DomainResult:
    """Pure domain result — no presentation concerns.

    This is the canonical output of the VAPT workflow.
    CLI, API, and GUI create their own presentation from this.
    """
    run_id: str = ""
    scenario: str = ""
    mode: str = "simulation"
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


@dataclass
class PresentationResult:
    """Presentation-layer result for display/export.

    Created from DomainResult by the presentation layer.
    """
    domain: DomainResult = field(default_factory=DomainResult)
    report: dict[str, Any] = field(default_factory=dict)
    graph_summary: dict[str, Any] = field(default_factory=dict)
    scored_candidates: list[dict] = field(default_factory=list)
    pipeline_summary: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_domain(
        cls,
        domain: DomainResult,
        report: dict[str, Any] | None = None,
        graph: Any = None,
        scored_candidates: list[dict] | None = None,
        pipeline: dict[str, Any] | None = None,
    ) -> "PresentationResult":
        """Create presentation result from domain result."""
        graph_summary = graph.summary() if graph and hasattr(graph, "summary") else {}
        return cls(
            domain=domain,
            report=report or {},
            graph_summary=graph_summary,
            scored_candidates=scored_candidates or [],
            pipeline_summary=pipeline or {},
        )


# Backward compatibility alias
VAPTResult = PresentationResult


# ---------------------------------------------------------------------------
# Application Service
# ---------------------------------------------------------------------------

class VAPTApplication:
    """Canonical VAPT application workflow service.

    This is the single entry point for all VAPT workflows.
    CLI, API, and GUI must use this service.
    """

    def __init__(self):
        self._run_counter = 0

    def _generate_run_id(self) -> str:
        """Generate a unique run identifier."""
        self._run_counter += 1
        return f"run-{self._run_counter:04d}-{uuid.uuid4().hex[:8]}"

    def run(self, request: VAPTRequest) -> VAPTResult:
        """Execute the full VAPT workflow."""
        run_id = self._generate_run_id()
        domain = DomainResult(run_id=run_id, scenario=request.scenario, mode=request.mode)

        try:
            # Step 1: Load candidates
            candidates = self._load_candidates(request)

            # Step 2: Enrich candidates with vulnerability intelligence
            candidates = self._enrich_candidates(candidates)

            # Step 3: Build asset/vulnerability graph
            graph = self._build_graph(candidates)

            # Step 4: Decision intelligence scoring
            scored_candidates = self._score_candidates(candidates, graph)

            # Step 5: Build executor
            executor = self._build_executor(request, candidates)

            # Step 6: Controlled validation pipeline
            pipeline_result = self._run_validation_pipeline(scored_candidates, executor, request)

            # Step 7: Run decision engine
            final_state = self._run_engine(request, candidates, executor)

            # Step 8: Build result from engine state
            self._build_result(domain, final_state, request)

            # Create presentation result
            report = self._generate_report(domain, final_state, request)
            return PresentationResult.from_domain(
                domain,
                report=report,
                graph=graph,
                scored_candidates=scored_candidates,
                pipeline=pipeline_result,
            )

        except Exception as e:
            domain.final_status = "FAILED"
            domain.safety_notice = f"Error: {str(e)}"
            return PresentationResult.from_domain(domain)

    def _enrich_candidates(self, candidates: list[dict]) -> list[dict]:
        """Enrich candidates with vulnerability intelligence."""
        from vapt_platform.enrichment import enrich_findings
        from vapt_platform.normalization import CanonicalFinding

        # Convert dicts to CanonicalFinding objects
        findings = []
        for c in candidates:
            if isinstance(c, dict):
                # Create a minimal CanonicalFinding from candidate dict
                finding = CanonicalFinding(
                    finding_id=c.get("id", ""),
                    source=c.get("source", "unknown"),
                    target=c.get("target", c.get("host", "")),
                    host=c.get("host", ""),
                    port=c.get("port", 0),
                    protocol=c.get("protocol", "tcp"),
                    title=c.get("title", c.get("id", "")),
                    severity=c.get("severity", "unknown"),
                    rule_id=c.get("rule_id", c.get("id", "")),
                    description=c.get("description", ""),
                    evidence=c.get("evidence", []),
                    tags=c.get("tags", []),
                    metadata=c.get("metadata", {}),
                )
                findings.append(finding)
            else:
                findings.append(c)

        # Enrich findings
        enriched = enrich_findings(findings)

        # Convert back to dicts, preserving original fields
        result = []
        for i, f in enumerate(enriched):
            # Start with original candidate to preserve all fields
            if i < len(candidates) and isinstance(candidates[i], dict):
                enriched_dict = dict(candidates[i])
            else:
                enriched_dict = {}

            # Add/update with enriched fields (only if finding has a value)
            if f.finding_id or f.rule_id:
                enriched_dict["id"] = f.finding_id or f.rule_id
            if f.source:
                enriched_dict["source"] = f.source
            if f.target:
                enriched_dict["target"] = f.target
            if f.host:
                enriched_dict["host"] = f.host
            if f.port:
                enriched_dict["port"] = f.port
            if f.protocol:
                enriched_dict["protocol"] = f.protocol
            if f.title:
                enriched_dict["title"] = f.title
            if f.severity:
                enriched_dict["severity"] = f.severity
            if f.rule_id:
                enriched_dict["rule_id"] = f.rule_id
            if f.description:
                enriched_dict["description"] = f.description
            if f.evidence is not None:
                enriched_dict["evidence"] = f.evidence
            if f.tags is not None:
                enriched_dict["tags"] = f.tags
            # Always update metadata with enriched data
            enriched_dict["metadata"] = {**(enriched_dict.get("metadata", {})), **f.metadata}
            result.append(enriched_dict)

        return result

    def _build_graph(self, candidates: list[dict]) -> Any:
        """Build asset/vulnerability graph from candidates."""
        from vapt_platform.graph_builder import VAPTGraph
        from vapt_platform.normalization import CanonicalFinding

        findings = []
        for c in candidates:
            if isinstance(c, dict):
                finding = CanonicalFinding(
                    finding_id=c.get("id", ""),
                    source=c.get("source", "unknown"),
                    target=c.get("target", c.get("host", "")),
                    host=c.get("host", ""),
                    port=c.get("port", 0),
                    protocol=c.get("protocol", "tcp"),
                    title=c.get("title", c.get("id", "")),
                    severity=c.get("severity", "unknown"),
                    rule_id=c.get("rule_id", c.get("id", "")),
                    description=c.get("description", ""),
                    evidence=c.get("evidence", []),
                    tags=c.get("tags", []),
                    metadata=c.get("metadata", {}),
                )
                findings.append(finding)

        return VAPTGraph.from_findings(findings)

    def _score_candidates(self, candidates: list[dict], graph: Any) -> list[dict]:
        """Add decision intelligence scores to candidates."""
        from vapt_platform.decision_intelligence import get_decision_intelligence

        di = get_decision_intelligence()
        scored = []

        for c in candidates:
            factors = di.compute_score(c, graph=graph)
            c["_score"] = factors.to_dict()
            scored.append(c)

        return scored

    def _load_candidates(self, request: VAPTRequest) -> list[dict]:
        """Load candidates from scenario or scan file."""
        from prototype.demo_data import SCENARIOS
        from prototype.docker_demo_data import DOCKER_SCENARIOS
        from prototype.engine_integration import load_vapt_corpus_scenario
        from vapt_platform.scanners import get_scanner_registry
        from vapt_platform.enrichment import enrich_findings

        all_scenarios = {**SCENARIOS, **DOCKER_SCENARIOS}

        if request.scan_file:
            # Use new scanner adapter system
            registry = get_scanner_registry()
            findings = registry.parse(request.scan_file)
            # Enrich findings
            enriched = enrich_findings(findings)
            # Convert to candidate dicts
            return [
                {
                    "id": f.finding_id or f.rule_id,
                    "source": f.source,
                    "target": f.target,
                    "host": f.host,
                    "port": f.port,
                    "protocol": f.protocol,
                    "title": f.title,
                    "severity": f.severity,
                    "rule_id": f.rule_id,
                    "description": f.description,
                    "evidence": f.evidence,
                    "tags": f.tags,
                    "metadata": f.metadata,
                }
                for f in enriched
            ]
        elif request.scenario in all_scenarios:
            fn, kwargs = all_scenarios[request.scenario]
            return fn(**kwargs)
        elif request.scenario == "corpus":
            return load_vapt_corpus_scenario()
        else:
            raise ValueError(f"Unknown scenario: {request.scenario}")

    def _build_executor(self, request: VAPTRequest, candidates: list[dict]):
        """Build the appropriate executor for the request."""
        from prototype.execution_layer import create_lab_executor, create_simulation_executor
        from prototype.lab_runner import _validate_target

        if request.mode == "lab":
            if not request.target:
                raise ValueError("--target required for lab mode")
            _validate_target(request.target)

            # Build path_map from candidates that have a 'path' key
            path_map = {}
            for c in candidates:
                if "path" in c and c["path"] != request.path:
                    path_map[c["id"]] = c["path"]

            return create_lab_executor(
                request.target, request.port, request.path,
                path_map=path_map if path_map else None
            )
        else:
            return create_simulation_executor()

    def _run_engine(self, request: VAPTRequest, candidates: list[dict], executor) -> dict:
        """Run the decision engine with the configured assessor."""
        from prototype.engine_integration import run_decision_scenario

        return run_decision_scenario(
            candidates,
            max_attempts=request.max_attempts,
            mode=request.mode,
            executor=executor,
            assessment_mode=request.assessor_mode,
            assessment_provider=request.assessor_provider,
            assessment_api_key=request.assessor_api_key,
        )

    def _run_validation_pipeline(self, candidates: list[dict], executor, request: VAPTRequest) -> dict:
        """Run the controlled validation pipeline."""
        from vapt_platform.pipeline import ValidationPipeline

        # Build allowlist from request
        allowlist = set()
        if request.target:
            allowlist.add(request.target)

        pipeline = ValidationPipeline(allowlist=allowlist)
        return pipeline.run(candidates, graph=None, executor=executor)

    def _build_result(self, domain: DomainResult, final_state: dict, request: VAPTRequest) -> None:
        """Build the domain result from engine state."""
        # Extract presentation metadata
        presentation = final_state.get("_presentation", {})
        assessment = final_state.get("_assessment", {})

        # Build result
        domain.final_status = final_state.get("status", "UNKNOWN")
        domain.total_attempts = presentation.get("total_attempts", 0)
        domain.pivot_count = presentation.get("pivot_count", 0)
        domain.candidates_processed = presentation.get("candidates_processed", [])
        domain.decision_trace = final_state.get("logs", [])
        domain.assessment = assessment

        # Extract candidates
        for c in final_state.get("candidates", []):
            if hasattr(c, 'model_dump'):
                domain.candidates.append(c.model_dump(mode="json"))
            elif hasattr(c, '__dict__'):
                domain.candidates.append(c.__dict__)
            else:
                domain.candidates.append(c)

        # Extract execution results
        for r in final_state.get("results", []):
            if hasattr(r, 'model_dump'):
                domain.execution_results.append(r.model_dump(mode="json"))
            elif hasattr(r, '__dict__'):
                domain.execution_results.append(r.__dict__)
            else:
                domain.execution_results.append(r)

        # Evidence tier
        if request.mode == "lab":
            domain.evidence_tier = "DOCKER_OBSERVED"
            domain.safety_notice = (
                "LAB MODE (DOCKER OBSERVED): Outcomes are from the Docker-isolated emulator. "
                "Target is allowlisted. No external systems were targeted."
            )
        else:
            domain.evidence_tier = "SIMULATED"
            domain.safety_notice = (
                "SIMULATION MODE: Outcomes are resolved from supplied demo ground truth. "
                "No real vulnerabilities were validated."
            )

    def _generate_report(self, domain: DomainResult, final_state: dict, request: VAPTRequest) -> dict[str, Any]:
        """Generate the final report."""
        import json
        from prototype.report_generator import generate_json_report

        report_str = generate_json_report(
            domain.scenario,
            final_state,
            request.max_attempts,
            request.mode,
        )
        return json.loads(report_str)


# Singleton application instance
_application = VAPTApplication()


def get_application() -> VAPTApplication:
    """Get the singleton application instance."""
    return _application
