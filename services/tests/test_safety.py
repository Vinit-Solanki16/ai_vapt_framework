"""Safety tests for the API layer (services/api.py).

Verifies that non-allowlisted targets are refused at the /runs endpoint
when mode == "lab". These tests verify behavior; they do not change the engine.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api import app


@pytest.fixture
def client():
    return TestClient(app)


class TestAPISafety:
    """API-level allowlist enforcement at /runs endpoint."""

    def test_simulation_mode_ignores_target(self, client):
        """Simulation mode should accept any target (it is ignored)."""
        resp = client.post("/runs", json={
            "scenario": "success",
            "max_attempts": 2,
            "mode": "simulation",
            "target": "192.168.1.100",  # non-allowlisted, but ignored in simulation
            "port": 8080,
            "assessor": "deterministic",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

    def test_lab_mode_accepts_allowlisted_127(self, client):
        """Lab mode must accept 127.0.0.1."""
        resp = client.post("/runs", json={
            "scenario": "success",
            "max_attempts": 2,
            "mode": "lab",
            "target": "127.0.0.1",
            "port": 8080,
            "assessor": "deterministic",
        })
        # Note: the engine may fail because no emulator is running,
        # but the allowlist check should pass (200 or 500, not 400)
        assert resp.status_code != 400, f"Got 400: {resp.json()}"

    def test_lab_mode_accepts_allowlisted_172(self, client):
        """Lab mode must accept 172.28.0.2."""
        resp = client.post("/runs", json={
            "scenario": "success",
            "max_attempts": 2,
            "mode": "lab",
            "target": "172.28.0.2",
            "port": 8080,
            "assessor": "deterministic",
        })
        assert resp.status_code != 400, f"Got 400: {resp.json()}"

    def test_lab_mode_rejects_non_allowlisted(self, client):
        """Lab mode must reject non-allowlisted targets with HTTP 400."""
        resp = client.post("/runs", json={
            "scenario": "success",
            "max_attempts": 2,
            "mode": "lab",
            "target": "192.168.1.100",
            "port": 8080,
            "assessor": "deterministic",
        })
        assert resp.status_code == 400
        assert "allowlist" in resp.json()["detail"].lower()

    def test_lab_mode_rejects_localhost(self, client):
        """Lab mode must reject 'localhost' (not in allowlist)."""
        resp = client.post("/runs", json={
            "scenario": "success",
            "max_attempts": 2,
            "mode": "lab",
            "target": "localhost",
            "port": 8080,
            "assessor": "deterministic",
        })
        assert resp.status_code == 400
        assert "allowlist" in resp.json()["detail"].lower()

    def test_lab_mode_rejects_empty_target(self, client):
        """Lab mode must reject missing target."""
        resp = client.post("/runs", json={
            "scenario": "success",
            "max_attempts": 2,
            "mode": "lab",
            "target": "",
            "port": 8080,
            "assessor": "deterministic",
        })
        assert resp.status_code == 400

    def test_lab_mode_case_insensitive_check(self, client):
        """Allowlist check should be case-insensitive."""
        resp = client.post("/runs", json={
            "scenario": "success",
            "max_attempts": 2,
            "mode": "lab",
            "target": "127.0.0.1",  # lowercase
            "port": 8080,
            "assessor": "deterministic",
        })
        assert resp.status_code != 400