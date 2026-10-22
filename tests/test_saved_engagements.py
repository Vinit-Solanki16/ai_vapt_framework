"""Tests for Saved Engagement Profiles and Scope Governance.

Verifies:
  - EngagementProfile dataclass behavior and expiry check.
  - EngagementManager atomic persistence, seeding, CRUD, and scope matching.
  - Path prefix restrictions and strict hostname/port validation.
  - Fail-closed security against wildcards, slashes, and invalid ports.
  - Integration with services.api FastAPI endpoints (GET, POST, PUT, DELETE, /validate).
  - Target validation via /targets/validate incorporating engagement_id.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from services.api import app as fastapi_app
from vapt_platform.engagements import (
    EngagementManager,
    EngagementProfile,
    EngagementValidationError,
    get_engagement_manager,
    set_engagement_manager,
)
from vapt_platform.web_target import validate_web_target


def _mock_dns(monkeypatch, ips: list[str]) -> None:
    import socket
    def fake(host, port, family=0, type=0, proto=0, flags=0):
        out = []
        for ip in ips:
            fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
            out.append((fam, socket.SOCK_STREAM, 0, "", (ip, 0)))
        return out
    monkeypatch.setattr("vapt_platform.web_target.socket.getaddrinfo", fake)


@pytest.fixture
def temp_engagement_manager(tmp_path, monkeypatch):
    _mock_dns(monkeypatch, ["93.184.216.34"])
    storage_file = str(tmp_path / "engagements_test.json")
    mgr = EngagementManager(storage_path=storage_file)
    old_mgr = get_engagement_manager()
    set_engagement_manager(mgr)
    yield mgr
    set_engagement_manager(old_mgr)


class TestEngagementProfileModel:
    def test_default_is_active(self):
        p = EngagementProfile(
            id="test-p1",
            name="Test Profile",
            authorized_hosts=["example.com"],
            allowed_ports=[80, 443],
        )
        assert p.is_active() is True
        d = p.to_dict()
        assert d["is_active"] is True
        assert d["id"] == "test-p1"
        assert d["name"] == "Test Profile"

    def test_status_inactive(self):
        p = EngagementProfile(
            id="test-p2",
            name="Inactive Profile",
            authorized_hosts=["example.com"],
            allowed_ports=[80],
            status="inactive",
        )
        assert p.is_active() is False

    def test_future_expiry_is_active(self):
        future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        p = EngagementProfile(
            id="test-p3",
            name="Future Expiry",
            authorized_hosts=["example.com"],
            allowed_ports=[80],
            expires_at=future,
        )
        assert p.is_active() is True

    def test_past_expiry_is_inactive(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        p = EngagementProfile(
            id="test-p4",
            name="Past Expiry",
            authorized_hosts=["example.com"],
            allowed_ports=[80],
            expires_at=past,
        )
        assert p.is_active() is False

    def test_malformed_expiry_fails_closed(self):
        p = EngagementProfile(
            id="test-p5",
            name="Malformed Expiry",
            authorized_hosts=["example.com"],
            allowed_ports=[80],
            expires_at="not-a-date",
        )
        assert p.is_active() is False


class TestEngagementManagerUnit:
    def test_seeds_defaults_on_empty(self, temp_engagement_manager):
        profiles = temp_engagement_manager.list_profiles()
        assert len(profiles) >= 2
        ids = {p.id for p in profiles}
        assert "eng-local-lab" in ids
        assert "eng-pentest-ground" in ids

    def test_create_and_persist_profile(self, temp_engagement_manager):
        created = temp_engagement_manager.create_profile({
            "name": "Acme PenTest 2026",
            "description": "Authorized client testing",
            "authorized_hosts": ["acme.test", "192.168.1.100"],
            "allowed_ports": [8080, 8443],
            "permitted_paths": ["/app", "/api"],
            "authorization_reference": "ROE-ACME-2026-001",
        })
        assert created.id.startswith("eng-")
        assert created.name == "Acme PenTest 2026"
        assert created.authorized_hosts == ["acme.test", "192.168.1.100"]
        assert created.allowed_ports == [8080, 8443]
        assert created.permitted_paths == ["/app", "/api"]
        assert created.authorization_reference == "ROE-ACME-2026-001"

        # Verify atomic persistence across reload
        reloaded_mgr = EngagementManager(storage_path=temp_engagement_manager.storage_path)
        fetched = reloaded_mgr.get_profile(created.id)
        assert fetched is not None
        assert fetched.name == "Acme PenTest 2026"
        assert fetched.authorized_hosts == ["acme.test", "192.168.1.100"]

    def test_update_profile_partial_and_full(self, temp_engagement_manager):
        created = temp_engagement_manager.create_profile({
            "name": "Update Target",
            "authorized_hosts": ["update.test"],
            "allowed_ports": [80],
            "authorization_reference": "REF-123",
        })
        # Partial update: status only
        updated = temp_engagement_manager.update_profile(created.id, {"status": "inactive"})
        assert updated.status == "inactive"
        assert updated.name == "Update Target"

        # Full update: ports and reference
        updated2 = temp_engagement_manager.update_profile(created.id, {
            "allowed_ports": [8080, 443],
            "authorization_reference": "REF-UPDATED-999",
            "status": "active",
        })
        assert updated2.allowed_ports == [8080, 443]
        assert updated2.authorization_reference == "REF-UPDATED-999"
        assert updated2.status == "active"

    def test_delete_profile(self, temp_engagement_manager):
        created = temp_engagement_manager.create_profile({
            "name": "To Delete",
            "authorized_hosts": ["delete.test"],
            "allowed_ports": [80],
            "authorization_reference": "DEL-1",
        })
        assert temp_engagement_manager.delete_profile(created.id) is True
        assert temp_engagement_manager.get_profile(created.id) is None
        assert temp_engagement_manager.delete_profile("nonexistent") is False

    def test_validation_rejects_wildcards_and_schemes(self, temp_engagement_manager):
        with pytest.raises(EngagementValidationError, match="cannot contain"):
            temp_engagement_manager.create_profile({
                "name": "Wildcard Attempt",
                "authorized_hosts": ["*.example.com"],
                "allowed_ports": [80],
                "authorization_reference": "BAD-1",
            })

        with pytest.raises(EngagementValidationError, match="cannot contain"):
            temp_engagement_manager.create_profile({
                "name": "Scheme Attempt",
                "authorized_hosts": ["https://example.com"],
                "allowed_ports": [443],
                "authorization_reference": "BAD-2",
            })

    def test_validation_rejects_invalid_ports(self, temp_engagement_manager):
        with pytest.raises(EngagementValidationError, match="Invalid port"):
            temp_engagement_manager.create_profile({
                "name": "Bad Port",
                "authorized_hosts": ["example.com"],
                "allowed_ports": [99999],
                "authorization_reference": "BAD-3",
            })

    def test_path_prefix_enforcement(self, temp_engagement_manager):
        created = temp_engagement_manager.create_profile({
            "name": "Path Restricted Lab",
            "authorized_hosts": ["path-test.internal"],
            "allowed_ports": [8080],
            "permitted_paths": ["/safe/path", "/v1/api"],
            "authorization_reference": "PATH-TEST-01",
        })
        # Allowed path
        res1 = temp_engagement_manager.validate_target_against_profile(created.id, "http://path-test.internal:8080/safe/path/index.html")
        assert res1["authorized"] is True

        # Disallowed path
        res2 = temp_engagement_manager.validate_target_against_profile(created.id, "http://path-test.internal:8080/forbidden/admin")
        assert res2["authorized"] is False
        assert "does not match any permitted paths" in res2["reason"]

    def test_validate_target_against_profile_port_mismatch(self, temp_engagement_manager):
        created = temp_engagement_manager.create_profile({
            "name": "Port 80 Only",
            "authorized_hosts": ["port-check.test"],
            "allowed_ports": [80],
            "authorization_reference": "PORT-80",
        })
        res = temp_engagement_manager.validate_target_against_profile(created.id, "http://port-check.test:8080/")
        assert res["authorized"] is False
        assert "is not in allowed ports" in res["reason"]


class TestEngagementAPI:
    def test_list_engagements_endpoint(self, temp_engagement_manager):
        client = TestClient(fastapi_app)
        resp = client.get("/engagements")
        assert resp.status_code == 200
        data = resp.json()
        assert "engagements" in data
        assert len(data["engagements"]) >= 2

    def test_crud_lifecycle_api(self, temp_engagement_manager):
        client = TestClient(fastapi_app)

        # Create
        create_payload = {
            "name": "API Created Profile",
            "description": "Via REST endpoint",
            "authorized_hosts": ["api-test.corp"],
            "allowed_ports": [443],
            "authorization_reference": "ROE-REST-001",
        }
        res_create = client.post("/engagements", json=create_payload)
        assert res_create.status_code == 200
        eng = res_create.json()["engagement"]
        prof_id = eng["id"]
        assert eng["name"] == "API Created Profile"

        # Get
        res_get = client.get(f"/engagements/{prof_id}")
        assert res_get.status_code == 200
        assert res_get.json()["engagement"]["id"] == prof_id

        # Update
        res_update = client.put(f"/engagements/{prof_id}", json={"status": "inactive"})
        assert res_update.status_code == 200
        assert res_update.json()["engagement"]["status"] == "inactive"

        # Delete
        res_del = client.delete(f"/engagements/{prof_id}")
        assert res_del.status_code == 200
        assert res_del.json()["status"] == "deleted"

        # 404 after delete
        assert client.get(f"/engagements/{prof_id}").status_code == 404

    def test_validate_target_against_profile_api(self, temp_engagement_manager):
        client = TestClient(fastapi_app)
        # Seeded profile for pentest-ground:4280
        resp = client.post(
            "/engagements/eng-pentest-ground/validate",
            json={"target_url": "https://pentest-ground.com:4280/login"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["authorized"] is True
        assert data["matched"] is True

    def test_targets_validate_with_engagement_id(self, temp_engagement_manager, monkeypatch):
        # Even if VAPT_AUTHORIZED_WEB_SCOPES is unset, passing engagement_id
        # authorizes the target!
        monkeypatch.delenv("VAPT_AUTHORIZED_WEB_SCOPES", raising=False)
        client = TestClient(fastapi_app)

        resp = client.post(
            "/targets/validate",
            json={
                "target_url": "https://pentest-ground.com:4280/",
                "engagement_id": "eng-pentest-ground",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["authorized"] is True
        assert data["in_scope"] is True
        assert data["engagement_id"] == "eng-pentest-ground"
        assert data["engagement_name"] == "Pentest Ground Authorized Lab"
        assert data["authorization_reference"] == "ROE-2026-PENTEST-GROUND-4280"
