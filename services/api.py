"""FastAPI backend for the decision engine."""
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

app = FastAPI(title="AI VAPT Decision Engine API", version="0.1.0")


def _run_engine(run_id: str, req: RunRequest):
    """Execute the decision engine for a run."""
    from prototype.engine_integration import run_decision_scenario
    from prototype.execution_layer import create_lab_executor
    from decision_engine.adapters.scan_adapter import candidates_from_scan, candidates_to_scenario
    from prototype.demo_data import SCENARIOS
    from prototype.engine_integration import load_vapt_corpus_scenario

    job_manager.update(run_id, status="running")

    candidates = None
    scenario_name = req.scenario

    if req.scan_file:
        candidates = candidates_to_scenario(candidates_from_scan(req.scan_file))
        scenario_name = f"scan:{os.path.basename(req.scan_file)}"
    elif req.scenario in SCENARIOS:
        fn, kwargs = SCENARIOS[req.scenario]
        candidates = fn(**kwargs)
    elif req.scenario == "corpus":
        candidates = load_vapt_corpus_scenario()
    else:
        raise ValueError(f"Unknown scenario: {req.scenario}")

    executor = None
    if req.mode == "lab":
        if not req.target:
            raise ValueError("--target required for lab mode")
        executor = create_lab_executor(req.target, req.port)

    final_state = run_decision_scenario(
        candidates,
        max_attempts=req.max_attempts,
        mode=req.mode,
        executor=executor,
        assessor=req.assessor,
    )

    job_manager.set_state(run_id, final_state)
    return final_state


@app.post("/runs", response_model=RunResponse)
def start_run(req: RunRequest):
    """Start a new decision engine run."""
    if req.mode == "lab" and req.target not in LAB_TARGET_ALLOWLIST:
        raise HTTPException(status_code=400, detail="Target not in allowlist")

    run_id = job_manager.create(req.scenario, req.mode)
    try:
        _run_engine(run_id, req)
        return RunResponse(run_id=run_id, status="completed", message="Run completed")
    except Exception as e:
        job_manager.set_failed(run_id, str(e))
        raise HTTPException(status_code=500, detail=str(e))


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
    logs = state.get("logs", []) if isinstance(state, dict) else []
    events = [TraceEvent(phase="log", detail=log) for log in logs]
    return RunTrace(run_id=run_id, events=events)


@app.get("/runs/{run_id}/report", response_model=ReportResponse)
def get_report(run_id: str):
    """Get JSON report."""
    job = job_manager.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail="Run not found")
    state = job.get("state", {}) if isinstance(job.get("state"), dict) else {}
    presentation = state.get("_presentation", {})
    # Convert ActionCandidate objects to dicts for the response schema
    candidates = []
    for c in (state.get("candidates", []) if isinstance(state, dict) else []):
        if hasattr(c, 'model_dump'):
            candidates.append(c.model_dump(mode="json"))
        elif hasattr(c, '__dict__'):
            candidates.append(c.__dict__)
        else:
            candidates.append(c)
    return ReportResponse(
        run_id=run_id,
        scenario=job.get("scenario"),
        execution_mode=job.get("mode", "simulation"),
        final_status=state.get("status") if isinstance(state, dict) else None,
        candidates=candidates,
        execution_results=state.get("results", []) if isinstance(state, dict) else [],
        decision_trace=state.get("logs", []) if isinstance(state, dict) else [],
        total_attempts=presentation.get("total_attempts", 0),
        pivot_count=presentation.get("pivot_count", 0),
        candidates_processed=presentation.get("candidates_processed", []),
        safety_notice="SIMULATION MODE" if job.get("mode") == "simulation" else "LAB MODE (DOCKER OBSERVED)",
    )


@app.get("/health")
def health():
    return {"status": "healthy"}
