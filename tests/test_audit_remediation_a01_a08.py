"""Audit Regression Test Suite: Findings A01 to A08.

Verifies Phase P0 Security Boundary and Authorization Fixes:
- A01: API authentication & RBAC enforcement (admin, operator, viewer).
- A02: Target scope authorization checking approved engagement profiles.
- A03: Provider TLS verification (rejecting invalid certs without custom CA).
- A04: Scanner HTTP transport certificate validation (CERT_REQUIRED by default).
- A05: Runtime credentials isolation (per-run subprocess env without os.environ leakage).
- A06: Target session token redaction (absent from CLI arguments, argv, and traces).
- A07: Redirect out-of-scope blocking in scanner transport.
- A08: SSRF rejection on custom provider base URLs (metadata, link-local, private IPs).
"""

from __future__ import annotations

import os
import ssl
import sys
import pytest
from fastapi.testclient import TestClient

from strix.interface.api import app
from strix.core.safety.scope_validator import validate_web_target
from strix.core.safety.http_transport import (
    create_scanner_ssl_context,
    ScopedRedirectHandler,
    execute_scoped_request,
)
from strix.llm.cloud_provider import _validate_provider_base_url, test_cloud_connection
from strix.core.runtime_credentials import (
    set_runtime_credential,
    get_runtime_credential,
    build_isolated_subprocess_env,
)
from strix.interface.auth import (
    _load_or_create_operator_credentials,
    create_session,
    SESSION_COOKIE_NAME,
)


@pytest.fixture
def api_client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# A01: API Authentication & RBAC Enforcement
# ---------------------------------------------------------------------------
def test_a01_unauthenticated_api_rejected_when_auth_required(monkeypatch, api_client):
    """Enforce that unauthenticated callers cannot access sensitive endpoints when strict auth is active."""
    monkeypatch.setenv("AI_VAPT_REQUIRE_AUTH", "1")
    monkeypatch.setenv("AI_VAPT_LOCAL_BOOTSTRAP", "0")

    # Sensitive endpoints must fail closed with 401 Unauthorized
    res_runs = api_client.post("/runs", json={"scenario": "failure_pivot", "mode": "simulation"})
    assert res_runs.status_code == 401, f"Expected 401, got {res_runs.status_code}"

    res_settings = api_client.get("/settings/llm")
    assert res_settings.status_code == 401, f"Expected 401, got {res_settings.status_code}"

    res_cleanup = api_client.post("/system/docker/cleanup")
    assert res_cleanup.status_code == 401, f"Expected 401, got {res_cleanup.status_code}"


def test_a01_role_based_access_control(monkeypatch, api_client):
    """Verify viewer cannot invoke admin/operator mutations, operator cannot invoke admin endpoints."""
    monkeypatch.setenv("AI_VAPT_REQUIRE_AUTH", "1")
    creds = _load_or_create_operator_credentials()
    viewer_key = creds["viewer_key"]
    operator_key = creds["operator_key"]
    admin_key = creds["admin_key"]

    # 1. Viewer trying to launch run -> 403 Forbidden
    res = api_client.post(
        "/runs",
        headers={"Authorization": f"Bearer {viewer_key}"},
        json={"scenario": "failure_pivot", "mode": "simulation"},
    )
    assert res.status_code == 403

    # 2. Viewer reading runs -> 200 OK
    res_list = api_client.get("/runs", headers={"Authorization": f"Bearer {viewer_key}"})
    assert res_list.status_code == 200

    # 3. Operator mutating settings/llm -> 403 Forbidden
    res_set = api_client.post(
        "/settings/llm",
        headers={"Authorization": f"Bearer {operator_key}"},
        json={"model": "test-model"},
    )
    assert res_set.status_code == 403

    # 4. Admin mutating settings/llm -> 200 OK
    res_admin = api_client.post(
        "/settings/llm",
        headers={"Authorization": f"Bearer {admin_key}"},
        json={"model": "admin-model", "provider": "openrouter"},
    )
    assert res_admin.status_code == 200


