"""Tests for the vulnerability intelligence enrichment layer."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vapt_platform.enrichment import (
    _extract_cve_ids,
    _load_cisa_kev,
    _load_epss_corpus,
    clear_cache,
    enrich_finding,
    enrich_findings,
)
from vapt_platform.normalization import CanonicalFinding


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear dataset cache before each test."""
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def sample_kev_file(tmp_path):
    """Create a temporary CISA KEV file with known entries."""
    kev_data = {
        "title": "Test KEV",
        "catalogVersion": "2026.01.01",
        "dateReleased": "2026-01-01T00:00:00Z",
        "count": 3,
        "vulnerabilities": [
            {
                "cveID": "CVE-2021-44228",
                "vendorProject": "Apache",
                "product": "Log4j",
                "vulnerabilityName": "Log4j RCE",
                "dateAdded": "2026-01-01",
                "shortDescription": "Test",
                "requiredAction": "Test",
                "dueDate": "2026-02-01",
                "knownRansomwareCampaignUse": "Known",
                "notes": "",
                "cwes": ["CWE-502"],
            },
            {
                "cveID": "CVE-2017-0144",
                "vendorProject": "Microsoft",
                "product": "Windows",
                "vulnerabilityName": "EternalBlue",
                "dateAdded": "2026-01-01",
                "shortDescription": "Test",
                "requiredAction": "Test",
                "dueDate": "2026-02-01",
                "knownRansomwareCampaignUse": "Known",
                "notes": "",
                "cwes": ["CWE-200"],
            },
            {
                "cveID": "CVE-2023-34362",
                "vendorProject": "MOVEit",
                "product": "MOVEit Transfer",
                "vulnerabilityName": "SQLi",
                "dateAdded": "2026-01-01",
                "shortDescription": "Test",
                "requiredAction": "Test",
                "dueDate": "2026-02-01",
                "knownRansomwareCampaignUse": "Known",
                "notes": "",
                "cwes": ["CWE-89"],
            },
        ],
    }
    kev_path = tmp_path / "cisa_kev.json"
    with open(kev_path, "w") as f:
        json.dump(kev_data, f)
    return kev_path


@pytest.fixture
def sample_epss_file(tmp_path):
    """Create a temporary EPSS corpus file."""
    epss_data = {
        "CVE-2021-44228": 0.99999,
        "CVE-2017-0144": 0.9923,
        "CVE-2023-34362": 0.99934,
        "CVE-2023-38408": 0.797,
        "CVE-2022-22965": 0.99638,
    }
    epss_path = tmp_path / "epss_corpus_enrichment.json"
    with open(epss_path, "w") as f:
        json.dump(epss_data, f)
    return epss_path


@pytest.fixture
def patched_datasets(sample_kev_file, sample_epss_file):
    """Patch dataset paths to use temp files."""
    with patch("vapt_platform.enrichment.CISA_KEV_PATH", sample_kev_file), \
         patch("vapt_platform.enrichment.EPSS_CORPUS_PATH", sample_epss_file):
        clear_cache()
        yield
        clear_cache()


# ---------------------------------------------------------------------------
# CVE extraction tests
# ---------------------------------------------------------------------------

class TestExtractCveIds:
    def test_from_metadata_cve_ids(self):
        f = CanonicalFinding(metadata={"cve_ids": ["CVE-2021-44228", "CVE-2023-34362"]})
        cves = _extract_cve_ids(f)
        assert "CVE-2021-44228" in cves
        assert "CVE-2023-34362" in cves

    def test_from_metadata_cve_string(self):
        f = CanonicalFinding(metadata={"cve": "CVE-2021-44228"})
        cves = _extract_cve_ids(f)
        assert "CVE-2021-44228" in cves

    def test_from_rule_id(self):
        f = CanonicalFinding(rule_id="CVE-2021-44228")
        cves = _extract_cve_ids(f)
        assert "CVE-2021-44228" in cves

    def test_from_evidence(self):
        f = CanonicalFinding(evidence=["CVE-2021-44228", "some other evidence"])
        cves = _extract_cve_ids(f)
        assert "CVE-2021-44228" in cves

    def test_no_cve_returns_empty(self):
        f = CanonicalFinding(rule_id="port-80", evidence=["no cve here"])
        cves = _extract_cve_ids(f)
        assert cves == []

    def test_case_normalization(self):
        f = CanonicalFinding(metadata={"cve": "cve-2021-44228"})
        cves = _extract_cve_ids(f)
        assert "CVE-2021-44228" in cves

    def test_deduplication(self):
        f = CanonicalFinding(
            rule_id="CVE-2021-44228",
            metadata={"cve_ids": ["CVE-2021-44228"], "cve": "CVE-2021-44228"},
        )
        cves = _extract_cve_ids(f)
        assert cves.count("CVE-2021-44228") == 1


