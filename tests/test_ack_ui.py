"""Regression tests for the external-target acknowledgement UI hotfix.

Covers the complete path: SPA source contracts, Streamlit widget state,
API schema/enforcement, and the application-layer gate — with mocked DNS
and mocked/stubbed application execution. No live network, no live scan.

Required coverage (hotfix section 4):
  1. acknowledgement checkbox visibility for an external authorized target
  2. checkbox unchecked by default
  3. starting without acknowledgement is blocked
  4. checking the box sends target_scope_acknowledged: true
  5. changing hostname or port resets acknowledgement
  6. revalidation does not automatically acknowledge
  7. an unauthorized target is still rejected
  8. localhost behavior remains unchanged (no ack required)
  9. API/backend rejects missing or false acknowledgement (external)
 10. SPA and Streamlit remain consistent
"""
from __future__ import annotations

import socket
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.api import app as api_app
from vapt_platform.application import VAPTApplication, VAPTRequest
from vapt_platform.web_target import (
    SCOPE_ENV_VAR,
    WebTargetAuthorizationError,
    validate_web_target,
)

PG = "pentest-ground.com"
PG_PORT = 4280
PG_URL = f"https://{PG}:{PG_PORT}/"
PUBLIC_IP = "93.184.216.34"

SPA_JS = Path("frontend/web/js/app.js").read_text(encoding="utf-8")
SPA_HTML = Path("frontend/web/index.html").read_text(encoding="utf-8")
STREAMLIT = Path("frontend/app.py").read_text(encoding="utf-8")


def _fake_addrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (PUBLIC_IP, 0))]


@pytest.fixture
def external_scope(monkeypatch):
    monkeypatch.setenv(SCOPE_ENV_VAR, f"{PG}:{PG_PORT}")
    monkeypatch.setattr("vapt_platform.web_target.socket.getaddrinfo", _fake_addrinfo)
    monkeypatch.setattr(
        "vapt_platform.web_target._probe_target",
        lambda t, timeout: {"http_status": 200, "location": ""},
    )


@pytest.fixture(autouse=True)
def _clean_scope(monkeypatch):
    monkeypatch.delenv(SCOPE_ENV_VAR, raising=False)
    yield


