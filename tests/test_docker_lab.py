"""Tests for Docker lab integration and real-execution workflow."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from decision_engine.core.schemas import ActionCandidate, Outcome, QualityRank
from prototype.docker_demo_data import (
    docker_vuln_scenario,
    docker_fail_scenario,
    docker_pivot_scenario,
    docker_multi_scenario,
    DOCKER_SCENARIOS,
)
from prototype.execution_layer import create_docker_lab_executor


# ---------------------------------------------------------------------------
# Docker demo data tests
# ---------------------------------------------------------------------------

class TestDockerDemoData:
    def test_docker_vuln_scenario(self):
        s = docker_vuln_scenario()
        assert len(s) == 1
        assert s[0]["id"] == "docker-vuln-1"
        assert "ground_truth" not in s[0]
        assert s[0]["path"] == "/vuln"

    def test_docker_fail_scenario(self):
        s = docker_fail_scenario()
        assert len(s) == 1
        assert s[0]["path"] == "/fail"

    def test_docker_pivot_scenario(self):
        s = docker_pivot_scenario()
        assert len(s) == 2
        assert s[0]["path"] == "/fail"
        assert s[1]["path"] == "/vuln"

    def test_docker_multi_scenario(self):
        s = docker_multi_scenario()
        assert len(s) == 3

    def test_no_ground_truth(self):
        """Docker scenarios must NOT have ground_truth (real execution)."""
        for name, (fn, kwargs) in DOCKER_SCENARIOS.items():
            scenario = fn(**kwargs)
            for c in scenario:
                assert "ground_truth" not in c, f"{name} should not have ground_truth"


# ---------------------------------------------------------------------------
# Docker lab executor tests
# ---------------------------------------------------------------------------

class TestDockerLabExecutor:
    def test_create_docker_lab_executor(self):
        executor = create_docker_lab_executor("172.28.0.2", 8080, "/vuln")
        assert executor.mode == "lab_docker"

    def test_non_allowlisted_target_raises(self):
        with pytest.raises(ValueError, match="not in the lab allowlist"):
            create_docker_lab_executor("8.8.8.8", 8080)

    def test_path_map_per_candidate(self):
        executor = create_docker_lab_executor(
            "172.28.0.2", 8080, "/vuln",
            path_map={"cand-a": "/fail", "cand-b": "/vuln"}
        )
        assert executor.mode == "lab_docker"


# ---------------------------------------------------------------------------
# Integration tests (mocked Docker)
# ---------------------------------------------------------------------------

class TestDockerLabIntegration:
    @patch("urllib.request.urlopen")
    def test_vuln_endpoint_returns_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"outcome": "SUCCESS", "detail": "VULNERABLE"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        executor = create_docker_lab_executor("172.28.0.2", 8080, "/vuln")
        candidate = ActionCandidate(id="test-1", probability=0.9)
        result = executor.execute(candidate)

        assert result.outcome == Outcome.SUCCESS
        assert "docker-observed" in result.detail

    @patch("urllib.request.urlopen")
    def test_fail_endpoint_returns_fail(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"outcome": "FAIL_TIMEOUT", "detail": "NOT_VULNERABLE"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        executor = create_docker_lab_executor("172.28.0.2", 8080, "/fail")
        candidate = ActionCandidate(id="test-2", probability=0.8)
        result = executor.execute(candidate)

        assert result.outcome == Outcome.FAIL_TIMEOUT
        assert "docker-observed" in result.detail

    @patch("urllib.request.urlopen")
    def test_per_candidate_path_map(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"outcome": "FAIL_TIMEOUT", "detail": "NOT_VULNERABLE"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        executor = create_docker_lab_executor(
            "172.28.0.2", 8080, "/vuln",
            path_map={"cand-a": "/fail"}
        )
        candidate = ActionCandidate(id="cand-a", probability=0.7)
        result = executor.execute(candidate)

        assert result.outcome == Outcome.FAIL_TIMEOUT


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

class TestCLIDockerLab:
    def test_cli_uses_application(self):
        """Verify CLI uses VAPTApplication."""
        from prototype.cli import _run_scenario
        assert callable(_run_scenario)

    def test_docker_scenarios_exist(self):
        """Verify Docker scenarios are registered."""
        from prototype.docker_demo_data import DOCKER_SCENARIOS
        assert "docker_vuln" in DOCKER_SCENARIOS
        assert "docker_fail" in DOCKER_SCENARIOS
        assert "docker_pivot" in DOCKER_SCENARIOS
        assert "docker_multi" in DOCKER_SCENARIOS
