"""Mathematical priority formulation and candidate ranking for GAP-1."""

from __future__ import annotations

from typing import Any

from strix.core.triage.exploit_assessor import ExploitAssessment, UsabilityRank


def calculate_composite_score(
    candidate: dict[str, Any],
    assessment: ExploitAssessment,
) -> float:
    """Calculate the composite priority score for an action candidate.

    Formula:
        FinalScore = probability * (0.5 + 0.5 * quality_weight)
        where quality_weight: HIGH=1.0, MEDIUM=0.6, LOW=0.3
    """
    raw_cvss = float(candidate.get("cvss") or candidate.get("cvss_score") or 7.0)
    base_prob = float(candidate.get("probability") or candidate.get("base_prob") or (raw_cvss / 10.0))
    exposure = float(candidate.get("exposure", 1.0))
    effective_prob = min(1.0, max(0.05, base_prob * exposure))

    if assessment.usability_rank == UsabilityRank.HIGH:
        quality_weight = 1.0
    elif assessment.usability_rank == UsabilityRank.MEDIUM:
        quality_weight = 0.6
    else:
        quality_weight = 0.3

    final_score = effective_prob * (0.5 + 0.5 * quality_weight)
    return round(final_score, 4)


def rank_action_candidates(
    candidates: list[dict[str, Any]],
    assessments: dict[str, ExploitAssessment] | None = None,
) -> list[dict[str, Any]]:
    """Sort a list of candidates in descending order of composite priority score."""
    assessments = assessments or {}
    scored_candidates = []

    for c in candidates:
        cid = c.get("id", "")
        assess = assessments.get(cid)
        if not assess:
            # Generate default assessment if not provided
            from strix.core.triage.exploit_assessor import assess_exploit_quality

            assess = assess_exploit_quality(candidate_id=cid)

        score = calculate_composite_score(c, assess)
        enriched = dict(c)
        enriched["composite_score"] = score
        enriched["usability_rank"] = assess.usability_rank.value
        scored_candidates.append(enriched)

    scored_candidates.sort(key=lambda x: x["composite_score"], reverse=True)
    return scored_candidates
