"""Gap-1: domain-independent candidate quality assessment (pre-execution).

The original VAPT assessor graded CVE exploit code. Here, the assessor grades
any "candidate action" surfaced by a domain adapter. The grading contract is a
structured-LLM matrix (syntax_valid, complexity, prerequisites, quality_rank).

For research reproducibility without a live LLM, this module also provides a
deterministic fallback assessor so benchmarks run offline.
"""
from __future__ import annotations

from typing import Callable, Optional

from decision_engine.core.schemas import ActionCandidate, QualityRank


# Default deterministic fallback: maps a candidate's id/priority to a rank.
# Used by benchmarks and simulation so engine behaviour is reproducible offline.
def deterministic_assessor(candidate: ActionCandidate) -> QualityRank:
    """Offline, deterministic Gap-1 scorer (research fallback, not a claim)."""
    if candidate.ground_truth == __import__("decision_engine.core.schemas", fromlist=["Outcome"]).Outcome.SUCCESS:
        return QualityRank.HIGH
    if candidate.probability >= 0.9:
        return QualityRank.MEDIUM
    return QualityRank.LOW


def assess_candidates(
    candidates: list[ActionCandidate],
    assess_fn: Optional[Callable[[ActionCandidate], QualityRank]] = None,
) -> list[ActionCandidate]:
    """Grade every not-yet-assessed candidate in place.

    assess_fn defaults to deterministic_assessor (offline). A domain adapter or
    a live LLM may pass a real scoring function (see vapt_adapter.py).
    """
    fn = assess_fn or deterministic_assessor
    for c in candidates:
        if not c.assessed:
            c.quality_rank = fn(c)
            c.assessed = True
    return candidates
