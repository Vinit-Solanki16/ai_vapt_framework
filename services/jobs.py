"""In-memory job state manager for the decision engine backend."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from services.schemas import RunStatus


class JobManager:
    """Manages run lifecycle: create, track, complete, fail."""

    def __init__(self):
        self._jobs: Dict[str, dict] = {}

    def create(self, scenario: Optional[str], mode: str) -> str:
        run_id = str(uuid.uuid4())[:8]
        self._jobs[run_id] = {
            "run_id": run_id,
            "scenario": scenario,
            "mode": mode,
            "status": "pending",
            "state": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }
        return run_id

    def get(self, run_id: str) -> Optional[dict]:
        return self._jobs.get(run_id)

    def update(self, run_id: str, **kwargs):
        job = self._jobs.get(run_id)
        if job:
            job.update(kwargs)
            job["updated_at"] = datetime.now(timezone.utc).isoformat()

    def set_state(self, run_id: str, state: dict):
        job = self._jobs.get(run_id)
        if not job:
            # Auto-create job entry if it doesn't exist
            self._jobs[run_id] = {
                "run_id": run_id,
                "scenario": state.get("scenario"),
                "mode": state.get("mode", "simulation"),
                "status": "pending",
                "state": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            }
            job = self._jobs[run_id]
        job["state"] = state
        job["status"] = "completed"
        job["updated_at"] = datetime.now(timezone.utc).isoformat()

    def set_failed(self, run_id: str, error: str):
        job = self._jobs.get(run_id)
        if job:
            job["status"] = "failed"
            job["error"] = error
            job["updated_at"] = datetime.now(timezone.utc).isoformat()

    def get_status(self, run_id: str) -> Optional[RunStatus]:
        job = self._jobs.get(run_id)
        if not job:
            return None
        state = job.get("state", {}) or {}
        presentation = state.get("_presentation", {}) if isinstance(state, dict) else {}
        return RunStatus(
            run_id=run_id,
            status=job["status"],
            scenario=job.get("scenario"),
            mode=job.get("mode", "simulation"),
            final_status=state.get("status") if isinstance(state, dict) else None,
            total_attempts=presentation.get("total_attempts", 0),
            pivot_count=presentation.get("pivot_count", 0),
            candidates_processed=presentation.get("candidates_processed", []),
        )

    def list_jobs(self) -> list:
        return [
            {
                "run_id": j["run_id"],
                "scenario": j["scenario"],
                "mode": j["mode"],
                "status": j["status"],
                "created_at": j["created_at"],
            }
            for j in self._jobs.values()
        ]


# Singleton
job_manager = JobManager()
