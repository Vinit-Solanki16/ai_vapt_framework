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
class VAPTResult:
    """Unified result model for the VAPT workflow.

    Fields:
        run_id: Unique run identifier
        scenario: Scenario name
        mode: Execution mode
        final_status: Final engine status
        candidates: List of processed candidates
        execution_results: List of execution outcomes
        decision_trace: List of trace events
        total_attempts: Total execution attempts
        pivot_count: Total pivot events
        candidates_processed: List of processed candidate IDs
        evidence_tier: Evidence tier label
        assessment: Assessment provenance info
        safety_notice: Safety notice text
        report: Generated report dict
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
    report: dict[str, Any] = field(default_factory=dict)


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
        """Execute the full VAPT workflow.

        Args:
            request: Unified request model

        Returns:
            Unified result model
        """
        run_id = self._generate_run_id()
        result = VAPTResult(run_id=run_id, scenario=request.scenario, mode=request.mode)

        try:
            # Step 1: Load candidates
            candidates = self._load_candidates(request)

            # Step 2: Build executor
            executor = self._build_executor(request, candidates)

            # Step 3: Run decision engine
            final_state = self._run_engine(request, candidates, executor)

            # Step 4: Build result from engine state
            self._build_result(result, final_state, request)

        except Exception as e:
            result.final_status = "FAILED"
            result.safety_notice = f"Error: {str(e)}"

        return result

    def _load_candidates(self, request: VAPTRequest) -> list[dict]:
        """Load candidates from scenario or scan file."""
        from prototype.demo_data import SCENARIOS
        from prototype.docker_demo_data import DOCKER_SCENARIOS
        from decision_engine.adapters.scan_adapter import candidates_from_scan, candidates_to_scenario
        from prototype.engine_integration import load_vapt_corpus_scenario

        all_scenarios = {**SCENARIOS, **DOCKER_SCENARIOS}

        if request.scan_file:
            return candidates_to_scenario(candidates_from_scan(request.scan_file))
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

    def _build_result(self, result: VAPTResult, final_state: dict, request: VAPTRequest) -> None:
        """Build the unified result from engine state."""
        # Extract presentation metadata
        presentation = final_state.get("_presentation", {})
        assessment = final_state.get("_assessment", {})

        # Build result
        result.final_status = final_state.get("status", "UNKNOWN")
        result.total_attempts = presentation.get("total_attempts", 0)
        result.pivot_count = presentation.get("pivot_count", 0)
        result.candidates_processed = presentation.get("candidates_processed", [])
        result.decision_trace = final_state.get("logs", [])
        result.assessment = assessment

        # Extract candidates
        for c in final_state.get("candidates", []):
            if hasattr(c, 'model_dump'):
                result.candidates.append(c.model_dump(mode="json"))
            elif hasattr(c, '__dict__'):
                result.candidates.append(c.__dict__)
            else:
                result.candidates.append(c)

        # Extract execution results
        for r in final_state.get("results", []):
            if hasattr(r, 'model_dump'):
                result.execution_results.append(r.model_dump(mode="json"))
            elif hasattr(r, '__dict__'):
                result.execution_results.append(r.__dict__)
            else:
                result.execution_results.append(r)

        # Evidence tier
        if request.mode == "lab":
            result.evidence_tier = "DOCKER_OBSERVED"
            result.safety_notice = (
                "LAB MODE (DOCKER OBSERVED): Outcomes are from the Docker-isolated emulator. "
                "Target is allowlisted. No external systems were targeted."
            )
        else:
            result.evidence_tier = "SIMULATED"
            result.safety_notice = (
                "SIMULATION MODE: Outcomes are resolved from supplied demo ground truth. "
                "No real vulnerabilities were validated."
            )

        # Generate report
        result.report = self._generate_report(result, final_state, request)

    def _generate_report(self, result: VAPTResult, final_state: dict, request: VAPTRequest) -> dict[str, Any]:
        """Generate the final report."""
        import json
        from prototype.report_generator import generate_json_report

        report_str = generate_json_report(
            result.scenario,
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
