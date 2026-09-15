"""Tests for scan_adapter.py (Phase 3).

Verifies that scanner output is correctly normalized into ActionCandidates.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from decision_engine.core.schemas import ActionCandidate

from decision_engine.adapters.scan_adapter import (
    candidates_from_scan,
    findings_to_candidates,
    candidates_to_scenario,
)


class TestFindingsToCandidates:
    def test_empty_findings(self):
        result = findings_to_candidates([])
        assert result == []

    def test_single_finding(self):
        f = MagicMock()
        f.finding_id = "CVE-2021-44228"
        f.rule_id = ""
        f.port = 8080
        f.metadata = {"epss_score": 0.95}
        result = findings_to_candidates([f])
        assert len(result) == 1
        assert isinstance(result[0], ActionCandidate)
        assert result[0].id == "CVE-2021-44228"
        assert result[0].probability == 0.95
        assert result[0].quality_rank is None
        assert result[0].ground_truth is None

    def test_finding_with_no_id_uses_rule_id(self):
        f = MagicMock()
        f.finding_id = ""
        f.rule_id = "RULE-001"
        f.port = 80
        f.metadata = {}
        result = findings_to_candidates([f])
        assert result[0].id == "RULE-001"

    def test_finding_with_port_only(self):
        f = MagicMock()
        f.finding_id = ""
        f.rule_id = ""
        f.port = 80
        f.metadata = {}
        result = findings_to_candidates([f])
        assert result[0].id == "PORT-80"

    def test_finding_with_no_port(self):
        f = MagicMock()
        f.finding_id = ""
        f.rule_id = ""
        f.port = None
        f.metadata = {}
        result = findings_to_candidates([f])
        assert result[0].id == "PORT-UNKNOWN"

    def test_probability_clamped_to_0_1(self):
        f = MagicMock()
        f.finding_id = "CVE-TEST"
        f.rule_id = ""
        f.port = 80
        f.metadata = {"epss_score": 1.5}
        result = findings_to_candidates([f])
        assert result[0].probability == 1.0

    def test_negative_probability_clamped(self):
        f = MagicMock()
        f.finding_id = "CVE-TEST"
        f.rule_id = ""
        f.port = 80
        f.metadata = {"epss_score": -0.5}
        result = findings_to_candidates([f])
        assert result[0].probability == 0.0

    def test_multiple_findings(self):
        findings = []
        for i in range(5):
            f = MagicMock()
            f.finding_id = f"CVE-2021-000{i}"
            f.rule_id = ""
            f.port = 8000 + i
            f.metadata = {"epss_score": 0.1 * (i + 1)}
            findings.append(f)
        result = findings_to_candidates(findings)
        assert len(result) == 5
        assert all(isinstance(c, ActionCandidate) for c in result)


class TestCandidatesFromScan:
    def test_calls_registry_parse(self):
        with patch("decision_engine.adapters.scan_adapter.get_scanner_registry") as mock_reg:
            mock_reg.return_value.parse.return_value = []
            result = candidates_from_scan("test.json")
            mock_reg.return_value.parse.assert_called_once_with("test.json")
        assert result == []

    def test_with_findings(self):
        mock_f = MagicMock()
        mock_f.finding_id = "CVE-2021-44228"
        mock_f.rule_id = ""
        mock_f.port = 8080
        mock_f.metadata = {"epss_score": 0.95}
        with patch("decision_engine.adapters.scan_adapter.get_scanner_registry") as mock_reg:
            mock_reg.return_value.parse.return_value = [mock_f]
            result = candidates_from_scan("test.json")
        assert len(result) == 1
        assert result[0].id == "CVE-2021-44228"


class TestCandidatesToScenario:
    def test_empty(self):
        assert candidates_to_scenario([]) == []

    def test_single_candidate(self):
        c = ActionCandidate(id="X", probability=0.5)
        result = candidates_to_scenario([c])
        assert result == [{"id": "X", "probability": 0.5, "ground_truth": None}]

    def test_with_ground_truth(self):
        from decision_engine.core.schemas import Outcome
        c = ActionCandidate(id="X", probability=0.5, ground_truth=Outcome.SUCCESS)
        result = candidates_to_scenario([c])
        assert result[0]["ground_truth"] == "SUCCESS"