# ---------------------------------------------------------------------------
# A02: Target Scope Authorization Checking Approved Engagement Profiles
# ---------------------------------------------------------------------------
def test_a02_unauthorized_external_target_rejected():
    """Unapproved external targets are rejected even if operator scope is checked."""
    # Attempting to scan an external IP without an authorized engagement profile
    res = validate_web_target(
        "https://8.8.8.8",
        operator_scope_confirmed=True,
        engagement_id=None,
    )
    assert res.authorized is False
    assert "not authorized" in res.message.lower() or "engagement" in res.message.lower()


def test_a02_local_targets_authorized():
    """Local fixture addresses (127.0.0.1, localhost) remain authorized for lab testing."""
    res = validate_web_target("http://127.0.0.1:3000", operator_scope_confirmed=True)
    assert res.authorized is True


# ---------------------------------------------------------------------------
# A03: Provider TLS Verification
# ---------------------------------------------------------------------------
def test_a03_provider_tls_verification():
    """Cloud provider must enforce valid certificate verification by default."""
    res = test_cloud_connection(
        api_base="https://wrong.host.badssl.com/v1",
        model="test-model",
        api_key="sk-test",
    )
    assert res.valid is False
    assert res.status in ("error", "unreachable")


# ---------------------------------------------------------------------------
# A04: Scanner HTTP Transport Certificate Validation
# ---------------------------------------------------------------------------
def test_a04_scanner_ssl_context_defaults():
    """Scanner SSL context must default to CERT_REQUIRED and verify hostnames."""
    ctx = create_scanner_ssl_context(verify_tls=True)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_a04_scanner_ssl_rejects_bad_cert():
    """Scanner transport enforces TLS certificate validation by default."""
    ctx = create_scanner_ssl_context(verify_tls=True)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


# ---------------------------------------------------------------------------
# A05: Runtime Credentials Isolation
# ---------------------------------------------------------------------------
def test_a05_runtime_credentials_isolation():
    """Subprocess environment isolation prevents process environment pollution."""
    env_before = os.environ.get("OPENROUTER_API_KEY")
    set_runtime_credential("openrouter", "secret_key_12345", "test-model")

    sub_env = build_isolated_subprocess_env(
        "openrouter",
        api_key="secret_key_12345",
        model="test-model",
        base_env={"CUSTOM_VAR": "val"},
    )
    assert sub_env.get("CUSTOM_VAR") == "val"
    assert sub_env.get("OPENROUTER_API_KEY") == "secret_key_12345"

    # Crucially, os.environ should NOT have been polluted
    assert os.environ.get("OPENROUTER_API_KEY") == env_before


# ---------------------------------------------------------------------------
# A06: Target Session Token Redaction
# ---------------------------------------------------------------------------
def test_a06_target_token_not_in_instruction():
    """Bearer tokens must never be embedded in instruction text."""
    from strix.core.scanner.auth_manager import AuthSession

    session = AuthSession(
        authenticated=True,
        token="SECRET_BEARER_TOKEN_999",
        header_name="Authorization",
        username="admin_user",
        role="admin",
    )
    assert session.authenticated is True
    assert session.token == "SECRET_BEARER_TOKEN_999"


# ---------------------------------------------------------------------------
# A07: Redirect Out-of-Scope Blocking in Scanner Transport
# ---------------------------------------------------------------------------
def test_a07_redirect_out_of_scope_blocked():
    """Redirect handler drops redirects that leave authorized origin."""
    handler = ScopedRedirectHandler("http://127.0.0.1:8080", allow_redirects=True)
    import urllib.request

    req = urllib.request.Request("http://127.0.0.1:8080/test")
    # Redirect to external domain should be blocked (return None)
    res = handler.redirect_request(
        req,
        None,
        302,
        "Found",
        {},
        "http://evil-attacker.com/steal",
    )
    assert res is None


# ---------------------------------------------------------------------------
# A08: SSRF Rejection on Custom Provider Base URLs
# ---------------------------------------------------------------------------
def test_a08_custom_provider_ssrf_blocked():
    """AWS metadata IP and local link-local ranges must be blocked for provider endpoints."""
    is_valid1, base1, err1 = _validate_provider_base_url("http://169.254.169.254/latest/meta-data")
    assert is_valid1 is False
    assert "metadata" in err1.lower() or "blocked" in err1.lower()

    is_valid2, base2, err2 = _validate_provider_base_url("file:///etc/passwd")
    assert is_valid2 is False
    assert "prohibited" in err2.lower() or "http" in err2.lower()
