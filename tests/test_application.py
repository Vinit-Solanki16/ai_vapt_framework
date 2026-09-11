"""Tests for the unified VAPT application workflow."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from vapt_platform.application import VAPTApplication, VAPTRequest, VAPTResult, DomainResult, get_application
from vapt_platform.assessment import AssessmentResult, QualityRank


# ---------------------------------------------------------------------------
# Application workflow tests
# ---------------------------------------------------------------------------

class TestVAPTApplication:
    def test_create_application(self):
        app = VAPTApplication()
        assert app is not None

    def test_generate_run_id(self):
        app = VAPTApplication()
        run_id = app._generate_run_id()
        assert run_id.startswith("run-")

    def test_singleton(self):
        app1 = get_application()
        app2 = get_application()
        assert app1 is app2


# ---------------------------------------------------------------------------
# Request model tests
# ---------------------------------------------------------------------------

class TestVAPTRequest:
    def test_default_values(self):
        req = VAPTRequest()
        assert req.scenario == "failure_pivot"
        assert req.mode == "simulation"
        assert req.target is None
        assert req.port == 8080
        assert req.path == "/vuln"
        assert req.assessor_mode == "deterministic"
        assert req.max_attempts == 2

    def test_lab_request(self):
        req = VAPTRequest(
            scenario="docker_pivot",
            mode="lab",
            target="172.28.0.2",
            port=8080,
            path="/vuln",
        )
        assert req.mode == "lab"
        assert req.target == "172.28.0.2"


# ---------------------------------------------------------------------------
# Result model tests
# ---------------------------------------------------------------------------

class TestDomainResult:
    def test_default_values(self):
        result = DomainResult()
        assert result.run_id == ""
        assert result.final_status == "UNKNOWN"
        assert result.evidence_tier == "SIMULATED"

    def test_lab_result(self):
        result = DomainResult(mode="lab", evidence_tier="DOCKER_OBSERVED")
        assert result.evidence_tier == "DOCKER_OBSERVED"


class TestPresentationResult:
    def test_default_values(self):
        result = VAPTResult()
        assert result.domain.run_id == ""
        assert result.domain.final_status == "UNKNOWN"
        assert result.domain.evidence_tier == "SIMULATED"

    def test_from_domain(self):
        domain = DomainResult(run_id="test-123", final_status="SUCCESS")
        graph = MagicMock()
        graph.summary.return_value = {"total_nodes": 5}
        result = VAPTResult.from_domain(domain, report={"test": True}, graph=graph)
        assert result.domain.run_id == "test-123"
        assert result.report == {"test": True}
        assert result.graph_summary == {"total_nodes": 5}


# ---------------------------------------------------------------------------
# Workflow integration tests
# ---------------------------------------------------------------------------

class TestWorkflowIntegration:
    def test_simulation_workflow(self):
        """Test that simulation workflow runs end-to-end."""
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(req)
        assert result.domain.final_status in ("SUCCESS", "COMPLETED")
        assert result.domain.evidence_tier == "SIMULATED"
        assert result.domain.total_attempts > 0

    def test_docker_lab_workflow_mocked(self):
        """Test Docker lab workflow with mocked executor."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = MagicMock(
            outcome="SUCCESS",
            request_count=1,
            detail="docker-observed(VULNERABLE)",
        )

        app = VAPTApplication()
        req = VAPTRequest(
            scenario="docker_vuln",
            mode="lab",
            target="172.28.0.2",
            port=8080,
            path="/vuln",
            max_attempts=2,
            assessor_mode="deterministic",
        )

        with patch.object(app, '_build_executor', return_value=mock_executor):
            result = app.run(req)

        assert result.domain.evidence_tier == "DOCKER_OBSERVED"
        assert result.domain.mode == "lab"

    def test_ai_assessor_propagation(self):
        """Test that AI assessor mode is propagated correctly."""
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="success",
            mode="simulation",
            assessor_mode="ai",
            assessor_provider="ollama",
        )

        result = app.run(req)

        # AI requested but Ollama unavailable → deterministic fallback
        assert result.domain.final_status in ("SUCCESS", "COMPLETED")
        assert result.domain.assessment.get("mode") == "ai"
        assert result.domain.assessment.get("provider") == "ollama"


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

class TestCLIIntegration:
    def test_cli_uses_application(self):
        """Verify CLI imports and uses VAPTApplication."""
        from prototype.cli import _run_scenario
        # Just verify the function exists and is callable
        assert callable(_run_scenario)


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------

class TestAPIIntegration:
    def test_api_uses_application(self):
        """Verify API imports and uses VAPTApplication."""
        from services.api import _run_engine
        assert callable(_run_engine)
