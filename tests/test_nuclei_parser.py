"""Tests for the Nuclei JSON parser."""
from __future__ import annotations

import json
import pytest

from vapt_platform.parsers.nuclei_parser import (
    NucleiFinding,
    NucleiParser,
    parse_nuclei_json,
    parse_nuclei_jsonl,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_nuclei_record():
    """A single valid Nuclei finding."""
    return {
        "template-id": "CVE-2021-44228",
        "type": "http",
        "host": "https://example.com",
        "matched-at": "https://example.com/api",
        "matcher-name": "log4j",
        "extracted-results": ["result1", "result2"],
        "info": {
            "name": "Apache Log4j2 Remote Code Execution",
            "severity": "critical",
            "tags": ["cve", "rce", "log4j"],
            "description": "Apache Log4j2 RCE vulnerability",
            "reference": ["https://nvd.nist.gov/vuln/detail/CVE-2021-44228"],
            "classification": {
                "cve-id": ["CVE-2021-44228"],
                "cvss-score": 10.0,
                "cvss-metrics": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
                "cwe-id": ["CWE-502"]
            }
        },
        "ip": "1.2.3.4",
        "timestamp": "2024-01-01T00:00:00Z",
        "curl-command": "curl -X GET https://example.com/api",
        "matcher-status": True,
        "error-message": ""
    }


@pytest.fixture
def valid_nuclei_array(valid_nuclei_record):
    """A JSON array of Nuclei findings."""
    return [valid_nuclei_record, {
        **valid_nuclei_record,
        "template-id": "CVE-2023-38408",
        "info": {
            **valid_nuclei_record["info"],
            "name": "OpenSSH PKCS#11 Remote Code Execution",
            "severity": "high",
            "classification": {
                "cve-id": ["CVE-2023-38408"],
                "cvss-score": 9.8,
            }
        }
    }]


@pytest.fixture
def valid_nuclei_json(valid_nuclei_array):
    """Valid Nuclei JSON string."""
    return json.dumps(valid_nuclei_array)


@pytest.fixture
def valid_nuclei_jsonl(valid_nuclei_array):
    """Valid Nuclei JSONL string."""
    return "\n".join(json.dumps(record) for record in valid_nuclei_array)


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestNucleiParserValidInput:
    """Test parsing of valid Nuclei data."""

    def test_parse_json_array(self, valid_nuclei_json):
        """Parse a JSON array of findings."""
        parser = NucleiParser()
        findings = parser.parse(valid_nuclei_json)
        assert len(findings) == 2

    def test_parse_jsonl(self, valid_nuclei_jsonl):
        """Parse JSONL format."""
        parser = NucleiParser()
        findings = parser.parse(valid_nuclei_jsonl)
        assert len(findings) == 2

    def test_parse_single_record(self, valid_nuclei_record):
        """Parse a single JSON object."""
        parser = NucleiParser()
        findings = parser.parse(json.dumps(valid_nuclei_record))
        assert len(findings) == 1

    def test_extract_template_id(self, valid_nuclei_json):
        """Template ID is correctly extracted."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert findings[0].template_id == "CVE-2021-44228"

    def test_extract_severity(self, valid_nuclei_json):
        """Severity is correctly extracted."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert findings[0].severity == "critical"

    def test_extract_name(self, valid_nuclei_json):
        """Name is correctly extracted."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert findings[0].name == "Apache Log4j2 Remote Code Execution"

    def test_extract_cve_ids(self, valid_nuclei_json):
        """CVE IDs are correctly extracted."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert "CVE-2021-44228" in findings[0].cve_ids

    def test_extract_cvss_score(self, valid_nuclei_json):
        """CVSS score is correctly extracted."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert findings[0].cvss_score == 10.0

    def test_extract_target(self, valid_nuclei_json):
        """Target is correctly extracted (matched-at takes precedence)."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert findings[0].target == "https://example.com/api"

    def test_extract_tags(self, valid_nuclei_json):
        """Tags are correctly extracted."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert "cve" in findings[0].tags
        assert "log4j" in findings[0].tags

    def test_extract_references(self, valid_nuclei_json):
        """References are correctly extracted."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert len(findings[0].references) > 0

    def test_extract_type(self, valid_nuclei_json):
        """Type is correctly extracted."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert findings[0].type == "http"

    def test_extract_ip(self, valid_nuclei_json):
        """IP is correctly extracted."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert findings[0].ip == "1.2.3.4"

    def test_extract_timestamp(self, valid_nuclei_json):
        """Timestamp is correctly extracted."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert findings[0].timestamp == "2024-01-01T00:00:00Z"

    def test_extract_matcher_status(self, valid_nuclei_json):
        """Matcher status is correctly extracted."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert findings[0].matcher_status is True

    def test_raw_preserved(self, valid_nuclei_json):
        """Raw record is preserved."""
        findings = parse_nuclei_json(valid_nuclei_json)
        assert findings[0].raw is not None
        assert findings[0].raw["template-id"] == "CVE-2021-44228"


class TestNucleiParserMalformedInput:
    """Test handling of malformed input."""

    def test_empty_string(self):
        """Empty string returns empty list."""
        parser = NucleiParser()
        findings = parser.parse("")
        assert findings == []

    def test_none_raises_error(self):
        """None input raises ValueError."""
        parser = NucleiParser()
        with pytest.raises(ValueError):
            parser.parse(None)

    def test_malformed_json(self):
        """Malformed JSON returns empty list with error tracked."""
        parser = NucleiParser()
        findings = parser.parse("{invalid json")
        assert findings == []
        assert len(parser.errors) > 0

    def test_malformed_record_skipped(self):
        """Malformed individual records are skipped."""
        data = json.dumps([
            {"template-id": "valid", "info": {"name": "Valid", "severity": "high"}},
            "not a dict",
            {"template-id": "also-valid", "info": {"name": "Also Valid"}},
        ])
        parser = NucleiParser()
        findings = parser.parse(data)
        assert len(findings) == 2
        assert len(parser.warnings) > 0

    def test_missing_optional_fields(self):
        """Missing optional fields are safely defaulted."""
        data = json.dumps([{"template-id": "minimal"}])
        findings = parse_nuclei_json(data)
        assert len(findings) == 1
        assert findings[0].template_id == "minimal"
        assert findings[0].severity == "unknown"
        assert findings[0].name == "Unknown Finding"


class TestNucleiParserEdgeCases:
    """Test edge cases."""

    def test_empty_array(self):
        """Empty JSON array returns empty list."""
        findings = parse_nuclei_json("[]")
        assert findings == []

    def test_jsonl_with_empty_lines(self):
        """JSONL with empty lines is handled."""
        data = '{"template-id": "a"}\n\n{"template-id": "b"}\n'
        findings = parse_nuclei_jsonl(data)
        assert len(findings) == 2

    def test_severity_rank(self):
        """Severity rank is correctly computed."""
        finding = NucleiFinding(severity="critical")
        assert finding.severity_rank == 4

    def test_is_valid(self):
        """is_valid returns True for valid findings."""
        finding = NucleiFinding(template_id="CVE-2021-44228")
        assert finding.is_valid() is True

    def test_is_valid_false_for_unknown(self):
        """is_valid returns False for UNKNOWN template_id."""
        finding = NucleiFinding()
        assert finding.is_valid() is False

    def test_to_dict(self):
        """to_dict returns correct structure."""
        finding = NucleiFinding(template_id="test", name="Test", severity="high")
        d = finding.to_dict()
        assert d["template_id"] == "test"
        assert d["name"] == "Test"
        assert d["severity"] == "high"
