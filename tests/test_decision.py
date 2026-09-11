"""Tests for decision intelligence scoring."""
from __future__ import annotations

import pytest

from vapt_platform.decision_intelligence import DecisionIntelligence, ScoreFactors
from vapt_platform.graph_builder import VAPTGraph
from vapt_platform.normalization import CanonicalFinding
from vapt_platform.application import VAPTApplication, VAPTRequest


# ---------------------------------------------------------------------------
# Score factors tests
# ---------------------------------------------------------------------------

class TestScoreFactors:
    def test_default_values(self):
        factors = ScoreFactors()
        assert factors.base_probability == 0.0
        assert factors.final_score == 0.0

    def test_to_dict(self):
        factors = ScoreFactors(base_probability=0.5, severity_score=0.75, final_score=0.6)
        d = factors.to_dict()
        assert d["base_probability"] == 0.5
        assert d["severity_score"] == 0.75
        assert d["final_score"] == 0.6


# ---------------------------------------------------------------------------
# Decision intelligence tests
# ---------------------------------------------------------------------------

class TestDecisionIntelligence:
    def test_create(self):
        di = DecisionIntelligence()
        assert di is not None

    def test_compute_score_basic(self):
        di = DecisionIntelligence()
        candidate = {"probability": 0.8, "metadata": {"severity": "high"}}
        factors = di.compute_score(candidate)
        assert factors.base_probability == 0.8
        assert factors.severity_score > 0
        assert factors.final_score > 0

    def test_compute_score_with_cvss(self):
        di = DecisionIntelligence()
        candidate = {"probability": 0.5, "metadata": {"cvss_score": 9.5}}
        factors = di.compute_score(candidate)
        assert factors.severity_score == 0.95

    def test_compute_score_with_kev(self):
        di = DecisionIntelligence()
        candidate = {"probability": 0.5, "metadata": {"cisa_kev": True}}
        factors = di.compute_score(candidate)
        assert factors.kev_boost == 1.0

    def test_compute_score_with_ai_quality(self):
        di = DecisionIntelligence()
        candidate = {"probability": 0.5, "quality_rank": "HIGH"}
        factors = di.compute_score(candidate)
        assert factors.ai_quality == 1.0

    def test_rank_candidates(self):
        di = DecisionIntelligence()
        candidates = [
            {"id": "low", "probability": 0.2, "metadata": {"severity": "low"}},
            {"id": "high", "probability": 0.9, "metadata": {"severity": "critical"}},
        ]
        ranked = di.rank_candidates(candidates)
        assert len(ranked) == 2
        # High probability should be first
        assert ranked[0][0]["id"] == "high"

    def test_explanation(self):
        di = DecisionIntelligence()
        candidate = {"probability": 0.8, "metadata": {"severity": "high", "cisa_kev": True}}
        factors = di.compute_score(candidate)
        assert "EPSS" in factors.explanation
        assert "severity" in factors.explanation
        assert "KEV" in factors.explanation


# ---------------------------------------------------------------------------
# Graph-based scoring tests
# ---------------------------------------------------------------------------

class TestGraphBasedScoring:
    def test_asset_exposure(self):
        di = DecisionIntelligence()
        findings = [
            CanonicalFinding(host="10.0.0.1", metadata={"cve_ids": ["CVE-2021-44228"], "severity": "critical"}),
        ]
        graph = VAPTGraph.from_findings(findings)
        candidate = {"probability": 0.5, "host": "10.0.0.1"}
        factors = di.compute_score(candidate, graph=graph)
        assert factors.asset_exposure > 0

    def test_no_graph(self):
        di = DecisionIntelligence()
        candidate = {"probability": 0.5}
        factors = di.compute_score(candidate, graph=None)
        assert factors.asset_exposure == 0.0


# ---------------------------------------------------------------------------
# Application integration tests
# ---------------------------------------------------------------------------

class TestApplicationScoring:
    def test_score_candidates(self):
        app = VAPTApplication()
        candidates = [
            {"id": "test-1", "probability": 0.8, "metadata": {"severity": "high"}},
        ]
        graph = app._build_graph(candidates)
        scored = app._score_candidates(candidates, graph)
        assert len(scored) == 1
        assert "_score" in scored[0]

    def test_scoring_in_workflow(self):
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(req)
        assert result.domain.final_status in ("SUCCESS", "COMPLETED")
        # Scored candidates should be in result
        assert hasattr(result, "scored_candidates")
