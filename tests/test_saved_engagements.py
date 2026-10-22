"""Tests for Saved Engagement Profiles, Scope Governance, and Security Hardening.

Verifies:
  - EngagementProfile dataclass behavior, fail-closed external defaults, and expiry check.
  - EngagementManager atomic persistence, template seeding, CRUD, and scope matching.
  - Runtime storage location outside git and safe migration from legacy storage.
  - Explicit persistence errors, failure rollback, and corruption backup / isolation.
  - Rejection of secrets / API keys in engagement profiles.
  - API endpoint protection: admin authentication, loopback policy, CORS origin check.
  - Integration with services.api FastAPI endpoints (GET, POST, PUT, DELETE, diagnostics, /validate).
  - Target validation via /targets/validate incorporating engagement_id and immutable snapshot.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from services.api import app as fastapi_app
from vapt_platform.engagements import (
    EngagementManager,
    EngagementProfile,
    EngagementStorageError,
    EngagementValidationError,
    get_engagement_manager,
    set_engagement_manager,
)
from vapt_platform.web_target import validate_web_target


def _mock_dns(monkeypatch, ips: list[str]) -> None:
    import socket
    def fake(host, port, family=0, type=0, proto=0, flags=0):
        if host in ("127.0.0.1", "localhost"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))]
        out = []
        for ip in ips:
            fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
            out.append((fam, socket.SOCK_STREAM, 0, "", (ip, 0)))
        return out
    monkeypatch.setattr("vapt_platform.web_target.socket.getaddrinfo", fake)


@pytest.fixture
def temp_engagement_manager(tmp_path, monkeypatch):
    _mock_dns(monkeypatch, ["93.184.216.34"])
    # Clear VAPT_ADMIN_TOKEN by default so local tests run smoothly
    monkeypatch.delenv("VAPT_ADMIN_TOKEN", raising=False)
    storage_file = str(tmp_path / "engagements_test.json")
    mgr = EngagementManager(storage_path=storage_file)
    old_mgr = get_engagement_manager()
    set_engagement_manager(mgr)
    yield mgr
    set_engagement_manager(old_mgr)


class TestEngagementProfileModel:
    def test_default_is_active_for_local_loopback(self):
        p = EngagementProfile(
            id="test-p1",
            name="Test Local Profile",
            authorized_hosts=["127.0.0.1", "localhost"],
            allowed_ports=[80, 443],
        )
        assert p.is_external() is False
        assert p.is_active() is True
        d = p.to_dict()
        assert d["is_active"] is True
        assert d["id"] == "test-p1"
        assert d["name"] == "Test Local Profile"

    def test_external_without_authorization_reference_fails_closed(self):
        # External profile without a genuine reference must NOT be active
        p = EngagementProfile(
            id="test-ext-1",
            name="External Without RoE",
            authorized_hosts=["example.com"],
            allowed_ports=[80, 443],
            authorization_reference="",
        )
        assert p.is_external() is True
        assert p.is_active() is False

    def test_external_with_placeholder_reference_fails_closed(self):
        p = EngagementProfile(
            id="test-ext-placeholder",
            name="External With Placeholder",
            authorized_hosts=["pentest-ground.com"],
            allowed_ports=[4280],
            authorization_reference="PENDING_OPERATOR_AUTHORIZATION_REVIEW",
        )
        assert p.is_external() is True
        assert p.is_active() is False

    def test_external_with_valid_reference_is_active(self):
        p = EngagementProfile(
            id="test-ext-valid",
            name="External With RoE",
            authorized_hosts=["example.com"],
            allowed_ports=[80, 443],
            authorization_reference="ROE-2026-EXAMPLE-CORP",
        )
        assert p.is_external() is True
        assert p.is_active() is True

    def test_status_inactive(self):
        p = EngagementProfile(
            id="test-p2",
            name="Inactive Profile",
            authorized_hosts=["127.0.0.1"],
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
            authorization_reference="ROE-EXPIRY-001",
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
            authorization_reference="ROE-EXPIRY-002",
            expires_at=past,
        )
        assert p.is_active() is False

    def test_malformed_expiry_fails_closed(self):
        p = EngagementProfile(
            id="test-p5",
            name="Malformed Expiry",
            authorized_hosts=["127.0.0.1"],
            allowed_ports=[80],
            expires_at="not-a-date",
        )
        assert p.is_active() is False


class TestEngagementManagerUnit:
    def test_seeds_defaults_on_empty(self, temp_engagement_manager):
        profiles = temp_engagement_manager.list_profiles()
        assert len(profiles) >= 2
        id_map = {p.id: p for p in profiles}
        assert "eng-local-lab" in id_map
        assert "eng-pentest-ground" in id_map

        # Local lab is active by default
        assert id_map["eng-local-lab"].is_active() is True

        # External sample is strictly INACTIVE by default with placeholder reference
        assert id_map["eng-pentest-ground"].is_active() is False
        assert id_map["eng-pentest-ground"].status == "inactive"
        assert "PENDING" in id_map["eng-pentest-ground"].authorization_reference

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

    def test_create_external_profile_requires_authorization_reference(self, temp_engagement_manager):
        # Attempting to create an active external profile without an authorization reference must be rejected
        with pytest.raises(EngagementValidationError, match="cannot be active without a genuine recorded authorization reference"):
            temp_engagement_manager.create_profile({
                "name": "Unauthorized External",
                "authorized_hosts": ["external-victim.com"],
                "allowed_ports": [80],
                "authorization_reference": "",
                "status": "active",
            })

        # Attempting to create an active external profile with placeholder reference must be rejected
        with pytest.raises(EngagementValidationError, match="cannot be active without a genuine recorded authorization reference"):
            temp_engagement_manager.create_profile({
                "name": "Placeholder External",
                "authorized_hosts": ["external-victim.com"],
                "allowed_ports": [80],
                "authorization_reference": "PENDING_OPERATOR_AUTHORIZATION_REVIEW",
                "status": "active",
            })

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


class TestEngagementSecurityHardening:
    def test_secret_scanning_rejects_api_keys(self, temp_engagement_manager):
        # OpenRouter API key pattern
        with pytest.raises(EngagementValidationError, match="must not contain API keys, passwords, or credentials"):
            temp_engagement_manager.create_profile({
                "name": "Key In Name sk-or-v1-abcdef1234567890abcdef1234567890",
                "authorized_hosts": ["127.0.0.1"],
                "allowed_ports": [80],
                "authorization_reference": "REF-KEY-1",
            })

        # OpenAI API key pattern
        with pytest.raises(EngagementValidationError, match="must not contain API keys, passwords, or credentials"):
            temp_engagement_manager.create_profile({
                "name": "Normal Name",
                "authorized_hosts": ["127.0.0.1"],
                "allowed_ports": [80],
                "authorization_reference": "sk-abcdefghijklmnopqrstuvwxyz0123456789",
            })

        # Private key pattern
        with pytest.raises(EngagementValidationError, match="must not contain API keys, passwords, or credentials"):
            temp_engagement_manager.create_profile({
                "name": "Key In Desc",
                "description": "-----BEGIN RSA PRIVATE KEY----- MIIE...",
                "authorized_hosts": ["127.0.0.1"],
                "allowed_ports": [80],
                "authorization_reference": "REF-KEY-2",
            })

    def test_corrupt_storage_fails_closed_and_creates_backup(self, tmp_path):
        corrupt_file = tmp_path / "corrupt_engagements.json"
        corrupt_file.write_text("{ this is completely invalid JSON [[[", encoding="utf-8")

        mgr = EngagementManager(storage_path=str(corrupt_file))
        assert mgr.storage_corrupted is True

        # Fails closed: only safe local lab profile is present
        profiles = mgr.list_profiles()
        assert len(profiles) == 1
        assert profiles[0].id == "eng-local-lab"

        # Backup file was created
        backups = list(tmp_path.glob("corrupt_engagements.json.corrupt.*"))
        assert len(backups) == 1
        assert "{ this is completely invalid JSON" in backups[0].read_text(encoding="utf-8")

        # Refuses to overwrite corrupt file on save
        with pytest.raises(EngagementStorageError, match="storage at .* is corrupted"):
            mgr.create_profile({
                "name": "Attempt on Corrupt Storage",
                "authorized_hosts": ["127.0.0.1"],
                "allowed_ports": [80],
                "authorization_reference": "REF-1",
            })

    def test_zero_byte_storage_fails_closed_and_creates_backup(self, tmp_path):
        zero_byte_file = tmp_path / "zero_byte_engagements.json"
        zero_byte_file.write_bytes(b"")
        assert zero_byte_file.exists()
        assert zero_byte_file.stat().st_size == 0

        mgr = EngagementManager(storage_path=str(zero_byte_file))
        assert mgr.storage_corrupted is True
        assert mgr.last_storage_error is not None
        assert "empty (0 bytes)" in mgr.last_storage_error

        # Original zero-byte file must NOT be silently overwritten with defaults
        assert zero_byte_file.exists()
        assert zero_byte_file.stat().st_size == 0

        # Fails closed: only safe local lab fallback available; no external engagements active
        profiles = mgr.list_profiles()
        assert len(profiles) == 1
        assert profiles[0].id == "eng-local-lab"
        assert profiles[0].is_external() is False
        assert profiles[0].is_active() is True
        assert mgr.get_profile("eng-pentest-ground") is None

        # Timestamped corruption backup was created preserving the zero-byte file
        backups = list(tmp_path.glob("zero_byte_engagements.json.corrupt.*"))
        assert len(backups) == 1
        assert backups[0].stat().st_size == 0

        # Normal persistence mutations must not overwrite invalid storage in isolation mode
        with pytest.raises(EngagementStorageError, match="storage at .* is corrupted"):
            mgr.create_profile({
                "name": "Attempt on Zero Byte Storage",
                "authorized_hosts": ["127.0.0.1"],
                "allowed_ports": [80],
                "authorization_reference": "REF-ZERO",
            })
        assert zero_byte_file.stat().st_size == 0

    def test_missing_storage_file_initializes_clean_defaults(self, tmp_path):
        missing_file = tmp_path / "fresh_run_engagements.json"
        assert not missing_file.exists()

        mgr = EngagementManager(storage_path=str(missing_file))
        assert mgr.storage_corrupted is False
        assert mgr.last_storage_error is None

        # Missing storage file follows normal first-run initialization
        assert missing_file.exists()
        assert missing_file.stat().st_size > 0
        assert len(mgr.list_profiles()) == 2

        # No corruption backups created for normal first-run initialization
        backups = list(tmp_path.glob("*.corrupt.*"))
        assert len(backups) == 0

        # Normal persistence mutations succeed on cleanly initialized storage
        new_prof = mgr.create_profile({
            "name": "Fresh Lab Profile",
            "authorized_hosts": ["127.0.0.1"],
            "allowed_ports": [8000],
            "authorization_reference": "REF-FRESH",
        })
        assert new_prof.id in [p.id for p in mgr.list_profiles()]

    def test_persistence_failure_rolls_back_in_memory_state(self, tmp_path, monkeypatch):
        storage_file = str(tmp_path / "readonly_engagements.json")
        mgr = EngagementManager(storage_path=storage_file)

        # Force save to fail
        def broken_save():
            raise EngagementStorageError("Disk write failed: permission denied")
        monkeypatch.setattr(mgr, "_save", broken_save)

        with pytest.raises(EngagementStorageError, match="Disk write failed"):
            mgr.create_profile({
                "name": "Fail Profile",
                "authorized_hosts": ["127.0.0.1"],
                "allowed_ports": [80],
                "authorization_reference": "REF-FAIL",
            })

        # Profile was NOT retained in memory
        assert mgr.get_profile("eng-fail") is None

    def test_legacy_migration_forces_external_profiles_to_inactive(self, tmp_path, monkeypatch):
        # Create a legacy file in data/engagements.json
        legacy_dir = tmp_path / "repo_data"
        legacy_dir.mkdir()
        legacy_file = legacy_dir / "engagements.json"
        legacy_content = [
            {
                "id": "eng-legacy-local",
                "name": "Legacy Local",
                "authorized_hosts": ["127.0.0.1"],
                "allowed_ports": [80],
                "status": "active",
                "authorization_reference": "LEGACY-LOCAL-REF",
            },
            {
                "id": "eng-legacy-external",
                "name": "Legacy External Active",
                "authorized_hosts": ["pentest-ground.com"],
                "allowed_ports": [4280],
                "status": "active",  # WAS ACTIVE IN LEGACY
                "authorization_reference": "ROE-2026-LEGACY",
            },
        ]
        legacy_file.write_text(json.dumps(legacy_content), encoding="utf-8")
        monkeypatch.setattr("vapt_platform.engagements.LEGACY_REPO_ENGAGEMENTS_FILE", str(legacy_file))

        runtime_file = tmp_path / "migrated_runtime.json"
        mgr = EngagementManager(storage_path=str(runtime_file))

        # Local profile retained active
        local_prof = mgr.get_profile("eng-legacy-local")
        assert local_prof is not None
        assert local_prof.status == "active"

        # External profile was FORCED to inactive for safety
        ext_prof = mgr.get_profile("eng-legacy-external")
        assert ext_prof is not None
        assert ext_prof.status == "inactive"
        assert ext_prof.is_active() is False

    def test_audit_snapshot_immutability(self, temp_engagement_manager):
        # Create an active profile
        prof = temp_engagement_manager.create_profile({
            "name": "Snapshot Audit Lab",
            "authorized_hosts": ["127.0.0.1"],
            "allowed_ports": [9191],
            "authorization_reference": "ROE-AUDIT-2026",
            "status": "active",
        })

        # Validate target under this profile
        res = validate_web_target("http://127.0.0.1:9191/", engagement_id=prof.id)
        assert res.authorized is True
        snapshot = res.engagement_snapshot
        assert snapshot is not None
        assert snapshot["id"] == prof.id
        assert snapshot["authorization_reference"] == "ROE-AUDIT-2026"

        # Now delete or alter the profile
        temp_engagement_manager.delete_profile(prof.id)
        assert temp_engagement_manager.get_profile(prof.id) is None

        # Existing snapshot remains completely intact and unaffected
        assert snapshot["id"] == prof.id
        assert snapshot["authorization_reference"] == "ROE-AUDIT-2026"


class TestEngagementAPI:
    def test_list_engagements_endpoint(self, temp_engagement_manager):
        client = TestClient(fastapi_app)
        resp = client.get("/engagements")
        assert resp.status_code == 200
        data = resp.json()
        assert "engagements" in data
        assert len(data["engagements"]) >= 2

    def test_get_diagnostics_endpoint(self, temp_engagement_manager):
        client = TestClient(fastapi_app)
        resp = client.get("/engagements/diagnostics")
        assert resp.status_code == 200
        data = resp.json()
        assert "storage_path" in data
        assert "corrupted" in data
        assert data["corrupted"] is False
        assert "total_profiles" in data

    def test_crud_lifecycle_api_loopback(self, temp_engagement_manager):
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

    def test_admin_access_control_with_configured_token(self, temp_engagement_manager, monkeypatch):
        # Configure admin token on server
        monkeypatch.setenv("VAPT_ADMIN_TOKEN", "super-secret-admin-token")
        client = TestClient(fastapi_app)

        payload = {
            "name": "Token Protected Profile",
            "authorized_hosts": ["127.0.0.1"],
            "allowed_ports": [80],
            "authorization_reference": "ROE-ADMIN-01",
        }

        # 1. Missing token -> 401 Unauthorized
        res_no_token = client.post("/engagements", json=payload)
        assert res_no_token.status_code == 401
        assert "Admin authentication required" in res_no_token.json()["detail"]

        # 2. Invalid token -> 403 Forbidden
        res_bad_token = client.post(
            "/engagements",
            json=payload,
            headers={"X-Admin-Token": "wrong-token"},
        )
        assert res_bad_token.status_code == 403
        assert "Invalid admin token" in res_bad_token.json()["detail"]

        # 3. Valid X-Admin-Token -> 200 OK
        res_good_token = client.post(
            "/engagements",
            json=payload,
            headers={"X-Admin-Token": "super-secret-admin-token"},
        )
        assert res_good_token.status_code == 200
        prof_id = res_good_token.json()["engagement"]["id"]

        # 4. Valid Authorization: Bearer -> 200 OK
        res_bearer = client.put(
            f"/engagements/{prof_id}",
            json={"description": "Updated via bearer token"},
            headers={"Authorization": "Bearer super-secret-admin-token"},
        )
        assert res_bearer.status_code == 200

        # 5. Delete with token -> 200 OK
        res_del = client.delete(
            f"/engagements/{prof_id}",
            headers={"X-Admin-Token": "super-secret-admin-token"},
        )
        assert res_del.status_code == 200

    def test_untrusted_cors_origin_rejected_on_mutation(self, temp_engagement_manager):
        client = TestClient(fastapi_app)
        payload = {
            "name": "CSRF Attack Attempt",
            "authorized_hosts": ["127.0.0.1"],
            "allowed_ports": [80],
            "authorization_reference": "ROE-ATTACK-01",
        }
        resp = client.post(
            "/engagements",
            json=payload,
            headers={"Origin": "https://malicious-website.com"},
        )
        assert resp.status_code == 403
        assert "Untrusted origin" in resp.json()["detail"]

    def test_storage_error_returns_http_500(self, temp_engagement_manager, monkeypatch):
        client = TestClient(fastapi_app)
        def broken_create(payload):
            raise EngagementStorageError("Disk full error simulated")
        monkeypatch.setattr(temp_engagement_manager, "create_profile", broken_create)

        resp = client.post(
            "/engagements",
            json={
                "name": "Storage Error Profile",
                "authorized_hosts": ["127.0.0.1"],
                "allowed_ports": [80],
                "authorization_reference": "ROE-ERR-01",
            },
        )
        assert resp.status_code == 500
        assert "Storage error" in resp.json()["detail"]

    def test_validate_target_against_profile_api(self, temp_engagement_manager):
        client = TestClient(fastapi_app)

        # 1. Seeded profile for pentest-ground:4280 is inactive by default (placeholder reference)
        resp1 = client.post(
            "/engagements/eng-pentest-ground/validate",
            json={"target_url": "https://pentest-ground.com:4280/login"},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["authorized"] is False
        assert "inactive" in data1["reason"].lower() or "authorization review" in data1["reason"].lower()

        # 2. Operator updates profile with genuine reference and activates it
        temp_engagement_manager.update_profile("eng-pentest-ground", {
            "authorization_reference": "ROE-2026-PENTEST-GROUND-4280",
            "status": "active",
        })

        resp2 = client.post(
            "/engagements/eng-pentest-ground/validate",
            json={"target_url": "https://pentest-ground.com:4280/login"},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["authorized"] is True
        assert data2["matched"] is True

    def test_targets_validate_with_engagement_id(self, temp_engagement_manager, monkeypatch):
        monkeypatch.delenv("VAPT_AUTHORIZED_WEB_SCOPES", raising=False)
        client = TestClient(fastapi_app)

        # 1. When external profile is inactive by default, validation rejects it
        resp1 = client.post(
            "/targets/validate",
            json={
                "target_url": "https://pentest-ground.com:4280/",
                "engagement_id": "eng-pentest-ground",
            },
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["authorized"] is False
        assert "inactive" in data1["detail"].lower() or "authorization review" in data1["detail"].lower()

        # 2. Operator activates profile with genuine reference
        temp_engagement_manager.update_profile("eng-pentest-ground", {
            "authorization_reference": "ROE-2026-PENTEST-GROUND-4280",
            "status": "active",
        })

        resp2 = client.post(
            "/targets/validate",
            json={
                "target_url": "https://pentest-ground.com:4280/",
                "engagement_id": "eng-pentest-ground",
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["authorized"] is True
        assert data2["in_scope"] is True
        assert data2["engagement_id"] == "eng-pentest-ground"
        assert data2["engagement_name"] == "Pentest Ground Authorized Lab"
        assert data2["authorization_reference"] == "ROE-2026-PENTEST-GROUND-4280"
        assert data2["engagement_snapshot"] is not None
        assert data2["engagement_snapshot"]["id"] == "eng-pentest-ground"
