"""Tests for multi-agent orchestration layer (M8)."""

from __future__ import annotations

import pytest

from vapt_platform.orchestration import (
    AttackAction,
    AttackPlan,
    ExecutionResult,
    OrchestrationResult,
    OrchestrationStatus,
    Orchestrator,
    Planner,
    ValidationResult,
    Validator,
)
from vapt_platform.authorization import (
    AuditAction,
    AuditLogger,
    AuthorizationRecord,
    AuthorizationStatus,
    AuthorizationTracker,
    ScopeEnforcer,
)


# ---------------------------------------------------------------------------
# Planner tests
# ---------------------------------------------------------------------------


class TestPlanner:
    def test_empty_graph_returns_empty_plan(self):
        planner = Planner(graph=None)
        plan = planner.generate_plan()
        assert plan.actions == []

    def test_plan_has_valid_id(self):
        planner = Planner(graph=None)
        plan = planner.generate_plan()
        assert plan.plan_id == "empty"


# ---------------------------------------------------------------------------
# Executor tests
# ---------------------------------------------------------------------------


class TestExecutor:
    def test_empty_plan_returns_empty_results(self):
        from vapt_platform.orchestration import Executor
        executor = Executor()
        results = executor.execute_plan(AttackPlan(plan_id="test", actions=[]))
        assert results == []


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


class TestValidator:
    def test_validates_success_outcome(self):
        validator = Validator()
        plan = AttackPlan(
            plan_id="test",
            actions=[AttackAction(action_id="a1", target="host1", cve="CVE-2021-44228")],
        )
        results = [
            ExecutionResult(action_id="a1", status="completed", outcome="SUCCESS", attempts=1),
        ]
        validations = validator.validate(plan, results)
        assert len(validations) == 1
        assert validations[0].is_valid is True
        assert validations[0].confidence == 0.95

    def test_validates_failure_outcome(self):
        validator = Validator()
        plan = AttackPlan(
            plan_id="test",
            actions=[AttackAction(action_id="a1", target="host1")],
        )
        results = [
            ExecutionResult(action_id="a1", status="completed", outcome="FAIL_TIMEOUT", attempts=2),
        ]
        validations = validator.validate(plan, results)
        assert len(validations) == 1
        assert validations[0].is_valid is True
        assert validations[0].confidence == 0.8

    def test_missing_result_is_invalid(self):
        validator = Validator()
        plan = AttackPlan(
            plan_id="test",
            actions=[AttackAction(action_id="a1", target="host1")],
        )
        validations = validator.validate(plan, [])
        assert len(validations) == 1
        assert validations[0].is_valid is False
        assert validations[0].confidence == 0.0


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------


class TestOrchestrator:
    def test_orchestrator_initializes(self):
        orch = Orchestrator(graph=None)
        assert orch.planner is not None
        assert orch.executor is not None
        assert orch.validator is not None

    def test_run_with_no_graph(self):
        orch = Orchestrator(graph=None)
        result = orch.run()
        assert result.status == OrchestrationStatus.COMPLETED
        assert result.plan is not None
        assert result.plan.actions == []

    def test_run_result_has_expected_fields(self):
        orch = Orchestrator(graph=None)
        result = orch.run()
        assert hasattr(result, "total_attempts")
        assert hasattr(result, "candidates_processed")
        assert hasattr(result, "validation_results")


# ---------------------------------------------------------------------------
# AuthorizationTracker tests
# ---------------------------------------------------------------------------


class TestAuthorizationTracker:
    def test_default_allowlist_contains_loopback(self):
        tracker = AuthorizationTracker()
        assert "127.0.0.1" in tracker.allowlist

    def test_authorize_target(self):
        tracker = AuthorizationTracker()
        record = tracker.authorize("10.0.0.1", authorized_by="test_user")
        assert record.target == "10.0.0.1"
        assert record.authorized_by == "test_user"
        assert record.status == AuthorizationStatus.AUTHORIZED

    def test_is_authorized(self):
        tracker = AuthorizationTracker()
        tracker.authorize("10.0.0.1", authorized_by="test_user")
        assert tracker.is_authorized("10.0.0.1") is True

    def test_is_not_authorized(self):
        tracker = AuthorizationTracker()
        assert tracker.is_authorized("192.168.1.100") is False

    def test_revoke_authorization(self):
        tracker = AuthorizationTracker()
        tracker.authorize("10.0.0.1", authorized_by="test_user")
        assert tracker.is_authorized("10.0.0.1") is True
        tracker.revoke("10.0.0.1")
        assert tracker.is_authorized("10.0.0.1") is False

    def test_get_authorization(self):
        tracker = AuthorizationTracker()
        tracker.authorize("10.0.0.1", authorized_by="test_user", scope=["80", "443"])
        record = tracker.get_authorization("10.0.0.1")
        assert record is not None
        assert record.scope == ["80", "443"]

    def test_get_all_authorizations(self):
        tracker = AuthorizationTracker()
        tracker.authorize("10.0.0.1", authorized_by="user1")
        tracker.authorize("10.0.0.2", authorized_by="user2")
        all_auths = tracker.get_all_authorizations()
        assert len(all_auths) == 2


