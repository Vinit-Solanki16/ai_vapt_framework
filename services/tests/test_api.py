"""Tests for the FastAPI backend."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.api import app
from services.jobs import job_manager


@pytest.fixture
def client():
    return TestClient(app)


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
        resp = client.get(f"/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == run_id

    def test_get_status_missing(self, client):
        resp = client.get("/runs/nonexistent")
        assert resp.status_code == 404


class TestGetTrace:
    def test_get_trace(self, client):
        resp = client.post("/runs", json={"scenario": "success", "mode": "simulation"})
        run_id = resp.json()["run_id"]
        resp = client.get(f"/runs/{run_id}/trace")
        assert resp.status_code == 200
        assert "events" in resp.json()


class TestGetReport:
    def test_get_report(self, client):
        resp = client.post("/runs", json={"scenario": "success", "mode": "simulation"})
        run_id = resp.json()["run_id"]
        resp = client.get(f"/runs/{run_id}/report")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run_id
        assert "safety_notice" in data
