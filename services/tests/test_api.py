"""Tests for the FastAPI backend."""
from __future__ import annotations

import tempfile
import shutil
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.api import app
from services.jobs import job_manager
from vapt_platform.persistence import PersistenceConfig, JSONRunRepository
from vapt_platform.persistence.repository import set_repository


@pytest.fixture
def client():
    """Create a test client with isolated persistence."""
    # Create isolated temp directory for this test
    temp_dir = tempfile.mkdtemp()
    config = PersistenceConfig(storage_dir=temp_dir)
    repo = JSONRunRepository(config=config)
    set_repository(repo)
    
    yield TestClient(app)
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestStartRun:
    def test_start_run_success(self, client):
        resp = client.post("/runs", json={
            "scenario": "success",
            "max_attempts": 2,
            "mode": "simulation",
            "assessor": "deterministic",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "completed"

    def test_start_run_lab_rejects_non_allowlisted(self, client):
        resp = client.post("/runs", json={
            "scenario": "success",
            "mode": "lab",
            "target": "192.168.1.100",
            "port": 8080,
        })
        assert resp.status_code == 400
        assert "allowlist" in resp.json()["detail"]


class TestGetStatus:
    def test_get_status_existing(self, client):
        # Create a run first
        resp = client.post("/runs", json={"scenario": "success", "mode": "simulation"})
        run_id = resp.json()["run_id"]
        resp = client.get(f"/runs/{run_id}/persisted")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == run_id

    def test_get_status_missing(self, client):
        resp = client.get("/runs/nonexistent/persisted")
        assert resp.status_code == 404


class TestGetTrace:
    def test_get_trace(self, client):
        resp = client.post("/runs", json={"scenario": "success", "mode": "simulation"})
        run_id = resp.json()["run_id"]
        resp = client.get(f"/runs/{run_id}/persisted")
        assert resp.status_code == 200
        data = resp.json()
        assert "decision_trace" in data


class TestGetReport:
    def test_get_report(self, client):
        resp = client.post("/runs", json={"scenario": "success", "mode": "simulation"})
        run_id = resp.json()["run_id"]
        resp = client.get(f"/runs/{run_id}/report")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run_id
        assert "report" in data
        assert "format" in data
