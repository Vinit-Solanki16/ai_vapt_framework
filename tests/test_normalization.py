"""Tests for the canonical finding normalization layer."""
from __future__ import annotations

import pytest

from vapt_platform.normalization import (
    CanonicalFinding,
    deduplicate,
    from_custom_json_dict,
    from_nmap_json_dict,
    from_nmap_xml_dict,
    from_nuclei_finding,
    normalize_severity,
    severity_rank,
    highest_severity,
)


# ---------------------------------------------------------------------------
# Severity normalization tests
# ---------------------------------------------------------------------------

class TestSeverityNormalization:
    def test_standard_levels(self):
        assert normalize_severity("critical") == "critical"
        assert normalize_severity("high") == "high"
        assert normalize_severity("medium") == "medium"
        assert normalize_severity("low") == "low"
        assert normalize_severity("info") == "informational"

    def test_case_insensitive(self):
        assert normalize_severity("CRITICAL") == "critical"
        assert normalize_severity("High") == "high"

    def test_numeric_mapping(self):
        assert normalize_severity(9.5) == "critical"
        assert normalize_severity(7.0) == "high"
        assert normalize_severity(4.0) == "medium"
        assert normalize_severity(1.0) == "low"
        assert normalize_severity(0.0) == "informational"

    def test_none_returns_unknown(self):
        assert normalize_severity(None) == "unknown"

    def test_unknown_returns_unknown(self):
        assert normalize_severity("unknown") == "unknown"
        assert normalize_severity("invalid") == "unknown"


# ---------------------------------------------------------------------------
# Nmap XML mapping tests
# ---------------------------------------------------------------------------

class TestNmapXmlMapping:
    def test_basic_mapping(self):
        d = {
            "host": "192.168.1.10",
            "port": 80,
            "service": "http",
            "description": "Apache httpd",
            "cpe": ["cpe:/a:apache:http_server:2.4.25"],
        }
        f = from_nmap_xml_dict(d)
        assert f.source == "nmap-xml"
        assert f.host == "192.168.1.10"
        assert f.port == 80
        assert f.title == "http"
        assert "cpe:/a:apache:http_server:2.4.25" in f.evidence

    def test_missing_service(self):
        d = {"host": "10.0.0.1", "port": 443}
        f = from_nmap_xml_dict(d)
        assert f.title == "open port"
        assert f.port == 443

    def test_string_port_converted(self):
        d = {"host": "10.0.0.1", "port": "8080"}
        f = from_nmap_xml_dict(d)
        assert f.port == 8080


# ---------------------------------------------------------------------------
# Nmap JSON mapping tests
# ---------------------------------------------------------------------------

class TestNmapJsonMapping:
    def test_basic_mapping(self):
        d = {
            "host": "10.0.0.10",
            "port": 22,
            "service": "ssh",
            "description": "OpenSSH",
            "cve": "CVE-2023-38408",
        }
        f = from_nmap_json_dict(d)
        assert f.source == "nmap-json"
        assert f.host == "10.0.0.10"
        assert f.port == 22
        assert f.rule_id == "CVE-2023-38408"
        assert "CVE-2023-38408" in f.evidence

    def test_no_cve_uses_port(self):
        d = {"host": "10.0.0.1", "port": 80, "service": "http"}
        f = from_nmap_json_dict(d)
        assert f.rule_id == "port-80"


# ---------------------------------------------------------------------------
# Custom JSON mapping tests
# ---------------------------------------------------------------------------

class TestCustomJsonMapping:
    def test_basic_mapping(self):
        d = {
            "host": "10.0.0.0/24",
            "port": 8080,
            "service": "http",
            "cve": "CVE-2021-44228",
            "description": "Apache Log4j2 RCE",
        }
        f = from_custom_json_dict(d)
        assert f.source == "custom"
        assert f.host == "10.0.0.0/24"
        assert f.port == 8080
        assert f.rule_id == "CVE-2021-44228"
        assert "CVE-2021-44228" in f.evidence


# ---------------------------------------------------------------------------
# Nuclei mapping tests
# ---------------------------------------------------------------------------

class TestNucleiMapping:
    def test_basic_mapping(self):
        from vapt_platform.parsers.nuclei_parser import NucleiFinding

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
        assert f.source == "nuclei"
        assert f.host == "https://example.com"
        assert f.target == "https://example.com/api"
        assert f.port == 443  # https
        assert f.severity == "critical"
        assert f.rule_id == "CVE-2021-44228"
        assert "result1" in f.evidence

    def test_http_port(self):
        from vapt_platform.parsers.nuclei_parser import NucleiFinding

        nf = NucleiFinding(
            template_id="test",
            host="http://example.com",
            target="http://example.com",
        )
        f = from_nuclei_finding(nf)
        assert f.port == 80

    def test_severity_normalization(self):
        from vapt_platform.parsers.nuclei_parser import NucleiFinding

        nf = NucleiFinding(template_id="test", severity="HIGH")
        f = from_nuclei_finding(nf)
        assert f.severity == "high"


# ---------------------------------------------------------------------------
# Finding identity tests
# ---------------------------------------------------------------------------

class TestFindingIdentity:
    def test_deterministic_id(self):
        f1 = CanonicalFinding(source="nmap", host="10.0.0.1", port=80, rule_id="http")
        f2 = CanonicalFinding(source="nmap", host="10.0.0.1", port=80, rule_id="http")
        assert f1.compute_finding_id() == f2.compute_finding_id()

    def test_different_ids(self):
        f1 = CanonicalFinding(source="nmap", host="10.0.0.1", port=80)
        f2 = CanonicalFinding(source="nmap", host="10.0.0.1", port=443)
        assert f1.compute_finding_id() != f2.compute_finding_id()


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_removes_duplicates(self):
        f1 = CanonicalFinding(source="nmap", host="10.0.0.1", port=80, rule_id="http")
        f2 = CanonicalFinding(source="nmap", host="10.0.0.1", port=80, rule_id="http")
        result = deduplicate([f1, f2])
        assert len(result) == 1

    def test_keeps_distinct(self):
        f1 = CanonicalFinding(source="nmap", host="10.0.0.1", port=80)
        f2 = CanonicalFinding(source="nmap", host="10.0.0.1", port=443)
        result = deduplicate([f1, f2])
        assert len(result) == 2

    def test_merges_evidence(self):
        f1 = CanonicalFinding(source="nmap", host="10.0.0.1", port=80, evidence=["a"])
        f2 = CanonicalFinding(source="nmap", host="10.0.0.1", port=80, evidence=["b"])
        result = deduplicate([f1, f2])
        assert len(result) == 1
        assert "a" in result[0].evidence
        assert "b" in result[0].evidence


# ---------------------------------------------------------------------------
# Severity rank tests
# ---------------------------------------------------------------------------

class TestSeverityRank:
    def test_rank_order(self):
        assert severity_rank("critical") > severity_rank("high")
        assert severity_rank("high") > severity_rank("medium")
        assert severity_rank("medium") > severity_rank("low")

    def test_highest_severity(self):
        assert highest_severity("critical", "high") == "critical"
        assert highest_severity("low", "medium") == "medium"
