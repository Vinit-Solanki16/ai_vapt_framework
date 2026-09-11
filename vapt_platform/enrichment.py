"""Vulnerability intelligence enrichment layer.

This module enriches CanonicalFinding objects with threat intelligence
from local datasets (CISA KEV, EPSS scores). It does NOT call live APIs.

Architecture:
    CanonicalFinding ──> enrich_finding() ──> Enriched CanonicalFinding
                                              (with cisa_kev, epss_score,
                                               cvss_score, severity fields
                                               added to metadata)

Provider abstraction:
    VulnerabilityIntelligenceProvider (base)
    ├── LocalDatasetProvider (CISA KEV, EPSS from local files)
    └── Future: NVDProvider, CISAPRovider, etc.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
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
# Provider abstraction
# ---------------------------------------------------------------------------

class VulnerabilityIntelligenceProvider(ABC):
    """Base class for vulnerability intelligence providers."""

    @abstractmethod
    def get_epss(self, cve_id: str) -> float:
        """Get EPSS score for a CVE."""
        ...

    @abstractmethod
    def is_in_kev(self, cve_id: str) -> bool:
        """Check if CVE is in CISA KEV."""
        ...

    @abstractmethod
    def get_cvss(self, cve_id: str) -> Optional[float]:
        """Get CVSS score for a CVE."""
        ...

    @abstractmethod
    def get_cwe_ids(self, cve_id: str) -> list[str]:
        """Get CWE IDs for a CVE."""
        ...


class LocalDatasetProvider(VulnerabilityIntelligenceProvider):
    """Provider using local dataset files."""

    def __init__(self) -> None:
        self._kev_set: Optional[set[str]] = None
        self._epss_corpus: Optional[dict[str, float]] = None

    @property
    def kev_set(self) -> set[str]:
        if self._kev_set is None:
            self._kev_set = _load_cisa_kev()
        return self._kev_set

    @property
    def epss_corpus(self) -> dict[str, float]:
        if self._epss_corpus is None:
            self._epss_corpus = _load_epss_corpus()
        return self._epss_corpus

    def get_epss(self, cve_id: str) -> float:
        return self.epss_corpus.get(cve_id.upper(), 0.0)

    def is_in_kev(self, cve_id: str) -> bool:
        return cve_id.upper() in self.kev_set

    def get_cvss(self, cve_id: str) -> Optional[float]:
        # No local CVSS dataset yet
        return None

    def get_cwe_ids(self, cve_id: str) -> list[str]:
        # No local CWE dataset yet
        return []


# ---------------------------------------------------------------------------
# Caching loaders
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_cisa_kev() -> set[str]:
    """Load CISA KEV CVE IDs into a set for O(1) lookup."""
    try:
        with open(CISA_KEV_PATH, "r") as f:
            data = json.load(f)
        vulnerabilities = data.get("vulnerabilities", [])
        return {v["cveID"].strip().upper() for v in vulnerabilities if "cveID" in v}
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
        return set()


@lru_cache(maxsize=1)
def _load_epss_corpus() -> dict[str, float]:
    """Load EPSS scores from local corpus."""
    try:
        with open(EPSS_CORPUS_PATH, "r") as f:
            data = json.load(f)
        return {k.strip().upper(): float(v) for k, v in data.items()}
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# CVE extraction from findings
# ---------------------------------------------------------------------------

def _extract_cve_ids(finding: CanonicalFinding) -> list[str]:
    """Extract CVE IDs from a finding using multiple sources."""
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
# CWE extraction
# ---------------------------------------------------------------------------

def _extract_cwe_ids(finding: CanonicalFinding) -> list[str]:
    """Extract CWE IDs from a finding."""
    cwes: set[str] = set()

    # From metadata.cwe_ids (Nuclei parser populates this)
    cwe_ids = finding.metadata.get("cwe_ids")
    if cwe_ids:
        if isinstance(cwe_ids, list):
            for c in cwe_ids:
                if isinstance(c, str):
                    cwes.add(c.strip().upper())
        elif isinstance(cwe_ids, str):
            cwes.add(cwe_ids.strip().upper())

    return list(cwes)


# ---------------------------------------------------------------------------
# Severity determination
# ---------------------------------------------------------------------------

def _determine_severity(
    finding: CanonicalFinding,
    cves_in_kev: bool,
    epss_score: float,
    cvss_score: Optional[float],
) -> str:
    """Determine overall severity for a finding."""
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

    return "none"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_finding(
    finding: CanonicalFinding,
    provider: Optional[VulnerabilityIntelligenceProvider] = None,
) -> CanonicalFinding:
    """Enrich a single finding with threat intelligence.

    Adds to metadata:
        - cisa_kev: bool (whether any associated CVE is in KEV)
        - epss_score: float (highest EPSS score among associated CVEs)
        - cvss_score: float | None (from finding if available)
        - severity: string (determined severity level)
        - cwe_ids: list[str] (extracted CWE IDs)

    Returns the finding (same object, mutated in place).
    """
    if provider is None:
        provider = LocalDatasetProvider()

    cve_ids = _extract_cve_ids(finding)
    cwe_ids = _extract_cwe_ids(finding)

    if not cve_ids:
        finding.metadata["cisa_kev"] = False
        finding.metadata["epss_score"] = 0.0
        finding.metadata["cvss_score"] = finding.metadata.get("cvss_score")
        finding.metadata["severity"] = "none"
        finding.metadata["cwe_ids"] = cwe_ids
        return finding

    # Intelligence from provider
    in_kev = any(provider.is_in_kev(cve) for cve in cve_ids)
    epss_scores = [provider.get_epss(cve) for cve in cve_ids]
    max_epss = max(epss_scores) if epss_scores else 0.0

    # CVSS score (from finding metadata or provider)
    cvss = finding.metadata.get("cvss_score")
    if cvss is not None:
        try:
            cvss = float(cvss)
        except (ValueError, TypeError):
            cvss = None
    if cvss is None:
        # Try provider
        for cve in cve_ids:
            cvss = provider.get_cvss(cve)
            if cvss is not None:
                break

    # Determine severity
    severity = _determine_severity(finding, in_kev, max_epss, cvss)

    # Attach to metadata
    finding.metadata["cisa_kev"] = in_kev
    finding.metadata["epss_score"] = max_epss
    finding.metadata["cvss_score"] = cvss
    finding.metadata["severity"] = severity
    finding.metadata["cwe_ids"] = cwe_ids

    return finding


def enrich_findings(
    findings: list[CanonicalFinding],
    provider: Optional[VulnerabilityIntelligenceProvider] = None,
) -> list[CanonicalFinding]:
    """Enrich a list of findings with threat intelligence."""
    if provider is None:
        provider = LocalDatasetProvider()
    return [enrich_finding(f, provider=provider) for f in findings]


def clear_cache() -> None:
    """Clear cached dataset reloads (useful for testing)."""
    _load_cisa_kev.cache_clear()
    _load_epss_corpus.cache_clear()
