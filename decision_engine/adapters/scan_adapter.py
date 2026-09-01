"""Scan adapter — converts scanner output (Finding[]) into engine candidates (ActionCandidate[]).

This is the bridge between the VAPT input layer (core/scanner.py) and the
domain-independent decision engine. It normalizes findings into the
ActionCandidate schema so the engine can rank, assess, and pivot on them.

Read-only w.r.t. core/: imports core.scanner but never modifies it.
"""
from __future__ import annotations

import os
from typing import List, Optional

from decision_engine.core.schemas import ActionCandidate, candidate_from_dict

# Import the frozen scanner (read-only)
from core.scanner import process_scan


def candidates_from_scan(file_path: str, timeout: int = 5) -> List[ActionCandidate]:
    """Build ActionCandidates from a scan file.

    Steps:
      1. Call core.scanner.process_scan() to parse + enrich (EPSS) the scan.
      2. Normalize each Finding into an ActionCandidate.
      3. Return the list (unranked — the engine ranks by priority_score).

    Args:
        file_path: Path to scan file (Nmap XML/JSON or custom JSON).
        timeout: EPSS lookup timeout (per finding).

    Returns:
        List of ActionCandidate objects ready for run_engine().
    """
    findings = process_scan(file_path, timeout=timeout)
    return findings_to_candidates(findings)


def findings_to_candidates(findings) -> List[ActionCandidate]:
    """Convert a list of Finding objects to ActionCandidate objects.

    Mapping:
      - id = finding.cve (or "UNKNOWN-CVE" if none)
      - probability = finding.epss_score (0..1, live from FIRST.org)
      - quality_rank = None (to be filled by the assessor)
      - ground_truth = None (no simulation label; real observed outcome)

    Args:
        findings: List of core.schemas.Finding objects.

    Returns:
        List of ActionCandidate objects.
    """
    candidates = []
    for f in findings:
        cid = f.cve if f.cve and f.cve != "UNKNOWN-CVE" else f"PORT-{f.port or 'UNKNOWN'}"
        prob = f.epss_score if f.epss_score else 0.0
        candidates.append(ActionCandidate(
            id=cid,
            probability=min(max(float(prob), 0.0), 1.0),  # clamp to [0,1]
            quality_rank=None,
            ground_truth=None,
        ))
    return candidates


def candidates_to_scenario(candidates: List[ActionCandidate]) -> List[dict]:
    """Convert ActionCandidates back to scenario dicts (for serialization)."""
    return [
        {
            "id": c.id,
            "probability": c.probability,
            "ground_truth": c.ground_truth.value if c.ground_truth else None,
        }
        for c in candidates
    ]
