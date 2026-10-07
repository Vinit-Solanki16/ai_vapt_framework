"""FIX 1 — separate Nmap service discovery from vulnerability candidates.

Required coverage:
  1. Nmap service record is parsed.
  2. Service record remains available (domain / persistence / reports).
  3. Service record is NOT an actionable candidate.
  4. Genuine vulnerability findings can still become candidates.
  5. Existing Nuclei findings continue through the candidate pipeline.
  6. Existing scenarios remain unchanged.

Offline-safe: scanners and preflight are mocked; EPSS falls back locally.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import vapt_platform.scanner_service as scanner_service
import vapt_platform.web_target as web_target
from decision_engine.adapters.scan_adapter import (
    candidates_from_scan,
    discovery_from_scan,
    findings_to_candidates,
)
from vapt_platform.application import VAPTRequest, get_application
from vapt_platform.normalization import (
    FINDING_KIND_SERVICE_DISCOVERY,
    FINDING_KIND_VULNERABILITY,
    finding_kind,
    finding_to_service_info,
    from_nuclei_finding,
    is_service_discovery,
    is_vulnerability_finding,
    split_findings,
)
from vapt_platform.scanners import NmapXmlAdapter

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(autouse=True)
def isolated_repository():
    from vapt_platform.persistence.config import PersistenceConfig
    from vapt_platform.persistence.repository import JSONRunRepository, set_repository

    repo_dir = tempfile.mkdtemp()
    set_repository(JSONRunRepository(config=PersistenceConfig(storage_dir=repo_dir)))
    yield
    set_repository(JSONRunRepository())
    shutil.rmtree(repo_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nmap_only(monkeypatch):
    """Mock preflight + Nmap discovery (juice fixture) + Nuclei unavailable."""
    findings = NmapXmlAdapter().parse(str(DATA_DIR / "juice_shop_nmap.xml"))
    assert findings, "fixture must yield at least one Nmap service record"

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


def _nmap_plus_nuclei(monkeypatch):
    """Same as _nmap_only but Nuclei reports one genuine vulnerability."""
    nmap_findings = _nmap_only(monkeypatch)

    from vapt_platform.parsers.nuclei_parser import NucleiFinding
    nuclei_finding = from_nuclei_finding(NucleiFinding(
        template_id="CVE-2021-44228",
        name="Apache Log4j RCE (JNDI)",
        severity="critical",
        target="http://127.0.0.1:9191",
        host="127.0.0.1",
    ))
    assert finding_kind(nuclei_finding) == FINDING_KIND_VULNERABILITY

    nuclei_result = MagicMock()
    nuclei_result.findings = [nuclei_finding]
    nuclei_result.to_dict.return_value = {
        "scanner": "nuclei", "status": "COMPLETED", "exit_code": 0,
        "finding_count": 1, "target": "http://127.0.0.1:9191",
    }
    monkeypatch.setattr(scanner_service, "run_nuclei_scan", lambda *a, **k: nuclei_result)
    return nmap_findings, nuclei_finding


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
# 1. Nmap service record is parsed + classified as SERVICE_DISCOVERY
# ---------------------------------------------------------------------------

def test_nmap_service_record_is_parsed():
    findings = NmapXmlAdapter().parse(str(DATA_DIR / "juice_shop_nmap.xml"))
    assert findings

    rec = next(f for f in findings if f.port == 9191)
    assert rec.source == "nmap-xml"
    assert rec.host == "127.0.0.1"
    assert rec.protocol == "tcp"
    assert "sun-as-jpda" in rec.title
    assert rec.metadata.get("service") == "sun-as-jpda"
    # Classified as asset/service context, not a vulnerability finding.
    assert finding_kind(rec) == FINDING_KIND_SERVICE_DISCOVERY
    assert is_service_discovery(rec)
    assert not is_vulnerability_finding(rec)
    # No vulnerability severity is invented for pure discovery.
    assert rec.severity in ("unknown", "", "info", None)


def test_nmap_json_with_cves_stays_vulnerability():
    """Nmap records carrying CVE evidence remain actionable findings."""
    from vapt_platform.scanners import NmapJsonAdapter

    findings = NmapJsonAdapter().parse(str(DATA_DIR / "rich_scan_nmap.json"))
    assert findings
    with_cve = [f for f in findings if (f.metadata or {}).get("cve")]
    without_cve = [f for f in findings if not (f.metadata or {}).get("cve")]
    assert with_cve and without_cve
    assert all(finding_kind(f) == FINDING_KIND_VULNERABILITY for f in with_cve)
    assert all(finding_kind(f) == FINDING_KIND_SERVICE_DISCOVERY for f in without_cve)
    # Candidates come only from the CVE-bearing subset.
    assert len(candidates_from_scan(str(DATA_DIR / "rich_scan_nmap.json"))) == len(with_cve)


# ---------------------------------------------------------------------------
# 2 + 3. Service record remains available, but never becomes a candidate
# ---------------------------------------------------------------------------

def test_split_findings_keeps_discovery_available_and_out_of_candidates():
    findings = NmapXmlAdapter().parse(str(DATA_DIR / "juice_shop_nmap.xml"))
    actionable, discovery = split_findings(findings)

    # Discovery preserved with full asset context.
    assert len(discovery) == len(findings)
    info = finding_to_service_info(discovery[0])
    assert info["port"] == 9191
    assert info["protocol"] == "tcp"
    assert info["host"] == "127.0.0.1"
    assert info["service"]
    assert info["finding_kind"] == FINDING_KIND_SERVICE_DISCOVERY

    # Discovery never becomes an exploit candidate...
    assert findings_to_candidates(discovery) == []
    # ...while the split itself produces zero actionable candidates here.
    assert actionable == []
    assert candidates_from_scan(str(DATA_DIR / "juice_shop_nmap.xml")) == []
    # discovery_from_scan keeps the record visible for UI/reporting.
    assert len(discovery_from_scan(str(DATA_DIR / "juice_shop_nmap.xml"))) == len(findings)


def test_web_run_keeps_discovery_out_of_candidates(monkeypatch):
    _nmap_only(monkeypatch)
    result = get_application().run(_web_request())
    domain = result.domain

    # Service record remains available on the domain result.
    assert len(domain.service_discovery) >= 1
    disc = domain.service_discovery[0]
    assert disc["port"] == 9191
    assert disc["source"] == "nmap-xml"
    assert disc["service"] == "sun-as-jpda"
    assert disc["finding_kind"] == FINDING_KIND_SERVICE_DISCOVERY

    # ...but it is NOT an actionable candidate: no AI assessment/ranking/decision.
    assert domain.candidates == []
    assert domain.candidates_processed == []
    for trace in domain.decision_trace:
        assert "sun-as-jpda" not in str(trace)


def test_discovery_survives_persistence_and_reports(monkeypatch):
    _nmap_only(monkeypatch)
    app = get_application()
    result = app.run(_web_request())
    run_id = result.domain.run_id

    from vapt_platform.persistence import get_repository
    persisted = get_repository().get(run_id)
    assert persisted is not None
    # Persisted as service discovery, not as candidates.
    assert persisted.candidates == []
    assert len(persisted.service_discovery) >= 1
    assert persisted.service_discovery[0]["port"] == 9191

    # Reports preserve it, labelled as discovery/service information.
    report_json = json.loads(app.generate_report(run_id, "json"))
    assert report_json["candidates"] == []
    assert len(report_json["service_discovery"]) >= 1
    assert report_json["service_discovery"][0]["port"] == 9191
    assert report_json["service_discovery"][0]["record_type"] == "SERVICE_DISCOVERY"

    for fmt, needle in (
        ("markdown", "Service Discovery"),
        ("txt", "SERVICE DISCOVERY"),
        ("html", "Service Discovery"),
    ):
        rendered = app.generate_report(run_id, fmt)
        assert needle in rendered, f"{fmt} report must label discovery"
        assert "sun-as-jpda" in rendered or "9191" in rendered


def test_findings_api_returns_service_discovery_separately(monkeypatch):
    _nmap_only(monkeypatch)
    from fastapi.testclient import TestClient
    from services.api import app as api_app

    client = TestClient(api_app)
    started = client.post("/runs", json={
        "scenario": "web_target",
        "mode": "web",
        "assessment_type": "web",
        "target_url": "http://127.0.0.1:9191",
        "assessor": "deterministic",
        "assessor_provider": "ollama",
        "max_attempts": 2,
        "use_nmap": True,
        "use_nuclei": True,
    })
    assert started.status_code == 200, started.text
    run_id = started.json()["run_id"]

    findings = client.get(f"/runs/{run_id}/findings").json()
    assert findings["candidates"] == []
    assert len(findings["service_discovery"]) >= 1
    assert findings["service_discovery"][0]["port"] == 9191

    candidates = client.get(f"/runs/{run_id}/candidates").json()
    assert candidates["candidates"] == []
    for c in candidates["candidates"]:
        assert c.get("finding_kind") != FINDING_KIND_SERVICE_DISCOVERY


# ---------------------------------------------------------------------------
# 4. Genuine vulnerability findings can still become candidates
# ---------------------------------------------------------------------------

def test_genuine_vulnerability_findings_still_become_candidates(epss_offline):
    # CVE-bearing Nmap JSON + custom JSON (vulnerability scanners' output).
    nmap_candidates = candidates_from_scan(str(DATA_DIR / "rich_scan_nmap.json"))
    assert nmap_candidates
    assert any(c.id.startswith("CVE-") for c in nmap_candidates)

    custom_candidates = candidates_from_scan(str(DATA_DIR / "rich_scan_custom.json"))
    assert custom_candidates

    # Mixed input: discovery is split out, genuine vulns remain candidates.
    findings = NmapXmlAdapter().parse(str(DATA_DIR / "juice_shop_nmap.xml"))
    from vapt_platform.normalization import CanonicalFinding
    vuln = CanonicalFinding(
        source="custom",
        host="127.0.0.1",
        port=9191,
        title="Log4j RCE",
        severity="critical",
        rule_id="CVE-2021-44228",
        metadata={"cve": "CVE-2021-44228", "epss_score": 0.9},
    )
    actionable, discovery = split_findings(findings + [vuln])
    assert len(discovery) == len(findings)
    assert len(actionable) == 1
    candidates = findings_to_candidates(actionable)
    assert len(candidates) == 1
    assert candidates[0].id == "CVE-2021-44228"


@pytest.fixture
def epss_offline(monkeypatch):
    """Deterministic EPSS enrichment (offline)."""
    def _mock_enrich(findings, provider=None):
        return [
            {**f.model_dump(), "metadata": {**(f.metadata or {}), "epss_score": 0.5}}
            if hasattr(f, "model_dump") else f
            for f in findings
        ]

    monkeypatch.setattr("vapt_platform.enrichment.enrich_findings", _mock_enrich)


# ---------------------------------------------------------------------------
# 5. Existing Nuclei findings continue through the candidate pipeline
# ---------------------------------------------------------------------------

def test_nuclei_findings_continue_through_pipeline(monkeypatch):
    _nmap_plus_nuclei(monkeypatch)
    result = get_application().run(_web_request())
    domain = result.domain

    # Nuclei finding became an actionable candidate.
    assert len(domain.candidates) == 1
    cand = domain.candidates[0]
    assert cand["source"] == "nuclei"
    assert cand["id"] == "CVE-2021-44228"
    assert cand["severity"] == "critical"
    assert "validation_status" in cand

    # The Nmap service record stayed out of candidates but remained visible.
    assert any(c.get("source") == "nmap-xml" for c in domain.candidates) is False
    assert len(domain.service_discovery) >= 1
    assert domain.service_discovery[0]["port"] == 9191


# ---------------------------------------------------------------------------
# 6. Existing scenarios remain unchanged
# ---------------------------------------------------------------------------

def test_existing_scenarios_remain_unchanged(epss_offline):
    from prototype.demo_data import (
        all_fail_scenario,
        failure_pivot_scenario,
        multi_candidate_scenario,
        success_scenario,
    )
    from prototype.engine_integration import run_decision_scenario
    from decision_engine.core.schemas import EngineStatus

    state = run_decision_scenario(success_scenario(), max_attempts=2, mode="simulation")
    assert state["status"] == EngineStatus.SUCCESS.value

    state = run_decision_scenario(
        failure_pivot_scenario(max_attempts=2), max_attempts=2, mode="simulation"
    )
    assert state["status"] in (EngineStatus.SUCCESS.value, EngineStatus.COMPLETED.value)

    state = run_decision_scenario(multi_candidate_scenario(), max_attempts=2, mode="simulation")
    assert state["status"] in (EngineStatus.SUCCESS.value, EngineStatus.COMPLETED.value)

    state = run_decision_scenario(
        all_fail_scenario(max_attempts=2), max_attempts=2, mode="simulation"
    )
    assert state["status"] == EngineStatus.COMPLETED.value
