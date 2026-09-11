"""FastAPI backend for the decision engine.

Uses the canonical VAPTApplication workflow service.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from prototype.lab_runner import LAB_TARGET_ALLOWLIST
from services.schemas import (
    RunRequest, RunResponse, RunStatus, RunTrace, ReportResponse,
    CheckpointResponse, ErrorResponse, TraceEvent
)
from services.jobs import job_manager
from vapt_platform.application import VAPTRequest, get_application

app = FastAPI(title="AI VAPT Decision Engine API", version="0.1.0")


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
        max_attempts=req.max_attempts,
        scan_file=req.scan_file,
    )

    job_manager.update(run_id, status="running")

    # Run the canonical workflow
    application = get_application()
    result = application.run(vapt_request)

    # Store result in job manager
    job_manager.set_state(run_id, {
        "scenario": result.domain.scenario,
        "mode": result.domain.mode,
        "status": result.domain.final_status,
        "candidates": result.domain.candidates,
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
        max_attempts=req.max_attempts,
        scan_file=req.scan_file,
    )

    # Run the canonical workflow
    application = get_application()
    try:
        result = application.run(vapt_request)
        run_id = result.domain.run_id
        
        return RunResponse(run_id=run_id, status="completed", message="Run completed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
            }
            for run in runs
        ]
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
        raise HTTPException(status_code=500, detail=str(e))


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
    """Get processed candidates/findings."""
    job = job_manager.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail="Run not found")
    state = job.get("state", {}) if isinstance(job.get("state"), dict) else {}
    return {
        "run_id": run_id,
        "candidates": state.get("candidates", []),
    }


@app.get("/runs/{run_id}/candidates")
def get_candidates(run_id: str):
    """Get candidate ranking."""
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
