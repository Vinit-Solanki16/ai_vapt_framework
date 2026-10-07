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

    FIX 1: Pure Nmap service-discovery records (open port + service
    fingerprint only, e.g. ``sun-as-jpda?``) are ASSET/SERVICE CONTEXT,
    not vulnerability candidates, and are excluded here. Use
    :func:`discovery_from_scan` to retrieve them for display/reporting.

    FIX 2: Nuclei informational / fingerprint / discovery observations
    (technology detection, Juice Shop detection, header observations,
    exposed-service info with severity info and no CVE/CVSS/KEV) are
    also excluded from ranking. Use :func:`discovery_from_scan` /
    :func:`split_scan` to retrieve the complete inventory.

    Args:
        file_path: Path to scan file (Nmap XML/JSON or custom JSON).

    Returns:
        List of ActionCandidate objects ready for run_engine().
    """
    findings = get_scanner_registry().parse(file_path)
    return findings_to_candidates(findings)


def discovery_from_scan(file_path: str) -> List[dict]:
    """Return preserved non-actionable records (FIX 1 + FIX 2).

    These are the findings excluded from :func:`candidates_from_scan`:
    Nmap service discovery AND Nuclei informational / fingerprint /
    discovery observations, rendered as display-safe inventory records
    with candidate eligibility "INFORMATIONAL / DISCOVERY".
    No severity is invented.
    """
    from vapt_platform.normalization import finding_to_service_info, split_findings

    findings = get_scanner_registry().parse(file_path)
    _, discovery = split_findings(findings)
    return [finding_to_service_info(f) for f in discovery]


def split_scan(file_path: str) -> tuple[List[ActionCandidate], List[dict]]:
    """Split a scan file into (actionable candidates, discovery inventory).

    Convenience wrapper preserving both sides of FIX 1 + FIX 2 without a
    second workflow: actionable candidates enter AI assessment → ranking
    → decision; discovery (service context + informational observations)
    remains visible in the findings inventory with eligibility
    "INFORMATIONAL / DISCOVERY".
    """
    from vapt_platform.normalization import finding_to_service_info, split_findings

    findings = get_scanner_registry().parse(file_path)
    actionable, discovery = split_findings(findings)
    return (
        findings_to_candidates(actionable),
        [finding_to_service_info(f) for f in discovery],
    )


def findings_to_candidates(findings) -> List[ActionCandidate]:
    """Convert a list of CanonicalFinding objects to ActionCandidate objects.

    FIX 1: Skips pure service-discovery records (Nmap open-port /
    service-fingerprint findings with no CVE/KEV/CVSS). Only
    VULNERABILITY_FINDING records become ActionCandidates.

    FIX 2: Also skips informational / fingerprint / discovery
    observations (Nuclei technology detection, Juice Shop detection,
    header observations, exposed-service info with severity info and
    no CVE/CVSS/KEV). Only ACTIONABLE findings become candidates;
    the complete inventory remains available via
    :func:`findings_to_service_discovery` / :func:`split_scan`.

    Mapping (for actionable findings only):
      - id = finding.finding_id or rule_id (or CVE from metadata if present)
      - probability = metadata["epss_score"] if present (0..1)
      - quality_rank = None (to be filled by the assessor)
      - ground_truth = None (no simulation label; real observed outcome)

    Args:
        findings: List of CanonicalFinding objects.

    Returns:
        List of ActionCandidate objects (only ACTIONABLE findings;
        service discovery + informational observations excluded).
    """
    # Import here to avoid a hard import cycle at module load time.
    from vapt_platform.normalization import is_actionable_finding

    candidates = []
    for f in findings:
        try:
            if not is_actionable_finding(f):
                continue
        except Exception:
            # Fail open for unclassifiable test doubles: preserve legacy
            # candidate behaviour rather than dropping findings silently.
            pass
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


def findings_to_service_discovery(findings) -> List[dict]:
    """Return preserved non-actionable records for display/reporting.

    FIX 1 + FIX 2: service discovery AND informational / fingerprint /
    discovery observations, each labelled with candidate eligibility
    "INFORMATIONAL / DISCOVERY".
    """
    from vapt_platform.normalization import finding_to_service_info, split_findings

    _, discovery = split_findings(findings or [])
    return [finding_to_service_info(f) for f in discovery]


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