# ---------------------------------------------------------------------------
# Dataset loading tests
# ---------------------------------------------------------------------------

class TestLoadKev:
    def test_load_valid_kev(self, sample_kev_file):
        with patch("vapt_platform.enrichment.CISA_KEV_PATH", sample_kev_file):
            clear_cache()
            kev = _load_cisa_kev()
            assert "CVE-2021-44228" in kev
            assert "CVE-2017-0144" in kev
            assert "CVE-2023-34362" in kev

    def test_missing_file_returns_empty(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        with patch("vapt_platform.enrichment.CISA_KEV_PATH", missing):
            clear_cache()
            kev = _load_cisa_kev()
            assert kev == set()

    def test_malformed_json_returns_empty(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        with patch("vapt_platform.enrichment.CISA_KEV_PATH", bad):
            clear_cache()
            kev = _load_cisa_kev()
            assert kev == set()


class TestLoadEpss:
    def test_load_valid_epss(self, sample_epss_file):
        with patch("vapt_platform.enrichment.EPSS_CORPUS_PATH", sample_epss_file):
            clear_cache()
            epss = _load_epss_corpus()
            assert epss["CVE-2021-44228"] == 0.99999
            assert epss["CVE-2023-38408"] == 0.797

    def test_missing_file_returns_empty(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        with patch("vapt_platform.enrichment.EPSS_CORPUS_PATH", missing):
            clear_cache()
            epss = _load_epss_corpus()
            assert epss == {}

    def test_malformed_json_returns_empty(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        with patch("vapt_platform.enrichment.EPSS_CORPUS_PATH", bad):
            clear_cache()
            epss = _load_epss_corpus()
            assert epss == {}


# ---------------------------------------------------------------------------
# Enrichment tests
# ---------------------------------------------------------------------------

class TestEnrichFinding:
    def test_enrich_with_kev_cve(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            rule_id="CVE-2021-44228",
            metadata={"cve_ids": ["CVE-2021-44228"], "cvss_score": 10.0},
        )
        result = enrich_finding(f)
        assert result.metadata["cisa_kev"] is True
        assert result.metadata["epss_score"] == 0.99999
        assert result.metadata["cvss_score"] == 10.0
        assert result.metadata["severity"] == "critical"

    def test_enrich_with_non_kev_cve(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            rule_id="CVE-2023-38408",
            metadata={"cve_ids": ["CVE-2023-38408"], "cvss_score": 9.8},
        )
        result = enrich_finding(f)
        assert result.metadata["cisa_kev"] is False
        assert result.metadata["epss_score"] == 0.797
        assert result.metadata["severity"] == "critical"

    def test_enrich_no_cve(self, patched_datasets):
        f = CanonicalFinding(
            source="nmap",
            host="10.0.0.1",
            port=80,
            rule_id="port-80",
        )
        result = enrich_finding(f)
        assert result.metadata["cisa_kev"] is False
        assert result.metadata["epss_score"] == 0.0
        assert result.metadata["severity"] == "none"

    def test_enrich_preserves_existing_severity(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            rule_id="CVE-2023-38408",
            severity="medium",
            metadata={"cve_ids": ["CVE-2023-38408"]},
        )
        result = enrich_finding(f)
        # Existing severity should be preserved
        assert result.metadata["severity"] == "medium"

    def test_enrich_multiple_cves_takes_max_epss(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            rule_id="CVE-2021-44228",
            metadata={"cve_ids": ["CVE-2021-44228", "CVE-2023-38408"]},
        )
        result = enrich_finding(f)
        # Max EPSS between 0.99999 and 0.797
        assert result.metadata["epss_score"] == 0.99999

    def test_enrich_multiple_cves_any_in_kev(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            rule_id="CVE-2023-38408",
            metadata={"cve_ids": ["CVE-2023-38408", "CVE-2017-0144"]},
        )
        result = enrich_finding(f)
        # CVE-2017-0144 is in KEV
        assert result.metadata["cisa_kev"] is True

    def test_enrich_cvss_from_metadata(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            rule_id="CVE-2022-22965",
            metadata={"cve_ids": ["CVE-2022-22965"], "cvss_score": 9.8},
        )
        result = enrich_finding(f)
        assert result.metadata["cvss_score"] == 9.8

    def test_enrich_cvss_string_converted(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            rule_id="CVE-2022-22965",
            metadata={"cve_ids": ["CVE-2022-22965"], "cvss_score": "7.5"},
        )
        result = enrich_finding(f)
        assert result.metadata["cvss_score"] == 7.5

    def test_enrich_returns_same_object(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            rule_id="CVE-2021-44228",
            metadata={"cve_ids": ["CVE-2021-44228"]},
        )
        result = enrich_finding(f)
        assert result is f


# ---------------------------------------------------------------------------
# Batch enrichment tests
# ---------------------------------------------------------------------------

class TestEnrichFindings:
    def test_enrich_multiple_findings(self, patched_datasets):
        findings = [
            CanonicalFinding(
                source="nuclei",
                host="example.com",
                rule_id="CVE-2021-44228",
                metadata={"cve_ids": ["CVE-2021-44228"]},
            ),
            CanonicalFinding(
                source="nuclei",
                host="example.com",
                rule_id="CVE-2023-38408",
                metadata={"cve_ids": ["CVE-2023-38408"]},
            ),
            CanonicalFinding(
                source="nmap",
                host="10.0.0.1",
                port=80,
                rule_id="port-80",
            ),
        ]
        results = enrich_findings(findings)
        assert len(results) == 3
        assert results[0].metadata["cisa_kev"] is True
        assert results[1].metadata["cisa_kev"] is False
        assert results[2].metadata["severity"] == "none"

    def test_enrich_empty_list(self, patched_datasets):
        results = enrich_findings([])
        assert results == []


# ---------------------------------------------------------------------------
# Severity determination tests
# ---------------------------------------------------------------------------

class TestSeverityDetermination:
    def test_kev_severity_at_least_high(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            rule_id="CVE-2017-0144",
            metadata={"cve_ids": ["CVE-2017-0144"]},
        )
        result = enrich_finding(f)
        assert result.metadata["severity"] in ("high", "critical")

    def test_high_epss_severity(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            rule_id="CVE-2022-22965",
            metadata={"cve_ids": ["CVE-2022-22965"]},
        )
        result = enrich_finding(f)
        # EPSS 0.99638 >= 0.9 -> critical
        assert result.metadata["severity"] == "critical"

    def test_cvss_based_severity(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            rule_id="CVE-2023-38408",
            metadata={"cve_ids": ["CVE-2023-38408"], "cvss_score": 5.0},
        )
        result = enrich_finding(f)
        # CVSS 5.0 -> medium
        assert result.metadata["severity"] == "medium"

    def test_no_intel_returns_none(self, patched_datasets):
        f = CanonicalFinding(
            source="nmap",
            host="10.0.0.1",
            port=443,
            rule_id="port-443",
        )
        result = enrich_finding(f)
        assert result.metadata["severity"] == "none"


# ---------------------------------------------------------------------------
# Graceful fallback tests
# ---------------------------------------------------------------------------

class TestGracefulFallback:
    def test_missing_kev_file(self, tmp_path, sample_epss_file):
        missing_kev = tmp_path / "missing_kev.json"
        with patch("vapt_platform.enrichment.CISA_KEV_PATH", missing_kev), \
             patch("vapt_platform.enrichment.EPSS_CORPUS_PATH", sample_epss_file):
            clear_cache()
            f = CanonicalFinding(
                source="nuclei",
                host="example.com",
                rule_id="CVE-2021-44228",
                metadata={"cve_ids": ["CVE-2021-44228"]},
            )
            result = enrich_finding(f)
            assert result.metadata["cisa_kev"] is False
            assert result.metadata["epss_score"] == 0.99999

    def test_missing_epss_file(self, tmp_path, sample_kev_file):
        missing_epss = tmp_path / "missing_epss.json"
        with patch("vapt_platform.enrichment.CISA_KEV_PATH", sample_kev_file), \
             patch("vapt_platform.enrichment.EPSS_CORPUS_PATH", missing_epss):
            clear_cache()
            f = CanonicalFinding(
                source="nuclei",
                host="example.com",
                rule_id="CVE-2021-44228",
                metadata={"cve_ids": ["CVE-2021-44228"]},
            )
            result = enrich_finding(f)
            assert result.metadata["cisa_kev"] is True
            assert result.metadata["epss_score"] == 0.0

    def test_both_files_missing(self, tmp_path):
        missing1 = tmp_path / "missing1.json"
        missing2 = tmp_path / "missing2.json"
        with patch("vapt_platform.enrichment.CISA_KEV_PATH", missing1), \
             patch("vapt_platform.enrichment.EPSS_CORPUS_PATH", missing2):
            clear_cache()
            f = CanonicalFinding(
                source="nuclei",
                host="example.com",
                rule_id="CVE-2021-44228",
                metadata={"cve_ids": ["CVE-2021-44228"]},
            )
            result = enrich_finding(f)
            assert result.metadata["cisa_kev"] is False
            assert result.metadata["epss_score"] == 0.0
            assert result.metadata["severity"] == "none"


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------

class TestCache:
    def test_cache_is_used(self, sample_kev_file, sample_epss_file):
        with patch("vapt_platform.enrichment.CISA_KEV_PATH", sample_kev_file), \
             patch("vapt_platform.enrichment.EPSS_CORPUS_PATH", sample_epss_file):
            clear_cache()
            # First call loads from disk
            _load_cisa_kev()
            # Modify file (should not affect cached result)
            with open(sample_kev_file, "w") as f:
                json.dump({"vulnerabilities": []}, f)
            # Second call should return cached data
            kev = _load_cisa_kev()
            assert "CVE-2021-44228" in kev

    def test_clear_cache_reloads(self, sample_kev_file):
        with patch("vapt_platform.enrichment.CISA_KEV_PATH", sample_kev_file):
            clear_cache()
            kev1 = _load_cisa_kev()
            assert len(kev1) == 3
            clear_cache()
            # After clear, reloads from disk
            kev2 = _load_cisa_kev()
            assert len(kev2) == 3


# ---------------------------------------------------------------------------
# Integration with normalization tests
# ---------------------------------------------------------------------------

class TestNormalizationCompatibility:
    def test_enrich_preserves_finding_id(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            rule_id="CVE-2021-44228",
            metadata={"cve_ids": ["CVE-2021-44228"]},
        )
        original_id = f.compute_finding_id()
        result = enrich_finding(f)
        assert result.compute_finding_id() == original_id

    def test_enrich_preserves_all_fields(self, patched_datasets):
        f = CanonicalFinding(
            source="nuclei",
            host="example.com",
            target="https://example.com/api",
            port=443,
            protocol="tcp",
            title="Log4j RCE",
            severity="critical",
            rule_id="CVE-2021-44228",
            description="Apache Log4j2 RCE",
            evidence=["extracted"],
            tags=["cve", "rce"],
            metadata={"cve_ids": ["CVE-2021-44228"], "cvss_score": 10.0},
        )
        result = enrich_finding(f)
        assert result.source == "nuclei"
        assert result.host == "example.com"
        assert result.target == "https://example.com/api"
        assert result.port == 443
        assert result.protocol == "tcp"
        assert result.title == "Log4j RCE"
        assert result.severity == "critical"
        assert result.rule_id == "CVE-2021-44228"
        assert result.description == "Apache Log4j2 RCE"
        assert result.evidence == ["extracted"]
        assert result.tags == ["cve", "rce"]

    def test_enrich_works_with_from_nuclei_finding(self, patched_datasets):
        from vapt_platform.parsers.nuclei_parser import NucleiFinding
        from vapt_platform.normalization import from_nuclei_finding

        nf = NucleiFinding(
            template_id="CVE-2021-44228",
            name="Apache Log4j2 RCE",
            severity="critical",
            type="http",
            host="https://example.com",
            target="https://example.com/api",
            ip="1.2.3.4",
            description="Log4j2 RCE",
            extracted_results=["result1"],
            references=["https://nvd.nist.gov"],
            cve_ids=["CVE-2021-44228"],
            cvss_score=10.0,
        )
        f = from_nuclei_finding(nf)
        result = enrich_finding(f)
        assert result.metadata["cisa_kev"] is True
        assert result.metadata["epss_score"] == 0.99999
        assert result.metadata["cvss_score"] == 10.0
        assert result.metadata["severity"] == "critical"