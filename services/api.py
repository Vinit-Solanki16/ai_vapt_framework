"""FastAPI backend for the decision engine.

Uses the canonical VAPTApplication workflow service.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from prototype.lab_runner import LAB_TARGET_ALLOWLIST
from services.schemas import (
    RunRequest, RunResponse, RunStatus, RunTrace, ReportResponse,
    CheckpointResponse, ErrorResponse, TraceEvent,
    TargetValidateRequest, TargetValidateResponse,
)
from services.jobs import job_manager
from vapt_platform.application import VAPTRequest, get_application
from vapt_platform.provider_errors import redact


def _safe_error_detail(exc: BaseException, req: "RunRequest" = None) -> str:
    """Redacted error detail for an API response.

    Provider exceptions can embed the API key (e.g. echoed inside a provider
    error body). Strip the submitted key plus any key-shaped substrings before
    the message leaves the process.
    """
    secrets = [getattr(req, "assessor_api_key", None)] if req is not None else []
    secrets += [
        os.getenv("OPENROUTER_API_KEY"), os.getenv("OPENAI_API_KEY"),
    ]
    return redact(str(exc), secrets)


app = FastAPI(title="AI VAPT Decision Engine API", version="0.1.0")

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "web")
if os.path.exists(FRONTEND_DIR):
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")


def _run_engine(run_id: str, req: RunRequest):
    """Execute the decision engine for a run using the canonical workflow."""
    # Convert API request to unified request
    vapt_request = VAPTRequest(
        scenario=req.scenario,
        mode=req.mode,
        target=req.target,
        port=req.port,
        path=req.path,
        assessor_mode="ai" if req.assessor == "llm" else "deterministic",
        assessor_provider=req.assessor_provider,
        assessor_api_key=req.assessor_api_key,
        assessor_model=req.assessor_model,
        max_attempts=req.max_attempts,
        scan_file=req.scan_file,
        assessment_type=req.assessment_type,
        target_url=req.target_url,
        use_nmap=req.use_nmap,
        use_nuclei=req.use_nuclei,
    )

    job_manager.update(run_id, status="running")

    # Run the canonical workflow
    application = get_application()
    result = application.run(vapt_request)

    # Store result in job manager (FIX 1: discovery kept separate).
    job_manager.set_state(run_id, {
        "scenario": result.domain.scenario,
        "mode": result.domain.mode,
        "status": result.domain.final_status,
        "candidates": result.domain.candidates,
        "service_discovery": result.domain.service_discovery,
        "execution_results": result.domain.execution_results,
        "decision_trace": result.domain.decision_trace,
        "total_attempts": result.domain.total_attempts,
        "pivot_count": result.domain.pivot_count,
        "candidates_processed": result.domain.candidates_processed,
        "evidence_tier": result.domain.evidence_tier,
        "assessment": result.domain.assessment,
        "safety_notice": result.domain.safety_notice,
        "report": result.report,
    })

    return result


@app.post("/runs", response_model=RunResponse)
def start_run(req: RunRequest):
    """Start a new decision engine run."""
    if req.mode == "lab" and req.target not in LAB_TARGET_ALLOWLIST:
        raise HTTPException(status_code=400, detail="Target not in allowlist")

    # Web assessments: backend authorization enforcement (fail closed).
    # Frontend validation is UX only — this check is authoritative.
    if req.assessment_type == "web" or req.target_url:
        from vapt_platform.web_target import validate_web_target
        validation = validate_web_target(req.target_url or "")
        if not validation.authorized:
            raise HTTPException(status_code=400, detail=f"Target not authorized: {validation.reason}")

    # Convert API request to unified request
    vapt_request = VAPTRequest(
        scenario=req.scenario,
        mode=req.mode,
        target=req.target,
        port=req.port,
        path=req.path,
        assessor_mode="ai" if req.assessor == "llm" else "deterministic",
        assessor_provider=req.assessor_provider,
        assessor_api_key=req.assessor_api_key,
        assessor_model=req.assessor_model,
        max_attempts=req.max_attempts,
        scan_file=req.scan_file,
        assessment_type=req.assessment_type,
        target_url=req.target_url,
        use_nmap=req.use_nmap,
        use_nuclei=req.use_nuclei,
    )

    # Run the canonical workflow
    application = get_application()
    try:
        result = application.run(vapt_request)
        run_id = result.domain.run_id

        # Store result in job manager for later retrieval (FIX 1: separate).
        job_manager.set_state(run_id, {
            "scenario": result.domain.scenario,
            "mode": result.domain.mode,
            "status": result.domain.final_status,
            "candidates": result.domain.candidates,
            "service_discovery": result.domain.service_discovery,
            "execution_results": result.domain.execution_results,
            "decision_trace": result.domain.decision_trace,
            "total_attempts": result.domain.total_attempts,
            "pivot_count": result.domain.pivot_count,
            "candidates_processed": result.domain.candidates_processed,
            "evidence_tier": result.domain.evidence_tier,
            "assessment": result.domain.assessment,
            "safety_notice": result.domain.safety_notice,
            "report": result.report,
            "target_url": vapt_request.target_url,
            "assessment_type": vapt_request.assessment_type,
        })

        return RunResponse(run_id=run_id, status="completed", message="Run completed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_error_detail(e, req))


@app.get("/runs")
def list_runs(limit: int = 100):
    """List recent runs."""
    from vapt_platform.persistence import get_repository
    repository = get_repository()
    runs = repository.list_runs(limit=limit)
    return {
        "runs": [
            {
                "run_id": run.run_id,
                "scenario": run.scenario,
                "mode": run.mode,
                "status": run.status,
                "final_status": run.final_status,
                "evidence_tier": run.evidence_tier,
                "total_attempts": run.total_attempts,
                "pivot_count": run.pivot_count,
                "created_at": run.created_at,
                "target": run.target,
                "port": run.port,
                "target_url": run.target_url,
                "assessment_type": run.assessment_type,
                "finding_count": len(run.candidates or []),
                "service_discovery_count": len(getattr(run, "service_discovery", None) or []),
                "assessor_provider": run.assessor_provider,
            }
            for run in runs
        ]
    }


@app.post("/targets/validate", response_model=TargetValidateResponse)
def validate_target(req: TargetValidateRequest):
    """Preflight an authorized web target (authorization + reachability).

    Performs NO scanning — only URL validation and a single safe
    connectivity probe. Used by the GUI authorization indicator.
    """
    from vapt_platform.web_target import preflight_web_target, validate_web_target

    validation = validate_web_target(req.target_url or "")
    if not validation.authorized or validation.target is None:
        return TargetValidateResponse(
            authorized=False,
            authorization_status="REJECTED",
            preflight_status="TARGET NOT AUTHORIZED",
            reachable=False,
            target_url=(req.target_url or "").strip(),
            detail=validation.reason,
        )

    preflight = preflight_web_target(req.target_url)
    return TargetValidateResponse(
        authorized=True,
        authorization_status=preflight["authorization_status"],
        preflight_status=preflight["preflight_status"],
        reachable=preflight["reachable"],
        target_url=preflight["target_url"],
        resolved_host=preflight["resolved_host"],
        port=preflight["port"],
        http_status=preflight["http_status"],
        detail=preflight["detail"],
    )


@app.get("/scanners/status")
def get_scanner_status():
    """Report scanner executable availability (Nmap/Nuclei)."""
    from vapt_platform import scanner_service
    from vapt_platform.web_target import AUTHORIZED_WEB_HOSTS, AUTHORIZED_WEB_PORTS

    return {
        **scanner_service.scanner_status(),
        "authorized_hosts": sorted(AUTHORIZED_WEB_HOSTS),
        "authorized_ports": sorted(AUTHORIZED_WEB_PORTS),
    }


@app.get("/runs/{run_id}/persisted")
def get_persisted_run(run_id: str):
    """Get a persisted run by ID."""
    from vapt_platform.persistence import get_repository
    repository = get_repository()
    run = repository.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.to_dict()


@app.get("/runs/{run_id}", response_model=RunStatus)
def get_status(run_id: str):
    """Get run status."""
    status = job_manager.get_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    return status


@app.get("/runs/{run_id}/trace", response_model=RunTrace)
def get_trace(run_id: str):
    """Get decision trace."""
    job = job_manager.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail="Run not found")
    state = job.get("state", {}) or {}
    logs = state.get("decision_trace", []) if isinstance(state, dict) else []
    events = [TraceEvent(phase="log", detail=log) for log in logs]
    return RunTrace(run_id=run_id, events=events)


@app.get("/runs/{run_id}/events")
def get_run_events(run_id: str):
    """Get events for a run."""
    from vapt_platform.events import get_event_bus
    event_bus = get_event_bus()
    events = event_bus.get_events(run_id)
    return {
        "run_id": run_id,
        "events": [e.to_dict() for e in events],
        "current_state": event_bus.get_run_state(run_id),
    }


@app.get("/runs/{run_id}/report")
def get_report(run_id: str, format: str = "json"):
    """Get a report for a persisted run.
    
    Args:
        run_id: The run ID
        format: Report format (json, html, markdown, txt)
    """
    application = get_application()
    try:
        report = application.generate_report(run_id, format)
        return JSONResponse(content={"run_id": run_id, "format": format, "report": report})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_error_detail(e))


@app.get("/runs/{run_id}/evidence")
def get_evidence(run_id: str):
    """Get evidence tier and assessment provenance."""
    job = job_manager.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail="Run not found")
    state = job.get("state", {}) if isinstance(job.get("state"), dict) else {}
    return {
        "run_id": run_id,
        "evidence_tier": state.get("evidence_tier", "UNKNOWN"),
        "assessment": state.get("assessment", {}),
        "safety_notice": state.get("safety_notice", ""),
    }


@app.get("/runs/{run_id}/findings")
def get_findings(run_id: str):
    """Get the complete findings inventory (FIX 1 + FIX 2).

    ``candidates`` holds ONLY ACTIONABLE vulnerability findings
    (candidate_eligibility == "ACTIONABLE").
    ``service_discovery`` holds the preserved non-actionable inventory:
    Nmap service discovery AND Nuclei informational / fingerprint /
    discovery observations (candidate_eligibility ==
    "INFORMATIONAL / DISCOVERY"). Nothing is hidden: the Findings page
    shows both buckets with explicit eligibility.
    Falls back to the persisted run so inventory survives restarts.
    """
    job = job_manager.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail="Run not found")
    state = job.get("state", {}) if isinstance(job.get("state"), dict) else {}
    service_discovery = state.get("service_discovery", [])
    if not service_discovery:
        try:
            from vapt_platform.persistence import get_repository
            persisted = get_repository().get(run_id)
            if persisted is not None:
                service_discovery = list(getattr(persisted, "service_discovery", None) or [])
                if not service_discovery:
                    web = (persisted.pipeline_summary or {}).get("web", {}) or {}
                    service_discovery = list(
                        web.get("service_discovery", []) or web.get("discovery_snapshots", []) or []
                    )
        except Exception:
            service_discovery = []
    return {
        "run_id": run_id,
        "candidates": state.get("candidates", []),
        "service_discovery": service_discovery,
    }


@app.get("/runs/{run_id}/candidates")
def get_candidates(run_id: str):
    """Get candidate ranking (ACTIONABLE findings only, FIX 1 + FIX 2).

    Only findings with candidate_eligibility == "ACTIONABLE" appear here.
    Service-discovery records and informational / fingerprint / discovery
    observations are never included; they are available via ``/findings``
    → ``service_discovery`` and the Findings page inventory section with
    eligibility "INFORMATIONAL / DISCOVERY".
    """
    job = job_manager.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail="Run not found")
    state = job.get("state", {}) if isinstance(job.get("state"), dict) else {}
    return {
        "run_id": run_id,
        "candidates": state.get("candidates", []),
        "candidates_processed": state.get("candidates_processed", []),
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/")
def serve_frontend():
    """Serve the main frontend page."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "AI-VAPT API is running. Frontend not found."}