# ---------------------------------------------------------------------------
# ScopeEnforcer tests
# ---------------------------------------------------------------------------


class TestScopeEnforcer:
    def test_validate_authorized_target(self):
        tracker = AuthorizationTracker()
        tracker.authorize("10.0.0.1", authorized_by="test_user")
        enforcer = ScopeEnforcer(tracker)
        assert enforcer.validate_target("10.0.0.1") is True

    def test_validate_unauthorized_target_raises(self):
        tracker = AuthorizationTracker()
        enforcer = ScopeEnforcer(tracker)
        with pytest.raises(ValueError):
            enforcer.validate_target("192.168.1.100")

    def test_validate_scope_with_authorized_ports(self):
        tracker = AuthorizationTracker()
        tracker.authorize("10.0.0.1", authorized_by="test_user", scope=["80", "443"])
        enforcer = ScopeEnforcer(tracker)
        assert enforcer.validate_scope("10.0.0.1", ports=[80, 443]) is True

    def test_validate_scope_with_unauthorized_port_raises(self):
        tracker = AuthorizationTracker()
        tracker.authorize("10.0.0.1", authorized_by="test_user", scope=["80"])
        enforcer = ScopeEnforcer(tracker)
        with pytest.raises(ValueError):
            enforcer.validate_scope("10.0.0.1", ports=[80, 8080])


# ---------------------------------------------------------------------------
# AuditLogger tests
# ---------------------------------------------------------------------------


class TestAuditLogger:
    def test_log_entry(self):
        logger = AuditLogger()
        entry = logger.log(
            actor="test_user",
            action=AuditAction.AUTHORIZE,
            target="10.0.0.1",
            result="authorized",
        )
        assert entry.actor == "test_user"
        assert entry.action == "AUTHORIZE"
        assert entry.target == "10.0.0.1"
        assert entry.result == "authorized"

    def test_entry_count(self):
        logger = AuditLogger()
        assert logger.entry_count == 0
        logger.log("user", AuditAction.AUTHORIZE, "10.0.0.1", "ok")
        assert logger.entry_count == 1

    def test_get_entries_filter_by_target(self):
        logger = AuditLogger()
        logger.log("user", AuditAction.AUTHORIZE, "10.0.0.1", "ok")
        logger.log("user", AuditAction.AUTHORIZE, "10.0.0.2", "ok")
        entries = logger.get_entries(target="10.0.0.1")
        assert len(entries) == 1
        assert entries[0].target == "10.0.0.1"

    def test_get_entries_filter_by_action(self):
        logger = AuditLogger()
        logger.log("user", AuditAction.AUTHORIZE, "10.0.0.1", "ok")
        logger.log("user", AuditAction.EXECUTE, "10.0.0.1", "ok")
        entries = logger.get_entries(action=AuditAction.EXECUTE)
        assert len(entries) == 1
        assert entries[0].action == "EXECUTE"

    def test_export(self, tmp_path):
        logger = AuditLogger()
        logger.log("user", AuditAction.AUTHORIZE, "10.0.0.1", "ok")
        export_path = str(tmp_path / "audit.json")
        logger.export(export_path)
        with open(export_path) as f:
            lines = f.readlines()
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_authorization_workflow(self):
        tracker = AuthorizationTracker()
        enforcer = ScopeEnforcer(tracker)
        audit = AuditLogger()

        # Authorize
        tracker.authorize("10.0.0.1", authorized_by="admin", scope=["80", "443"])
        audit.log("admin", AuditAction.AUTHORIZE, "10.0.0.1", "authorized")

        # Validate
        assert enforcer.validate_scope("10.0.0.1", ports=[80]) is True
        audit.log("system", AuditAction.VALIDATE, "10.0.0.1", "valid")

        # Check audit trail
        assert audit.entry_count == 2

    def test_orchestrator_with_graph(self):
        """Test orchestrator with a mock graph."""
        class MockGraph:
            def get_attack_paths(self, source, target):
                return [[{"host": "10.0.0.1", "cve": "CVE-2021-44228", "port": 8080}]]

            def get_critical_vulns(self, host):
                return [{"host": "10.0.0.1", "cve": "CVE-2021-44228", "port": 8080, "severity": "critical"}]

        orch = Orchestrator(graph=MockGraph())
        result = orch.run()
        assert result.status == OrchestrationStatus.COMPLETED
        assert result.plan is not None
        assert len(result.plan.actions) >= 1
