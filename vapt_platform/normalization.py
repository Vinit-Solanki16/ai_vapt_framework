"""Platform-level canonical finding normalization layer.

This module provides a stable, scanner-independent representation of security
findings that different scanner output formats converge into BEFORE candidate
generation.

Target architecture:

    Nmap XML          Nmap JSON          Nuclei JSON          Custom scan input
         │                   │                   │                   │
         ▼                   ▼                   ▼                   ▼
    Parser-specific structures
         │
         ▼
    CANONICAL NORMALIZATION  (this module)
         │
         ▼
    CanonicalFinding[]
         │
         ▼
    canonical_to_candidates()  (bridge to the existing candidate bridge)
         │
         ▼
    ActionCandidate[]
         │
         ▼
    Existing research decision engine
         │
         ▼
    Execution / Pivot / Report

The normalization layer is PLATFORM ENGINEERING. It does not modify any
research-protected schema (decision_engine/core/schemas.py,
decision_engine/adapters/scan_adapter.py, core/scanner.py).

Architecture:
    Parser-specific structures (dicts from core.scanner, NucleiFinding from
    vapt_platform.parsers.nuclei_parser)
        ↓
    CANONICAL NORMALIZATION (this module)
        ↓
    CanonicalFinding[] (platform-level canonical representation)
        ↓
    canonical_to_candidates() (bridge)
        ↓
    ActionCandidate[] (decision_engine.core.schemas)
        ↓
    Existing research decision engine
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from decision_engine.core.schemas import ActionCandidate
from vapt_platform.parsers.nuclei_parser import NucleiFinding


# ---------------------------------------------------------------------------
# Severity normalization
# ---------------------------------------------------------------------------

# Standard severity levels in order of increasing severity
SEVERITY_LEVELS = ["unknown", "info", "low", "medium", "high", "critical"]
DEFAULT_SEVERITY = "unknown"

# Map CVSS qualitative ratings to canonical severity
CVSS_SEVERITY_MAP = {
    "none": "info",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "critical",
}


def normalize_severity(severity: Optional[str]) -> str:
    """Normalize a severity string to canonical lowercase form.

    Args:
        severity: Raw severity string from a scanner.

    Returns:
        Normalized severity (one of SEVERITY_LEVELS). Unknown if not present
        or not a recognized value.
    """
    if not severity:
        return DEFAULT_SEVERITY
    s = str(severity).strip().lower()
    if s in SEVERITY_LEVELS:
        return s
    if s in CVSS_SEVERITY_MAP:
        return CVSS_SEVERITY_MAP[s]
    return DEFAULT_SEVERITY


def cvss_score_to_severity(score: Optional[float]) -> str:
    """Convert a CVSS base score (0.0-10.0) to canonical severity.

    Uses the CVSS v3.x severity rating ranges:
        0.0: None -> info
        0.1-3.9: Low
        4.0-6.9: Medium
        7.0-8.9: High
        9.0-10.0: Critical
    """
    if score is None:
        return DEFAULT_SEVERITY
    try:
        s = float(score)
    except (ValueError, TypeError):
        return DEFAULT_SEVERITY
    if s == 0.0:
        return "info"
    if s < 4.0:
        return "low"
    if s < 7.0:
        return "medium"
    if s < 9.0:
        return "high"
    return "critical"


# ---------------------------------------------------------------------------
# Canonical finding model
# ---------------------------------------------------------------------------

class CanonicalFinding(BaseModel):
    """Platform-level canonical finding representation.

    This is a deliberately minimal, scanner-agnostic representation. All
    scanner-specific data is preserved in metadata and raw_record.

    Required fields:
        finding_id: Deterministic unique identifier for this finding.
        source: Scanner source ("nmap", "nuclei", "custom").
        target: Primary target URL or IP.
        host: Host IP or hostname.
        port: TCP/UDP port number (None if not applicable).
        protocol: Network protocol ("tcp", "udp", "http", "dns", etc.).
        title: Human-readable finding title.
        severity: Canonical severity level (info/low/medium/high/critical/unknown).

    Optional fields:
        template_or_rule_id: Scanner template/rule identifier (e.g., Nuclei
            template-id, CVE ID, or a derived rule key). Used for
            deduplication and candidate ID derivation.
        description: Detailed description of the finding.
        evidence: List of evidence strings (extracted results, CPEs, references).
        metadata: Scanner-specific metadata that does not fit other fields.
        cve_ids: List of CVE identifiers associated with this finding.
        cvss_score: CVSS base score (0.0-10.0) if available.
        cvss_metrics: CVSS vector string if available.
        cwe_ids: List of CWE identifiers.
        raw_record: Original scanner-specific record for forward compatibility.

    Source-specific fields are preserved in metadata/raw_record and do not
    leak into the decision engine (which only consumes ActionCandidate).
    """

    finding_id: str = Field(..., description="Deterministic unique identifier.")
    source: str = Field(..., description="Scanner source (nmap, nuclei, custom).")
    target: str = Field(..., description="Primary target URL or IP.")
    host: str = Field(..., description="Host IP or hostname.")
    port: Optional[int] = Field(default=None, description="TCP/UDP port number.")
    protocol: str = Field(default="unknown", description="Network protocol.")
    title: str = Field(..., description="Human-readable finding title.")
    severity: str = Field(default=DEFAULT_SEVERITY, description="Canonical severity level.")

    template_or_rule_id: Optional[str] = Field(
        default=None, description="Scanner template/rule identifier or CVE ID."
    )
    description: Optional[str] = Field(default=None, description="Detailed description.")
    evidence: List[str] = Field(
        default_factory=list, description="Evidence strings (results, CPEs, references)."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Scanner-specific metadata."
    )
    cve_ids: List[str] = Field(
        default_factory=list, description="CVE identifiers."
    )
    cvss_score: Optional[float] = Field(
        default=None, description="CVSS base score (0.0-10.0)."
    )
    cvss_metrics: Optional[str] = Field(
        default=None, description="CVSS vector string."
    )
    cwe_ids: List[str] = Field(
        default_factory=list, description="CWE identifiers."
    )
    raw_record: Optional[Dict[str, Any]] = Field(
        default=None, description="Original scanner-specific record."
    )

    @property
    def severity_rank(self) -> int:
        """Numeric rank for severity comparison (higher = more severe)."""
        try:
            return SEVERITY_LEVELS.index(self.severity.lower())
        except ValueError:
            return SEVERITY_LEVELS.index(DEFAULT_SEVERITY)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return self.model_dump()


# ---------------------------------------------------------------------------
# Identity and deduplication
# ---------------------------------------------------------------------------

def asset_identity(finding: CanonicalFinding) -> str:
    """Compute a deterministic asset identity for a canonical finding.

    Identity is based on host + port + protocol. This is the minimal identity
    needed for normalized findings and serves as the foundation for the future
    asset graph.
    """
    port_part = str(finding.port) if finding.port is not None else "any"
    return f"{finding.host}:{port_part}/{finding.protocol}"


def finding_identity(finding: CanonicalFinding) -> str:
    """Compute the deterministic identity key for deduplication.

    Two findings are duplicates when they share the same identity key. The
    identity is composed of:

        source + host + port + protocol + vulnerability/rule identity

    The vulnerability/rule identity is taken from template_or_rule_id when
    available (e.g., a CVE or Nuclei template-id). If no rule identifier is
    present, the first CVE ID is used. If neither exists, a hash of the title
    is used as a fallback so that findings without CVEs can still be
    deduplicated deterministically.

    Note: source is intentionally NOT part of the identity. The purpose of
    normalization is to let different scanner formats converge; a finding
    reported by both Nmap and Nuclei for the same CVE on the same host/port
    should be deduplicated as one canonical finding.
    """
    port_part = str(finding.port) if finding.port is not None else "any"

    # Determine vulnerability/rule identity (most specific available)
    rule_id = finding.template_or_rule_id
    if not rule_id and finding.cve_ids:
        rule_id = finding.cve_ids[0]
    if not rule_id:
        # Fallback: hash of the title (first 12 chars)
        title_hash = hashlib.sha256(finding.title.encode()).hexdigest()[:12]
        rule_id = f"hash-{title_hash}"

    return f"{finding.host}:{port_part}/{finding.protocol}|{rule_id}"


def deduplicate(findings: List[CanonicalFinding]) -> List[CanonicalFinding]:
    """Deterministically deduplicate canonical findings.

    Two findings are duplicates when finding_identity(finding) matches.

    When duplicates are found, information is MERGED rather than discarded:
      - the first occurrence's core fields are kept
      - evidence from later occurrences is appended (duplicates removed)
      - metadata from later occurrences is merged (later values win)
      - cve_ids and cwe_ids are unioned
      - severity is upgraded to the most severe value
      - cvss_score is upgraded to the highest value

    Args:
        findings: List of CanonicalFinding objects.

    Returns:
        Deduplicated list of CanonicalFinding objects in deterministic order
        (order of first occurrence).
    """
    seen: Dict[str, CanonicalFinding] = {}
    for f in findings:
        key = finding_identity(f)
        if key in seen:
            existing = seen[key]
            # Merge evidence (dedupe within the merged list)
            for ev in f.evidence:
                if ev not in existing.evidence:
                    existing.evidence.append(ev)
            # Merge metadata (later values win)
            existing.metadata.update(f.metadata)
            # Union CVEs and CWEs
            for cve in f.cve_ids:
                if cve not in existing.cve_ids:
                    existing.cve_ids.append(cve)
            for cwe in f.cwe_ids:
                if cwe not in existing.cwe_ids:
                    existing.cwe_ids.append(cwe)
            # Upgrade severity to the most severe value
            if f.severity_rank > existing.severity_rank:
                existing.severity = f.severity
            # Upgrade CVSS score to the highest value
            if f.cvss_score is not None and (
                existing.cvss_score is None or f.cvss_score > existing.cvss_score
            ):
                existing.cvss_score = f.cvss_score
        else:
            seen[key] = f
    return list(seen.values())


# ---------------------------------------------------------------------------
# Normalization functions (mapping rules)
# ---------------------------------------------------------------------------

def _as_int(value: Any) -> Optional[int]:
    """Safely convert a value to an integer, returning None on failure."""
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _as_list(value: Any) -> List[str]:
    """Safely convert a value to a list of strings."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)]


