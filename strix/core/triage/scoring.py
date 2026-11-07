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
        FinalScore = (w_cvss * S_cvss) + (w_exposure * E_exp) + (w_ai * Q_ai) + base_prob
    """
    # 1. Normalized CVSS severity [0.0 - 1.0]
    raw_cvss = float(candidate.get("cvss") or candidate.get("cvss_score") or 5.0)
    s_cvss = min(1.0, max(0.0, raw_cvss / 10.0))

    # 2. Asset exposure [0.0 - 1.0]
    e_exp = float(candidate.get("exposure", 1.0))

    # 3. AI Usability Rank boost
    if assessment.usability_rank == UsabilityRank.HIGH:
        q_ai = 1.0
    elif assessment.usability_rank == UsabilityRank.MEDIUM:
        q_ai = 0.5
    else:
        q_ai = 0.0

    # Weights
    w_cvss = 0.40
    w_exp = 0.20
    w_ai = 0.40

    final_score = (w_cvss * s_cvss) + (w_exp * e_exp) + (w_ai * q_ai)
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
