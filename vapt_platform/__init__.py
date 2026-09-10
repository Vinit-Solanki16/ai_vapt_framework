"""Platform package.

This package contains parsers for various scanner output formats and the
canonical normalization layer that converges different scanner formats into
a unified finding representation.

Submodules:
    parsers: Scanner-specific parsers (Nuclei, etc.)
    normalization: Canonical finding normalization and deduplication
"""
from vapt_platform.parsers.nuclei_parser import (
    NucleiParser,
    NucleiFinding,
    parse_nuclei_json,
    parse_nuclei_jsonl,
)

from vapt_platform.normalization import (
    CanonicalFinding,
    normalize_nmap_findings,
    normalize_nuclei_findings,
    normalize_custom_findings,
    normalize_findings,
    deduplicate_findings,
    canonical_to_candidates,
    asset_identity,
    finding_identity,
    normalize_severity,
    cvss_score_to_severity,
)

__all__ = [
    # Parsers
    "NucleiParser",
    "NucleiFinding",
    "parse_nuclei_json",
    "parse_nuclei_jsonl",
    # Normalization
    "CanonicalFinding",
    "normalize_nmap_findings",
    "normalize_nuclei_findings",
    "normalize_custom_findings",
    "normalize_findings",
    "deduplicate_findings",
    "canonical_to_candidates",
    "asset_identity",
    "finding_identity",
    "normalize_severity",
    "cvss_score_to_severity",
]