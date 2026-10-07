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
# Finding-kind classification (FIX 1 — service discovery vs vulnerability)
#
# Nmap service discovery must provide ASSET/SERVICE CONTEXT, not
# automatically become a vulnerability/exploit candidate.
#
#   SERVICE_DISCOVERY (ASSET_CONTEXT):
#       Pure Nmap open-port / service-fingerprint record with NO
#       vulnerability indicators (no CVE, no KEV, no CVSS). Example:
#       port 9191, service "sun-as-jpda?", HTTP banner from Juice Shop.
#       Preserved for target/port/protocol/service/version/evidence display,
#       but MUST NOT enter AI assessment → ranking → decision.
#
#   VULNERABILITY_FINDING (ACTIONABLE_CANDIDATE):
#       Any finding with vulnerability evidence (CVE linkage, KEV, CVSS)
#       or any non-Nmap scanner finding (Nuclei templates are vulnerability
#       checks by construction). These MAY enter candidate generation.
#
# No severity is invented here: classification only separates discovery
# context from actionable findings using already-observed fields.
# ---------------------------------------------------------------------------

#: Canonical finding-kind labels.
FINDING_KIND_SERVICE_DISCOVERY = "SERVICE_DISCOVERY"
FINDING_KIND_VULNERABILITY = "VULNERABILITY_FINDING"
#: FIX 2: Nuclei informational / fingerprint / discovery observations.
#: Preserved in the findings inventory but never ranked as exploit candidates.
FINDING_KIND_INFORMATIONAL = "INFORMATIONAL_FINDING"

#: Candidate-eligibility labels shown in UI/reports (FIX 2).
#: Every finding maps to exactly one of these; only ACTIONABLE enters
#: AI assessment → ranking → decision.
CANDIDATE_ELIGIBILITY_ACTIONABLE = "ACTIONABLE"
CANDIDATE_ELIGIBILITY_INFORMATIONAL = "INFORMATIONAL / DISCOVERY"

#: Sources that represent pure network/service discovery (not vuln scans).
NMAP_DISCOVERY_SOURCES = frozenset({"nmap", "nmap-xml", "nmap-json"})

_CVE_PREFIX = "CVE-"


def _finding_field(finding: Any, name: str, default: Any = None) -> Any:
    """Read a field from a CanonicalFinding, dict, or generic object."""
    if isinstance(finding, dict):
        return finding.get(name, default)
    if isinstance(finding, CanonicalFinding):
        return getattr(finding, name, default)
    # Generic objects (incl. test doubles): only trust real string values
    # for source classification; MagicMock attributes must NOT match Nmap.
    try:
        value = getattr(finding, name, default)
    except Exception:
        return default
    return value


def _normalized_source(finding: Any) -> str:
    """Return the lower-cased source string, or '' when not a real string."""
    source = _finding_field(finding, "source", "")
    if not isinstance(source, str):
        return ""
    return source.strip().lower()


def _has_cve_indicator(finding: Any) -> bool:
    """True when the finding carries an explicit CVE linkage."""
    rule_id = _finding_field(finding, "rule_id", "")
    if isinstance(rule_id, str) and rule_id.strip().upper().startswith(_CVE_PREFIX):
        return True

    metadata = _finding_field(finding, "metadata", None)
    if isinstance(metadata, dict):
        cve = metadata.get("cve")
        # Nmap JSON uses null when absent; only CVE-prefixed strings count.
        if isinstance(cve, str) and cve.strip().upper().startswith(_CVE_PREFIX):
            return True
        cve_ids = metadata.get("cve_ids")
        if isinstance(cve_ids, list) and any(
            isinstance(c, str) and c.strip().upper().startswith(_CVE_PREFIX) for c in cve_ids
        ):
            return True
        if isinstance(cve_ids, str) and cve_ids.strip().upper().startswith(_CVE_PREFIX):
            return True

    evidence = _finding_field(finding, "evidence", None)
    if isinstance(evidence, list):
        for ev in evidence:
            if isinstance(ev, str) and ev.strip().upper().startswith(_CVE_PREFIX):
                return True

    return False


