"""Tests for GAP-1 Exploit Quality Scoring and Prioritization."""

from __future__ import annotations

from strix.core.triage.exploit_assessor import (
    ExploitAssessment,
    UsabilityRank,
    assess_exploit_quality,
    run_gap1_triage,
)
from strix.core.triage.owasp_mapping import map_finding_to_owasp
from strix.core.triage.scoring import calculate_composite_score


def test_owasp_mapping():
    """Verify OWASP Top-10 profile mapping."""
    res1 = map_finding_to_owasp("PHPInfo sensitive environment disclosure")
    assert res1["owasp_id"] == "A01:2021"
    assert "CWE-200" in res1["default_cwes"]

    res2 = map_finding_to_owasp("Missing HSTS security header")
    assert res2["owasp_id"] == "A02:2021"

    res3 = map_finding_to_owasp("SQL Injection in login form")
    assert res3["owasp_id"] == "A03:2021"


def test_exploit_quality_assessment():
    """Verify AI exploit quality grading."""
    # High viability exploit
    high_assess = assess_exploit_quality("phpinfo-disclosure")
    assert high_assess.usability_rank == UsabilityRank.HIGH
    assert high_assess.prerequisites_met is True

    # Low viability / noisy exploit
    low_assess = assess_exploit_quality("heavy-blind-sqli")
    assert low_assess.usability_rank == UsabilityRank.LOW


def test_composite_scoring_prioritization():
    """Verify that composite scoring prioritizes higher-quality exploits."""
    cand_high = {"id": "c1", "cvss": 8.0, "exposure": 1.0}
    assess_high = ExploitAssessment(
        candidate_id="c1",
        usability_rank=UsabilityRank.HIGH,
    )

    cand_low = {"id": "c2", "cvss": 8.0, "exposure": 1.0}
    assess_low = ExploitAssessment(
        candidate_id="c2",
        usability_rank=UsabilityRank.LOW,
    )

    score_high = calculate_composite_score(cand_high, assess_high)
    score_low = calculate_composite_score(cand_low, assess_low)

    assert score_high > score_low


def test_run_gap1_triage_queue_order():
    """Verify triage outputs a descending sorted candidate queue."""
    candidates = run_gap1_triage("docker_pivot")
    assert len(candidates) > 0
    scores = [c["composite_score"] for c in candidates]
    assert scores == sorted(scores, reverse=True)