def _run_body(**overrides):
    body = {
        "scenario": "failure_pivot",
        "mode": "web",
        "assessment_type": "web",
        "target_url": PG_URL,
        "assessor": "deterministic",
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# 1 + 2. Checkbox visible for external target, unchecked by default (SPA)
# ---------------------------------------------------------------------------

def test_spa_ack_checkbox_markup_exists_and_unchecked():
    # The control exists and is rendered WITHOUT a checked attribute,
    # i.e. unchecked by default. It is revealed (display:block) only by
    # renderWebScopeDetails for authorized external targets.
    assert 'id="web-scope-ack"' in SPA_JS
    ack_input_line = next(
        line for line in SPA_JS.splitlines() if 'id="web-scope-ack"' in line
    )
    assert "checked" not in ack_input_line
    # Visibility toggle for external targets lives in renderWebScopeDetails.
    assert "ackGroup.style.display = 'block'" in SPA_JS
    assert "res.external_scope || res.acknowledgement_required" in SPA_JS


def test_spa_runs_blocker_note_element_exists():
    assert 'id="web-ack-gate-note"' in SPA_JS
    assert "updateWebRunGate" in SPA_JS
    assert "btn.disabled = blocked" in SPA_JS


# ---------------------------------------------------------------------------
# 3 + 4. Start blocked without ack; sends true only after interaction
# ---------------------------------------------------------------------------

def test_spa_sends_ack_only_from_explicit_interaction_state():
    # The run request derives the flag from state.webAckFor (recorded only
    # by the checkbox change handler) and the checkbox's current state —
    # never from ackRequired alone.
    assert "target_scope_acknowledged: ackGiven" in SPA_JS
    assert "state.webAckFor === preIdentity" in SPA_JS
    # The checkbox handler is the ONLY writer of a positive acknowledgement.
    assert "state.webAckFor = identity" in SPA_JS
    # No code path programmatically checks the box.
    assert ".checked = true" not in SPA_JS
    assert "checked = true" not in SPA_JS


def test_spa_start_without_ack_is_blocked():
    # Both the button gate (disabled) and the startWebAssessment guard exist.
    assert "ackRequired && !ackGiven" in SPA_JS
    assert "requires the" in SPA_JS and "authorization acknowledgement" in SPA_JS


# ---------------------------------------------------------------------------
# 5 + 6. Target change / revalidation resets acknowledgement
# ---------------------------------------------------------------------------

def test_spa_url_edit_resets_acknowledgement():
    # Per-keystroke input listener clears the ack before revalidation.
    assert "addEventListener('input', () => {" in SPA_JS
    assert "resetWebScopeAck();" in SPA_JS
    # Revalidation of a different identity also resets it.
    assert "state.webAckFor !== identity" in SPA_JS


def test_spa_revalidation_never_auto_acknowledges():
    # resetWebScopeAck only unchecks; nothing checks the box programmatically.
    reset_fn = SPA_JS.split("function resetWebScopeAck()")[1].split("function ")[0]
    assert "ackBox.checked = false" in reset_fn
    assert ".checked = true" not in SPA_JS


def test_streamlit_ack_keyed_by_exact_scope_entry():
    # A fresh unchecked widget is produced whenever host:port changes.
    assert 'key=f"web_scope_ack::{t.scope_entry}"' in STREAMLIT
    assert "value=False" in STREAMLIT


# ---------------------------------------------------------------------------
# 7. Unauthorized target still rejected (backend, with ack=true)
# ---------------------------------------------------------------------------

def test_unauthorized_target_rejected_even_with_ack(external_scope, monkeypatch):
    client = TestClient(api_app)
    resp = client.post(
        "/runs",
        json=_run_body(
            target_url="https://evil.example.com:443/",
            target_scope_acknowledged=True,
        ),
    )
    assert resp.status_code == 400
    assert "not authorized" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 8. Localhost unchanged: no acknowledgement required
# ---------------------------------------------------------------------------

def test_local_target_requires_no_ack(monkeypatch):
    monkeypatch.setattr(
        "vapt_platform.web_target.socket.getaddrinfo",
        lambda h, p, family=0, type=0, proto=0, flags=0: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))
        ],
    )
    v = validate_web_target("http://127.0.0.1:9191/")
    assert v.authorized is True
    assert v.target.external is False
    client = TestClient(api_app)
    api = client.post(
        "/targets/validate", json={"target_url": "http://127.0.0.1:9191/"}
    ).json()
    assert api["acknowledgement_required"] is False
    assert api["external_scope"] is False
    assert api["scope_kind"] == "LOCAL_LOOPBACK"


# ---------------------------------------------------------------------------
# 9. API/backend rejects missing or false acknowledgement
# ---------------------------------------------------------------------------

def test_api_rejects_missing_ack_field(external_scope):
    client = TestClient(api_app)
    body = _run_body()
    assert "target_scope_acknowledged" not in body  # field omitted entirely
    resp = client.post("/runs", json=body)
    assert resp.status_code == 400
    assert "target_scope_acknowledged" in resp.json()["detail"]


def test_api_rejects_false_ack(external_scope):
    client = TestClient(api_app)
    resp = client.post("/runs", json=_run_body(target_scope_acknowledged=False))
    assert resp.status_code == 400
    assert "target_scope_acknowledged" in resp.json()["detail"]


def test_api_ack_true_passes_gate_and_reaches_application(external_scope, monkeypatch):
    captured = {}

    class StubApp:
        def run(self, req):
            captured["req"] = req
            raise RuntimeError("stub-stop-after-gate")

    monkeypatch.setattr("services.api.get_application", lambda: StubApp())
    client = TestClient(api_app)
    resp = client.post("/runs", json=_run_body(target_scope_acknowledged=True))
    # Not the acknowledgement 400 — the request reached the application.
    assert resp.status_code == 202
    for _ in range(200):
        if "req" in captured:
            break
        time.sleep(0.01)
    assert "req" in captured
    assert captured["req"].target_scope_acknowledged is True
    assert captured["req"].target_url == PG_URL