def _has_strong_vuln_intel(finding: Any) -> bool:
    """True for KEV membership or a concrete CVSS score (observed intel)."""
    metadata = _finding_field(finding, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    if metadata.get("cisa_kev") is True:
        return True
    cvss = metadata.get("cvss_score")
    if cvss is not None:
        try:
            float(cvss)
            return True
        except (TypeError, ValueError):
            return False
    return False


# ---------------------------------------------------------------------------
# FIX 2 — informational / fingerprint / discovery observations
#
# Observed Nuclei metadata (data/scans/nuclei_127.0.0.1_9191.jsonl):
#   template-id: tech-detect, fingerprinthub-web-fingerprints,
#     owasp-juice-shop-detect, http-missing-security-headers,
#     swagger-api, prometheus-metrics
#   info.severity: info (12/13) vs medium (prometheus-metrics, CVSS 5.3)
#   info.tags: tech/discovery/fingerprint vs misconfig/headers vs
#     exposure/api/swagger vs exposure/config/vuln
#   classification: cve-id null (all info) vs CVSS present (prometheus)
#   title/name: "Wappalyzer Technology Detection",
#     "FingerprintHub Technology Fingerprint", "OWASP Juice Shop",
#     "HTTP Missing Security Headers", "Public Swagger API - Detect"
#
# Actionable counter-example: prometheus-metrics (severity medium +
# CVSS 5.3 + CWE-200) stays ACTIONABLE; CVE-2021-44228 (critical +
# CVE + CVSS 10.0) stays ACTIONABLE. UNKNOWN severity never maps to
# INFORMATIONAL (fail open — genuine vulns are never dropped).
# ---------------------------------------------------------------------------

#: Template-id substrings marking technology/fingerprint/discovery or
#: informational misconfiguration/exposure observations (lowercase match).
_INFORMATIONAL_TEMPLATE_SUBSTRINGS = (
    "tech-detect",
    "tech_detect",
    "technolog",
    "fingerprint",
    "fingerprinthub",
    "wappalyzer",
    "juice-shop",
    "juiceshop",
    "swagger",
    "missing-security-headers",
    "security-header",
    "security-headers",
    "-detect",
    "detection",
    "discovery",
)

#: Nuclei tag markers for informational/discovery observations (lowercase).
_INFORMATIONAL_TAG_MARKERS = frozenset({
    "tech",
    "fingerprint",
    "discovery",
    "detection",
    "detect",
    "misconfig",
    "misconfiguration",
    "headers",
    "header",
    "exposure",
    "exposed",
    "info",
    "informational",
    "banner",
})

#: Title/name substrings marking informational/discovery observations.
_INFORMATIONAL_TITLE_SUBSTRINGS = (
    "technology detection",
    "technology fingerprint",
    "fingerprint",
    "wappalyzer",
    "juice shop",
    "missing security headers",
    "security headers",
    "swagger",
    "exposed",
    "exposure",
    "discovery",
    "detect",
)


def _normalized_severity_value(finding: Any) -> str:
    """Return the normalized severity string, or '' for non-string input."""
    raw = _finding_field(finding, "severity", "")
    if not isinstance(raw, str):
        return ""
    try:
        return normalize_severity(raw)
    except Exception:
        return ""


def _finding_tags_lower(finding: Any) -> list[str]:
    """Return lower-cased tag strings (real strings only, '' excluded)."""
    tags = _finding_field(finding, "tags", None)
    if not isinstance(tags, list):
        return []
    out: list[str] = []
    for t in tags:
        if isinstance(t, str) and t.strip():
            out.append(t.strip().lower())
    return out


def _finding_title_lower(finding: Any) -> str:
    """Return the lower-cased title/name, or '' for non-string input."""
    title = _finding_field(finding, "title", "")
    if not isinstance(title, str):
        # NucleiFinding stores the display name in metadata-free fields;
        # CanonicalFinding.title is the mapped name — only trust strings.
        return ""
    return title.strip().lower()


def _finding_template_id_lower(finding: Any) -> str:
    """Return the lower-cased template/rule identifier for matching."""
    rule_id = _finding_field(finding, "rule_id", "")
    template = ""
    if isinstance(rule_id, str):
        template = rule_id.strip().lower()
    metadata = _finding_field(finding, "metadata", None)
    if isinstance(metadata, dict):
        tid = metadata.get("template_id")
        if isinstance(tid, str) and tid.strip():
            # Prefer the explicit Nuclei template_id when present.
            template = tid.strip().lower()
    return template


def _has_informational_marker(finding: Any) -> bool:
    """True when scanner metadata marks a fingerprint/discovery/info record."""
    template = _finding_template_id_lower(finding)
    if template:
        for sub in _INFORMATIONAL_TEMPLATE_SUBSTRINGS:
            if sub in template:
                return True
    for tag in _finding_tags_lower(finding):
        if tag in _INFORMATIONAL_TAG_MARKERS:
            return True
    title = _finding_title_lower(finding)
    if title:
        for sub in _INFORMATIONAL_TITLE_SUBSTRINGS:
            if sub in title:
                return True
    return False


def _is_informational_observation(finding: Any) -> bool:
    """True for informational / fingerprint / discovery observations.

    Requires ALL of:
      - normalized severity == "informational" (never "unknown");
      - no vulnerability identifiers (no CVE, no KEV, no CVSS);
      - an informational marker in template_id/tags/title.
    Fail open: any unclassifiable input (mocks, missing fields,
    UNKNOWN severity, genuine vuln intel) returns False → ACTIONABLE.
    """
    try:
        if _normalized_severity_value(finding) != "informational":
            return False
        if _has_cve_indicator(finding):
            return False
        if _has_strong_vuln_intel(finding):
            return False
        return _has_informational_marker(finding)
    except Exception:
        return False


def finding_kind(finding: Any) -> str:
    """Classify a finding as SERVICE_DISCOVERY, INFORMATIONAL or VULNERABILITY.

    Rules (no severity is invented; UNKNOWN is never informational):
      - Nmap sources with explicit vulnerability indicators (CVE linkage,
        KEV, CVSS) are VULNERABILITY_FINDING and may become candidates.
      - All other Nmap records (open port + service fingerprint/banner
        only, e.g. ``sun-as-jpda?`` on 9191) are SERVICE_DISCOVERY:
        asset context only, never an exploit candidate.
      - FIX 2: Nuclei (and similar) informational / fingerprint /
        discovery observations are INFORMATIONAL_FINDING when ALL hold:
          (a) normalized severity is ``informational`` (``info``),
              never ``unknown`` (UNKNOWN stays ACTIONABLE fail-open);
          (b) NO vulnerability identifiers (no CVE linkage, no KEV,
              no concrete CVSS score);
          (c) an informational marker is observed in scanner metadata:
              template_id substrings (tech-detect/fingerprint/detect/
              discovery/swagger/missing-security-headers/...), tags
              (tech/fingerprint/discovery/misconfig/headers/exposure/...),
              or title substrings (technology detection/fingerprint/
              Juice Shop/missing security headers/...).
        Severity alone never decides: (b) + (c) are required.
      - Everything else (incl. CVE-bearing findings, CVSS-scored
        findings, KEV members, medium+ severity exposures such as
        prometheus-metrics, and custom/unknown findings) is
        VULNERABILITY_FINDING and may become a candidate.
    """
    source = _normalized_source(finding)
    if source in NMAP_DISCOVERY_SOURCES:
        if _has_cve_indicator(finding):
            return FINDING_KIND_VULNERABILITY
        if _has_strong_vuln_intel(finding):
            return FINDING_KIND_VULNERABILITY
        return FINDING_KIND_SERVICE_DISCOVERY
    if _is_informational_observation(finding):
        return FINDING_KIND_INFORMATIONAL
    return FINDING_KIND_VULNERABILITY


def is_service_discovery(finding: Any) -> bool:
    """True when the finding is pure service-discovery / asset context."""
    return finding_kind(finding) == FINDING_KIND_SERVICE_DISCOVERY


def is_informational_finding(finding: Any) -> bool:
    """True for informational / fingerprint / discovery observations (FIX 2).

    These remain visible in the findings inventory but MUST NOT enter
    AI assessment → ranking → decision.
    """
    return finding_kind(finding) == FINDING_KIND_INFORMATIONAL


def is_vulnerability_finding(finding: Any) -> bool:
    """True when the finding may enter the actionable candidate pipeline."""
    return finding_kind(finding) == FINDING_KIND_VULNERABILITY


def is_actionable_finding(finding: Any) -> bool:
    """True only for ACTIONABLE findings eligible for candidate ranking.

    FIX 2: excludes both SERVICE_DISCOVERY (FIX 1) and
    INFORMATIONAL_FINDING (fingerprint / informational observations).
    Fail open for unclassifiable test doubles (non-string fields):
    finding_kind returns VULNERABILITY → actionable, preserving legacy
    candidate behaviour rather than dropping findings silently.
    """
    return is_vulnerability_finding(finding)


def candidate_eligibility(finding: Any) -> str:
    """Return the candidate-eligibility label for display/reporting.

    Returns:
        "ACTIONABLE" for vulnerability findings eligible for ranking;
        "INFORMATIONAL / DISCOVERY" for service-discovery asset context
        and informational / fingerprint / discovery observations.
    """
    try:
        if is_actionable_finding(finding):
            return CANDIDATE_ELIGIBILITY_ACTIONABLE
        return CANDIDATE_ELIGIBILITY_INFORMATIONAL
    except Exception:
        # Fail open for display: unclassifiable records stay actionable
        # so genuine findings are never hidden from ranking silently.
        return CANDIDATE_ELIGIBILITY_ACTIONABLE


def split_findings(findings: list[Any]) -> tuple[list[Any], list[Any]]:
    """Split findings into (actionable, discovery).

    FIX 2: discovery now holds BOTH pure Nmap service-discovery asset
    context (FIX 1) AND Nuclei informational / fingerprint / discovery
    observations. Both buckets remain visible in the findings inventory;
    only actionable (VULNERABILITY_FINDING) enters candidate generation.

    Returns:
        Tuple (actionable_findings, discovery_records) preserving order.
    """
    actionable: list[Any] = []
    discovery: list[Any] = []
    for f in findings or []:
        try:
            if is_actionable_finding(f):
                actionable.append(f)
            else:
                discovery.append(f)
        except Exception:
            # Fail open: unclassifiable records stay actionable.
            actionable.append(f)
    return actionable, discovery


def finding_to_service_info(finding: Any) -> dict[str, Any]:
    """Render a non-actionable record for inventory display (no severity invented).

    FIX 1: Nmap service-discovery asset context (target/port/protocol/
    service/version/banner).
    FIX 2: Nuclei informational / fingerprint / discovery observations
    (technology detection, Juice Shop detection, header observations,
    exposed-service info). Both buckets share the discovery side of
    split_findings and map to candidate eligibility
    "INFORMATIONAL / DISCOVERY" — visible everywhere, never ranked.

    Preserves the complete finding (severity/rule_id/tags/evidence/
    metadata) so no information is hidden from the user.
    """
    # Resolve the display kind without hiding information.
    try:
        kind = finding_kind(finding)
    except Exception:
        kind = FINDING_KIND_SERVICE_DISCOVERY
    if kind == FINDING_KIND_INFORMATIONAL:
        record_type = "INFORMATIONAL"
        label = "Informational / Discovery"
    else:
        kind = FINDING_KIND_SERVICE_DISCOVERY
        record_type = "SERVICE_DISCOVERY"
        label = "Service Discovery / Asset Information"
    if isinstance(finding, dict):
        metadata = finding.get("metadata") or {}
        service = finding.get("service", metadata.get("service", ""))
        severity = finding.get("severity", "")
        if not isinstance(severity, str):
            severity = ""
        rule_id = finding.get("rule_id", finding.get("template_id", ""))
        if not isinstance(rule_id, str):
            rule_id = ""
        return {
            "finding_id": finding.get("finding_id", finding.get("id", "")),
            "source": finding.get("source", "unknown"),
            "target": finding.get("target", finding.get("host", "")),
            "host": finding.get("host", ""),
            "port": finding.get("port", 0),
            "protocol": finding.get("protocol", "tcp"),
            "service": service or finding.get("title", ""),
            "title": finding.get("title", ""),
            "severity": severity,
            "rule_id": rule_id,
            "product": metadata.get("product", ""),
            "version": metadata.get("version", ""),
            "description": finding.get("description", ""),
            "evidence": list(finding.get("evidence", []) or []),
            "tags": list(finding.get("tags", []) or []),
            "metadata": dict(metadata),
            "finding_kind": kind,
            "record_type": record_type,
            "label": label,
            "candidate_eligibility": CANDIDATE_ELIGIBILITY_INFORMATIONAL,
        }
    metadata = dict(getattr(finding, "metadata", None) or {})
    service = metadata.get("service", "") or getattr(finding, "title", "")
    severity = getattr(finding, "severity", "")
    if not isinstance(severity, str):
        severity = ""
    rule_id = getattr(finding, "rule_id", "")
    if not isinstance(rule_id, str):
        rule_id = ""
    return {
        "finding_id": getattr(finding, "finding_id", ""),
        "source": getattr(finding, "source", "unknown"),
        "target": getattr(finding, "target", ""),
        "host": getattr(finding, "host", ""),
        "port": getattr(finding, "port", 0),
        "protocol": getattr(finding, "protocol", "tcp"),
        "service": service,
        "title": getattr(finding, "title", ""),
        "severity": severity,
        "rule_id": rule_id,
        "product": metadata.get("product", ""),
        "version": metadata.get("version", ""),
        "description": getattr(finding, "description", ""),
        "evidence": list(getattr(finding, "evidence", []) or []),
        "tags": list(getattr(finding, "tags", []) or []),
        "metadata": metadata,
        "finding_kind": kind,
        "record_type": record_type,
        "label": label,
        "candidate_eligibility": CANDIDATE_ELIGIBILITY_INFORMATIONAL,
    }


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
