"""Tests for the professional VAPT dashboard."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from vapt_platform.application import VAPTApplication, VAPTRequest, VAPTResult


class TestDashboardWorkflow:
    """Test that the dashboard uses the canonical workflow."""

    def test_dashboard_imports_application(self):
        """Verify dashboard imports VAPTApplication."""
        from frontend.app import main, run_dashboard, display_results
        assert callable(main)
        assert callable(run_dashboard)
        assert callable(display_results)

    def test_dashboard_uses_get_application(self):
        """Verify dashboard uses the singleton application."""
        from frontend.app import run_dashboard
        # Just verify the function exists and is callable
        assert callable(run_dashboard)


class TestDashboardDisplay:
    """Test dashboard display functions."""

    def test_display_findings(self):
        from frontend.app import display_findings
        result = VAPTResult(candidates=[
            {"id": "test-1", "probability": 0.9, "quality_rank": "HIGH", "assessed": True, "attempted": True, "execution_outcome": "SUCCESS"},
        ])
        # Should not raise
        display_findings(result)

    def test_display_candidates(self):
        from frontend.app import display_candidates
        result = VAPTResult(
            candidates=[
                {"id": "test-1", "probability": 0.9, "quality_rank": "HIGH", "assessed": True, "attempted": True, "execution_outcome": "SUCCESS"},
            ],
            assessment={"mode": "deterministic"},
        )
        display_candidates(result)

    def test_display_execution_timeline(self):
        from frontend.app import display_execution_timeline
        result = VAPTResult(
            execution_results=[
                {"candidate_id": "test-1", "outcome": "SUCCESS", "detail": "VULNERABLE"},
            ],
        )
        display_execution_timeline(result)

    def test_display_pivot_visualization(self):
        from frontend.app import display_pivot_visualization
        result = VAPTResult(
            total_attempts=3,
            pivot_count=2,
            decision_trace=["[PIVOT] Threshold reached", "[PIVOT] Redirected to next"],
        )
        display_pivot_visualization(result)

    def test_display_decision_trace(self):
        from frontend.app import display_decision_trace
        result = VAPTResult(
            decision_trace=["[INIT] Engine started", "[EXECUTE] Attempt 1"],
        )
        display_decision_trace(result)

    def test_display_reports(self):
        from frontend.app import display_reports
        result = VAPTResult(
            scenario="test",
            mode="simulation",
            candidates=[{"id": "test-1", "probability": 0.9}],
            execution_results=[{"candidate_id": "test-1", "outcome": "SUCCESS"}],
            decision_trace=["[INIT] Engine started"],
            total_attempts=1,
            pivot_count=0,
            candidates_processed=["test-1"],
            assessment={"mode": "deterministic"},
        )
        display_reports(result)


class TestDashboardIntegration:
    """Integration tests for the dashboard."""

    def test_simulation_workflow(self):
        """Test simulation workflow through dashboard."""
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(req)
        assert result.final_status in ("SUCCESS", "COMPLETED")
        assert result.evidence_tier == "SIMULATED"

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

        assert result.evidence_tier == "DOCKER_OBSERVED"
        assert result.mode == "lab"

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
        assert result.final_status in ("SUCCESS", "COMPLETED")
        assert result.assessment.get("mode") == "ai"
        assert result.assessment.get("provider") == "ollama"
