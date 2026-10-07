"""FIX 2 — filter informational / fingerprint findings from candidate ranking.

Required coverage:
  1. Fingerprint finding remains visible (inventory) but not a candidate.
  2. Informational finding remains visible (inventory) but not a candidate.
  3. Informational finding does not become a candidate (ranking exclusion).
  4. Actionable finding becomes a candidate (no genuine vuln dropped).
  5. UNKNOWN severity does not automatically become informational.
  6. Existing research scenarios remain unchanged (GAP-1/GAP-2 untouched).

Classification is deterministic and inspects actual scanner metadata
(template_id / tags / title + CVE / CVSS / KEV + normalized severity),
never severity alone. UNKNOWN is fail-open ACTIONABLE.

Offline-safe: no live scanners; uses synthetic CanonicalFinding objects
mirroring observed Nuclei metadata plus the real
data/scans/nuclei_127.0.0.1_9191.jsonl fixture where available.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from decision_engine.adapters.scan_adapter import (
    candidates_from_scan,
    findings_to_candidates,
    findings_to_service_discovery,
    split_scan,
)
from vapt_platform.normalization import (
    CANDIDATE_ELIGIBILITY_ACTIONABLE,
    CANDIDATE_ELIGIBILITY_INFORMATIONAL,
    FINDING_KIND_INFORMATIONAL,
    FINDING_KIND_SERVICE_DISCOVERY,
    FINDING_KIND_VULNERABILITY,
    CanonicalFinding,
    candidate_eligibility,
    finding_kind,
    finding_to_service_info,
    from_nuclei_finding,
    is_actionable_finding,
    is_informational_finding,
    split_findings,
)

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
# Helpers mirroring observed Nuclei records
# ---------------------------------------------------------------------------

def _nuclei_canonical(template_id, name, severity, tags, cve_ids=None, cvss=None):
    from vapt_platform.parsers.nuclei_parser import NucleiFinding

    nf = NucleiFinding(
        template_id=template_id,
        name=name,
        severity=severity,
        target="http://127.0.0.1:9191",
        host="127.0.0.1",
        tags=list(tags),
    )
    if cve_ids:
        nf.cve_ids = list(cve_ids)
    if cvss is not None:
        nf.cvss_score = cvss
    return from_nuclei_finding(nf)


def _fingerprint_finding():
    return _nuclei_canonical(
        "tech-detect", "Wappalyzer Technology Detection", "info", ["tech", "discovery"]
    )


def _juice_shop_finding():
    return _nuclei_canonical(
        "owasp-juice-shop-detect", "OWASP Juice Shop", "info", ["tech", "owasp", "discovery"]
    )


def _headers_finding():
    return _nuclei_canonical(
        "http-missing-security-headers",
        "HTTP Missing Security Headers",
        "info",
        ["misconfig", "headers", "generic", "vuln"],
    )


def _swagger_finding():
    return _nuclei_canonical(
        "swagger-api",
        "Public Swagger API - Detect",
        "info",
        ["exposure", "api", "swagger", "discovery"],
    )


def _actionable_cve_finding():
    return _nuclei_canonical(
        "CVE-2021-44228",
        "Apache Log4j RCE (JNDI)",
        "critical",
        ["cve", "rce"],
        cve_ids=["CVE-2021-44228"],
        cvss=10.0,
    )


def _actionable_exposure_finding():
    # prometheus-metrics: medium + CVSS 5.3 stays ACTIONABLE.
    return _nuclei_canonical(
        "prometheus-metrics",
        "Prometheus Metrics - Detect",
        "medium",
        ["exposure", "prometheus", "config", "vuln"],
        cvss=5.3,
    )


# ---------------------------------------------------------------------------
# 1-2. Fingerprint / informational findings remain visible with eligibility
# ---------------------------------------------------------------------------

def test_fingerprint_finding_remains_visible_with_eligibility():
    f = _fingerprint_finding()
    assert finding_kind(f) == FINDING_KIND_INFORMATIONAL
    assert is_informational_finding(f)
    assert not is_actionable_finding(f)
    assert candidate_eligibility(f) == CANDIDATE_ELIGIBILITY_INFORMATIONAL

    info = finding_to_service_info(f)
    # Complete finding preserved — nothing hidden.
    assert info["title"] == "Wappalyzer Technology Detection"
    assert info["severity"] == "informational"
    assert info["finding_kind"] == FINDING_KIND_INFORMATIONAL
    assert info["candidate_eligibility"] == CANDIDATE_ELIGIBILITY_INFORMATIONAL
    assert info["tags"] == ["tech", "discovery"]


def test_informational_header_finding_remains_visible():
    f = _headers_finding()
    assert finding_kind(f) == FINDING_KIND_INFORMATIONAL
    assert candidate_eligibility(f) == CANDIDATE_ELIGIBILITY_INFORMATIONAL
    info = finding_to_service_info(f)
    assert info["title"] == "HTTP Missing Security Headers"
    assert info["candidate_eligibility"] == CANDIDATE_ELIGIBILITY_INFORMATIONAL
    # Informational record keeps its severity/tags/evidence for display.
    assert info["severity"] == "informational"
    assert "headers" in info["tags"]


def test_juice_shop_and_swagger_are_informational():
    for f in (_juice_shop_finding(), _swagger_finding()):
        assert finding_kind(f) == FINDING_KIND_INFORMATIONAL
        assert candidate_eligibility(f) == CANDIDATE_ELIGIBILITY_INFORMATIONAL


# ---------------------------------------------------------------------------
# 3. Informational findings do not become candidates
# ---------------------------------------------------------------------------

def test_informational_findings_do_not_become_candidates():
    infos = [_fingerprint_finding(), _headers_finding(), _juice_shop_finding(), _swagger_finding()]
    assert findings_to_candidates(infos) == []
    actionable, discovery = split_findings(infos)
    assert actionable == []
    assert len(discovery) == len(infos)
    # Inventory preserves every record with eligibility.
    rendered = [finding_to_service_info(f) for f in discovery]
    assert all(r["candidate_eligibility"] == CANDIDATE_ELIGIBILITY_INFORMATIONAL for r in rendered)


def test_mixed_inventory_splits_actionable_from_informational():
    mixed = [_fingerprint_finding(), _headers_finding(), _actionable_cve_finding(), _actionable_exposure_finding()]
    actionable, discovery = split_findings(mixed)
    assert len(actionable) == 2
    assert len(discovery) == 2
    cands = findings_to_candidates(mixed)
    assert len(cands) == 2
    # Discovery side stays visible.
    assert len(findings_to_service_discovery(mixed)) == 2


# ---------------------------------------------------------------------------
# 4. Actionable findings become candidates (no genuine vuln dropped)
# ---------------------------------------------------------------------------

def test_actionable_findings_become_candidates():
    for f in (_actionable_cve_finding(), _actionable_exposure_finding()):
        assert finding_kind(f) == FINDING_KIND_VULNERABILITY
        assert is_actionable_finding(f)
        assert candidate_eligibility(f) == CANDIDATE_ELIGIBILITY_ACTIONABLE
    cands = findings_to_candidates([_actionable_cve_finding(), _actionable_exposure_finding()])
    assert len(cands) == 2


def test_real_nuclei_fixture_before_after_counts():
    """Real Juice Shop Nuclei output: 13 records → 1 actionable, 12 inventory."""
    fixture = DATA_DIR / "scans" / "nuclei_127.0.0.1_9191.jsonl"
    if not fixture.exists():
        pytest.skip("Nuclei fixture not present")
    from vapt_platform.scanners import NucleiAdapter

    findings = NucleiAdapter().parse(str(fixture))
    assert len(findings) == 13
    actionable, discovery = split_findings(findings)
    # Before FIX 2 every record would have been a candidate (13);
    # after FIX 2 only the CVSS-scored exposure remains actionable.
    assert len(actionable) == 1
    assert len(discovery) == 12
    assert len(findings_to_candidates(findings)) == 1
    assert actionable[0].rule_id == "prometheus-metrics"
    # Inventory preserves all 13 records across both buckets.
    assert len(actionable) + len(discovery) == len(findings)
    assert len(findings_to_service_discovery(findings)) == 12


# ---------------------------------------------------------------------------
# 5. UNKNOWN severity is never informational (fail open)
# ---------------------------------------------------------------------------

def test_unknown_severity_is_not_informational():
    # Minimal unknown finding with no markers stays actionable.
    f = CanonicalFinding(
        source="nuclei",
        host="127.0.0.1",
        target="http://127.0.0.1:9191",
        title="Some Finding",
        severity="unknown",
        rule_id="some-template",
        tags=["custom"],
    )
    assert finding_kind(f) == FINDING_KIND_VULNERABILITY
    assert candidate_eligibility(f) == CANDIDATE_ELIGIBILITY_ACTIONABLE
    assert len(findings_to_candidates([f])) == 1

    # Even a fingerprint template with UNKNOWN severity stays actionable
    # (UNKNOWN != INFORMATIONAL by construction).
    g = _nuclei_canonical("tech-detect", "Wappalyzer Technology Detection", "unknown", ["tech", "discovery"])
    assert finding_kind(g) == FINDING_KIND_VULNERABILITY
    assert candidate_eligibility(g) == CANDIDATE_ELIGIBILITY_ACTIONABLE
    assert len(findings_to_candidates([g])) == 1

    # UNKNOWN + CVE is always actionable.
    h = CanonicalFinding(
        source="nuclei",
        host="127.0.0.1",
        title="Log4j RCE",
        severity="unknown",
        rule_id="CVE-2021-44228",
        metadata={"cve_ids": ["CVE-2021-44228"]},
    )
    assert is_actionable_finding(h)
    assert len(findings_to_candidates([h])) == 1


def test_severity_alone_does_not_decide():
    # Severity info WITHOUT any fingerprint/misconfig/exposure marker
    # stays actionable (fail open — severity alone never filters).
    f = CanonicalFinding(
        source="nuclei",
        host="127.0.0.1",
        title="Unrelated Info Note",
        severity="informational",
        rule_id="unrelated-note",
        tags=["unrelated"],
    )
    assert finding_kind(f) == FINDING_KIND_VULNERABILITY
    assert candidate_eligibility(f) == CANDIDATE_ELIGIBILITY_ACTIONABLE


# ---------------------------------------------------------------------------
# 6. Research scenarios unchanged + web pipeline end-to-end
# ---------------------------------------------------------------------------

def test_existing_scenarios_remain_unchanged():
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


def test_web_run_filters_informational_but_preserves_inventory(monkeypatch):
    """Nmap discovery + Nuclei mix: only genuine vuln is ranked, all visible."""
    import vapt_platform.scanner_service as scanner_service
    import vapt_platform.web_target as web_target
    from vapt_platform.application import VAPTRequest, get_application
    from vapt_platform.scanners import NmapXmlAdapter

    nmap_findings = NmapXmlAdapter().parse(str(DATA_DIR / "juice_shop_nmap.xml"))
    assert nmap_findings
    nuclei_findings = [
        _fingerprint_finding(),
        _headers_finding(),
        _actionable_cve_finding(),
    ]

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
    nmap_result.findings = nmap_findings
    nmap_result.to_dict.return_value = {
        "scanner": "nmap", "status": "COMPLETED", "exit_code": 0,
        "finding_count": len(nmap_findings), "target": "http://127.0.0.1:9191",
    }
    nuclei_result = MagicMock()
    nuclei_result.findings = nuclei_findings
    nuclei_result.to_dict.return_value = {
        "scanner": "nuclei", "status": "COMPLETED", "exit_code": 0,
        "finding_count": len(nuclei_findings), "target": "http://127.0.0.1:9191",
    }
    monkeypatch.setattr(scanner_service, "run_nmap_discovery", lambda *a, **k: nmap_result)
    monkeypatch.setattr(scanner_service, "run_nuclei_scan", lambda *a, **k: nuclei_result)

    req = VAPTRequest(
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
    result = get_application().run(req)
    domain = result.domain

    # Only the CVE finding is ranked.
    assert len(domain.candidates) == 1
    assert domain.candidates[0]["candidate_eligibility"] == CANDIDATE_ELIGIBILITY_ACTIONABLE

    # Complete inventory preserved: Nmap (1+) + 2 informational.
    assert len(domain.service_discovery) >= 3
    eligibilities = {s.get("candidate_eligibility") for s in domain.service_discovery}
    assert eligibilities == {CANDIDATE_ELIGIBILITY_INFORMATIONAL}
    kinds = {s.get("finding_kind") for s in domain.service_discovery}
    assert FINDING_KIND_SERVICE_DISCOVERY in kinds
    assert FINDING_KIND_INFORMATIONAL in kinds

    # Reports include both inventory and eligibility (via ReportBuilder).
    import json as _json

    from vapt_platform.reporting.builder import ReportBuilder
    from vapt_platform.persistence import get_repository as _get_repo

    persisted = _get_repo().get(domain.run_id)
    assert persisted is not None
    builder = ReportBuilder()
    built = builder.from_persisted_run(persisted).to_dict()
    assert len(built["candidates"]) == 1
    assert built["candidates"][0]["candidate_eligibility"] == CANDIDATE_ELIGIBILITY_ACTIONABLE
    assert len(built["service_discovery"]) >= 3
    assert all(
        s.get("candidate_eligibility") == CANDIDATE_ELIGIBILITY_INFORMATIONAL
        for s in built["service_discovery"]
    )

    # Findings API returns full inventory; candidates API only actionable.
    # Mirror services/api.py job population (direct application.run does
    # not populate the in-memory job manager; the API POST path does).
    from services.jobs import job_manager as _jobs

    _jobs.set_state(domain.run_id, {
        "scenario": result.domain.scenario,
        "mode": result.domain.mode,
        "status": result.domain.final_status,
        "candidates": result.domain.candidates,
        "service_discovery": result.domain.service_discovery,
        "execution_results": result.domain.execution_results,
        "decision_trace": result.domain.decision_trace,
        "total_attempts": result.domain.total_attempts,
        "pivot_count": result.domain.pivot_count,
        "candidates_processed": result.domain.candidates_processed,
        "evidence_tier": result.domain.evidence_tier,
        "assessment": result.domain.assessment,
        "safety_notice": result.domain.safety_notice,
    })
    from fastapi.testclient import TestClient
    from services.api import app as api_app

    client = TestClient(api_app)
    findings = client.get(f"/runs/{domain.run_id}/findings").json()
    assert len(findings["candidates"]) == 1
    assert len(findings["service_discovery"]) >= 3
    candidates = client.get(f"/runs/{domain.run_id}/candidates").json()
    assert len(candidates["candidates"]) == 1
    assert all(
        c.get("candidate_eligibility", "ACTIONABLE") == "ACTIONABLE"
        for c in candidates["candidates"]
    )