def _build_title(service: str, description: str) -> str:
    """Build a human-readable title from service and description."""
    if description:
        return description
    if service:
        return service
    return "Open port"


def _build_evidence(cpe: Any) -> List[str]:
    """Build an evidence list from CPE data."""
    return _as_list(cpe)


def _build_metadata(service: str, description: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build metadata dict for Nmap/custom findings."""
    metadata = {
        "service": service,
        "raw_description": description,
    }
    if extra:
        metadata.update(extra)
    return metadata


# ---------------------------------------------------------------------------
# Nmap normalization
# ---------------------------------------------------------------------------

def normalize_nmap_findings(raw_findings: List[Dict[str, Any]]) -> List[CanonicalFinding]:
    """Normalize Nmap parser output into CanonicalFinding objects.

    Accepts the raw dict structures produced by core.scanner.parse_nmap_xml()
    and core.scanner.parse_nmap_json():

        {"host": "192.168.1.10", "port": 22, "service": "ssh",
         "description": "OpenSSH 8.9p1", "cpe": [...], "cve": "CVE-..."}

    Mapping rules (Nmap -> CanonicalFinding):
        host          -> host + target
        port          -> port
        protocol      -> "tcp" (Nmap scan protocol; UDP not represented in
                        the current parser)
        service       -> metadata["service"] + title fallback
        description   -> description + title fallback
        cpe           -> evidence + metadata["cpe"]
        cve           -> template_or_rule_id + cve_ids
        severity      -> "unknown" (Nmap does not emit severity)
        source        -> "nmap"
    """
    results = []
    for item in raw_findings:
        host = str(item.get("host") or "unknown")
        port = _as_int(item.get("port"))
        service = str(item.get("service") or "")
        description = str(item.get("description") or "")
        cve = str(item.get("cve")) if item.get("cve") else None
        cpe = _as_list(item.get("cpe"))

        title = _build_title(service, description)
        evidence = _build_evidence(cpe)

        finding = CanonicalFinding(
            finding_id=f"nmap|{host}:{port or 'any'}/tcp|{cve or 'none'}",
            source="nmap",
            target=host,
            host=host,
            port=port,
            protocol="tcp",
            title=title,
            severity=DEFAULT_SEVERITY,
            template_or_rule_id=cve,
            description=description or None,
            evidence=evidence,
            metadata=_build_metadata(service, description, {"cpe": cpe}),
            cve_ids=[cve] if cve else [],
            raw_record=item,
        )
        results.append(finding)
    return results


# ---------------------------------------------------------------------------
# Nuclei normalization
# ---------------------------------------------------------------------------

def normalize_nuclei_findings(nuclei_findings: List[NucleiFinding]) -> List[CanonicalFinding]:
    """Normalize Nuclei parser output into CanonicalFinding objects.

    Accepts the NucleiFinding dataclass objects produced by
    vapt_platform.parsers.nuclei_parser.NucleiParser.

    Mapping rules (Nuclei -> CanonicalFinding):
        template-id   -> template_or_rule_id + cve_ids (from classification)
        info.name     -> title
        info.severity -> severity (already lowercase by the parser)
        type          -> protocol
        host          -> host
        matched-at    -> target (takes precedence over host)
        description   -> description
        reference     -> evidence
        extracted-results -> evidence
        ip            -> metadata["ip"]
        cvss-*        -> cvss_score / cvss_metrics + metadata
        cwe-id        -> cwe_ids + metadata
        curl-command  -> evidence
        timestamp     -> metadata["timestamp"]
        source        -> "nuclei"
    """
    results = []
    for nf in nuclei_findings:
        host = nf.host or nf.ip or "unknown"
        target = nf.target or nf.host or "unknown"

        # Extract port from URL when possible
        port = None
        if target:
            try:
                from urllib.parse import urlparse

                parsed = urlparse(target)
                if parsed.port:
                    port = parsed.port
                elif nf.type == "http" and target.startswith("https://"):
                    port = 443
                elif nf.type == "http" and target.startswith("http://"):
                    port = 80
            except (ValueError, TypeError):
                port = None

        protocol = str(nf.type or "unknown")
        evidence = _as_list(nf.extracted_results)
        if nf.references:
            evidence.extend(_as_list(nf.references))
        if nf.curl_command:
            evidence.append(f"curl: {nf.curl_command}")

        metadata: Dict[str, Any] = {
            "matched_at": nf.matched_at,
            "matcher_name": nf.matcher_name,
            "tags": list(nf.tags),
            "type": nf.type,
            "ip": nf.ip,
            "timestamp": nf.timestamp,
            "matcher_status": nf.matcher_status,
        }
        if nf.error_message:
            metadata["error_message"] = nf.error_message

        finding = CanonicalFinding(
            finding_id=f"nuclei|{host}:{port or 'any'}/{protocol}|{nf.template_id}",
            source="nuclei",
            target=target,
            host=host,
            port=port,
            protocol=protocol,
            title=nf.name,
            severity=nf.severity,
            template_or_rule_id=nf.template_id,
            description=nf.description or None,
            evidence=evidence,
            metadata=metadata,
            cve_ids=list(nf.cve_ids) if nf.cve_ids else [],
            cvss_score=nf.cvss_score,
            cvss_metrics=nf.cvss_metrics,
            cwe_ids=list(nf.cwe_ids) if nf.cwe_ids else [],
            raw_record=nf.raw,
        )
        results.append(finding)
    return results


# ---------------------------------------------------------------------------
# Custom normalization
# ---------------------------------------------------------------------------

def normalize_custom_findings(raw_findings: List[Dict[str, Any]]) -> List[CanonicalFinding]:
    """Normalize custom JSON parser output into CanonicalFinding objects.

    Accepts the raw dict structures produced by core.scanner.parse_custom_json():

        {"host": "10.0.0.0/24", "port": 22, "service": "ssh",
         "cve": "CVE-2023-38408", "description": "OpenSSH PKCS#11 RCE"}

    Mapping rules (Custom -> CanonicalFinding):
        target (top-level, inherited as host) -> host + target
        port          -> port
        protocol      -> "tcp" (custom schema does not specify protocol)
        service       -> metadata["service"] + title fallback
        description   -> description + title fallback
        cve           -> template_or_rule_id + cve_ids
        severity      -> "unknown" (custom schema does not emit severity)
        source        -> "custom"
    """
    results = []
    for item in raw_findings:
        host = str(item.get("host") or "unknown")
        port = _as_int(item.get("port"))
        service = str(item.get("service") or "")
        description = str(item.get("description") or "")
        cve = str(item.get("cve")) if item.get("cve") else None

        title = _build_title(service, description)

        finding = CanonicalFinding(
            finding_id=f"custom|{host}:{port or 'any'}/tcp|{cve or 'none'}",
            source="custom",
            target=host,
            host=host,
            port=port,
            protocol="tcp",
            title=title,
            severity=DEFAULT_SEVERITY,
            template_or_rule_id=cve,
            description=description or None,
            metadata=_build_metadata(service, description),
            cve_ids=[cve] if cve else [],
            raw_record=item,
        )
        results.append(finding)
    return results


# ---------------------------------------------------------------------------
# Bridge to ActionCandidate (existing candidate bridge)
# ---------------------------------------------------------------------------

def canonical_to_candidates(findings: List[CanonicalFinding]) -> List[ActionCandidate]:
    """Convert canonical findings into engine ActionCandidates.

    This is the bridge between the platform-level normalization layer and the
    existing research-protected candidate bridge. The mapping mirrors
    decision_engine.adapters.scan_adapter.findings_to_candidates():

        id      = first CVE in cve_ids, else template_or_rule_id, else finding_id
        probability = 0.0 (EPSS enrichment happens AFTER normalization)
        quality_rank = None (to be filled by the assessor)
        ground_truth = None (no simulation label)

    Args:
        findings: List of CanonicalFinding objects.

    Returns:
        List of ActionCandidate objects ready for run_engine().
    """
    candidates = []
    for f in findings:
        if f.cve_ids:
            cid = f.cve_ids[0]
        elif f.template_or_rule_id:
            cid = f.template_or_rule_id
        else:
            cid = f.finding_id
        candidates.append(
            ActionCandidate(
                id=cid,
                probability=0.0,
                quality_rank=None,
                ground_truth=None,
            )
        )
    return candidates


# ---------------------------------------------------------------------------
# Unified normalization entry point
# ---------------------------------------------------------------------------

def normalize_findings(raw_findings: List[Any], source: str) -> List[CanonicalFinding]:
    """Unified normalization entry point.

    Dispatches parser-specific structures to the appropriate normalizer.

    Args:
        raw_findings: Parser-specific output:
            - "nmap": list of dicts from core.scanner.parse_nmap_xml() or
              parse_nmap_json()
            - "nuclei": list of NucleiFinding objects from the Nuclei parser
            - "custom": list of dicts from core.scanner.parse_custom_json()
        source: Scanner source ("nmap", "nuclei", "custom").

    Returns:
        List of CanonicalFinding objects.

    Raises:
        ValueError: If source is unknown.
    """
    if source == "nmap":
        return normalize_nmap_findings(raw_findings)
    if source == "nuclei":
        return normalize_nuclei_findings(raw_findings)
    if source == "custom":
        return normalize_custom_findings(raw_findings)
    raise ValueError(f"Unknown source: {source!r}")


def deduplicate_findings(findings: List[CanonicalFinding]) -> List[CanonicalFinding]:
    """Convenience wrapper around deduplicate()."""
    return deduplicate(findings)