def test_application_gate_blocks_unacknowledged_external_target(external_scope):
    app = VAPTApplication.__new__(VAPTApplication)  # no init side effects
    request = VAPTRequest(
        mode="web",
        assessment_type="web",
        target_url=PG_URL,
        target_scope_acknowledged=False,
    )
    with pytest.raises(WebTargetAuthorizationError, match="acknowledgement"):
        app._load_web_candidates(request)


def test_application_gate_accepts_acknowledged_external_target(external_scope, monkeypatch):
    app = VAPTApplication.__new__(VAPTApplication)
    request = VAPTRequest(
        mode="web",
        assessment_type="web",
        target_url=PG_URL,
        target_scope_acknowledged=True,
    )
    # Stub everything downstream of the gate so this stays an offline unit
    # test of the acknowledgement gate itself.
    from vapt_platform import scanner_service
    monkeypatch.setattr(
        scanner_service, "run_nmap_discovery",
        lambda *a, **k: SimpleNamespace(to_dict=lambda: {"scanner": "nmap", "status": "SKIPPED"}),
    )
    monkeypatch.setattr(
        scanner_service, "run_nuclei_scan",
        lambda *a, **k: SimpleNamespace(to_dict=lambda: {"scanner": "nuclei", "status": "SKIPPED"}),
    )
    # _load_web_candidates continues into preflight + scanning + parsing.
    # Patch the module-level imports it uses after the gate.
    import vapt_platform.web_target as wt
    monkeypatch.setattr(wt, "preflight_web_target", lambda url, timeout=5.0: {
        "reachable": True, "http_status": 200, "redirect": None,
        "resolved_host": PUBLIC_IP, "port": PG_PORT, "scheme": "https",
        "hostname": PG, "target_url": f"https://{PG}:{PG_PORT}",
        "authorization_status": "AUTHORIZED", "preflight_status": "TARGET REACHABLE",
    })
    try:
        app._load_web_candidates(request)
    except WebTargetAuthorizationError:
        pytest.fail("acknowledged external target must pass the ack gate")
    except Exception:
        # Downstream stubs may not cover every later stage; the gate itself
        # (the subject of this test) did not raise.
        pass


# ---------------------------------------------------------------------------
# 10. SPA and Streamlit remain consistent + backend validate agreement
# ---------------------------------------------------------------------------

def test_spa_and_streamlit_share_backend_fields_and_labels(external_scope):
    # Both frontends display external vs local distinctly.
    assert "AUTHORIZED EXTERNAL TARGET" in SPA_JS
    assert "OUT OF SCOPE" in SPA_JS and "OUT OF SCOPE" in STREAMLIT
    # Both reference the same env var and acknowledge the backend check.
    assert "VAPT_AUTHORIZED_WEB_SCOPES" in SPA_JS
    assert "VAPT_AUTHORIZED_WEB_SCOPES" in STREAMLIT
    # SPA cache-busted so a stale app.js without the checkbox cannot load.
    assert "app.js?v=" in SPA_HTML
    # API validate response supplies the fields both UIs render.
    client = TestClient(api_app)
    api = client.post("/targets/validate", json={"target_url": PG_URL}).json()
    local = validate_web_target(PG_URL)
    assert api["authorized"] == local.authorized
    assert api["acknowledgement_required"] is True
    assert api["external_scope"] is True
    assert api["normalized_host"] == PG
    assert api["port"] == PG_PORT


def test_no_ack_state_in_report_payloads(external_scope, monkeypatch):
    """The ack flag is a gate, not report content; reports keep no secret."""
    import json

    from vapt_platform.reporting.builder import _build_web_provenance

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hotfix-secret")
    prov = _build_web_provenance(
        {"web": {"authorization": {"status": "AUTHORIZED", "acknowledged": True}}},
        {"details": []},
        [],
    )
    blob = json.dumps(prov, default=str)
    assert "sk-or" not in blob
