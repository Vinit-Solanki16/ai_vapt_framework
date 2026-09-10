"""Canonical finding normalization layer.

This module provides a platform-level boundary between scanner-specific
output formats and downstream VAPT decision processing.

It does NOT modify the research engine. It provides a clean adapter
between scanner outputs and the existing candidate generation pipeline.

Architecture:
    Nmap XML/JSON/Custom ──> parser-specific structures ──> CanonicalFinding
    Nuclei JSON ──────────> NucleiFinding ───────────────> CanonicalFinding
                                                      │
                                                      v
                                              Candidate Generation
                                                      │
                                                      v
                                              Decision Engine
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Severity normalization
# ---------------------------------------------------------------------------

SEVERITY_MAP = {
    # Standard levels
    "info": "informational",
    "informational": "informational",
    "low": "low",
    "medium": "medium",
    "moderate": "medium",
    "high": "high",
    "critical": "critical",
    "severe": "critical",
    "important": "high",
    "unknown": "unknown",
    # Numeric mappings
    "0": "informational",
    "1": "low",
    "2": "medium",
    "3": "high",
    "4": "critical",
}

SEVERITY_ORDER = ["informational", "low", "medium", "high", "critical", "unknown"]


def normalize_severity(severity: Any) -> str:
    """Normalize any severity representation to canonical form."""
    if severity is None:
        return "unknown"
    s = str(severity).strip().lower()
    if s in SEVERITY_MAP:
        return SEVERITY_MAP[s]
    # Try numeric
    try:
        num = float(s)
        if num >= 9.0:
            return "critical"
        elif num >= 7.0:
            return "high"
        elif num >= 4.0:
            return "medium"
        elif num > 0:
            return "low"
        else:
            return "informational"
    except (ValueError, TypeError):
        return "unknown"


# ---------------------------------------------------------------------------
# Canonical Finding
# ---------------------------------------------------------------------------

@dataclass
class CanonicalFinding:
    """A normalized, scanner-agnostic finding representation.

    This is the single canonical format that all scanner outputs converge to
    before candidate generation.

    Fields:
        finding_id: Stable deterministic identity for deduplication
        source: Scanner/parser that produced this finding (e.g., "nmap", "nuclei")
        target: The primary target (host URL/IP)
        host: The hostname or IP
        port: TCP/UDP port number (0 if not applicable)
        protocol: Transport protocol (tcp/udp)
        title: Short finding name/title
        severity: Normalized severity (informational/low/medium/high/critical/unknown)
        rule_id: Scanner-specific rule/template identifier
        description: Detailed description
        evidence: Evidence or reference strings
        tags: Classification tags
        metadata: Scanner-specific data preserved for downstream use
    """
    finding_id: str = ""
    source: str = "unknown"
    target: str = ""
    host: str = ""
    port: int = 0
    protocol: str = "tcp"
    title: str = ""
    severity: str = "unknown"
    rule_id: str = ""
    description: str = ""
    evidence: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_finding_id(self) -> str:
        """Compute a deterministic identity for deduplication."""
        parts = [
            self.source,
            self.host,
            str(self.port),
            self.protocol,
            self.rule_id,
            self.target,
        ]
        key = "|".join(p.strip().lower() for p in parts)
        return hashlib.sha256(key.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Source-specific mappers
# ---------------------------------------------------------------------------

def from_nmap_xml_dict(d: dict[str, Any]) -> CanonicalFinding:
    """Convert Nmap XML parser output dict to CanonicalFinding."""
    port = d.get("port", 0)
    try:
        port = int(port) if port else 0
    except (ValueError, TypeError):
        port = 0

    cpe_list = d.get("cpe", []) or []
    if isinstance(cpe_list, str):
        cpe_list = [cpe_list]

    return CanonicalFinding(
        source="nmap-xml",
        host=d.get("host", "unknown"),
        target=d.get("host", "unknown"),
        port=port,
        protocol="tcp",
        title=d.get("service") or d.get("description") or "open port",
        severity="unknown",
        rule_id=f"port-{port}" if port else "unknown",
        description=d.get("description") or "",
        evidence=cpe_list,
        tags=["nmap", "port-scan"] + ([d["service"]] if d.get("service") else []),
        metadata={
            "service": d.get("service"),
            "product": d.get("product") or d.get("description", "").split()[0] if d.get("description") else None,
            "cpe": cpe_list,
        },
    )


def from_nmap_json_dict(d: dict[str, Any]) -> CanonicalFinding:
    """Convert Nmap JSON parser output dict to CanonicalFinding."""
    port = d.get("port", 0)
    try:
        port = int(port) if port else 0
    except (ValueError, TypeError):
        port = 0

    cve = d.get("cve")
    rule_id = cve if cve and cve != "UNKNOWN-CVE" else f"port-{port}"

    return CanonicalFinding(
        source="nmap-json",
        host=d.get("host", "unknown"),
        target=d.get("host", "unknown"),
        port=port,
        protocol="tcp",
        title=d.get("service") or d.get("description") or "open port",
        severity="unknown",
        rule_id=rule_id,
        description=d.get("description") or "",
        evidence=[cve] if cve and cve != "UNKNOWN-CVE" else [],
        tags=["nmap", "port-scan"] + ([d["service"]] if d.get("service") else []),
        metadata={
            "service": d.get("service"),
            "cve": cve,
        },
    )


def from_custom_json_dict(d: dict[str, Any]) -> CanonicalFinding:
    """Convert custom JSON parser output dict to CanonicalFinding."""
    port = d.get("port", 0)
    try:
        port = int(port) if port else 0
    except (ValueError, TypeError):
        port = 0

    cve = d.get("cve")
    rule_id = cve if cve and cve not in ("", "UNKNOWN-CVE") else f"port-{port}"

    return CanonicalFinding(
        source="custom",
        host=d.get("host", "unknown"),
        target=d.get("host", "unknown"),
        port=port,
        protocol="tcp",
        title=d.get("service") or d.get("description") or "finding",
        severity="unknown",
        rule_id=rule_id,
        description=d.get("description") or "",
        evidence=[cve] if cve and cve not in ("", "UNKNOWN-CVE") else [],
        tags=["custom"] + ([d.get("service")] if d.get("service") else []),
        metadata={
            "service": d.get("service"),
            "cve": cve,
        },
    )


def from_nuclei_finding(f: Any) -> CanonicalFinding:
    """Convert NucleiFinding to CanonicalFinding."""
    # Determine port from target URL
    port = 0
    if f.target:
        try:
            parsed = urlparse(f.target)
            if parsed.port:
                port = parsed.port
            elif parsed.scheme == "https":
                port = 443
            elif parsed.scheme == "http":
                port = 80
        except Exception:
            pass

    # Build evidence list
    evidence = list(f.extracted_results) if f.extracted_results else []
    if f.references:
        evidence.extend(f.references[:3])  # Limit references

    return CanonicalFinding(
        source="nuclei",
        host=f.host or f.ip or "unknown",
        target=f.target or f.host or "unknown",
        port=port,
        protocol="tcp",
        title=f.name or f.template_id,
        severity=normalize_severity(f.severity),
        rule_id=f.template_id or "unknown",
        description=f.description or "",
        evidence=evidence,
        tags=list(f.tags) if f.tags else [],
        metadata={
            "template_id": f.template_id,
            "info": f.info if hasattr(f, "info") else {},
            "cvss_score": f.cvss_score,
            "cvss_metrics": f.cvss_metrics,
            "cve_ids": f.cve_ids,
            "cwe_ids": f.cwe_ids,
            "ip": f.ip,
            "timestamp": f.timestamp,
            "curl_command": f.curl_command,
            "matcher_status": f.matcher_status,
        },
    )


# ---------------------------------------------------------------------------
# Batch normalization
# ---------------------------------------------------------------------------

def normalize_nmap_findings(findings: list[dict[str, Any]], format: str = "xml") -> list[CanonicalFinding]:
    """Normalize a list of Nmap finding dicts."""
    mapper = from_nmap_xml_dict if format == "xml" else from_nmap_json_dict
    return [mapper(f) for f in findings]


def normalize_custom_findings(findings: list[dict[str, Any]]) -> list[CanonicalFinding]:
    """Normalize a list of custom JSON finding dicts."""
    return [from_custom_json_dict(f) for f in findings]


def normalize_nuclei_findings(findings: list[Any]) -> list[CanonicalFinding]:
    """Normalize a list of NucleiFinding objects."""
    return [from_nuclei_finding(f) for f in findings]


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate(findings: list[CanonicalFinding]) -> list[CanonicalFinding]:
    """Deduplicate findings by deterministic identity."""
    seen: dict[str, CanonicalFinding] = {}
    for f in findings:
        fid = f.compute_finding_id()
        if fid not in seen:
            seen[fid] = f
        else:
            # Merge evidence from duplicate
            existing = seen[fid]
            for ev in f.evidence:
                if ev not in existing.evidence:
                    existing.evidence.append(ev)
            for tag in f.tags:
                if tag not in existing.tags:
                    existing.tags.append(tag)
    return list(seen.values())


# ---------------------------------------------------------------------------
# Severity utilities
# ---------------------------------------------------------------------------

def severity_rank(severity: str) -> int:
    """Return numeric rank for severity comparison (higher = more severe)."""
    try:
        return SEVERITY_ORDER.index(severity.lower())
    except ValueError:
        return SEVERITY_ORDER.index("unknown")


def highest_severity(a: str, b: str) -> str:
    """Return the more severe of two severity levels."""
    return a if severity_rank(a) >= severity_rank(b) else b
