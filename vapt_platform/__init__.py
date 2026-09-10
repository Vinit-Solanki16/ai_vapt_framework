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
    deduplicate,
    normalize_severity,
    severity_rank,
    highest_severity,
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
    "deduplicate",
    "normalize_severity",
    "severity_rank",
    "highest_severity",
]
