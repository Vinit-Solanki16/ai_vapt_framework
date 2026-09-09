"""Platform parsers subpackage.

Contains parsers for scanner output formats (Nuclei, Nmap, Web recon, etc.).
Each parser produces a normalized intermediate representation.
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