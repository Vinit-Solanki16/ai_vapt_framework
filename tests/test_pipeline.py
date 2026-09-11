"""Tests for controlled validation pipeline."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from vapt_platform.pipeline import (
    ValidationPipeline,
    Planner,
    SafetyGate,
    Verifier,
    EvidenceCollector,
    PlannedAction,
    ValidationStatus,
)
from vapt_platform.application import VAPTApplication, VAPTRequest


# ---------------------------------------------------------------------------
# Planner tests
# ---------------------------------------------------------------------------

class TestPlanner:
    def test_create_planner(self):
        planner = Planner(max_actions=5)
        assert planner.max_actions == 5

    def test_generate_plan(self):
        planner = Planner()
        candidates = [
            {"id": "test-1", "probability": 0.8, "host": "10.0.0.1", "port": 80},
        ]
        plan = planner.generate_plan(candidates)
        assert len(plan) == 1
        assert plan[0].candidate_id == "test-1"

    def test_max_actions(self):
        planner = Planner(max_actions=2)
        candidates = [
            {"id": f"test-{i}", "probability": 0.5} for i in range(5)
        ]
        plan = planner.generate_plan(candidates)
        assert len(plan) == 2


# ---------------------------------------------------------------------------
# Safety gate tests
# ---------------------------------------------------------------------------

class TestSafetyGate:
    def test_create_gate(self):
        gate = SafetyGate(allowlist={"10.0.0.1"})
        assert "10.0.0.1" in gate.allowlist

    def test_validate_approved(self):
        gate = SafetyGate(allowlist={"10.0.0.1"})
        action = PlannedAction(
            action_id="a1",
            candidate_id="c1",
            target="10.0.0.1",
            port=80,
            protocol="tcp",
            path="/",
            description="test",
        )
        result = gate.validate(action)
        assert result.is_valid
        assert result.authorization_check

    def test_validate_rejected(self):
        gate = SafetyGate(allowlist={"10.0.0.1"})
        action = PlannedAction(
            action_id="a1",
            candidate_id="c1",
            target="192.168.1.100",
            port=80,
            protocol="tcp",
            path="/",
            description="test",
        )
        result = gate.validate(action)
        assert not result.is_valid
        assert not result.authorization_check

    def test_add_to_allowlist(self):
        gate = SafetyGate()
        gate.add_to_allowlist("10.0.0.1")
        assert "10.0.0.1" in gate.allowlist


# ---------------------------------------------------------------------------
# Verifier tests
# ---------------------------------------------------------------------------

class TestVerifier:
    def test_verify_success(self):
        verifier = Verifier()
        action = PlannedAction(
            action_id="a1",
            candidate_id="c1",
            target="10.0.0.1",
            port=80,
            protocol="tcp",
            path="/",
            description="test",
        )
        result = verifier.verify(action, {"outcome": "SUCCESS"})
        assert result.is_verified
        assert result.confidence >= 0.9

    def test_verify_failure(self):
        verifier = Verifier()
        action = PlannedAction(
            action_id="a1",
            candidate_id="c1",
            target="10.0.0.1",
            port=80,
            protocol="tcp",
            path="/",
            description="test",
        )
        result = verifier.verify(action, {"outcome": "FAIL_TIMEOUT"})
        assert result.is_verified  # Expected failure
        assert result.confidence >= 0.7


# ---------------------------------------------------------------------------
# Evidence collector tests
# ---------------------------------------------------------------------------

class TestEvidenceCollector:
    def test_create(self):
        collector = EvidenceCollector()
        assert collector.entry_count == 0

    def test_add_record(self):
        collector = EvidenceCollector()
        record = collector.add_record("a1", "test", {"key": "value"})
        assert record.evidence_id.startswith("ev-")
        assert record.action_id == "a1"
        assert collector.entry_count == 1

    def test_chain_integrity(self):
        collector = EvidenceCollector()
        collector.add_record("a1", "test1", {"k": "v1"})
        collector.add_record("a2", "test2", {"k": "v2"})
        collector.add_record("a3", "test3", {"k": "v3"})
        assert collector.verify_chain()

    def test_get_records(self):
        collector = EvidenceCollector()
        collector.add_record("a1", "test1", {})
        collector.add_record("a2", "test2", {})
        records = collector.get_records("a1")
        assert len(records) == 1


# ---------------------------------------------------------------------------
# Validation pipeline tests
# ---------------------------------------------------------------------------

class TestValidationPipeline:
    def test_create(self):
        pipeline = ValidationPipeline(allowlist={"10.0.0.1"})
        assert pipeline.planner is not None
        assert pipeline.safety_gate is not None

    def test_run_pipeline(self):
        pipeline = ValidationPipeline(allowlist={"10.0.0.1"})
        candidates = [
            {"id": "test-1", "host": "10.0.0.1", "port": 80, "probability": 0.8},
        ]
        result = pipeline.run(candidates)
        assert "plan" in result
        assert "validated" in result
        assert "evidence" in result
        assert result["chain_valid"]

    def test_pipeline_rejects_unauthorized(self):
        pipeline = ValidationPipeline(allowlist={"10.0.0.1"})
        candidates = [
            {"id": "test-1", "host": "192.168.1.100", "port": 80, "probability": 0.8},
        ]
        result = pipeline.run(candidates)
        # Should have plan but no validated actions
        assert len(result["plan"]) == 1
        assert len(result["validated"]) == 0


# ---------------------------------------------------------------------------
# Application integration tests
# ---------------------------------------------------------------------------

class TestApplicationPipeline:
    def test_pipeline_in_workflow(self):
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(req)
        assert result.domain.final_status in ("SUCCESS", "COMPLETED")
        assert hasattr(result, "pipeline_summary")
        assert "plan" in result.pipeline_summary
        assert "evidence" in result.pipeline_summary

    def test_pipeline_with_target(self):
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="docker_vuln",
            mode="lab",
            target="172.28.0.2",
            port=8080,
            max_attempts=2,
            assessor_mode="deterministic",
        )
        # Mock the executor to avoid network calls in test
        mock_executor = MagicMock()
        mock_result = MagicMock()
        mock_result.outcome = "SUCCESS"
        mock_result.request_count = 1
        mock_result.detail = "docker-observed(VULNERABLE)"
        mock_result.model_dump.return_value = {
            "outcome": "SUCCESS",
            "request_count": 1,
            "detail": "docker-observed(VULNERABLE)",
        }
        mock_executor.execute.return_value = mock_result
        with patch.object(app, '_build_executor', return_value=mock_executor):
            result = app.run(req)
        # Pipeline summary should be present
        assert hasattr(result, 'pipeline_summary')
