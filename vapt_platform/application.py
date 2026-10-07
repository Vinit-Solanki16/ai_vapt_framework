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


#: Phase 32B: explicit validation-availability marker for web-target runs.
#: No web validation executor is implemented: web runs are
#: scanner-driven and assessment-only (assess → rank → plan, then stop
#: before execution). This status is recorded in the web context and
#: pipeline summary so UI/reports never imply validation occurred.
WEB_VALIDATION_UNAVAILABLE = "WEB_VALIDATION_UNAVAILABLE"


def _most_common_path(paths: list[str]) -> str:
    """Return the most common path; ties resolve to first occurrence."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for path in paths:
        if path not in counts:
            counts[path] = 0
            order.append(path)
        counts[path] += 1
    return max(order, key=lambda p: counts[p]) if order else "/vuln"


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
        assessor_model: Explicit model name (optional). None -> the
            authoritative provider default from vapt_platform.model_config
            (llama3.2:3b for ollama, the official thesis baseline).
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
    assessor_model: Optional[str] = None
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

    FIX 1: ``candidates`` holds ONLY actionable vulnerability findings
    (VULNERABILITY_FINDING). Pure Nmap service-discovery records are
    preserved separately in ``service_discovery`` as asset/service
    context and never enter AI assessment → ranking → decision.
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
    # FIX 1: preserved Nmap asset/service context (never ranked as exploits).
    service_discovery: list[dict] = field(default_factory=list)


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
            # Step 1: Load candidates (FIX 1: actionable vuln findings only;
            # pure Nmap service discovery is stashed on the request as
            # asset/service context and never enters the candidate pipeline).
            publisher.transition_to(RunState.INGESTING)
            candidates = self._load_candidates(request)
            service_discovery = list(getattr(request, "_service_discovery", None) or [])
            publisher.emit(EventType.FINDINGS_INGESTED, {"count": len(candidates)})

            # Step 2: Enrich candidates with vulnerability intelligence
            publisher.transition_to(RunState.NORMALIZING)
            candidates = self._enrich_candidates(candidates)
            publisher.emit(EventType.FINDINGS_NORMALIZED, {"count": len(candidates)})

            # Step 3: Build asset/vulnerability graph (FIX 1: include
            # service-discovery records so hosts/services remain visible
            # as asset context even though they are not candidates).
            graph = self._build_graph(candidates + service_discovery)
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
            # FIX 1: preserve any already-discovered asset context on failure.
            try:
                preserved = list(getattr(request, "_service_discovery", None) or [])
                if preserved and not getattr(domain, "service_discovery", None):
                    domain.service_discovery = [dict(s) for s in preserved if isinstance(s, dict)]
            except Exception:
                pass
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

        # Build persistent run (FIX 1: persist service discovery separately).
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
            service_discovery=list(getattr(domain, "service_discovery", []) or []),
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
        """Build asset/vulnerability graph from candidates + discovery.

        FIX 1: Accepts both actionable candidate dicts (``id``) and
        preserved service-discovery dicts (``finding_id``) so hosts and
        services remain visible as asset context.
        """
        from vapt_platform.graph_builder import VAPTGraph
        from vapt_platform.normalization import CanonicalFinding

        findings = []
        for c in candidates:
            if isinstance(c, dict):
                cid = c.get("id", "") or c.get("finding_id", "")
                finding = CanonicalFinding(
                    finding_id=c.get("finding_id", cid),
                    source=c.get("source", "unknown"),
                    target=c.get("target", c.get("host", "")),
                    host=c.get("host", ""),
                    port=c.get("port", 0),
                    protocol=c.get("protocol", "tcp"),
                    title=c.get("title", cid),
                    severity=c.get("severity", "unknown"),
                    rule_id=c.get("rule_id", cid),
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
            # Use new scanner adapter system (FIX 1: split discovery vs vuln).
            # FIX 2: split also separates informational / fingerprint /
            # discovery observations (still visible, never ranked).
            from vapt_platform.normalization import (
                CANDIDATE_ELIGIBILITY_ACTIONABLE,
                FINDING_KIND_VULNERABILITY,
                finding_to_service_info,
                split_findings,
            )

            registry = get_scanner_registry()
            findings = registry.parse(request.scan_file)
            # Enrich findings
            enriched = enrichment.enrich_findings(findings)
            actionable, discovery = split_findings(enriched)
            # Preserve asset/service context + informational observations
            # for Findings-page + reports (eligibility INFORMATIONAL).
            request._service_discovery = [finding_to_service_info(f) for f in discovery]  # type: ignore[attr-defined]
            # Convert actionable findings to candidate dicts only.
            # Every candidate carries explicit eligibility ACTIONABLE.
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
                    "finding_kind": FINDING_KIND_VULNERABILITY,
                    "candidate_eligibility": CANDIDATE_ELIGIBILITY_ACTIONABLE,
                }
                for f in actionable
            ]
        elif request.scenario in all_scenarios:
            request._service_discovery = []  # type: ignore[attr-defined]
            fn, kwargs = all_scenarios[request.scenario]
            return fn(**kwargs)
        elif request.scenario == "corpus":
            request._service_discovery = []  # type: ignore[attr-defined]
            return load_vapt_corpus_scenario()
        else:
            raise ValueError(f"Unknown scenario: {request.scenario}")

    def _load_web_candidates(self, request: VAPTRequest) -> list[dict]:
        """Run the authorized web-target discovery pipeline.

        FIX 1 + FIX 2 flow (single canonical pipeline, no second workflow):
            preflight (authorize + scope + connectivity)
                → Nmap discovery → Nuclei scan
                → CanonicalFinding → dedup → enrichment
                → SPLIT (actionable vs discovery/informational)
                → actionable candidate dicts (vuln only, eligibility
                  ACTIONABLE) + preserved discovery/informational
                  inventory (eligibility INFORMATIONAL / DISCOVERY)

        Nmap service discovery (e.g. port 9191 ``sun-as-jpda?`` with an
        HTTP banner) remains visible as Service Discovery / Asset
        Information but never becomes an AI/ranking/exploit candidate.
        Nuclei informational / fingerprint / discovery observations
        (technology detection, Juice Shop detection, header observations,
        exposed-service info with severity info and no CVE/CVSS/KEV)
        remain visible in the findings inventory with eligibility
        INFORMATIONAL / DISCOVERY but never enter ranking.

        Raises WebTargetAuthorizationError / ValueError on any failure
        (fail closed — run() converts these into a FAILED run and scanners
        are never invoked after an authorization rejection).
        """
        import time as _time

        from vapt_platform import enrichment
        from vapt_platform import scanner_service
        from vapt_platform.normalization import (
            CANDIDATE_ELIGIBILITY_ACTIONABLE,
            FINDING_KIND_VULNERABILITY,
            deduplicate,
            finding_to_service_info,
            split_findings,
        )
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

        # FIX 1 + FIX 2: split actionable vulnerability findings from
        # non-actionable inventory (Nmap asset context + Nuclei
        # informational / fingerprint / discovery observations).
        # Only actionable findings become candidates. No severity invented;
        # UNKNOWN severity stays ACTIONABLE (fail open).
        actionable, discovery = split_findings(enriched)
        service_discovery = [finding_to_service_info(f) for f in discovery]

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
            "finding_count": len(actionable),
            "service_discovery_count": len(service_discovery),
            "total_findings": len(enriched),
            "pipeline_s": round(_time.perf_counter() - pipeline_start, 3),
            "scanner_versions": {
                "nmap": scanner_service.nmap_status().get("version"),
                "nuclei": scanner_service.nuclei_status().get("version"),
            },
            "service_discovery": service_discovery,
        }
        # Uniform stash consumed by run() for graph + DomainResult.
        request._service_discovery = list(service_discovery)  # type: ignore[attr-defined]

        # --- Phase: candidate generation (same dict shape as scan_file path,
        # plus probability prior from EPSS and scanner-detection marker) ---
        # FIX 1 + FIX 2: only actionable (vulnerability) findings become
        # candidates, each labelled ACTIONABLE. Informational / discovery
        # records stay in service_discovery with eligibility
        # INFORMATIONAL / DISCOVERY.
        # Phase 32B FIX 3: each candidate preserves its own resource path
        # derived from its target URL (never the /vuln scenario default).
        from urllib.parse import urlsplit

        def _resource_path(target_url: str) -> str:
            try:
                path = urlsplit(str(target_url or "")).path or "/"
            except Exception:
                return "/"
            return path or "/"

        candidates = []
        for f in actionable:
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
                    "finding_kind": FINDING_KIND_VULNERABILITY,
                    "candidate_eligibility": CANDIDATE_ELIGIBILITY_ACTIONABLE,
                    "path": _resource_path(f.target),
                }
            )
        # Phase 32B FIX 3: the run-level path is the most common candidate
        # resource path — never the /vuln simulation default. Per-candidate
        # paths above remain authoritative when candidates differ.
        if candidates:
            request.path = _most_common_path([_c["path"] for _c in candidates])
        # Phase 32B FIX 1: explicit validation-availability marker. No web
        # validator is implemented, so every web run stops before execution.
        request._web_context["validation"] = {  # type: ignore[attr-defined]
            "status": WEB_VALIDATION_UNAVAILABLE,
            "detail": (
                "No web validation executor is implemented for scanner "
                "findings: assessed and ranked only; validation unavailable."
            ),
        }
        # Snapshot for post-engine metadata merge (result building) and audit.
        # Includes discovery snapshots so reports/UI can show asset context.
        request._web_context["finding_snapshots"] = [dict(c) for c in candidates]  # type: ignore[attr-defined]
        request._web_context["discovery_snapshots"] = [dict(s) for s in service_discovery]  # type: ignore[attr-defined]
        # Discovery-only runs are valid: no actionable candidates, but asset
        # context is preserved. The engine step handles the empty list.
        return candidates

    def _build_executor(self, request: VAPTRequest, candidates: list[dict]):
        """Build the appropriate executor for the request.

        Phase 32B FIX 1: WEB mode is assessment-only — no web validation
        executor is implemented, so this returns None instead of falling
        through to the simulation executor (which fabricated FAIL_TIMEOUT
        from missing ground_truth). ``run()`` takes the explicit
        assessment-only path (assess → rank → plan, then STOP before
        execution) when the executor is None for a web run.

        Modes:
          simulation → simulation executor (ground-truth labels)
          lab        → Docker/lab executor (observed emulator responses)
          web        → None (WEB_VALIDATION_UNAVAILABLE)
        """
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
        if (
            request.mode == "web"
            or getattr(request, "assessment_type", "") == "web"
            or getattr(request, "target_url", None)
        ):
            # Assessment-only: no validator exists for web scanner findings.
            return None
        return create_simulation_executor()

    def _run_engine(self, request: VAPTRequest, candidates: list[dict], executor) -> dict:
        """Run the decision engine with the configured assessor.

        FIX 1: Discovery-only runs (no actionable vulnerability findings)
        bypass the engine — there is nothing to assess/rank/decide — and
        return a COMPLETED state preserving discovery context. Research
        (GAP-1/GAP-2) logic is untouched; this is a pre-engine guard.
        """
        if not candidates:
            discovery = list(getattr(request, "_service_discovery", None) or [])
            detail = (
                "No actionable vulnerability findings: "
                f"{len(discovery)} service-discovery record(s) preserved as "
                "asset context; nothing entered AI assessment/ranking/decision."
            )
            return {
                "candidates": [],
                "results": [],
                "logs": [
                    "Engine initialized: 0 actionable candidates "
                    f"(service discovery preserved: {len(discovery)}), "
                    f"pivot_threshold={request.max_attempts}, mode={request.mode}",
                    f"[Engine] {detail}",
                    "[Pivot] All candidates processed. Workflow complete.",
                ],
                "status": "COMPLETED",
                "current_index": 0,
                "current_id": "NONE",
                "quality_rank": "NONE",
                "attempt_count": 0,
                "max_attempts": request.max_attempts,
                "mode": request.mode,
                "_assessment": {
                    "mode": request.assessor_mode,
                    "provider": (
                        request.assessor_provider
                        if request.assessor_mode == "ai"
                        else "deterministic"
                    ),
                    "model": None,
                },
                "_assessment_details": [],
                "_presentation": {
                    "scenario_candidates": 0,
                    "total_attempts": 0,
                    "pivot_count": 0,
                    "candidates_processed": [],
                    "max_attempts": request.max_attempts,
                    "mode": request.mode,
                },
            }

        from prototype.engine_integration import run_decision_scenario

        # Phase 32B FIX 1: assessment-only web path. The executor is None
        # because no web validator exists — assess + rank the actionable
        # candidates, record that validation is unavailable, and STOP
        # before execution. This produces NO execution results, NO pivot
        # events, NO attempts, and NO fabricated outcomes (GAP-2 untouched:
        # pivots are only ever produced by real executor operations).
        if executor is None:
            return self._run_assessment_only(request, candidates)

        return run_decision_scenario(
            candidates,
            max_attempts=request.max_attempts,
            mode=request.mode,
            executor=executor,
            assessment_mode=request.assessor_mode,
            assessment_provider=request.assessor_provider,
            assessment_api_key=request.assessor_api_key,
            assessment_model=request.assessor_model,
        )

    def _run_assessment_only(self, request: VAPTRequest, candidates: list[dict]) -> dict:
        """Assess + rank candidates without executing (web assessment-only).

        Mirrors the GAP-1 assess-before-rank ordering of the research
        engine (assess every candidate, then rank by priority_score) but
        performs zero executions: no ``results``, no attempt counters, no
        pivot logic. Per-candidate AI provenance is recorded exactly as
        the engine integration records it (observation only).
        """
        import time as _time

        from decision_engine.core.assessor import assess_candidates
        from decision_engine.core.engine import rank_candidates
        from decision_engine.core.schemas import QualityRank, candidate_from_dict
        from vapt_platform.assessment import create_assessor

        # Normalize exactly as the engine integration does.
        normalized = []
        for d in candidates:
            nd = dict(d)
            if nd.get("ground_truth") is not None:
                nd["ground_truth"] = str(nd["ground_truth"]).upper()
            normalized.append(nd)
        raw_candidates = [candidate_from_dict(d) for d in normalized]

        assessor_fn = create_assessor(
            mode=request.assessor_mode,
            provider=request.assessor_provider,
            api_key=request.assessor_api_key,
            model_name=request.assessor_model,
        )
        assessment_details: list[dict] = []

        def _assess_fn(candidate) -> QualityRank:
            _t0 = _time.perf_counter()
            assessed_result = assessor_fn(candidate)
            _latency = _time.perf_counter() - _t0
            assessment_details.append({
                "candidate_id": candidate.id,
                "quality_rank": assessed_result.quality_rank.value,
                "source": assessed_result.source,
                "provider": assessed_result.provider,
                "model": assessed_result.model,
                "fallback": assessed_result.fallback,
                "reasoning": assessed_result.reasoning,
                "error": assessed_result.error,
                "latency_s": round(_latency, 4),
            })
            return assessed_result.quality_rank

        assess_candidates(raw_candidates, assess_fn=_assess_fn)
        ranked = rank_candidates(raw_candidates)

        effective_provider = (
            request.assessor_provider
            if request.assessor_mode == "ai"
            else "deterministic"
        )
        model = None
        if request.assessor_mode == "ai":
            from vapt_platform.model_config import resolve_model

            model = resolve_model(request.assessor_provider, request.assessor_model)
        return {
            "candidates": ranked,
            "results": [],
            "logs": [
                f"Engine initialized: {len(ranked)} actionable candidates "
                f"(assessment-only, {WEB_VALIDATION_UNAVAILABLE}), "
                f"pivot_threshold={request.max_attempts}, mode={request.mode}",
                "[Assessment] AI assessment + ranking completed for "
                f"{len(ranked)} actionable candidate(s).",
                f"[Validation] {WEB_VALIDATION_UNAVAILABLE}: no web validator "
                "is implemented for scanner findings — stopping before "
                "execution. No attempts, no pivots, no outcomes fabricated.",
            ],
            "status": "COMPLETED",
            "current_index": 0,
            "current_id": ranked[0].id if ranked else "NONE",
            "quality_rank": "NONE",
            "attempt_count": 0,
            "max_attempts": request.max_attempts,
            "mode": request.mode,
            "_assessment": {
                "mode": request.assessor_mode,
                "provider": effective_provider,
                "model": model,
            },
            "_assessment_details": list(assessment_details),
            "_presentation": {
                "scenario_candidates": len(candidates),
                "total_attempts": 0,
                "pivot_count": 0,
                "candidates_processed": [],
                "max_attempts": request.max_attempts,
                "mode": request.mode,
            },
        }

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

        # FIX 1 + FIX 2: preserve non-actionable inventory (service
        # discovery asset context + informational / fingerprint /
        # discovery observations) with eligibility INFORMATIONAL.
        # Stashed by _load_candidates/_load_web_candidates; also mirrored in
        # the web context for persistence/reporting round-trips.
        preserved = list(getattr(request, "_service_discovery", None) or [])
        web_ctx_early = getattr(request, "_web_context", None) or {}
        if not preserved and isinstance(web_ctx_early, dict):
            preserved = list(
                web_ctx_early.get("service_discovery", [])
                or web_ctx_early.get("discovery_snapshots", [])
                or []
            )
        domain.service_discovery = [dict(s) for s in preserved if isinstance(s, dict)]

        # Extract candidates (FIX 1 + FIX 2: only ACTIONABLE findings;
        # discovery/informational never appear here). Engine candidates
        # carry only (id, probability, quality_rank, outcome), so stamp
        # explicit eligibility ACTIONABLE for UI/report display.
        # FIX 3: stamp honest per-candidate validation status derived from
        # the run mode/evidence (never fabricating validation success).
        # Web candidates are re-labelled by _merge_web_finding_metadata
        # below (SCANNER-DETECTED → VALIDATION NOT AVAILABLE); scenario
        # and lab candidates get SIMULATED / DOCKER_OBSERVED here so the
        # API, persistence and reports share one backend source of truth.
        from vapt_platform.normalization import CANDIDATE_ELIGIBILITY_ACTIONABLE as _ELIGIBLE
        from vapt_platform.normalization import FINDING_KIND_VULNERABILITY as _VULN_KIND

        for c in final_state.get("candidates", []):
            if hasattr(c, 'model_dump'):
                domain.candidates.append(c.model_dump(mode="json"))
            elif hasattr(c, '__dict__'):
                domain.candidates.append(c.__dict__)
            else:
                domain.candidates.append(c)
        _is_web_run = bool(getattr(request, "_web_context", None))
        _mode_validation = (
            "DOCKER_OBSERVED" if getattr(request, "mode", "") == "lab"
            else "SIMULATED"
        )
        _scanner_sources = {
            "nmap", "nmap-xml", "nmap-json", "nuclei", "custom",
        }
        for c in domain.candidates:
            if isinstance(c, dict):
                c.setdefault("candidate_eligibility", _ELIGIBLE)
                c.setdefault("finding_kind", _VULN_KIND)
                if not _is_web_run:
                    # Do not overwrite an explicit validation_status if a
                    # future controlled-validation path sets VALIDATED.
                    # Scanner-file findings are SCANNER-DETECTED inventory
                    # with no controlled validation → NOT AVAILABLE;
                    # pure demo scenarios → SIMULATED / DOCKER_OBSERVED.
                    _src = str(c.get("source", "") or "").strip().lower()
                    if _src in _scanner_sources:
                        c.setdefault("validation_status", "VALIDATION NOT AVAILABLE")
                    else:
                        c.setdefault("validation_status", _mode_validation)

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
                    "metadata", "finding_kind", "candidate_eligibility",
                    "path",
                ):
                    if key in snap:
                        c[key] = snap[key]
            # Every ranked candidate is ACTIONABLE by construction (only
            # actionable findings enter the engine). Stamp explicitly so
            # the Candidate Ranking page/report can display eligibility.
            from vapt_platform.normalization import CANDIDATE_ELIGIBILITY_ACTIONABLE as _ACT
            from vapt_platform.normalization import FINDING_KIND_VULNERABILITY as _VK

            c.setdefault("finding_kind", _VK)
            c.setdefault("candidate_eligibility", _ACT)
            # Server-side score + engine execution priority (display only).
            if cid in score_map:
                c["_score"] = score_map[cid]
            if cid in priority_of:
                c["priority"] = priority_of[cid]
            # Honest validation labelling. Phase 32B: web runs are
            # assessment-only — no validator executed, so every web finding
            # is VALIDATION NOT AVAILABLE. SIMULATED-OUTCOME is never set
            # here (no simulation-mode execution happens for web targets).
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
