"""Web-target assessment integration + safety rejection tests (Phase 32).

Covers: preflight-gated pipeline, canonical finding flow, AI assessment
metadata, ranking/decision display data, persistence, and reporting —
all with mocked scanners/preflight (offline-safe).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import vapt_platform.scanner_service as scanner_service
import vapt_platform.web_target as web_target
from vapt_platform.application import VAPTRequest, get_application
from vapt_platform.web_target import WebTargetAuthorizationError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(autouse=True)
def isolated_repository(tmp_path):
    """Isolate persistence per test (other suites mutate the global singleton)."""
    import shutil as _shutil
    import tempfile as _tempfile

    from vapt_platform.persistence.config import PersistenceConfig
    from vapt_platform.persistence.repository import JSONRunRepository, set_repository

    repo_dir = _tempfile.mkdtemp()
    set_repository(JSONRunRepository(config=PersistenceConfig(storage_dir=repo_dir)))
    yield
    set_repository(JSONRunRepository())
    _shutil.rmtree(repo_dir, ignore_errors=True)


def _mock_scanners(monkeypatch, tmp_path):
    """Mock preflight reachable + nmap discovery from the real Juice XML fixture."""
    from vapt_platform.scanners import NmapXmlAdapter

    findings = NmapXmlAdapter().parse(str(DATA_DIR / "juice_shop_nmap.xml"))
    assert findings, "fixture must yield at least one finding"

    monkeypatch.setattr(
        web_target, "preflight_web_target",
        lambda _url, timeout=5.0: {
            "target_url": "http://127.0.0.1:9191",
            "resolved_host": "127.0.0.1",
            "port": 9191,
            "authorization_status": "AUTHORIZED",
            "preflight_status": "TARGET REACHABLE",
            "reachable": True,
            "http_status": 200,
            "detail": "HTTP 200 (mocked)",
        },
    )
    nmap_result = MagicMock()
    nmap_result.findings = findings
    nmap_result.to_dict.return_value = {
        "scanner": "nmap", "status": "COMPLETED", "exit_code": 0,
        "finding_count": len(findings), "target": "http://127.0.0.1:9191",
    }
    nuclei_result = MagicMock()
    nuclei_result.findings = []
    nuclei_result.to_dict.return_value = {
        "scanner": "nuclei", "status": "NOT AVAILABLE",
        "detail": "Nuclei not installed (mocked).",
    }
    monkeypatch.setattr(scanner_service, "run_nmap_discovery", lambda *a, **k: nmap_result)
    monkeypatch.setattr(scanner_service, "run_nuclei_scan", lambda *a, **k: nuclei_result)
    return findings


def _web_request() -> VAPTRequest:
    return VAPTRequest(
        scenario="web_target",
        mode="web",
        assessment_type="web",
        target_url="http://127.0.0.1:9191",
        use_nmap=True,
        use_nuclei=True,
        assessor_mode="deterministic",
        assessor_provider="ollama",
        max_attempts=2,
    )


# ---------------------------------------------------------------------------
# Integration: authorized target flows through the canonical pipeline
# ---------------------------------------------------------------------------

def test_web_assessment_end_to_end(monkeypatch, tmp_path):
    _mock_scanners(monkeypatch, tmp_path)
    result = get_application().run(_web_request())

    domain = result.domain
    assert domain.final_status in ("SUCCESS", "COMPLETED", "FAILED")
    # At least the Nmap finding entered the pipeline.
    assert len(domain.candidates) >= 1
    cand = domain.candidates[0]
    assert cand["port"] == 9191
    assert cand["source"] == "nmap-xml"
    assert "validation_status" in cand
    assert domain.evidence_tier == "OBSERVED_LOCAL"
    assert "VALIDATION NOT AVAILABLE" in domain.safety_notice
    assert domain.assessment.get("provider") == "deterministic"
    # GAP-1: engine assessed before ranking — quality ranks present.
    assert any(c.get("quality_rank") for c in domain.candidates)


def test_web_assessment_persists_and_reports(monkeypatch, tmp_path):
    _mock_scanners(monkeypatch, tmp_path)
    app = get_application()
    result = app.run(_web_request())

    from vapt_platform.persistence import get_repository
    repo = get_repository()
    persisted = repo.get(result.domain.run_id)
    assert persisted is not None
    assert persisted.target_url == "http://127.0.0.1:9191"
    assert persisted.assessment_type == "web"
    assert persisted.pipeline_summary["web"]["target_url"] == "http://127.0.0.1:9191"
    assert persisted.pipeline_summary["web"]["preflight"]["reachable"] is True

    for fmt in ("json", "txt", "markdown"):
        report = app.generate_report(result.domain.run_id, fmt)
        assert isinstance(report, str) and len(report) > 0


def test_web_run_survives_repository_roundtrip(monkeypatch, tmp_path):
    _mock_scanners(monkeypatch, tmp_path)
    result = get_application().run(_web_request())
    from vapt_platform.persistence import get_repository
    repo = get_repository()
    run = repo.get(result.domain.run_id)
    assert run is not None
    clone = run.to_dict()
    from vapt_platform.persistence import PersistentRun
    restored = PersistentRun.from_dict(clone)
    assert restored.target_url == "http://127.0.0.1:9191"
    assert restored.target == "127.0.0.1"
    assert restored.port == 9191


# ---------------------------------------------------------------------------
# Safety: rejection paths never invoke scanners
# ---------------------------------------------------------------------------

def test_web_assessment_rejects_public_target(monkeypatch, offline_guard):
    nmap_mock = MagicMock(side_effect=AssertionError("scanner must not run"))
    nuclei_mock = MagicMock(side_effect=AssertionError("scanner must not run"))
    monkeypatch.setattr(scanner_service, "run_nmap_discovery", nmap_mock)
    monkeypatch.setattr(scanner_service, "run_nuclei_scan", nuclei_mock)

    req = _web_request()
    req.target_url = "https://example.com"
    result = get_application().run(req)

    assert result.domain.final_status == "FAILED"
    assert "not authorized" in result.domain.safety_notice.lower()
    nmap_mock.assert_not_called()
    nuclei_mock.assert_not_called()


def test_web_assessment_rejects_unauthorized_port(monkeypatch, offline_guard):
    nmap_mock = MagicMock(side_effect=AssertionError("scanner must not run"))
    monkeypatch.setattr(scanner_service, "run_nmap_discovery", nmap_mock)

    req = _web_request()
    req.target_url = "http://127.0.0.1:8080"
    result = get_application().run(req)

    assert result.domain.final_status == "FAILED"
    nmap_mock.assert_not_called()


def test_web_assessment_requires_target_url():
    req = _web_request()
    req.target_url = None
    with pytest.raises(Exception):
        get_application()._load_candidates(req)


def test_api_rejects_unauthorized_web_target():
    from fastapi.testclient import TestClient
    from services.api import app

    client = TestClient(app)
    resp = client.post("/runs", json={
        "scenario": "web_target",
        "mode": "web",
        "assessment_type": "web",
        "target_url": "https://example.com",
        "assessor": "deterministic",
        "assessor_provider": "ollama",
        "max_attempts": 2,
    })
    assert resp.status_code == 400
    assert "not authorized" in resp.text.lower()
