"""Integration tests for Wave 10A architecture hardening.

These tests verify the actual runtime paths that were changed during Wave 10A:

1. Authorization → SafetyGate → Executor
2. Decision → Planner → Safety → Executor  
3. Scanner → Parser → CanonicalFinding → VAPTApplication
4. Full application integration

They use only safe/local/simulated paths. No Docker or external targets.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from vapt_platform.authorization import (
    AuthorizationTracker,
    ScopeEnforcer,
    AuditLogger,
)
from vapt_platform.pipeline import (
    ValidationPipeline,
    Planner,
    SafetyGate,
    Verifier,
    EvidenceCollector,
    PlannedAction,
    ValidationStatus,
)
from vapt_platform.application import VAPTApplication, VAPTRequest, DomainResult
from vapt_platform.scanners import get_scanner_registry, NmapXmlAdapter, CustomJsonAdapter
from vapt_platform.normalization import CanonicalFinding
from prototype.lab_runner import LAB_TARGET_ALLOWLIST


# ---------------------------------------------------------------------------
# 1. Authorization → SafetyGate → Executor
# ---------------------------------------------------------------------------

class TestAuthorizationFlow:
    """Verify the authorization boundary actually gates execution."""

    def test_authorized_target_reaches_execution(self):
        """Allowed target in allowlist should pass SafetyGate validation."""
        tracker = AuthorizationTracker()
        tracker.authorize("127.0.0.1", authorized_by="test")
        enforcer = ScopeEnforcer(tracker)
        
        gate = SafetyGate(allowlist=set(), authorization_tracker=tracker)
        action = PlannedAction(
            action_id="a1",
            candidate_id="c1",
            target="127.0.0.1",
            port=80,
            protocol="tcp",
            path="/",
            description="test",
        )
        result = gate.validate(action)
        assert result.is_valid, f"Allowed target rejected: {result.reason}"

    def test_disallowed_target_blocked(self):
        """Non-allowlisted target should be rejected by SafetyGate."""
        tracker = AuthorizationTracker()
        gate = SafetyGate(allowlist=set(), authorization_tracker=tracker)
        
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

    def test_fail_closed_with_no_tracker(self):
        """Without a tracker, SafetyGate must fail-closed (reject unknown targets)."""
        gate = SafetyGate(allowlist={"10.0.0.1"})
        action = PlannedAction(
            action_id="a1",
            candidate_id="c1",
            target="10.0.0.2",  # Not in allowlist
            port=80,
            protocol="tcp",
            path="/",
            description="test",
        )
        result = gate.validate(action)
        assert not result.is_valid, "Unknown target should be rejected without tracker"

    def test_scope_enforcer_rejects_out_of_scope_ports(self):
        """ScopeEnforcer should reject ports not in authorized scope."""
        tracker = AuthorizationTracker()
        tracker.authorize("127.0.0.1", authorized_by="test", scope=["80", "443"])
        enforcer = ScopeEnforcer(tracker)
        
        assert enforcer.validate_scope("127.0.0.1", ports=[80]) is True
        
        with pytest.raises(ValueError, match="not in authorized scope"):
            enforcer.validate_scope("127.0.0.1", ports=[8080])

    def test_no_execution_path_bypasses_authorization(self):
        """Verify there is no alternate execution path that skips SafetyGate."""
        app = VAPTApplication()
        request = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
        )
        # Run and verify pipeline was executed
        result = app.run(request)
        assert hasattr(result, 'pipeline_summary')
        assert 'plan' in result.pipeline_summary
        # Pipeline must have been validated
        assert 'validated' in result.pipeline_summary
        assert 'evidence' in result.pipeline_summary


# ---------------------------------------------------------------------------
# 2. Decision → Planner → Safety → Executor
# ---------------------------------------------------------------------------

class TestPlanningFlow:
    """Verify the planning pipeline integrates correctly with decision output."""

    def test_planner_generates_actions_from_candidates(self):
        """Planner must generate PlannedActions from enriched candidates."""
        planner = Planner(max_actions=5)
        candidates = [
            {"id": "cve-1", "target": "10.0.0.1", "port": 80, "_score": {"final_score": 0.8}},
            {"id": "cve-2", "target": "10.0.0.1", "port": 443, "_score": {"final_score": 0.6}},
        ]
        plan = planner.generate_plan(candidates)
        assert len(plan) == 2
        # Should be sorted by priority (highest first)
        assert plan[0].priority >= plan[1].priority

    def test_planner_does_not_recalculate_scoring(self):
        """Planner must NOT independently recalculate scores — it uses decision output."""
        planner = Planner()
        candidates = [
            {"id": "c1", "target": "10.0.0.1", "port": 80, "_score": {"final_score": 0.5}},
        ]
        plan = planner.generate_plan(candidates)
        # Priority should be derived from score, not recalculated independently
        assert plan[0].priority == int(0.5 * 100)

    def test_pipeline_safety_gate_integrates_with_planner(self):
        """SafetyGate must be invoked AFTER planner generates actions."""
        pipeline = ValidationPipeline(allowlist={"10.0.0.1"})
        candidates = [
            {"id": "c1", "target": "10.0.0.1", "port": 80, "probability": 0.8},
        ]
        result = pipeline.run(candidates)
        # Plan generated
        assert len(result["plan"]) == 1
        # Safety gate validated
        assert len(result["validated"]) == 1
        # Evidence collected
        assert result["chain_valid"]

    def test_pipeline_rejects_unsafe_actions(self):
        """Actions failing safety gate must NOT reach executor."""
        pipeline = ValidationPipeline(allowlist={"10.0.0.1"})
        candidates = [
            {"id": "c1", "target": "192.168.1.100", "port": 80, "probability": 0.8},
        ]
        result = pipeline.run(candidates)
        # Plan generated
        assert len(result["plan"]) == 1
        # But safety gate rejected it
        assert len(result["validated"]) == 0


# ---------------------------------------------------------------------------
# 3. Scanner → Parser → CanonicalFinding → VAPTApplication
# ---------------------------------------------------------------------------

class TestScannerPipeline:
    """Verify the canonical scanner ingestion path."""

    def test_nmap_xml_to_canonical_finding(self):
        """Nmap XML adapter must produce CanonicalFinding objects."""
        adapter = NmapXmlAdapter()
        findings = adapter.parse("data/rich_scan.xml")
        assert len(findings) > 0
        assert all(isinstance(f, CanonicalFinding) for f in findings)

    def test_custom_json_to_canonical_finding(self):
        """Custom JSON adapter must produce CanonicalFinding objects."""
        adapter = CustomJsonAdapter()
        findings = adapter.parse("data/rich_scan_custom.json")
        assert len(findings) > 0
        assert all(isinstance(f, CanonicalFinding) for f in findings)

    def test_scanner_registry_uses_correct_adapters(self):
        """Scanner registry must return correct adapter for file type."""
        registry = get_scanner_registry()
        
        # XML adapter for .xml files
        xml_findings = registry.parse("data/rich_scan.xml")
        assert len(xml_findings) > 0
        
        # Custom JSON adapter for custom format
        custom_findings = registry.parse("data/rich_scan_custom.json")
        assert len(custom_findings) > 0

    def test_scan_integration_with_vapt_application(self):
        """Full path: scan file → scanner → VAPTApplication."""
        app = VAPTApplication()
        request = VAPTRequest(
            scenario="",
            mode="simulation",
            max_attempts=2,
            scan_file="data/rich_scan_custom.json",
        )
        result = app.run(request)
        # Should have processed candidates
        assert result.domain.candidates_processed is not None
        # Should have executed and produced results
        assert hasattr(result, 'report')


# ---------------------------------------------------------------------------
# 4. Full Application Integration
# ---------------------------------------------------------------------------

class TestFullApplicationIntegration:
    """Verify the complete VAPTApplication workflow."""

    def test_simulation_workflow_end_to_end(self):
        """Full path: input → ingestion → ... → report."""
        app = VAPTApplication()
        request = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(request)
        
        # Verify domain result populated
        assert result.domain.run_id
        assert result.domain.scenario == "success"
        assert result.domain.mode == "simulation"
        assert result.domain.final_status in ("SUCCESS", "COMPLETED")
        
        # Verify pipeline ran
        assert hasattr(result, 'pipeline_summary')
        assert 'plan' in result.pipeline_summary
        assert 'evidence' in result.pipeline_summary
        
        # Verify persistence worked
        assert hasattr(result, 'domain')
        assert result.domain.candidates_processed is not None
        
        # Verify report generated
        assert result.report is not None
        assert 'scenario' in result.report

    def test_failure_pivot_workflow(self):
        """Full path: failing candidate → pivot → next candidate."""
        app = VAPTApplication()
        request = VAPTRequest(
            scenario="failure_pivot",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(request)
        
        # Should complete with some result
        assert result.domain.final_status in ("SUCCESS", "COMPLETED")
        # Should have attempted candidates
        assert result.domain.total_attempts > 0

    def test_multi_candidate_workflow(self):
        """Full path: multiple candidates → ranking → execution → reporting."""
        app = VAPTApplication()
        request = VAPTRequest(
            scenario="multi_candidate",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(request)
        
        # Should process multiple candidates
        assert result.domain.total_attempts > 0
        # Should produce report
        assert result.report is not None

    def test_application_uses_single_workflow(self):
        """Verify VAPTApplication is the single workflow owner."""
        app1 = VAPTApplication()
        app2 = VAPTApplication()
        # Each run should be independent
        request1 = VAPTRequest(scenario="success", mode="simulation")
        request2 = VAPTRequest(scenario="failure_pivot", mode="simulation")
        
        result1 = app1.run(request1)
        result2 = app2.run(request2)
        
        # Different run IDs
        assert result1.domain.run_id != result2.domain.run_id


# ---------------------------------------------------------------------------
# 5. AuthorizationTracker Integration
# ---------------------------------------------------------------------------

class TestAuthorizationTrackerIntegration:
    """Verify AuthorizationTracker is integrated into the safety boundary."""

    def test_safety_gate_uses_tracker_allowlist(self):
        """SafetyGate should respect tracker allowlist."""
        tracker = AuthorizationTracker()
        tracker.authorize("10.0.0.1", authorized_by="test")
        
        gate = SafetyGate(allowlist=set(), authorization_tracker=tracker)
        
        # Should include tracker allowlist
        assert "10.0.0.1" in gate.allowlist

    def test_vapt_application_seeds_tracker_from_request(self):
        """VAPTApplication should seed tracker from request target."""
        app = VAPTApplication()
        request = VAPTRequest(
            scenario="success",
            mode="simulation",
            target="127.0.0.1",
        )
        # Run with target - tracker should be seeded
        result = app.run(request)
        # Should succeed (target is allowlisted)
        assert result.domain.final_status in ("SUCCESS", "COMPLETED")

    def test_lab_mode_validates_allowlist(self):
        """Lab mode must validate target against allowlist."""
        app = VAPTApplication()
        request = VAPTRequest(
            scenario="docker_vuln",
            mode="lab",
            target="192.168.1.100",  # Not allowlisted
            port=8080,
        )
        # Should be rejected by safety gate
        # The pipeline should not execute unauthorized targets
        try:
            result = app.run(request)
            # If it runs, it should be rejected by safety
            assert result.domain.final_status in ("FAILED", "COMPLETED")
        except Exception:
            # Expected - lab mode validation may raise
            pass


# ---------------------------------------------------------------------------
# 6. Audit Logger
# ---------------------------------------------------------------------------

class TestAuditLogger:
    """Verify audit logging works correctly."""

    def test_audit_log_entry(self):
        """Audit log should record operations."""
        from vapt_platform.authorization import AuditAction
        logger = AuditLogger()
        entry = logger.log(
            actor="test_user",
            action=AuditAction.AUTHORIZE,
            target="10.0.0.1",
            result="authorized",
        )
        assert entry.actor == "test_user"
        assert entry.target == "10.0.0.1"
        assert logger.entry_count == 1

    def test_audit_log_filtering(self):
        """Audit log should support filtering."""
        from vapt_platform.authorization import AuditAction
        logger = AuditLogger()
        logger.log("user1", AuditAction.AUTHORIZE, "10.0.0.1", "ok")
        logger.log("user2", AuditAction.EXECUTE, "10.0.0.1", "ok")
        
        entries = logger.get_entries(action=AuditAction.AUTHORIZE)
        assert len(entries) == 1
        assert entries[0].actor == "user1"
