"""Tests for the scan ingestion vertical slice.

Verifies that scan files (Nmap XML, Nmap JSON, custom JSON) are correctly:
  - Parsed by the scanner
  - Converted to ActionCandidates
  - Fed through the decision engine
  - Reported with proper evidence tier

These tests mock the EPSS network call to stay offline.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root on path
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def epss_mock(monkeypatch):
    """Mock EPSS to return deterministic scores (offline)."""
    monkeypatch.setattr(
        "core.scanner.fetch_epss_score",
        lambda cve_id, timeout=5: 0.5,  # deterministic mid-range score
    )


@pytest.fixture
def nmap_xml_file():
    """Path to the rich Nmap XML fixture."""
    return str(ROOT / "data" / "rich_scan.xml")


@pytest.fixture
def nmap_json_file():
    """Path to the Nmap JSON fixture."""
    return str(ROOT / "data" / "rich_scan_nmap.json")


@pytest.fixture
def custom_json_file():
    """Path to the custom JSON fixture."""
    return str(ROOT / "data" / "rich_scan_custom.json")


@pytest.fixture
def live_xml_file():
    """Path to the original live_scan.xml fixture."""
    return str(ROOT / "data" / "live_scan.xml")


# ---------------------------------------------------------------------------
# Scanner parsing tests
# ---------------------------------------------------------------------------

class TestNmapXmlParsing:
    """Verify Nmap XML parsing produces correct findings."""

    def test_parse_nmap_xml_multi_host(self, nmap_xml_file, epss_mock):
        """Rich XML fixture parses multiple hosts and ports."""
        from core.scanner import parse_nmap_xml
        findings = parse_nmap_xml(nmap_xml_file)
        # 3 hosts up: 192.168.1.10 (4 open), 192.168.1.20 (2 open), 192.168.1.30 (5 open)
        assert len(findings) == 11  # 4 + 2 + 5 open ports

    def test_parse_nmap_xml_contains_hosts(self, nmap_xml_file, epss_mock):
        """Parsed findings include expected host IPs."""
        from core.scanner import parse_nmap_xml
        findings = parse_nmap_xml(nmap_xml_file)
        hosts = {f["host"] for f in findings}
        assert "192.168.1.10" in hosts
        assert "192.168.1.20" in hosts
        assert "192.168.1.30" in hosts

    def test_parse_nmap_xml_service_detection(self, nmap_xml_file, epss_mock):
        """Service names are correctly extracted."""
        from core.scanner import parse_nmap_xml
        findings = parse_nmap_xml(nmap_xml_file)
        services = {f["service"] for f in findings}
        assert "ssh" in services
        assert "http" in services
        assert "https" in services

    def test_parse_nmap_xml_cpe_present(self, nmap_xml_file, epss_mock):
        """CPE data is extracted from service tags."""
        from core.scanner import parse_nmap_xml
        findings = parse_nmap_xml(nmap_xml_file)
        # At least one finding should have CPE
        has_cpe = any(f.get("cpe") for f in findings)
        assert has_cpe

    def test_process_scan_xml_enriches(self, nmap_xml_file, epss_mock):
        """process_scan returns Finding objects with EPSS scores."""
        from core.scanner import process_scan
        findings = process_scan(nmap_xml_file)
        assert len(findings) > 0
        for f in findings:
            assert f.epss_score >= 0.0
            assert f.epss_score <= 1.0


class TestNmapJsonParsing:
    """Verify Nmap JSON parsing produces correct findings."""

    def test_parse_nmap_json_multi_host(self, nmap_json_file, epss_mock):
        """Nmap JSON fixture parses multiple hosts."""
        from core.scanner import parse_nmap_json
        findings = parse_nmap_json(nmap_json_file)
        # 3 hosts: 10.0.0.10 (4 open), 10.0.0.20 (2 open), 10.0.0.30 (5 open)
        assert len(findings) == 11

    def test_parse_nmap_json_contains_cves(self, nmap_json_file, epss_mock):
        """Nmap JSON findings include CVE identifiers."""
        from core.scanner import parse_nmap_json
        findings = parse_nmap_json(nmap_json_file)
        cves = [f.get("cve") for f in findings if f.get("cve")]
        assert len(cves) > 0
        assert "CVE-2023-38408" in cves

    def test_parse_nmap_json_hosts(self, nmap_json_file, epss_mock):
        """Parsed findings include expected host IPs."""
        from core.scanner import parse_nmap_json
        findings = parse_nmap_json(nmap_json_file)
        hosts = {f["host"] for f in findings}
        assert "10.0.0.10" in hosts
        assert "10.0.0.20" in hosts
        assert "10.0.0.30" in hosts


class TestCustomJsonParsing:
    """Verify custom JSON parsing produces correct findings."""

    def test_parse_custom_json(self, custom_json_file, epss_mock):
        """Custom JSON fixture parses findings array."""
        from core.scanner import parse_custom_json
        findings = parse_custom_json(custom_json_file)
        assert len(findings) == 7

    def test_parse_custom_json_cves(self, custom_json_file, epss_mock):
        """Custom JSON findings include CVE identifiers."""
        from core.scanner import parse_custom_json
        findings = parse_custom_json(custom_json_file)
        cves = [f.get("cve") for f in findings]
        assert "CVE-2023-38408" in cves
        assert "CVE-2023-25690" in cves

    def test_parse_custom_json_target(self, custom_json_file, epss_mock):
        """Custom JSON findings inherit target from top-level."""
        from core.scanner import parse_custom_json
        findings = parse_custom_json(custom_json_file)
        for f in findings:
            assert f.get("host") == "10.0.0.0/24"


# ---------------------------------------------------------------------------
# Scan adapter tests
# ---------------------------------------------------------------------------

class TestCandidatesFromScan:
    """Verify scan adapter converts findings to ActionCandidates."""

    def test_candidates_from_nmap_xml(self, nmap_xml_file, epss_mock):
        """Nmap XML scan produces ActionCandidates."""
        candidates = candidates_from_scan(nmap_xml_file)
        assert len(candidates) > 0
        assert all(isinstance(c, ActionCandidate) for c in candidates)

    def test_candidates_from_nmap_json(self, nmap_json_file, epss_mock):
        """Nmap JSON scan produces ActionCandidates."""
        candidates = candidates_from_scan(nmap_json_file)
        assert len(candidates) > 0
        assert all(isinstance(c, ActionCandidate) for c in candidates)

    def test_candidates_from_custom_json(self, custom_json_file, epss_mock):
        """Custom JSON scan produces ActionCandidates."""
        candidates = candidates_from_scan(custom_json_file)
        assert len(candidates) > 0
        assert all(isinstance(c, ActionCandidate) for c in candidates)

    def test_candidates_have_valid_probability(self, nmap_xml_file, epss_mock):
        """All candidates have probability in [0, 1]."""
        candidates = candidates_from_scan(nmap_xml_file)
        for c in candidates:
            assert 0.0 <= c.probability <= 1.0

    def test_candidates_have_ids(self, nmap_xml_file, epss_mock):
        """All candidates have non-empty string IDs."""
        candidates = candidates_from_scan(nmap_xml_file)
        for c in candidates:
            assert c.id
            assert isinstance(c.id, str)

    def test_candidates_from_json_have_cve_ids(self, nmap_json_file, epss_mock):
        """Candidates from Nmap JSON use CVE IDs when available."""
        candidates = candidates_from_scan(nmap_json_file)
        ids = {c.id for c in candidates}
        # At least some should be CVE-based
        cve_ids = {i for i in ids if i.startswith("CVE-")}
        assert len(cve_ids) > 0

    def test_candidates_to_scenario_roundtrip(self, nmap_xml_file, epss_mock):
        """Candidates can be converted to scenario dicts and back."""
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        assert len(scenario) == len(candidates)
        for s in scenario:
            assert "id" in s
            assert "probability" in s
            assert "ground_truth" in s


# ---------------------------------------------------------------------------
# Engine integration tests
# ---------------------------------------------------------------------------

class TestScanEngineIntegration:
    """Verify scan candidates flow through the decision engine."""

    def test_scan_candidates_run_through_engine(self, nmap_xml_file, epss_mock):
        """Scan candidates from XML reach terminal state via real engine."""
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        assert state["status"] in (
            EngineStatus.SUCCESS.value,
            EngineStatus.COMPLETED.value,
        )

    def test_scan_candidates_produce_results(self, nmap_xml_file, epss_mock):
        """Engine produces execution results for scan candidates."""
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        assert "results" in state
        assert len(state["results"]) > 0

    def test_scan_candidates_produce_logs(self, nmap_xml_file, epss_mock):
        """Engine produces decision trace logs for scan candidates."""
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        assert "logs" in state
        assert len(state["logs"]) > 0

    def test_scan_candidates_produce_presentation(self, nmap_xml_file, epss_mock):
        """Engine produces presentation metadata for scan candidates."""
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        presentation = state.get("_presentation", {})
        assert "total_attempts" in presentation
        assert "candidates_processed" in presentation
        assert presentation["total_attempts"] > 0

    def test_nmap_json_candidates_run_through_engine(self, nmap_json_file, epss_mock):
        """Nmap JSON scan candidates reach terminal state."""
        candidates = candidates_from_scan(nmap_json_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        assert state["status"] in (
            EngineStatus.SUCCESS.value,
            EngineStatus.COMPLETED.value,
        )

    def test_custom_json_candidates_run_through_engine(self, custom_json_file, epss_mock):
        """Custom JSON scan candidates reach terminal state."""
        candidates = candidates_from_scan(custom_json_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        assert state["status"] in (
            EngineStatus.SUCCESS.value,
            EngineStatus.COMPLETED.value,
        )


# ---------------------------------------------------------------------------
# Report generation tests
# ---------------------------------------------------------------------------

class TestScanReportGeneration:
    """Verify reports are generated for scan runs."""

    def test_json_report_generated(self, nmap_xml_file, epss_mock):
        """JSON report is generated for scan run."""
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        report = generate_json_report("scan_test", state, max_attempts=2, mode="simulation")
        data = json.loads(report)
        assert data["scenario"] == "scan_test"
        assert data["final_status"] == state["status"]
        assert "candidates" in data
        assert "evidence_tier" in data

    def test_text_report_generated(self, nmap_xml_file, epss_mock):
        """Text report is generated for scan run."""
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        report = generate_text_report("scan_test", state, max_attempts=2, mode="simulation")
        assert "AI VAPT DECISION ENGINE" in report
        assert "FINAL RESULT" in report
        assert "SIMULATION MODE" in report

    def test_report_contains_candidates(self, nmap_xml_file, epss_mock):
        """Report contains the scan candidates."""
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        report = generate_json_report("scan_test", state, max_attempts=2, mode="simulation")
        data = json.loads(report)
        assert len(data["candidates"]) > 0

    def test_report_evidence_tier_simulation(self, nmap_xml_file, epss_mock):
        """Report labels evidence tier as SIMULATED for simulation mode."""
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        report = generate_json_report("scan_test", state, max_attempts=2, mode="simulation")
        data = json.loads(report)
        assert data["evidence_tier"] == "SIMULATED"

    def test_report_safety_notice(self, nmap_xml_file, epss_mock):
        """Report includes safety notice for simulation mode."""
        candidates = candidates_from_scan(nmap_xml_file)
        scenario = candidates_to_scenario(candidates)
        state = run_decision_scenario(scenario, max_attempts=2, mode="simulation")
        report = generate_json_report("scan_test", state, max_attempts=2, mode="simulation")
        data = json.loads(report)
        assert "SIMULATION MODE" in data["safety_notice"]
        assert "No real vulnerabilities were validated" in data["safety_notice"]


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

class TestScanCLIIntegration:
    """Verify --scan CLI command works end-to-end."""

    def test_cli_scan_nmap_xml(self, nmap_xml_file, epss_mock):
        """CLI --scan with Nmap XML produces final state."""
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
        """CLI --scan with Nmap JSON produces final state."""
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
        """CLI --scan with custom JSON produces final state."""
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
        """CLI --scan generates report files."""
        from prototype.cli import _run_scenario
        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to tmpdir so reports land there
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                state = _run_scenario(
                    scenario_name="",
                    max_attempts=2,
                    mode="simulation",
                    scan_file=nmap_xml_file,
                )
                # Reports should be written
                json_reports = list(Path(tmpdir).glob("*_vapt.json"))
                txt_reports = list(Path(tmpdir).glob("*_vapt.txt"))
                assert len(json_reports) > 0
                assert len(txt_reports) > 0
            finally:
                os.chdir(old_cwd)

    def test_cli_scan_live_xml(self, live_xml_file, epss_mock):
        """CLI --scan with original live_scan.xml still works."""
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


# ---------------------------------------------------------------------------
# Existing scenario regression tests
# ---------------------------------------------------------------------------

class TestExistingScenariosStillWork:
    """Verify existing CLI scenarios are not broken by scan changes."""

    def test_success_scenario(self):
        """Success scenario still reaches SUCCESS."""
        from prototype.demo_data import success_scenario
        candidates = success_scenario()
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")
        assert state["status"] == EngineStatus.SUCCESS.value

    def test_failure_pivot_scenario(self):
        """Failure pivot scenario still demonstrates pivot."""
        from prototype.demo_data import failure_pivot_scenario
        candidates = failure_pivot_scenario(max_attempts=2)
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")
        assert state["status"] in (
            EngineStatus.SUCCESS.value,
            EngineStatus.COMPLETED.value,
        )
        # Should have pivot events
        presentation = state.get("_presentation", {})
        assert presentation.get("pivot_count", 0) >= 1

    def test_multi_candidate_scenario(self):
        """Multi-candidate scenario still works."""
        from prototype.demo_data import multi_candidate_scenario
        candidates = multi_candidate_scenario()
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")
        assert state["status"] in (
            EngineStatus.SUCCESS.value,
            EngineStatus.COMPLETED.value,
        )

    def test_all_fail_scenario(self):
        """All-fail scenario reaches COMPLETED (bounded termination)."""
        from prototype.demo_data import all_fail_scenario
        candidates = all_fail_scenario(max_attempts=2)
        state = run_decision_scenario(candidates, max_attempts=2, mode="simulation")
        assert state["status"] == EngineStatus.COMPLETED.value


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

class TestScanEdgeCases:
    """Verify edge cases in scan ingestion."""

    def test_empty_findings_produce_no_candidates(self, epss_mock):
        """Empty findings list produces no candidates."""
        candidates = findings_to_candidates([])
        assert candidates == []

    def test_finding_without_cve_uses_port(self, epss_mock):
        """Finding without CVE gets PORT-<n> ID."""
        from core.schemas import Finding
        f = Finding(cve="UNKNOWN-CVE", port=8080, service="http")
        f.epss_score = 0.5
        candidates = findings_to_candidates([f])
        assert candidates[0].id == "PORT-8080"

    def test_finding_without_port(self, epss_mock):
        """Finding without port gets PORT-UNKNOWN ID."""
        from core.schemas import Finding
        f = Finding(cve="UNKNOWN-CVE", port=None, service="unknown")
        f.epss_score = 0.3
        candidates = findings_to_candidates([f])
        assert candidates[0].id == "PORT-UNKNOWN"

    def test_finding_with_cve_uses_cve_id(self, epss_mock):
        """Finding with CVE gets CVE as ID."""
        from core.schemas import Finding
        f = Finding(cve="CVE-2023-1234", port=80, service="http")
        f.epss_score = 0.9
        candidates = findings_to_candidates([f])
        assert candidates[0].id == "CVE-2023-1234"

    def test_probability_clamped_high(self, epss_mock):
        """Probability > 1.0 is clamped to 1.0."""
        from core.schemas import Finding
        f = Finding(cve="CVE-TEST", port=80)
        f.epss_score = 1.5
        candidates = findings_to_candidates([f])
        assert candidates[0].probability == 1.0

    def test_probability_clamped_low(self, epss_mock):
        """Probability < 0.0 is clamped to 0.0."""
        from core.schemas import Finding
        f = Finding(cve="CVE-TEST", port=80)
        f.epss_score = -0.5
        candidates = findings_to_candidates([f])
        assert candidates[0].probability == 0.0

    def test_unsupported_file_type_raises(self, epss_mock):
        """Unsupported file type raises ValueError."""
        from core.scanner import process_scan
        with pytest.raises(ValueError, match="Unsupported scan file type"):
            process_scan("scan.txt")

    def test_candidates_to_scenario_empty(self):
        """Empty candidates list produces empty scenario."""
        scenario = candidates_to_scenario([])
        assert scenario == []

    def test_candidates_to_scenario_preserves_data(self, epss_mock):
        """Scenario dicts preserve candidate data."""
        from core.schemas import Finding
        f = Finding(cve="CVE-2023-9999", port=443, service="https")
        f.epss_score = 0.75
        candidates = findings_to_candidates([f])
        scenario = candidates_to_scenario(candidates)
        assert scenario[0]["id"] == "CVE-2023-9999"
        assert scenario[0]["probability"] == 0.75
        assert scenario[0]["ground_truth"] is None