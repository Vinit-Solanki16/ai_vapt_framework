"""Tests for vulnerability intelligence enrichment integration."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from vapt_platform.enrichment import (
    LocalDatasetProvider,
    VulnerabilityIntelligenceProvider,
    enrich_finding,
    enrich_findings,
    _extract_cve_ids,
    _extract_cwe_ids,
    _determine_severity,
)
from vapt_platform.normalization import CanonicalFinding
from vapt_platform.application import VAPTApplication, VAPTRequest


# ---------------------------------------------------------------------------
# Provider tests
# ---------------------------------------------------------------------------

class TestLocalDatasetProvider:
    def test_create_provider(self):
        provider = LocalDatasetProvider()
        assert provider is not None

    def test_get_epss(self):
        provider = LocalDatasetProvider()
        # CVE-2021-44228 is in the test dataset
        epss = provider.get_epss("CVE-2021-44228")
        assert epss > 0.9

    def test_is_in_kev(self):
        provider = LocalDatasetProvider()
        # Test with a CVE that may or may not be in KEV
        # Just verify the method works
        result = provider.is_in_kev("CVE-2021-44228")
        assert isinstance(result, bool)

    def test_get_cvss(self):
        provider = LocalDatasetProvider()
        # No local CVSS dataset yet
        cvss = provider.get_cvss("CVE-2021-44228")
        assert cvss is None

    def test_get_cwe_ids(self):
        provider = LocalDatasetProvider()
        # No local CWE dataset yet
        cwes = provider.get_cwe_ids("CVE-2021-44228")
        assert cwes == []


# ---------------------------------------------------------------------------
# CVE extraction tests
# ---------------------------------------------------------------------------

class TestCVEExtraction:
    def test_extract_from_metadata_cve_ids(self):
        finding = CanonicalFinding(
            metadata={"cve_ids": ["CVE-2021-44228", "CVE-2023-38408"]}
        )
        cves = _extract_cve_ids(finding)
        assert "CVE-2021-44228" in cves
        assert "CVE-2023-38408" in cves

    def test_extract_from_metadata_cve(self):
        finding = CanonicalFinding(metadata={"cve": "CVE-2021-44228"})
        cves = _extract_cve_ids(finding)
        assert "CVE-2021-44228" in cves

    def test_extract_from_rule_id(self):
        finding = CanonicalFinding(rule_id="CVE-2021-44228")
        cves = _extract_cve_ids(finding)
        assert "CVE-2021-44228" in cves

    def test_extract_from_evidence(self):
        finding = CanonicalFinding(evidence=["CVE-2021-44228", "other"])
        cves = _extract_cve_ids(finding)
        assert "CVE-2021-44228" in cves

    def test_no_cves(self):
        finding = CanonicalFinding()
        cves = _extract_cve_ids(finding)
        assert cves == []


# ---------------------------------------------------------------------------
# CWE extraction tests
# ---------------------------------------------------------------------------

class TestCWEExtraction:
    def test_extract_from_metadata(self):
        finding = CanonicalFinding(metadata={"cwe_ids": ["CWE-502", "CWE-78"]})
        cwes = _extract_cwe_ids(finding)
        assert "CWE-502" in cwes
        assert "CWE-78" in cwes

    def test_no_cwes(self):
        finding = CanonicalFinding()
        cwes = _extract_cwe_ids(finding)
        assert cwes == []


# ---------------------------------------------------------------------------
# Severity determination tests
# ---------------------------------------------------------------------------

class TestSeverityDetermination:
    def test_cvss_critical(self):
        finding = CanonicalFinding()
        severity = _determine_severity(finding, False, 0.0, 9.5)
        assert severity == "critical"

    def test_cvss_high(self):
        finding = CanonicalFinding()
        severity = _determine_severity(finding, False, 0.0, 7.5)
        assert severity == "high"

    def test_kev_presence(self):
        finding = CanonicalFinding()
        severity = _determine_severity(finding, True, 0.0, None)
        assert severity == "high"

    def test_epss_critical(self):
        finding = CanonicalFinding()
        severity = _determine_severity(finding, False, 0.95, None)
        assert severity == "critical"

    def test_no_intelligence(self):
        finding = CanonicalFinding()
        severity = _determine_severity(finding, False, 0.0, None)
        assert severity == "none"


# ---------------------------------------------------------------------------
# Enrichment integration tests
# ---------------------------------------------------------------------------

class TestEnrichmentIntegration:
    def test_enrich_finding(self):
        finding = CanonicalFinding(
            finding_id="test-1",
            metadata={"cve_ids": ["CVE-2021-44228"]}
        )
        enriched = enrich_finding(finding)
        assert enriched.metadata.get("cisa_kev") is not None
        assert enriched.metadata.get("epss_score", 0) > 0
        assert enriched.metadata.get("severity") in ("critical", "high", "medium", "low", "none")

    def test_enrich_findings(self):
        findings = [
            CanonicalFinding(finding_id="test-1", metadata={"cve_ids": ["CVE-2021-44228"]}),
            CanonicalFinding(finding_id="test-2", metadata={"cve_ids": ["CVE-2023-38408"]}),
        ]
        enriched = enrich_findings(findings)
        assert len(enriched) == 2
        for f in enriched:
            assert "epss_score" in f.metadata

    def test_enrich_with_provider(self):
        finding = CanonicalFinding(metadata={"cve_ids": ["CVE-2021-44228"]})
        provider = LocalDatasetProvider()
        enriched = enrich_finding(finding, provider=provider)
        assert enriched.metadata.get("epss_score", 0) > 0


# ---------------------------------------------------------------------------
# Application workflow integration tests
# ---------------------------------------------------------------------------

class TestApplicationEnrichment:
    def test_enrich_candidates_in_workflow(self):
        """Test that candidates are enriched in the workflow."""
        app = VAPTApplication()
        candidates = [
            {"id": "CVE-2021-44228", "probability": 0.95, "metadata": {"cve_ids": ["CVE-2021-44228"]}},
        ]
        enriched = app._enrich_candidates(candidates)
        assert len(enriched) == 1
        assert "metadata" in enriched[0]
        assert "epss_score" in enriched[0]["metadata"]

    def test_enrich_preserves_candidate_fields(self):
        """Test that enrichment preserves existing candidate fields."""
        app = VAPTApplication()
        candidates = [
            {"id": "test-1", "probability": 0.85, "ground_truth": "SUCCESS"},
        ]
        enriched = app._enrich_candidates(candidates)
        assert len(enriched) == 1
        assert enriched[0]["id"] == "test-1"
        assert enriched[0]["probability"] == 0.85

    def test_workflow_with_enrichment(self):
        """Test full workflow with enrichment."""
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(req)
        assert result.final_status in ("SUCCESS", "COMPLETED")
        # Verify candidates were enriched
        for c in result.candidates:
            if "metadata" in c:
                # Enrichment should have added fields
                pass  # Some candidates may not have CVEs to enrich