@app.get("/scenarios")
def list_scenarios():
    """List available scenarios."""
    from prototype.demo_data import SCENARIOS
    from prototype.docker_demo_data import DOCKER_SCENARIOS

    all_scenarios = {**SCENARIOS, **DOCKER_SCENARIOS}
    return {
        "scenarios": [
            {
                "name": name,
                "description": fn.__doc__ or "No description",
            }
            for name, (fn, _) in all_scenarios.items()
        ]
    }


@app.get("/intelligence/lookup")
def lookup_cve(cve: str):
    """Look up CVE intelligence (EPSS, CISA KEV)."""
    from vapt_platform.enrichment import LocalDatasetProvider

    provider = LocalDatasetProvider()
    return {
        "cve": cve,
        "epss": provider.get_epss(cve),
        "in_kev": provider.is_in_kev(cve),
        "cvss": provider.get_cvss(cve),
        "cwe_ids": provider.get_cwe_ids(cve),
    }


@app.get("/system/health")
def system_health():
    """Get detailed system health."""
    health_status: dict = {
        "application": "READY",
        "persistence": "READY",
        "research_core": "PROTECTED",
    }

    # Check Ollama
    try:
        from core.exploit_assessor import get_llm
        from vapt_platform.model_config import DEFAULT_OLLAMA_MODEL

        llm = get_llm(provider="ollama", model_name=DEFAULT_OLLAMA_MODEL)
        health_status["ollama"] = "READY"
        health_status["ollama_model"] = DEFAULT_OLLAMA_MODEL
        # Phase 33A: expose the experimental arm separately so the UI can
        # offer it without ever making it the implicit default.
        from vapt_platform.model_config import EXPERIMENTAL_MODELS

        health_status["ollama_experimental_models"] = list(EXPERIMENTAL_MODELS)
    except Exception as e:
        health_status["ollama"] = "UNAVAILABLE"
        health_status["ollama_error"] = _safe_error_detail(e)

    # Optional hosted provider: report CONFIGURATION state only. The API key
    # is never included in the payload — only whether it is present.
    try:
        from core.exploit_assessor import ChatOpenRouter, get_llm
        from vapt_platform.model_config import (
            OPENROUTER_MODELS, api_key_env_for, default_model_for,
            is_valid_model_name,
        )

        key_env = api_key_env_for("openrouter") or "OPENROUTER_API_KEY"
        key_configured = bool(os.getenv(key_env))
        health_status["openrouter"] = (
            "CONFIGURED" if key_configured else "NOT CONFIGURED"
        )
        health_status["openrouter_key_env"] = key_env
        health_status["openrouter_key_configured"] = key_configured
        # Effective model: honours the OPENROUTER_MODEL override when set.
        # A malformed override is reported as an error rather than shown as a
        # model name that would never actually be accepted by resolve_model.
        _model = default_model_for("openrouter")
        if is_valid_model_name(_model):
            health_status["openrouter_model"] = _model
        else:
            health_status["openrouter_model"] = None
            health_status["openrouter_model_error"] = (
                f"OPENROUTER_MODEL override is malformed: {_model!r}. "
                "Assessment requests will fail until it is corrected."
            )
        health_status["openrouter_models"] = list(OPENROUTER_MODELS)
        health_status["openrouter_integration"] = (
            "AVAILABLE" if ChatOpenRouter is not None else "NOT INSTALLED"
        )
        # Build the client only when both the key and the integration exist.
        if key_configured and ChatOpenRouter is not None:
            get_llm(provider="openrouter")
            health_status["openrouter_client"] = "READY"
    except Exception as e:
        health_status["openrouter"] = "UNAVAILABLE"
        health_status["openrouter_error"] = _safe_error_detail(e)

    # Docker status: probe the lab executor service (localhost:9090).
    # The executor container exposes /health when the Docker lab is running.
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:9090/health", timeout=2) as resp:
            if resp.status == 200:
                health_status["docker"] = "AVAILABLE"
                health_status["docker_note"] = "Docker lab executor healthy (localhost:9090)"
            else:
                health_status["docker"] = "UNAVAILABLE"
                health_status["docker_note"] = f"Executor responded with HTTP {resp.status}"
    except Exception:
        health_status["docker"] = "UNAVAILABLE"
        health_status["docker_note"] = "Docker lab executor not reachable (localhost:9090)"

    # Scanner availability for authorized web-target assessments.
    try:
        from vapt_platform import scanner_service
        scanners = scanner_service.scanner_status()
        health_status["nmap"] = "READY" if scanners["nmap"]["available"] else "UNAVAILABLE"
        health_status["nuclei"] = "READY" if scanners["nuclei"]["available"] else "NOT INSTALLED"
    except Exception:
        health_status["nmap"] = "UNKNOWN"
        health_status["nuclei"] = "UNKNOWN"

    return health_status


@app.get("/runs/{run_id}/assessment")
def get_assessment(run_id: str):
    """Get assessment details for a run."""
    job = job_manager.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail="Run not found")
    state = job.get("state", {}) if isinstance(job.get("state"), dict) else {}
    return {
        "run_id": run_id,
        "assessment": state.get("assessment", {}),
        "evidence_tier": state.get("evidence_tier", "UNKNOWN"),
    }
