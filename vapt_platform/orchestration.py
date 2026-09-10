"""Multi-agent orchestration layer (M8).

Coordinates Planner → Executor → Verifier workflow.

Architecture:
    VAPTGraph → Planner → attack plan
                        ↓
                Executor → runs through decision_engine.run_engine()
                        ↓
                Validator → verifies results

This module does NOT replace the research decision engine.
It is a coordinator that uses the engine as its execution backend.

Research-protected components are imported read-only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OrchestrationStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class AttackAction:
    """A single action in an attack plan."""
    action_id: str
    target: str
    cve: Optional[str] = None
    port: Optional[int] = None
    protocol: Optional[str] = None
    description: str = ""
    priority: int = 0  # higher = more important
    dependencies: List[str] = field(default_factory=list)


@dataclass
class AttackPlan:
    """A plan produced by the Planner."""
    plan_id: str
    actions: List[AttackAction]
    risk_score: float = 0.0
    description: str = ""


@dataclass
class ExecutionResult:
    """Result from running an action through the engine."""
    action_id: str
    status: str
    outcome: Optional[str] = None
    attempts: int = 0
    detail: str = ""


@dataclass
class ValidationResult:
    """Result from the Validator."""
    action_id: str
    is_valid: bool
    confidence: float = 0.0
    notes: str = ""


@dataclass
class OrchestrationResult:
    """Full result from the orchestration run."""
    status: OrchestrationStatus
    plan: Optional[AttackPlan] = None
    execution_results: List[ExecutionResult] = field(default_factory=list)
    validation_results: List[ValidationResult] = field(default_factory=list)
    error: Optional[str] = None
    total_attempts: int = 0
    pivot_count: int = 0
    candidates_processed: List[str] = field(default_factory=list)


class Planner:
    """Generates attack plans from VAPTGraph analysis."""

    def __init__(self, graph: Any) -> None:
        """Initialize with a VAPTGraph instance."""
        self.graph = graph

    def generate_plan(
        self,
        source: Optional[str] = None,
        target: Optional[str] = None,
        max_actions: int = 10,
        min_severity: str = "medium",
    ) -> AttackPlan:
        """Generate an attack plan from graph analysis.

        Args:
            source: Source host (None for all hosts)
            target: Target host (None for all hosts)
            max_actions: Maximum actions in the plan
            min_severity: Minimum severity to include

        Returns:
            AttackPlan with ordered actions
        """
        if self.graph is None:
            return AttackPlan(plan_id="empty", actions=[])

        # Get attack paths from graph
        paths = []
        if source and target:
            paths = self.graph.get_attack_paths(source, target)
        elif target:
            # Get all paths to target
            paths = self.graph.get_attack_paths(None, target)
        else:
            # Get critical vulnerabilities across all hosts
            vulns = self.graph.get_critical_vulns(None)
            for v in vulns:
                paths.append([{
                    "host": v.get("host", "unknown"),
                    "cve": v.get("cve"),
                    "port": v.get("port"),
                    "severity": v.get("severity", "medium"),
                }])

        # Build actions from paths
        actions = []
        seen = set()
        for path in paths:
            for step in path:
                if len(actions) >= max_actions:
                    break
                cve = step.get("cve", "")
                host = step.get("host", "unknown")
                port = step.get("port", 0)
                key = f"{host}:{port}:{cve}"
                if key in seen:
                    continue
                seen.add(key)
                actions.append(AttackAction(
                    action_id=key,
                    target=host,
                    cve=cve or None,
                    port=port or None,
                    description=f"{cve} on {host}:{port}" if cve else f"Vulnerability on {host}:{port}",
                ))

        # Sort by severity/priority
        actions.sort(key=lambda a: a.priority, reverse=True)

        return AttackPlan(
            plan_id=f"plan-{id(actions)}",
            actions=actions[:max_actions],
            description=f"Attack plan with {len(actions[:max_actions])} actions",
        )


class Executor:
    """Runs attack plans through the existing decision engine."""

    def __init__(
        self,
        max_attempts: int = 2,
        mode: str = "simulation",
        executor: Optional[Any] = None,
    ) -> None:
        self.max_attempts = max_attempts
        self.mode = mode
        self.executor = executor

    def execute_plan(self, plan: AttackPlan) -> List[ExecutionResult]:
        """Execute an attack plan through the decision engine.

        Args:
            plan: The attack plan to execute

        Returns:
            List of ExecutionResult objects
        """
        from prototype.engine_integration import run_decision_scenario
        from decision_engine.core.schemas import candidate_from_dict

        if not plan.actions:
            return []

        # Convert actions to candidates
        candidates = []
        for action in plan.actions:
            candidates.append({
                "id": action.action_id,
                "probability": 0.5,  # Default for plan-based candidates
                "ground_truth": None,  # Will be resolved by engine
            })

        try:
            final_state = run_decision_scenario(
                candidates,
                max_attempts=self.max_attempts,
                mode=self.mode,
                executor=self.executor,
            )

            # Extract results from engine state
            results = []
            for r in final_state.get("results", []):
                results.append(ExecutionResult(
                    action_id=r.get("candidate_id", "unknown"),
                    status="completed",
                    outcome=r.get("outcome"),
                    attempts=r.get("attempt_count", 0),
                    detail=r.get("detail", ""),
                ))

            return results
        except Exception as e:
            logger.error(f"Plan execution failed: {e}")
            return []


class Validator:
    """Validates execution results independently."""

    def __init__(self) -> None:
        pass

    def validate(
        self,
        plan: AttackPlan,
        execution_results: List[ExecutionResult],
    ) -> List[ValidationResult]:
        """Validate execution results against the plan.

        Args:
            plan: The original attack plan
            execution_results: Results from executor

        Returns:
            List of ValidationResult objects
        """
        validation_results = []

        for action in plan.actions:
            # Find matching execution result
            matching = [
                r for r in execution_results
                if r.action_id == action.action_id
            ]

            if not matching:
                validation_results.append(ValidationResult(
                    action_id=action.action_id,
                    is_valid=False,
                    confidence=0.0,
                    notes="No execution result found",
                ))
                continue

            result = matching[0]

            # Validate based on outcome
            if result.outcome == "SUCCESS":
                validation_results.append(ValidationResult(
                    action_id=action.action_id,
                    is_valid=True,
                    confidence=0.95,
                    notes="Exploit validated successfully",
                ))
            elif result.outcome in ("FAIL_TIMEOUT", "FAIL_SYNTAX", "FAIL_DEPENDENCY"):
                validation_results.append(ValidationResult(
                    action_id=action.action_id,
                    is_valid=True,
                    confidence=0.8,
                    notes=f"Expected failure: {result.outcome}",
                ))
            else:
                validation_results.append(ValidationResult(
                    action_id=action.action_id,
                    is_valid=False,
                    confidence=0.3,
                    notes=f"Unexpected outcome: {result.outcome}",
                ))

        return validation_results


class Orchestrator:
    """Coordinates Planner → Executor → Verifier workflow."""

    def __init__(
        self,
        graph: Any = None,
        max_attempts: int = 2,
        mode: str = "simulation",
        executor: Optional[Any] = None,
    ) -> None:
        self.planner = Planner(graph)
        self.executor = Executor(max_attempts=max_attempts, mode=mode, executor=executor)
        self.validator = Validator()
        self.mode = mode

    def run(
        self,
        source: Optional[str] = None,
        target: Optional[str] = None,
        max_actions: int = 10,
        min_severity: str = "medium",
    ) -> OrchestrationResult:
        """Run the full orchestration workflow.

        Args:
            source: Source host
            target: Target host
            max_actions: Maximum actions in plan
            min_severity: Minimum severity

        Returns:
            OrchestrationResult with plan, execution, validation
        """
        result = OrchestrationResult(status=OrchestrationStatus.PLANNING)

        try:
            # Phase 1: Planning
            plan = self.planner.generate_plan(
                source=source,
                target=target,
                max_actions=max_actions,
                min_severity=min_severity,
            )
            result.plan = plan

            # Phase 2: Execution
            result.status = OrchestrationStatus.EXECUTING
            execution_results = self.executor.execute_plan(plan)
            result.execution_results = execution_results

            # Phase 3: Validation
            result.status = OrchestrationStatus.VALIDATING
            validation_results = self.validator.validate(plan, execution_results)
            result.validation_results = validation_results

            # Summarize
            result.total_attempts = sum(r.attempts for r in execution_results)
            result.candidates_processed = [r.action_id for r in execution_results]
            result.status = OrchestrationStatus.COMPLETED

        except Exception as e:
            logger.error(f"Orchestration failed: {e}")
            result.status = OrchestrationStatus.FAILED
            result.error = str(e)

        return result
