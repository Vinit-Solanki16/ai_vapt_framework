"""Regression coverage for the asynchronous assessment job contract."""
from __future__ import annotations

import threading
import time

import pytest
from fastapi import HTTPException

import services.api as api
from services.jobs import JobCapacityError, JobManager
from services.schemas import RunRequest
from vapt_platform.persistence import JSONRunRepository, PersistenceConfig
from vapt_platform.persistence.repository import set_repository


@pytest.fixture(autouse=True)
def isolated_repository(tmp_path):
    set_repository(JSONRunRepository(config=PersistenceConfig(storage_dir=str(tmp_path))))
    yield
    set_repository(JSONRunRepository())


def _wait_for(manager: JobManager, run_id: str, terminal: bool = True):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = manager.get_status(run_id)
        if status and (not terminal or status.status in {"completed", "failed"}):
            return status
        time.sleep(0.01)
    raise AssertionError(f"job {run_id} did not reach a terminal state")


def test_submission_returns_before_long_assessment_finishes(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_engine(run_id, req, runtime_key=None):
        started.set()
        release.wait(2)
        api.job_manager.set_state(run_id, {
            "scenario": req.scenario,
            "mode": req.mode,
            "status": "SUCCESS",
            "assessment": {"provider": "deterministic", "model": None},
            "report": {"run_id": run_id},
        })

    monkeypatch.setattr(api, "_run_engine", slow_engine)
    begin = time.monotonic()
    response = api.start_run(RunRequest(scenario="async-immediate", mode="simulation"))
    elapsed = time.monotonic() - begin

    assert elapsed < 0.5
    assert response.status == "queued"
    assert response.run_id
    assert started.wait(1)
    assert api.get_status(response.run_id).status in {"queued", "running"}
    release.set()
    assert _wait_for(api.job_manager, response.run_id).status == "completed"


def test_accepted_run_is_persisted_before_worker_starts(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_engine(run_id, req, runtime_key=None):
        started.set()
        release.wait(2)
        api.job_manager.set_state(run_id, {
            "scenario": req.scenario,
            "mode": req.mode,
            "status": "SUCCESS",
        })

    monkeypatch.setattr(api, "_run_engine", slow_engine)
    response = api.start_run(RunRequest(scenario="persisted-queue", mode="simulation"))

    from vapt_platform.persistence import get_repository

    persisted = get_repository().get(response.run_id)
    assert persisted is not None
    assert persisted.status == "PENDING"
    assert started.wait(1)
    release.set()
    assert _wait_for(api.job_manager, response.run_id).status == "completed"


def test_successful_async_completion_exposes_report_and_counts():
    response = api.start_run(RunRequest(scenario="failure_pivot", mode="simulation"))
    status = _wait_for(api.job_manager, response.run_id)
    assert api.get_status(response.run_id).status == "completed"

    assert response.status == "queued"
    assert status.status == "completed"
    assert status.final_status in {"SUCCESS", "COMPLETED"}
    assert status.total_attempts == 3
    assert status.pivot_count >= 1
    assert status.evidence_tier == "SIMULATED"
    assert status.assessment["provider"] == "deterministic"
    assert status.report


def test_worker_exception_becomes_sanitized_failed_state(monkeypatch):
    secret = "sk-or-v1-0123456789abcdef0123456789abcdef0123456789abcdef"

    def explode(run_id, req, runtime_key=None):
        raise RuntimeError(f"provider timeout with {secret}")

    monkeypatch.setattr(api, "_run_engine", explode)
    response = api.start_run(RunRequest(scenario="worker-failure", mode="simulation"))
    status = _wait_for(api.job_manager, response.run_id)

    assert status.status == "failed"
    assert api.get_status(response.run_id).status == "failed"
    assert status.error
    assert "running" not in status.error.lower()
    assert secret not in status.error
    assert api._persisted_state(response.run_id) is not None


def test_queue_states_duplicate_coalescing_and_capacity():
    manager = JobManager(max_workers=1, max_queue=0)
    started = threading.Event()
    release = threading.Event()

    def worker(run_id):
        manager.update(run_id, status="running")
        started.set()
        release.wait(2)
        manager.set_state(run_id, {"scenario": "x", "mode": "simulation", "status": "SUCCESS"})

    first, duplicate = manager.submit("x", "simulation", "same-request", worker)
    assert duplicate is False
    assert started.wait(1)
    assert manager.get_status(first).status == "running"

    same, duplicate = manager.submit("x", "simulation", "same-request", worker)
    assert same == first
    assert duplicate is True

    with pytest.raises(JobCapacityError):
        manager.submit("y", "simulation", "different-request", worker)

    release.set()
    assert _wait_for(manager, first).status == "completed"


def test_authorization_rejects_before_scheduling(monkeypatch):
    called = []
    monkeypatch.setattr(api, "_run_engine", lambda *args, **kwargs: called.append(args))
    with pytest.raises(HTTPException) as exc:
        api.start_run(RunRequest(scenario="auth-first", mode="lab", target="192.0.2.1"))

    assert exc.value.status_code == 400
    assert called == []


def test_ollama_timeout_fallback_keeps_provider_model_and_response_provenance(monkeypatch):
    from decision_engine.core.schemas import ActionCandidate
    from vapt_platform import assessment

    def timeout(*args, errors=None, **kwargs):
        errors.append("ollama timeout after 30s")
        return None

    monkeypatch.setattr(assessment, "_try_ollama_assess", timeout)
    assessor = assessment.create_assessor(
        mode="ai", provider="ollama", model_name="llama3.2:3b"
    )
    result = assessor(ActionCandidate(id="timeout-candidate", probability=0.5))

    assert result.fallback is True
    assert result.source == "deterministic"
    assert result.provider == "ollama"
    assert result.model == "llama3.2:3b"
    assert result.llm_response_received is False
    assert "timeout" in result.error.lower()
