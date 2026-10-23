"""Bounded in-memory job queue for long-running decision-engine runs.

The queue owns the request-independent lifecycle. The assessment itself is
run by a worker thread, so a FastAPI request never waits for scanners or LLM
inference to finish.
"""
from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from services.schemas import RunStatus


class JobCapacityError(RuntimeError):
    """Raised when the bounded worker and waiting queue are full."""


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


class JobManager:
    """Track jobs and execute each accepted job at most once.

    ``max_workers`` limits concurrent scans/inference. ``max_queue`` limits
    accepted work waiting for a worker. An active request fingerprint is
    coalesced, which prevents browser retries from starting a second copy of
    the same assessment while the first one is queued or running.
    """

    def __init__(self, max_workers: Optional[int] = None, max_queue: Optional[int] = None):
        self.max_workers = max_workers or _bounded_int("VAPT_MAX_WORKERS", 2, 1, 16)
        self.max_queue = max_queue if max_queue is not None else _bounded_int(
            "VAPT_MAX_QUEUED_JOBS", 8, 0, 128
        )
        self._jobs: Dict[str, dict] = {}
        self._active_fingerprints: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._capacity = threading.BoundedSemaphore(self.max_workers + self.max_queue)
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="vapt-assessment",
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _new_job(
        self,
        run_id: str,
        scenario: Optional[str],
        mode: str,
        fingerprint: str,
        slot_reserved: bool = False,
    ) -> dict:
        now = self._now()
        return {
            "run_id": run_id,
            "scenario": scenario,
            "mode": mode,
            "status": "queued",
            "state": None,
            "created_at": now,
            "updated_at": now,
            "error": None,
            "fingerprint": fingerprint,
            "_slot_released": not slot_reserved,
        }

    @staticmethod
    def _new_run_id() -> str:
        return str(uuid.uuid4())

    def create(self, scenario: Optional[str], mode: str) -> str:
        """Create a queued job for compatibility with direct callers."""
        if not self._capacity.acquire(blocking=False):
            raise JobCapacityError("Assessment worker capacity is full; retry later.")
        run_id = self._new_run_id()
        with self._lock:
            self._jobs[run_id] = self._new_job(run_id, scenario, mode, "", slot_reserved=True)
        return run_id

    def submit(
        self,
        scenario: Optional[str],
        mode: str,
        fingerprint: str,
        worker: Callable[[str], None],
        on_accept: Optional[Callable[[str], None]] = None,
    ) -> tuple[str, bool]:
        """Atomically accept a worker and return ``(run_id, deduplicated)``.

        ``on_accept`` runs after the stable ID is allocated but before the
        worker is submitted. This lets callers persist the queued record
        without a race where a fast worker completes and is then overwritten
        by a late ``PENDING`` record.
        """
        with self._lock:
            existing_id = self._active_fingerprints.get(fingerprint)
            if existing_id:
                existing = self._jobs.get(existing_id)
                if existing and existing["status"] in {"queued", "running"}:
                    return existing_id, True
                self._active_fingerprints.pop(fingerprint, None)

            if not self._capacity.acquire(blocking=False):
                raise JobCapacityError(
                    "Assessment worker capacity is full; retry later. "
                    f"Maximum concurrent workers: {self.max_workers}; "
                    f"queued jobs: {self.max_queue}."
                )

            run_id = self._new_run_id()
            self._jobs[run_id] = self._new_job(
                run_id, scenario, mode, fingerprint, slot_reserved=True
            )
            self._active_fingerprints[fingerprint] = run_id
            try:
                if on_accept is not None:
                    on_accept(run_id)
                self._executor.submit(self._execute, run_id, fingerprint, worker)
            except Exception:
                self._jobs[run_id]["status"] = "failed"
                self._jobs[run_id]["error"] = "Assessment worker could not be scheduled."
                self._active_fingerprints.pop(fingerprint, None)
                self._release_slot_locked(self._jobs[run_id])
                raise
            return run_id, False

    def _execute(self, run_id: str, fingerprint: str, worker: Callable[[str], None]) -> None:
        try:
            worker(run_id)
        except BaseException:
            # The API worker handles ordinary exceptions with a sanitized
            # actionable message. This final guard prevents an unexpected
            # thread-level failure from leaving a run stuck in ``running``.
            self.set_failed(
                run_id,
                "Assessment worker terminated unexpectedly. Check server logs and retry the run.",
            )
        finally:
            with self._lock:
                if self._active_fingerprints.get(fingerprint) == run_id:
                    self._active_fingerprints.pop(fingerprint, None)
                job = self._jobs.get(run_id)
                if job:
                    self._release_slot_locked(job)

    def _release_slot_locked(self, job: dict) -> None:
        if not job.get("_slot_released", True):
            job["_slot_released"] = True
            self._capacity.release()

    def get(self, run_id: str) -> Optional[dict]:
        with self._lock:
            return self._jobs.get(run_id)

    def update(self, run_id: str, **kwargs) -> None:
        with self._lock:
            job = self._jobs.get(run_id)
            if job:
                job.update(kwargs)
                job["updated_at"] = self._now()

    def set_state(self, run_id: str, state: dict) -> None:
        with self._lock:
            job = self._jobs.get(run_id)
            if not job:
                # Direct application callers may publish a completed result
                # without first submitting through this manager.
                job = self._new_job(
                    run_id, state.get("scenario"), state.get("mode", "simulation"), ""
                )
                self._jobs[run_id] = job
            job["state"] = state
            job["status"] = "completed"
            job["error"] = None
            job["updated_at"] = self._now()
            self._release_slot_locked(job)

    def set_failed(self, run_id: str, error: str, state: Optional[dict] = None) -> None:
        with self._lock:
            job = self._jobs.get(run_id)
            if job:
                if state is not None:
                    job["state"] = state
                job["status"] = "failed"
                job["error"] = error
                job["updated_at"] = self._now()
                self._release_slot_locked(job)

    def get_status(self, run_id: str) -> Optional[RunStatus]:
        job = self.get(run_id)
        if not job:
            return None
        state = job.get("state", {}) or {}
        if not isinstance(state, dict):
            state = {}
        presentation = state.get("_presentation", {}) or {}
        return RunStatus(
            run_id=run_id,
            status=job["status"],
            scenario=job.get("scenario"),
            mode=job.get("mode", "simulation"),
            final_status=state.get("status"),
            total_attempts=state.get("total_attempts", presentation.get("total_attempts", 0)),
            pivot_count=state.get("pivot_count", presentation.get("pivot_count", 0)),
            candidates_processed=state.get(
                "candidates_processed", presentation.get("candidates_processed", [])
            ) or [],
            evidence_tier=state.get("evidence_tier"),
            assessment=state.get("assessment", {}) or {},
            decision_trace=state.get("decision_trace", []) or [],
            candidates=state.get("candidates", []) or [],
            execution_results=state.get("execution_results", []) or [],
            service_discovery=state.get("service_discovery", []) or [],
            report=state.get("report", {}) or {},
            error=job.get("error"),
            updated_at=job.get("updated_at"),
        )

    def list_jobs(self) -> list:
        with self._lock:
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


# Singleton used by the API process. Deployment settings are bounded by the
# constructor even when environment variables contain invalid values.
job_manager = JobManager()
