"""Vulnerability intelligence enrichment layer.

This module enriches CanonicalFinding objects with threat intelligence
from local datasets (CISA KEV, EPSS scores). It does NOT call live APIs.

Architecture:
    CanonicalFinding ──> enrich_finding() ──> Enriched CanonicalFinding
                                              (with cisa_kev, epss_score,
                                               cvss_score, severity fields
                                               added to metadata)
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from vapt_platform.normalization import CanonicalFinding, normalize_severity


# ---------------------------------------------------------------------------
# Dataset paths
# ---------------------------------------------------------------------------

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"
CISA_KEV_PATH = DATASETS_DIR / "cisa_kev.json"
EPSS_CORPUS_PATH = DATASETS_DIR / "epss_corpus_enrichment.json"


# ---------------------------------------------------------------------------
# Caching loaders
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_cisa_kev() -> set[str]:
    """Load CISA KEV CVE IDs into a set for O(1) lookup.

    Returns empty set if file is missing or malformed.
    """
    try:
        with open(CISA_KEV_PATH, "r") as f:
            data = json.load(f)
        vulnerabilities = data.get("vulnerabilities", [])
        return {v["cveID"].strip().upper() for v in vulnerabilities if "cveID" in v}
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
        return set()


@lru_cache(maxsize=1)
def _load_epss_corpus() -> dict[str, float]:
    """Load EPSS scores from local corpus.

    Returns empty dict if file is missing or malformed.
    """
    try:
        with open(EPSS_CORPUS_PATH, "r") as f:
            data = json.load(f)
        # Normalize keys to uppercase CVE IDs
        return {k.strip().upper(): float(v) for k, v in data.items()}
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# CVE extraction from findings
# ---------------------------------------------------------------------------

def _extract_cve_ids(finding: CanonicalFinding) -> list[str]:
    """Extract CVE IDs from a finding using multiple sources.

    Searches:
    1. metadata.cve_ids (list)
    2. metadata.cve (single string)
    3. rule_id (if it looks like a CVE)
    4. evidence list (any entry that looks like a CVE)

    Returns a list of uppercase CVE strings.
    """
    cves: set[str] = set()

    # From metadata.cve_ids
    cve_ids = finding.metadata.get("cve_ids")
    if cve_ids:
        if isinstance(cve_ids, list):
            for c in cve_ids:
                if isinstance(c, str):
                    cves.add(c.strip().upper())
        elif isinstance(cve_ids, str):
            cves.add(cve_ids.strip().upper())

    # From metadata.cve
    cve = finding.metadata.get("cve")
    if cve and isinstance(cve, str):
        cves.add(cve.strip().upper())

    # From rule_id (often set to CVE for scanner findings)
    rule_id = finding.rule_id
    if rule_id and isinstance(rule_id, str):
        rid = rule_id.strip().upper()
        if rid.startswith("CVE-"):
            cves.add(rid)

    # From evidence list
    for ev in finding.evidence:
        if isinstance(ev, str):
            e = ev.strip().upper()
            if e.startswith("CVE-"):
                cves.add(e)

    return list(cves)


# ---------------------------------------------------------------------------
# Severity determination
# ---------------------------------------------------------------------------

def _determine_severity(
    finding: CanonicalFinding,
    cves_in_kev: bool,
    epss_score: float,
    cvss_score: Optional[float],
) -> str:
    """Determine overall severity for a finding.

    Priority:
    1. If finding already has a non-unknown severity, use it
    2. If CVSS >= 9.0 -> critical
    3. If CVSS >= 7.0 -> high
    4. If CVSS >= 4.0 -> medium
    5. If CVSS > 0 -> low
    6. If CVE is in KEV -> high
    7. If EPSS >= 0.9 -> critical
    8. If EPSS >= 0.5 -> high
    9. Otherwise -> none

    Returns one of: critical/high/medium/low/informational/none
    """
    existing = normalize_severity(finding.severity)
    if existing != "unknown":
        return existing

    # CVSS-based severity (takes priority)
    if cvss_score is not None:
        if cvss_score >= 9.0:
            return "critical"
        elif cvss_score >= 7.0:
            return "high"
        elif cvss_score >= 4.0:
            return "medium"
        elif cvss_score > 0:
            return "low"

    # KEV presence indicates active exploitation
    if cves_in_kev:
        return "high"

    # Very high EPSS score
    if epss_score >= 0.9:
        return "critical"
    if epss_score >= 0.5:
        return "high"

    # No intelligence available
    return "none"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_finding(finding: CanonicalFinding) -> CanonicalFinding:
    """Enrich a single finding with threat intelligence.

    Adds to metadata:
        - cisa_kev: bool (whether any associated CVE is in KEV)
        - epss_score: float (highest EPSS score among associated CVEs)
        - cvss_score: float | None (from finding if available)
        - severity: string (determined severity level)

    Returns the finding (same object, mutated in place).
    """
    cve_ids = _extract_cve_ids(finding)

    if not cve_ids:
        finding.metadata["cisa_kev"] = False
        finding.metadata["epss_score"] = 0.0
        finding.metadata["cvss_score"] = finding.metadata.get("cvss_score")
        finding.metadata["severity"] = "none"
        return finding

    # Load datasets (cached)
    kev_set = _load_cisa_kev()
    epss_corpus = _load_epss_corpus()

    # CISA KEV check
    in_kev = any(cve in kev_set for cve in cve_ids)

    # EPSS score (take max across all CVEs)
    epss_scores = [epss_corpus.get(cve, 0.0) for cve in cve_ids]
    max_epss = max(epss_scores) if epss_scores else 0.0

    # CVSS score
    cvss = finding.metadata.get("cvss_score")
    if cvss is not None:
        try:
            cvss = float(cvss)
        except (ValueError, TypeError):
            cvss = None

    # Determine severity
    severity = _determine_severity(finding, in_kev, max_epss, cvss)

    # Attach to metadata
    finding.metadata["cisa_kev"] = in_kev
    finding.metadata["epss_score"] = max_epss
    finding.metadata["cvss_score"] = cvss
    finding.metadata["severity"] = severity

    return finding


def enrich_findings(findings: list[CanonicalFinding]) -> list[CanonicalFinding]:
    """Enrich a list of findings with threat intelligence.

    Processes each finding through enrich_finding().
    """
    return [enrich_finding(f) for f in findings]


def clear_cache() -> None:
    """Clear cached dataset reloads (useful for testing)."""
    _load_cisa_kev.cache_clear()
    _load_epss_corpus.cache_clear()