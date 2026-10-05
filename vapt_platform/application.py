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
        mode: Execution mode ("simulation", "lab", or "web")
        target: Lab target IP (required for lab mode)
        port: Lab target port (default: 8080)
        path: Default lab target path (default: "/vuln")
        assessor_mode: Assessment mode ("deterministic" or "ai")
        assessor_provider: AI provider ("ollama" or "openai")
        assessor_api_key: OpenAI API key (optional)
        max_attempts: Pivot threshold (default: 2)
        scan_file: Path to scan file (optional, overrides scenario)
        assessment_type: "scenario" (default) or "web" (authorized URL target)
        target_url: Authorized web application URL (required for web assessments,
            e.g., "http://127.0.0.1:9191"). Backend-validated, fail closed.
        use_nmap: Run Nmap discovery for web assessments (default: True)
        use_nuclei: Run Nuclei scan for web assessments (default: True)
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
    assessment_type: str = "scenario"
    target_url: Optional[str] = None
    use_nmap: bool = True
    use_nuclei: bool = True


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
        
        # Initialize event publisher
        from vapt_platform.events import EventPublisher, EventType, RunState
        publisher = EventPublisher(run_id)
        publisher.emit(EventType.RUN_CREATED, {"scenario": request.scenario, "mode": request.mode})
        publisher.transition_to(RunState.CREATED)

        try:
            # Step 1: Load candidates
            publisher.transition_to(RunState.INGESTING)
            candidates = self._load_candidates(request)
            publisher.emit(EventType.FINDINGS_INGESTED, {"count": len(candidates)})

            # Step 2: Enrich candidates with vulnerability intelligence
            publisher.transition_to(RunState.NORMALIZING)
            candidates = self._enrich_candidates(candidates)
            publisher.emit(EventType.FINDINGS_NORMALIZED, {"count": len(candidates)})

            # Step 3: Build asset/vulnerability graph
            graph = self._build_graph(candidates)
            publisher.emit(EventType.CANDIDATES_GENERATED, {"count": len(candidates)})

            # Step 4: Decision intelligence scoring
            publisher.transition_to(RunState.ASSESSING)
            scored_candidates = self._score_candidates(candidates, graph)
            publisher.emit(EventType.ASSESSMENT_COMPLETED, {"count": len(scored_candidates)})
            # Stash server-side scores for result merging/persistence (GAP-1
            # display uses these — the frontend never computes scores).
            request._scored_candidates = scored_candidates  # type: ignore[attr-defined]

            # Step 5: Build executor
            publisher.transition_to(RunState.PLANNING)
            executor = self._build_executor(request, candidates)

            # Step 6: Controlled validation pipeline
            pipeline_result = self._run_validation_pipeline(scored_candidates, executor, request)
            publisher.emit(EventType.DECISION_MADE, {"pipeline": pipeline_result.get("status", "unknown")})

            # Attach web-target provenance (if any) so it is persisted/reported.
            web_context = getattr(request, "_web_context", None)
            if web_context:
                pipeline_result["web"] = web_context

            # Step 7: Run decision engine
            publisher.transition_to(RunState.EXECUTING)
            publisher.emit(EventType.EXECUTION_STARTED, {"candidate_count": len(candidates)})
            final_state = self._run_engine(request, candidates, executor)
            
            # Emit attempt completed events
            for i, result in enumerate(final_state.get("results", [])):
                publisher.emit(EventType.ATTEMPT_COMPLETED, {
                    "candidate_id": result.get("candidate_id", "?"),
                    "outcome": result.get("outcome", "?"),
                    "attempt_number": i + 1,
                })
            
            # Emit pivot events
            presentation = final_state.get("_presentation", {})
            pivot_count = presentation.get("pivot_count", 0)
            if pivot_count > 0:
                publisher.emit(EventType.PIVOT_OCCURRED, {"pivot_count": pivot_count})

            # Step 8: Build result from engine state
            publisher.transition_to(RunState.VERIFYING)
            self._build_result(domain, final_state, request)
            publisher.emit(EventType.VERIFICATION_COMPLETED, {"status": domain.final_status})

            # Create presentation result
            publisher.transition_to(RunState.REPORTING)
            report = self._generate_report(domain, final_state, request)
            result = PresentationResult.from_domain(
                domain,
                report=report,
                graph=graph,
                scored_candidates=scored_candidates,
                pipeline=pipeline_result,
            )

            # Persist the run (including server-side scores for ranking display)
            pipeline_result["scored_candidates"] = getattr(
                request, "_scored_candidates", []
            )
            self._persist_run(domain, request, pipeline_result)
            publisher.emit(EventType.EVIDENCE_CAPTURED, {"evidence_tier": domain.evidence_tier})

            # Complete
            publisher.transition_to(RunState.COMPLETED)
            publisher.emit(EventType.RUN_COMPLETED, {"status": domain.final_status})

            return result

        except Exception as e:
            domain.final_status = "FAILED"
            domain.safety_notice = f"Error: {str(e)}"
            # Persist failed run too
            self._persist_run(domain, request, {})
            publisher.transition_to(RunState.FAILED)
            publisher.emit(EventType.RUN_FAILED, {"error": str(e)})
            return PresentationResult.from_domain(domain)

    def _persist_run(self, domain: DomainResult, request: VAPTRequest, pipeline_summary: dict) -> None:
        """Persist a completed run to the repository."""
        from vapt_platform.persistence import get_repository, PersistentRun, RunStatus
        from vapt_platform.reporting.builder import ReportBuilder

        # Determine status
        status = RunStatus.COMPLETED.value if domain.final_status in ("SUCCESS", "COMPLETED") else RunStatus.FAILED.value

        # Build report for persistence
        builder = ReportBuilder()
        report = builder.from_domain_result(domain, request, pipeline_summary)

        # Build persistent run
        persistent = PersistentRun(
            run_id=domain.run_id,
            scenario=domain.scenario,
            mode=domain.mode,
            status=status,
            final_status=domain.final_status,
            candidates=domain.candidates,
            execution_results=domain.execution_results,
            decision_trace=domain.decision_trace,
            total_attempts=domain.total_attempts,
            pivot_count=domain.pivot_count,
            candidates_processed=domain.candidates_processed,
            evidence_tier=domain.evidence_tier,
            assessment=domain.assessment,
            safety_notice=domain.safety_notice,
            target=request.target,
            port=request.port,
            path=request.path,
            max_attempts=request.max_attempts,
            assessor_mode=request.assessor_mode,
            assessor_provider=request.assessor_provider,
            target_url=request.target_url,
            assessment_type=request.assessment_type,
            pipeline_summary=pipeline_summary,
            scored_candidates=pipeline_summary.get("scored_candidates", []),
        )

        try:
            repository = get_repository()
            repository.save(persistent)
        except Exception:
            # Persistence failures should not break the workflow
            pass

    def generate_report(self, run_id: str, format: str = "json") -> str:
        """Generate a report for a persisted run.
        
        Args:
            run_id: The run ID to generate report for
            format: Report format (json, html, markdown, txt)
            
        Returns:
            Rendered report string
            
        Raises:
            ValueError: If run not found
        """
        from vapt_platform.persistence import get_repository
        from vapt_platform.reporting.builder import ReportBuilder
        from vapt_platform.reporting.renderers import get_renderer

        repository = get_repository()
        run = repository.get(run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")

        builder = ReportBuilder()
        report = builder.from_persisted_run(run)
        renderer = get_renderer(format)
        return renderer.render(report)

    def _enrich_candidates(self, candidates: list[dict]) -> list[dict]:
        """Enrich candidates with vulnerability intelligence."""
        from vapt_platform import enrichment
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
        enriched = enrichment.enrich_findings(findings)

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
        """Load candidates from scenario, scan file, or authorized web target."""
        from prototype.demo_data import SCENARIOS
        from prototype.docker_demo_data import DOCKER_SCENARIOS
        from prototype.engine_integration import load_vapt_corpus_scenario
        from vapt_platform.scanners import get_scanner_registry
        from vapt_platform import enrichment

        all_scenarios = {**SCENARIOS, **DOCKER_SCENARIOS}

        if request.assessment_type == "web" or request.target_url:
            return self._load_web_candidates(request)

        if request.scan_file:
            # Use new scanner adapter system
            registry = get_scanner_registry()
            findings = registry.parse(request.scan_file)
            # Enrich findings
            enriched = enrichment.enrich_findings(findings)
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

    def _load_web_candidates(self, request: VAPTRequest) -> list[dict]:
        """Run the authorized web-target discovery pipeline.

        Flow (all through the existing canonical pipeline, no alternate
        finding representation):
            preflight (authorize + scope + connectivity)
                → Nmap discovery → Nuclei scan
                → CanonicalFinding → dedup → enrichment
                → candidate dicts

        Raises WebTargetAuthorizationError / ValueError on any failure
        (fail closed — run() converts these into a FAILED run and scanners
        are never invoked after an authorization rejection).
        """
        import time as _time

        from vapt_platform import enrichment
        from vapt_platform import scanner_service
        from vapt_platform.normalization import deduplicate
        from vapt_platform.web_target import (
            WebTargetAuthorizationError,
            parse_web_target,
            preflight_web_target,
        )

        if not request.target_url:
            raise WebTargetAuthorizationError(
                "Web assessment requires target_url."
            )

        pipeline_start = _time.perf_counter()

        # --- Phase: authorization + scope (fail closed) ---
        target = parse_web_target(request.target_url)

        # Seed request context so reports/history show the real target.
        request.target = target.host
        request.port = target.port
        if request.scenario in ("failure_pivot",):
            request.scenario = "web_target"

        # --- Phase: preflight (no scanners until this passes) ---
        preflight = preflight_web_target(request.target_url)
        if not preflight["reachable"]:
            raise ValueError(
                f"Web target preflight failed: {preflight['detail']}. "
                "Scanners were not invoked."
            )

        # --- Phase: controlled scanner discovery ---
        nmap_result = None
        nuclei_result = None
        if request.use_nmap:
            nmap_result = scanner_service.run_nmap_discovery(request.target_url)
        if request.use_nuclei:
            nuclei_result = scanner_service.run_nuclei_scan(request.target_url)

        findings: list = []
        if nmap_result is not None:
            findings.extend(nmap_result.findings)
        if nuclei_result is not None:
            findings.extend(nuclei_result.findings)

        # --- Phase: normalization → dedup → enrichment (canonical path) ---
        findings = deduplicate(findings)
        enriched = enrichment.enrich_findings(findings)

        if not enriched:
            raise ValueError(
                "Web assessment produced no findings: target is reachable but "
                "scanners reported no open services/vulnerabilities. "
                "Nothing entered the decision pipeline."
            )

        # Stash provenance for result building / persistence / reporting.
        request._web_context = {  # type: ignore[attr-defined]
            "target": target.to_dict(),
            "target_url": target.normalized_url,
            "preflight": preflight,
            "nmap": nmap_result.to_dict() if nmap_result else {
                "scanner": "nmap", "status": "SKIPPED",
                "detail": "Nmap discovery disabled for this run.",
            },
            "nuclei": nuclei_result.to_dict() if nuclei_result else {
                "scanner": "nuclei", "status": "SKIPPED",
                "detail": "Nuclei scan disabled for this run.",
            },
            "finding_count": len(enriched),
            "pipeline_s": round(_time.perf_counter() - pipeline_start, 3),
            "scanner_versions": {
                "nmap": scanner_service.nmap_status().get("version"),
                "nuclei": scanner_service.nuclei_status().get("version"),
            },
        }

        # --- Phase: candidate generation (same dict shape as scan_file path,
        # plus probability prior from EPSS and scanner-detection marker) ---
        candidates = []
        for f in enriched:
            epss = 0.0
            try:
                epss = float((f.metadata or {}).get("epss_score", 0.0) or 0.0)
            except (TypeError, ValueError):
                epss = 0.0
            probability = min(max(epss, 0.0), 1.0)
            candidates.append(
                {
                    "id": f.finding_id or f.rule_id,
                    "probability": probability,
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
                    "validation_status": "SCANNER-DETECTED",
                }
            )
        # Snapshot for post-engine metadata merge (result building) and audit.
        request._web_context["finding_snapshots"] = [dict(c) for c in candidates]  # type: ignore[attr-defined]
        return candidates

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
        from vapt_platform.authorization import AuthorizationTracker
        from vapt_platform.pipeline import ValidationPipeline

        # Build authorization tracker seeded from the lab target allowlist
        tracker = AuthorizationTracker()
        if request.target:
            tracker.authorize(request.target, authorized_by="VAPTApplication")

        pipeline = ValidationPipeline(allowlist=set(), authorization_tracker=tracker)
        return pipeline.run(candidates, graph=None, executor=executor)

    def _build_result(self, domain: DomainResult, final_state: dict, request: VAPTRequest) -> None:
        """Build the domain result from engine state."""
        # Extract presentation metadata
        presentation = final_state.get("_presentation", {})
        assessment = final_state.get("_assessment", {})
        assessment_details = final_state.get("_assessment_details", [])

        # Build result
        domain.final_status = final_state.get("status", "UNKNOWN")
        domain.total_attempts = presentation.get("total_attempts", 0)
        domain.pivot_count = presentation.get("pivot_count", 0)
        domain.candidates_processed = presentation.get("candidates_processed", [])
        domain.decision_trace = final_state.get("logs", [])
        domain.assessment = assessment
        # Per-candidate AI provenance (reasoning/latency/fallback) — observed
        # from the engine's own assessment step, NOT a second assessment.
        if assessment_details:
            domain.assessment = {**assessment, "details": assessment_details}

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
        elif getattr(request, "_web_context", None):
            web_ctx = request._web_context
            domain.evidence_tier = "OBSERVED_LOCAL"
            domain.safety_notice = (
                "WEB TARGET MODE (OBSERVED LOCAL): Findings are real scanner output "
                f"from the authorized local target {web_ctx.get('target_url', '')} "
                "(Nmap discovery"
                f"{' + Nuclei scan' if (web_ctx.get('nuclei') or {}).get('status') == 'COMPLETED' else ''}). "
                "Scanner findings are NOT automatically confirmed vulnerabilities: "
                "validation status is VALIDATION NOT AVAILABLE unless a controlled "
                "validation action was executed and verified. "
                "No external systems were targeted."
            )
            self._merge_web_finding_metadata(domain, final_state, request)
        else:
            domain.evidence_tier = "SIMULATED"
            domain.safety_notice = (
                "SIMULATION MODE: Outcomes are resolved from supplied demo ground truth. "
                "No real vulnerabilities were validated."
            )

    def _merge_web_finding_metadata(
        self, domain: DomainResult, final_state: dict, request: VAPTRequest
    ) -> None:
        """Merge scanner finding metadata back into engine candidates.

        The research engine intentionally carries only (id, probability,
        quality_rank, outcome). For web assessments the UI/report must also
        show severity, source, CVE/CVSS/EPSS/KEV/CWE and validation status,
        so the pre-engine enriched candidate dicts are merged back by id.
        Engine ranking/decision fields are never overwritten.
        """
        # Reconstruct the enriched pre-engine candidate dicts keyed by id.
        # They were produced by _load_web_candidates; rebuild the lookup from
        # the persisted web context findings when available.
        web_ctx = getattr(request, "_web_context", None) or {}
        pre: dict[str, dict] = {}
        # The candidates passed to the engine are not retained on the request,
        # so merge from execution metadata: engine candidates carry the id;
        # scanner metadata is recovered from the stored finding snapshot.
        for snapshot in (web_ctx.get("finding_snapshots") or []):
            if isinstance(snapshot, dict) and snapshot.get("id"):
                pre[snapshot["id"]] = snapshot

        executed = {}
        for r in final_state.get("results", []):
            cid = r.get("candidate_id", "?") if isinstance(r, dict) else "?"
            executed[cid] = r.get("outcome", "?") if isinstance(r, dict) else "?"

        # Server-side decision-intelligence scores (GAP-1 display data).
        score_map = {}
        for s in (getattr(request, "_scored_candidates", None) or []):
            if isinstance(s, dict) and s.get("id"):
                score_map[s["id"]] = s.get("_score", {})

        # Priority = engine's actual execution order (candidates_processed).
        order = list(domain.candidates_processed or [])
        priority_of = {cid: i + 1 for i, cid in enumerate(order)}

        merged = []
        for c in domain.candidates:
            if not isinstance(c, dict):
                merged.append(c)
                continue
            cid = c.get("id", "?")
            snap = pre.get(cid, {})
            if snap:
                for key in (
                    "source", "target", "host", "port", "protocol", "title",
                    "severity", "rule_id", "description", "evidence", "tags",
                    "metadata",
                ):
                    if key in snap:
                        c[key] = snap[key]
            # Server-side score + engine execution priority (display only).
            if cid in score_map:
                c["_score"] = score_map[cid]
            if cid in priority_of:
                c["priority"] = priority_of[cid]
            # Honest validation labelling: scanner-detected unless the
            # controlled pipeline executed AND verified this candidate.
            outcome = executed.get(cid)
            if outcome in ("SUCCESS", "FAIL_TIMEOUT", "FAIL_SYNTAX", "FAIL_DEPENDENCY"):
                c["validation_status"] = (
                    "SIMULATED-OUTCOME (validation not available for "
                    "scanner findings in this mode)"
                )
            else:
                c["validation_status"] = "VALIDATION NOT AVAILABLE"
            merged.append(c)
        domain.candidates = merged

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
