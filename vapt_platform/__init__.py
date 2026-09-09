"""Platform parsers package.

This package contains parsers for various scanner output formats.
Each parser normalizes scanner-specific output into a common intermediate
representation suitable for the normalization layer.
"""

from vapt_platform.parsers.nuclei_parser import (
    NucleiParser,
    NucleiFinding,
    parse_nuclei_json,
    parse_nuclei_jsonl,
)

__all__ = [
    "NucleiParser",
    "NucleiFinding",
    "parse_nuclei_json",
    "parse_nuclei_jsonl",
]