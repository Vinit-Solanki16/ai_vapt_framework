"""Scan adapter — converts scanner output (Finding[]) into engine candidates (ActionCandidate[]).

This is the bridge between the VAPT input layer (canonical scanner adapters) and the
domain-independent decision engine. It normalizes findings into the
ActionCandidate schema so the engine can rank, assess, and pivot on them.
"""
from __future__ import annotations

from typing import List, Optional

from decision_engine.core.schemas import ActionCandidate, candidate_from_dict
from vapt_platform.scanners import get_scanner_registry


def candidates_from_scan(file_path: str) -> List[ActionCandidate]:
    """Build ActionCandidates from a scan file.

    Steps:
      1. Call the canonical scanner registry to parse the scan.
      2. Normalize each CanonicalFinding into an ActionCandidate.
      3. Return the list (unranked — the engine ranks by priority_score).

    Args:
        file_path: Path to scan file (Nmap XML/JSON or custom JSON).

    Returns:
        List of ActionCandidate objects ready for run_engine().
    """
    findings = get_scanner_registry().parse(file_path)
    return findings_to_candidates(findings)


def findings_to_candidates(findings) -> List[ActionCandidate]:
    """Convert a list of CanonicalFinding objects to ActionCandidate objects.

    Mapping:
      - id = finding.finding_id or rule_id (or CVE from metadata if present)
      - probability = metadata["epss_score"] if present (0..1)
      - quality_rank = None (to be filled by the assessor)
      - ground_truth = None (no simulation label; real observed outcome)

    Args:
        findings: List of CanonicalFinding objects.

    Returns:
        List of ActionCandidate objects.
    """
    candidates = []
    for f in findings:
        if hasattr(f, 'metadata'):
            metadata = f.metadata or {}
            cve = metadata.get("cve")
            cid = cve or f.finding_id or f.rule_id or f"PORT-{f.port or 'UNKNOWN'}"
            epss = metadata.get("epss_score", 0.0)
            prob = float(epss or 0.0)
        else:
            metadata = {}
            cve = getattr(f, 'cve', None)
            cid = cve or getattr(f, 'finding_id', None) or getattr(f, 'rule_id', None) or f"PORT-{getattr(f, 'port', None) or 'UNKNOWN'}"
            epss = getattr(f, 'epss_score', 0.0)
            prob = float(epss or 0.0)
        candidates.append(ActionCandidate(
            id=cid,
            probability=min(max(prob, 0.0), 1.0),
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