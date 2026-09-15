"""Tests for the scan ingestion vertical slice.

Verifies that scan files (Nmap XML, Nmap JSON, custom JSON) are correctly:
  - Parsed by the scanner
  - Converted to ActionCandidates
  - Fed through the decision engine
  - Reported with proper evidence tier

These tests mock the EPSS lookup to stay offline.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decision_engine.core.schemas import ActionCandidate, EngineStatus, Outcome
from decision_engine.adapters.scan_adapter import (
    candidates_from_scan,
    findings_to_candidates,
    candidates_to_scenario,
)
from prototype.engine_integration import run_decision_scenario
from prototype.report_generator import generate_json_report, generate_text_report
from vapt_platform.normalization import CanonicalFinding
from vapt_platform.scanners import (
    NmapXmlAdapter, NmapJsonAdapter, CustomJsonAdapter, get_scanner_registry
)


@pytest.fixture
def epss_mock(monkeypatch):
    """Mock EPSS enrichment to return deterministic scores (offline)."""
    def _mock_enrich(findings, provider=None):
        return [
            {**f.model_dump(), "metadata": {**(f.metadata or {}), "epss_score": 0.5}}
            if hasattr(f, 'model_dump') else f
            for f in findings
        ]

    monkeypatch.setattr("vapt_platform.enrichment.enrich_findings", _mock_enrich)


@pytest.fixture
def nmap_xml_file():
    return str(ROOT / "data" / "rich_scan.xml")


@pytest.fixture
def nmap_json_file():
    return str(ROOT / "data" / "rich_scan_nmap.json")


@pytest.fixture
def custom_json_file():
    return str(ROOT / "data" / "rich_scan_custom.json")


@pytest.fixture
def live_xml_file():
    return str(ROOT / "data" / "live_scan.xml")


class TestNmapXmlParsing:

    def test_parse_nmap_xml_multi_host(self, nmap_xml_file, epss_mock):
        adapter = NmapXmlAdapter()
        findings = adapter.parse(nmap_xml_file)
        assert len(findings) == 11

    def test_parse_nmap_xml_contains_hosts(self, nmap_xml_file, epss_mock):
        adapter = NmapXmlAdapter()
        findings = adapter.parse(nmap_xml_file)
        hosts = {f.host for f in findings}
        assert "192.168.1.10" in hosts
        assert "192.168.1.20" in hosts
        assert "192.168.1.30" in hosts

    def test_parse_nmap_xml_service_detection(self, nmap_xml_file, epss_mock):
        adapter = NmapXmlAdapter()
        findings = adapter.parse(nmap_xml_file)
        services = {f.metadata.get("service") for f in findings if f.metadata}
        assert "ssh" in services
        assert "http" in services

    def test_parse_nmap_xml_cpe_present(self, nmap_xml_file, epss_mock):
        adapter = NmapXmlAdapter()
        findings = adapter.parse(nmap_xml_file)
        has_cpe = any(f.evidence for f in findings)
        assert has_cpe


class TestNmapJsonParsing:

    def test_parse_nmap_json_multi_host(self, nmap_json_file, epss_mock):
        adapter = NmapJsonAdapter()
        findings = adapter.parse(nmap_json_file)
        assert len(findings) == 11

    def test_parse_nmap_json_contains_cves(self, nmap_json_file, epss_mock):
        adapter = NmapJsonAdapter()
        findings = adapter.parse(nmap_json_file)
        cves = [f.metadata.get("cve") for f in findings if f.metadata and f.metadata.get("cve")]
        assert "CVE-2023-38408" in cves

    def test_parse_nmap_json_hosts(self, nmap_json_file, epss_mock):
        adapter = NmapJsonAdapter()
        findings = adapter.parse(nmap_json_file)
        hosts = {f.host for f in findings}
        assert "10.0.0.10" in hosts
        assert "10.0.0.20" in hosts
        assert "10.0.0.30" in hosts


class TestCustomJsonParsing:

    def test_parse_custom_json(self, custom_json_file, epss_mock):
        adapter = CustomJsonAdapter()
        findings = adapter.parse(custom_json_file)
        assert len(findings) == 7

    def test_parse_custom_json_cves(self, custom_json_file, epss_mock):
        adapter = CustomJsonAdapter()
        findings = adapter.parse(custom_json_file)
        cves = [f.metadata.get("cve") for f in findings if f.metadata and f.metadata.get("cve")]
        assert "CVE-2023-38408" in cves


class TestCandidatesFromScan:

    def test_candidates_from_nmap_xml(self, nmap_xml_file, epss_mock):
        candidates = candidates_from_scan(nmap_xml_file)
        assert len(candidates) > 0
        assert all(isinstance(c, ActionCandidate) for c in candidates)

    def test_candidates_from_nmap_json(self, nmap_json_file, epss_mock):
        candidates = candidates_from_scan(nmap_json_file)
        assert len(candidates) > 0
        assert all(isinstance(c, ActionCandidate) for c in candidates)

    def test_candidates_from_custom_json(self, custom_json_file, epss_mock):
        candidates = candidates_from_scan(custom_json_file)
        assert len(candidates) > 0
        assert all(isinstance(c, ActionCandidate) for c in candidates)

    def test_candidates_have_valid_probability(self, nmap_xml_file, epss_mock):
        candidates = candidates_from_scan(nmap_xml_file)
        for c in candidates:
            assert 0.0 <= c.probability <= 1.0

    def test_candidates_have_ids(self, nmap_xml_file, epss_mock):
        candidates = candidates_from_scan(nmap_xml_file)
        for c in candidates:
            assert c.id
            assert isinstance(c.id, str)

    def test_candidates_from_json_have_cve_ids(self, nmap_json_file, epss_mock):
        candidates = candidates_from_scan(nmap_json_file)
        ids = {c.id for c in candidates}
        cve_ids = {i for i in ids if i.startswith("CVE-")}
        assert len(cve_ids) > 0


class TestScanEngineIntegration:

    def test_scan_candidates_run_through_engine(self, nmap_xml_file, epss_mock):
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        assert state["status"] in (
            EngineStatus.SUCCESS.value,
            EngineStatus.COMPLETED.value,
        )

    def test_scan_candidates_produce_results(self, nmap_xml_file, epss_mock):
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        assert "results" in state
        assert len(state["results"]) > 0


class TestExistingScenariosStillWork:

    def test_success_scenario(self):
        from prototype.demo_data import success_scenario
        candidates = success_scenario()
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")
        assert state["status"] == EngineStatus.SUCCESS.value

    def test_failure_pivot_scenario(self):
        from prototype.demo_data import failure_pivot_scenario
        candidates = failure_pivot_scenario(max_attempts=2)
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")
        assert state["status"] in (
            EngineStatus.SUCCESS.value,
            EngineStatus.COMPLETED.value,
        )

    def test_multi_candidate_scenario(self):
        from prototype.demo_data import multi_candidate_scenario
        candidates = multi_candidate_scenario()
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")
        assert state["status"] in (
            EngineStatus.SUCCESS.value,
            EngineStatus.COMPLETED.value,
        )

    def test_all_fail_scenario(self):
        from prototype.demo_data import all_fail_scenario
        candidates = all_fail_scenario(max_attempts=2)
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")
        assert state["status"] == EngineStatus.COMPLETED.value


class TestScanEdgeCases:

    def test_empty_findings_produce_no_candidates(self, epss_mock):
        """Empty findings list produces no candidates."""
        candidates = findings_to_candidates([])
        assert candidates == []

    def test_candidates_to_scenario_empty(self):
        """Empty candidates list produces empty scenario."""
        scenario = candidates_to_scenario([])
        assert scenario == []

    def test_candidates_to_scenario_preserves_data(self, epss_mock):
        """Scenario dicts preserve candidate data."""
        f = CanonicalFinding(finding_id="CVE-2023-9999", host="1.2.3.4", port=443, metadata={"cve": "CVE-2023-9999", "epss_score": 0.75})
        candidates = findings_to_candidates([f])
        scenario = candidates_to_scenario(candidates)
        assert scenario[0]["id"] == "CVE-2023-9999"
        assert scenario[0]["probability"] == 0.75
        assert scenario[0]["ground_truth"] is None

    def test_finding_without_cve_uses_port(self, epss_mock):
        """Finding without CVE gets PORT-<n> ID."""
        f = CanonicalFinding(host="1.2.3.4", port=8080, metadata={"epss_score": 0.5})
        candidates = findings_to_candidates([f])
        assert candidates[0].id == "PORT-8080"

    def test_finding_without_port(self, epss_mock):
        """Finding without port gets PORT-UNKNOWN ID."""
        f = CanonicalFinding(host="1.2.3.4", port=0, metadata={"epss_score": 0.3})
        candidates = findings_to_candidates([f])
        assert candidates[0].id == "PORT-UNKNOWN"

    def test_finding_with_cve_uses_cve_id(self, epss_mock):
        """Finding with CVE gets CVE as ID."""
        f = CanonicalFinding(host="1.2.3.4", port=80, metadata={"cve": "CVE-2023-1234", "epss_score": 0.9})
        candidates = findings_to_candidates([f])
        assert candidates[0].id == "CVE-2023-1234"

    def test_probability_clamped_high(self, epss_mock):
        """Probability > 1.0 is clamped to 1.0."""
        f = CanonicalFinding(host="1.2.3.4", port=80, metadata={"epss_score": 1.5})
        candidates = findings_to_candidates([f])
        assert candidates[0].probability == 1.0

    def test_probability_clamped_low(self, epss_mock):
        """Probability < 0.0 is clamped to 0.0."""
        f = CanonicalFinding(host="1.2.3.4", port=80, metadata={"epss_score": -0.5})
        candidates = findings_to_candidates([f])
        assert candidates[0].probability == 0.0

    def test_unsupported_file_type_raises(self, epss_mock):
        """Unsupported file type raises ValueError."""
        with pytest.raises(ValueError, match="No adapter found"):
            candidates_from_scan("scan.txt")

    def test_candidates_to_scenario_roundtrip(self, nmap_xml_file, epss_mock):
        """Candidates can be converted to scenario dicts and back."""
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        assert len(scenario) == len(candidates)
        for s in scenario:
            assert "id" in s
            assert "probability" in s
            assert "ground_truth" in s


class TestScanReportGeneration:

    def test_json_report_generated(self, nmap_xml_file, epss_mock):
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        report = generate_json_report("scan_test", state, max_attempts=2, mode="simulation")
        data = json.loads(report)
        assert data["scenario"] == "scan_test"
        assert data["final_status"] == state["status"]

    def test_text_report_generated(self, nmap_xml_file, epss_mock):
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        report = generate_text_report("scan_test", state, max_attempts=2, mode="simulation")
        assert "AI VAPT DECISION ENGINE" in report

    def test_report_contains_candidates(self, nmap_xml_file, epss_mock):
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        report = generate_json_report("scan_test", state, max_attempts=2, mode="simulation")
        data = json.loads(report)
        assert len(data["candidates"]) > 0

    def test_report_evidence_tier_simulation(self, nmap_xml_file, epss_mock):
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        report = generate_json_report("scan_test", state, max_attempts=2, mode="simulation")
        data = json.loads(report)
        assert data["evidence_tier"] == "SIMULATED"

    def test_report_safety_notice(self, nmap_xml_file, epss_mock):
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        report = generate_json_report("scan_test", state, max_attempts=2, mode="simulation")
        data = json.loads(report)
        assert "SIMULATION MODE" in data["safety_notice"]
        assert "No real vulnerabilities were validated" in data["safety_notice"]


class TestScanCLIIntegration:

    def test_cli_scan_nmap_xml(self, nmap_xml_file, epss_mock):
        from prototype.cli import _run_scenario
        state = _run_scenario(
            scenario_name="",
            max_attempts=2,
            mode="simulation",
            scan_file=nmap_xml_file,
        )
        assert state["status"] in (
            EngineStatus.SUCCESS.value,
            EngineStatus.COMPLETED.value,
        )

    def test_cli_scan_nmap_json(self, nmap_json_file, epss_mock):
        from prototype.cli import _run_scenario
        state = _run_scenario(
            scenario_name="",
            max_attempts=2,
            mode="simulation",
            scan_file=nmap_json_file,
        )
        assert state["status"] in (
            EngineStatus.SUCCESS.value,
            EngineStatus.COMPLETED.value,
        )

    def test_cli_scan_custom_json(self, custom_json_file, epss_mock):
        from prototype.cli import _run_scenario
        state = _run_scenario(
            scenario_name="",
            max_attempts=2,
            mode="simulation",
            scan_file=custom_json_file,
        )
        assert state["status"] in (
            EngineStatus.SUCCESS.value,
            EngineStatus.COMPLETED.value,
        )

    def test_cli_scan_generates_reports(self, nmap_xml_file, epss_mock):
        from prototype.cli import _run_scenario
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                state = _run_scenario(
                    scenario_name="",
                    max_attempts=2,
                    mode="simulation",
                    scan_file=nmap_xml_file,
                )
                json_reports = list(Path(tmpdir).glob("*_vapt.json"))
                txt_reports = list(Path(tmpdir).glob("*_vapt.txt"))
                assert len(json_reports) > 0
                assert len(txt_reports) > 0
            finally:
                os.chdir(old_cwd)

    def test_cli_scan_live_xml(self, live_xml_file, epss_mock):
        from prototype.cli import _run_scenario
        state = _run_scenario(
            scenario_name="",
            max_attempts=2,
            mode="simulation",
            scan_file=live_xml_file,
        )
        assert state["status"] in (
            EngineStatus.SUCCESS.value,
            EngineStatus.COMPLETED.value,
        )
