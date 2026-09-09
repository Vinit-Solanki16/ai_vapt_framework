"""Nuclei JSON/JSONL parser.

Parses Nuclei scanner output (JSON or JSONL) into a normalized intermediate
representation (NucleiFinding). This parser is read-only — it does NOT execute
Nuclei, contact targets, or perform any scanning.

Nuclei output format reference:
  https://github.com/projectdiscovery/nuclei

Typical Nuclei JSON record:
{
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
        "description": "...",
        "reference": ["https://..."],
        "classification": {
            "cve-id": ["CVE-2021-44228"],
            "cvss-score": 10.0,
            "cvss-metrics": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
            "cwe-id": ["CWE-502"]
        }
    },
    "ip": "1.2.3.4",
    "timestamp": "2024-01-01T00:00:00Z",
    "curl-command": "curl ...",
    "matcher-status": true,
    "error-message": ""
}

Normalized output (NucleiFinding):
    template_id: str
    name: str
    severity: str
    type: str
    host: str
    target: str
    ip: str
    matched_at: str
    matcher_name: str
    extracted_results: list[str]
    tags: list[str]
    description: str
    references: list[str]
    cve_ids: list[str]
    cvss_score: float | None
    cvss_metrics: str | None
    cwe_ids: list[str]
    timestamp: str | None
    curl_command: str | None
    matcher_status: bool
    error_message: str | None
    raw: dict  # original record for forward compatibility
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional


# Severity levels in order of increasing severity
SEVERITY_LEVELS = ["info", "low", "medium", "high", "critical", "unknown"]

# Default severity when not specified
DEFAULT_SEVERITY = "unknown"


@dataclass
class NucleiFinding:
    """Normalized intermediate representation of a single Nuclei finding.

    This structure is designed to be compatible with the future normalization
    layer and convertible to ActionCandidate via the scan adapter.

    Fields:
        template_id: Nuclei template identifier (e.g., "CVE-2021-44228")
        name: Human-readable finding name from info.name
        severity: Severity level (info/low/medium/high/critical/unknown)
        type: Finding type (http/dns/tcp/ssl/etc.)
        host: The host URL/IP from the finding
        target: The matched target URL (falls back to host if not present)
        ip: Resolved IP address (if available)
        matched_at: The URL/path where the match occurred
        matcher_name: Name of the matcher that triggered
        extracted_results: List of extracted result strings
        tags: List of tags associated with the template
        description: Finding description
        references: List of reference URLs
        cve_ids: List of CVE identifiers
        cvss_score: CVSS base score (0.0-10.0)
        cvss_metrics: CVSS vector string
        cwe_ids: List of CWE identifiers
        timestamp: ISO 8601 timestamp of the finding
        curl_command: Reproducible curl command (if available)
        matcher_status: Whether the matcher matched
        error_message: Error message (if any)
        raw: The original raw record dict for forward compatibility
    """

    template_id: str = "UNKNOWN"
    name: str = "Unknown Finding"
    severity: str = DEFAULT_SEVERITY
    type: str = "unknown"
    host: str = ""
    target: str = ""
    ip: str = ""
    matched_at: str = ""
    matcher_name: str = ""
    extracted_results: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str = ""
    references: list[str] = field(default_factory=list)
    cve_ids: list[str] = field(default_factory=list)
    cvss_score: Optional[float] = None
    cvss_metrics: Optional[str] = None
    cwe_ids: list[str] = field(default_factory=list)
    timestamp: Optional[str] = None
    curl_command: Optional[str] = None
    matcher_status: bool = False
    error_message: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "template_id": self.template_id,
            "name": self.name,
            "severity": self.severity,
            "type": self.type,
            "host": self.host,
            "target": self.target,
            "ip": self.ip,
            "matched_at": self.matched_at,
            "matcher_name": self.matcher_name,
            "extracted_results": self.extracted_results,
            "tags": self.tags,
            "description": self.description,
            "references": self.references,
            "cve_ids": self.cve_ids,
            "cvss_score": self.cvss_score,
            "cvss_metrics": self.cvss_metrics,
            "cwe_ids": self.cwe_ids,
            "timestamp": self.timestamp,
            "curl_command": self.curl_command,
            "matcher_status": self.matcher_status,
            "error_message": self.error_message,
        }

    @property
    def severity_rank(self) -> int:
        """Numeric rank for severity comparison (higher = more severe)."""
        try:
            return SEVERITY_LEVELS.index(self.severity.lower())
        except ValueError:
            return SEVERITY_LEVELS.index("unknown")

    def is_valid(self) -> bool:
        """Check if the finding has minimum required fields populated."""
        return bool(self.template_id and self.template_id != "UNKNOWN")


class NucleiParser:
    """Parser for Nuclei JSON/JSONL output.

    This parser handles:
    - Single JSON array of findings
    - JSONL (one finding per line)
    - Single finding as a JSON object
    - Malformed records (skipped with error tracking)
    - Missing optional fields (safely defaulted)

    Usage:
        parser = NucleiParser()
        findings = parser.parse(json_string)
        findings = parser.parse_file(file_path)
    """

    def __init__(self) -> None:
        """Initialize the parser."""
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def parse(self, data: str) -> list[NucleiFinding]:
        """Parse Nuclei JSON or JSONL data.

        Args:
            data: JSON string (array or single object) or JSONL (one JSON per line)

        Returns:
            List of normalized NucleiFinding objects

        Raises:
            ValueError: If data is None
        """
        self.errors = []
        self.warnings = []

        if data is None:
            raise ValueError("Input data cannot be None")

        data = data.strip()
        if not data:
            return []

        # Try parsing as JSON array or single object first
        try:
            parsed = json.loads(data)
            if isinstance(parsed, list):
                return self._parse_records(parsed)
            elif isinstance(parsed, dict):
                return self._parse_records([parsed])
            else:
                self.errors.append(f"Unexpected JSON type: {type(parsed).__name__}")
                return []
        except json.JSONDecodeError:
            pass

        # Try JSONL format (one JSON object per line)
        return self._parse_jsonl(data)

    def parse_file(self, file_path: str) -> list[NucleiFinding]:
        """Parse a Nuclei JSON/JSONL file.

        Args:
            file_path: Path to the Nuclei output file

        Returns:
            List of normalized NucleiFinding objects

        Raises:
            FileNotFoundError: If file does not exist
            PermissionError: If file cannot be read
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = f.read()

        return self.parse(data)

    def _parse_jsonl(self, data: str) -> list[NucleiFinding]:
        """Parse JSONL format (one JSON object per line)."""
        findings = []
        lines = data.strip().split("\n")

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
                if isinstance(record, dict):
                    finding = self._normalize_record(record)
                    if finding.is_valid():
                        findings.append(finding)
                    else:
                        self.warnings.append(
                            f"Line {line_num}: Record skipped (missing template-id)"
                        )
                else:
                    self.warnings.append(
                        f"Line {line_num}: Expected object, got {type(record).__name__}"
                    )
            except json.JSONDecodeError as e:
                self.errors.append(f"Line {line_num}: Invalid JSON - {e}")
                continue

        return findings

    def _parse_records(self, records: list[dict]) -> list[NucleiFinding]:
        """Parse a list of record dicts."""
        findings = []

        for idx, record in enumerate(records):
            if not isinstance(record, dict):
                self.warnings.append(
                    f"Record {idx}: Expected object, got {type(record).__name__}"
                )
                continue

            finding = self._normalize_record(record)
            if finding.is_valid():
                findings.append(finding)
            else:
                self.warnings.append(
                    f"Record {idx}: Skipped (missing template-id)"
                )

        return findings

    def _normalize_record(self, record: dict[str, Any]) -> NucleiFinding:
        """Normalize a single Nuclei record into a NucleiFinding.

        Safely extracts all fields, handling missing or malformed data.
        """
        info = record.get("info") or {}
        if not isinstance(info, dict):
            info = {}

        classification = info.get("classification") or {}
        if not isinstance(classification, dict):
            classification = {}

        # Extract CVE IDs from classification or template-id
        cve_ids = []
        raw_cves = classification.get("cve-id", [])
        if isinstance(raw_cves, list):
            cve_ids = [str(c) for c in raw_cves if c]
        elif raw_cves:
            cve_ids = [str(raw_cves)]

        # Also check template-id for CVE references
        template_id = record.get("template-id", "")
        if template_id and "CVE-" in template_id.upper():
            cve_str = template_id.upper()
            if cve_str not in [c.upper() for c in cve_ids]:
                cve_ids.append(template_id)

        # Extract CWE IDs
        cwe_ids = []
        raw_cwes = classification.get("cwe-id", [])
        if isinstance(raw_cwes, list):
            cwe_ids = [str(c) for c in raw_cwes if c]
        elif raw_cwes:
            cwe_ids = [str(raw_cwes)]

        # Extract CVSS score
        cvss_score = classification.get("cvss-score")
        try:
            cvss_score = float(cvss_score) if cvss_score is not None else None
        except (ValueError, TypeError):
            cvss_score = None

        # Extract references
        references = info.get("reference", [])
        if isinstance(references, list):
            references = [str(r) for r in references if r]
        elif references:
            references = [str(references)]
        else:
            references = []

        # Extract tags
        tags = info.get("tags", [])
        if isinstance(tags, list):
            tags = [str(t) for t in tags]
        elif tags:
            tags = [str(tags)]
        else:
            tags = []

        # Extract extracted-results
        extracted = record.get("extracted-results", [])
        if isinstance(extracted, list):
            extracted = [str(e) for e in extracted]
        elif extracted:
            extracted = [str(extracted)]
        else:
            extracted = []

        # Determine target (matched-at takes precedence over host)
        host = record.get("host", "")
        matched_at = record.get("matched-at", "")
        target = matched_at or host

        # Normalize severity
        severity = info.get("severity", DEFAULT_SEVERITY)
        if not isinstance(severity, str):
            severity = DEFAULT_SEVERITY
        severity = severity.lower()

        return NucleiFinding(
            template_id=str(template_id) if template_id else "UNKNOWN",
            name=str(info.get("name", "Unknown Finding")),
            severity=severity,
            type=str(record.get("type", "unknown")),
            host=str(host) if host else "",
            target=str(target),
            ip=str(record.get("ip", "")) if record.get("ip") else "",
            matched_at=str(matched_at) if matched_at else "",
            matcher_name=str(record.get("matcher-name", "")),
            extracted_results=extracted,
            tags=tags,
            description=str(info.get("description", "")),
            references=references,
            cve_ids=cve_ids,
            cvss_score=cvss_score,
            cvss_metrics=str(classification.get("cvss-metrics", "")) if classification.get("cvss-metrics") else None,
            cwe_ids=cwe_ids,
            timestamp=str(record.get("timestamp", "")) if record.get("timestamp") else None,
            curl_command=str(record.get("curl-command", "")) if record.get("curl-command") else None,
            matcher_status=bool(record.get("matcher-status", False)),
            error_message=str(record.get("error-message", "")) if record.get("error-message") else None,
            raw=record,
        )


def parse_nuclei_json(data: str) -> list[NucleiFinding]:
    """Convenience function to parse Nuclei JSON/JSONL data.

    Args:
        data: JSON string (array or single object) or JSONL

    Returns:
        List of normalized NucleiFinding objects
    """
    parser = NucleiParser()
    return parser.parse(data)


def parse_nuclei_jsonl(data: str) -> list[NucleiFinding]:
    """Convenience function to parse Nuclei JSONL data.

    Args:
        data: JSONL string (one JSON object per line)

    Returns:
        List of normalized NucleiFinding objects
    """
    parser = NucleiParser()
    return parser._parse_jsonl(data)