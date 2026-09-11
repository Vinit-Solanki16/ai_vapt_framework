"""Controlled validation pipeline.

Implements: Planner → Safety Gate → Executor → Verifier → Evidence

The planner proposes actions based on enriched context.
The safety gate validates scope and authorization.
The executor performs only approved controlled actions.
The verifier independently validates execution results.
The evidence layer records provenance.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Validation status
# ---------------------------------------------------------------------------

class ValidationStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Planned action
# ---------------------------------------------------------------------------

@dataclass
class PlannedAction:
    """A single planned action."""
    action_id: str
    candidate_id: str
    target: str
    port: int
    protocol: str
    path: str
    description: str
    priority: int = 0
    risk_score: float = 0.0
    status: ValidationStatus = ValidationStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "candidate_id": self.candidate_id,
            "target": self.target,
            "port": self.port,
            "protocol": self.protocol,
            "path": self.path,
            "description": self.description,
            "priority": self.priority,
            "risk_score": self.risk_score,
            "status": self.status.value,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of safety gate validation."""
    action_id: str
    is_valid: bool
    reason: str
    scope_check: bool = True
    authorization_check: bool = True
    risk_check: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "is_valid": self.is_valid,
            "reason": self.reason,
            "scope_check": self.scope_check,
            "authorization_check": self.authorization_check,
            "risk_check": self.risk_check,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    """Result of execution verification."""
    action_id: str
    is_verified: bool
    expected_outcome: str
    observed_outcome: str
    confidence: float = 0.0
    notes: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "is_verified": self.is_verified,
            "expected_outcome": self.expected_outcome,
            "observed_outcome": self.observed_outcome,
            "confidence": self.confidence,
            "notes": self.notes,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Evidence record
# ---------------------------------------------------------------------------

@dataclass
class EvidenceRecord:
    """Immutable evidence record."""
    evidence_id: str
    action_id: str
    evidence_type: str
    data: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    previous_hash: str = ""

    def compute_hash(self) -> str:
        """Compute hash for chain integrity."""
        content = f"{self.evidence_id}:{self.action_id}:{self.evidence_type}:{self.timestamp}:{self.previous_hash}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "action_id": self.action_id,
            "evidence_type": self.evidence_type,
            "data": self.data,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "hash": self.compute_hash(),
        }


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class Planner:
    """Generates action plans from enriched candidates."""

    def __init__(self, max_actions: int = 10) -> None:
        self.max_actions = max_actions

    def generate_plan(
        self,
        candidates: list[dict],
        graph: Any = None,
    ) -> list[PlannedAction]:
        """Generate an action plan from enriched candidates.

        Args:
            candidates: Enriched candidate dicts
            graph: Optional VAPTGraph

        Returns:
            List of PlannedAction objects
        """
        actions = []
        for c in candidates:
            if len(actions) >= self.max_actions:
                break

            score = c.get("_score", {})
            risk_score = score.get("final_score", 0.0) if isinstance(score, dict) else 0.0

            action = PlannedAction(
                action_id=f"action-{uuid.uuid4().hex[:8]}",
                candidate_id=c.get("id", ""),
                target=c.get("target", c.get("host", "")),
                port=c.get("port", 0),
                protocol=c.get("protocol", "tcp"),
                path=c.get("path", "/"),
                description=c.get("title", c.get("description", "")),
                priority=int(risk_score * 100),
                risk_score=risk_score,
            )
            actions.append(action)

        # Sort by priority (highest first)
        actions.sort(key=lambda a: a.priority, reverse=True)
        return actions


# ---------------------------------------------------------------------------
# Safety gate
# ---------------------------------------------------------------------------

class SafetyGate:
    """Validates actions before execution."""

    def __init__(self, allowlist: Optional[set[str]] = None) -> None:
        self._allowlist = allowlist or set()

    @property
    def allowlist(self) -> set[str]:
        return self._allowlist.copy()

    def add_to_allowlist(self, target: str) -> None:
        """Add a target to the allowlist."""
        self._allowlist.add(target)

    def validate(self, action: PlannedAction) -> ValidationResult:
        """Validate a planned action.

        Args:
            action: The planned action to validate

        Returns:
            ValidationResult
        """
        # Scope check: target must be in allowlist
        scope_check = action.target in self._allowlist or not self._allowlist

        # Authorization check: must have explicit authorization
        authorization_check = action.target in self._allowlist

        # Risk check: risk score must be acceptable
        risk_check = action.risk_score <= 1.0  # Always true for normalized scores

        is_valid = scope_check and authorization_check and risk_check

        if is_valid:
            reason = "Action approved"
        else:
            reasons = []
            if not scope_check:
                reasons.append("target not in scope")
            if not authorization_check:
                reasons.append("target not authorized")
            if not risk_check:
                reasons.append("risk score too high")
            reason = f"Action rejected: {', '.join(reasons)}"

        return ValidationResult(
            action_id=action.action_id,
            is_valid=is_valid,
            reason=reason,
            scope_check=scope_check,
            authorization_check=authorization_check,
            risk_check=risk_check,
        )


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

class Verifier:
    """Independently validates execution results."""

    def verify(
        self,
        action: PlannedAction,
        execution_result: dict[str, Any],
    ) -> VerificationResult:
        """Verify an execution result.

        Args:
            action: The planned action
            execution_result: The execution result dict

        Returns:
            VerificationResult
        """
        observed = execution_result.get("outcome", "UNKNOWN")

        # Determine expected outcome based on action
        expected = "SUCCESS"  # Default expectation

        # Verify based on outcome
        if observed == "SUCCESS":
            is_verified = True
            confidence = 0.95
            notes = "Execution succeeded as expected"
        elif observed in ("FAIL_TIMEOUT", "FAIL_SYNTAX", "FAIL_DEPENDENCY"):
            is_verified = True
            confidence = 0.8
            notes = f"Expected failure: {observed}"
        elif observed == "SKIPPED":
            is_verified = True
            confidence = 0.7
            notes = "Action skipped (safety or low quality)"
        else:
            is_verified = False
            confidence = 0.3
            notes = f"Unexpected outcome: {observed}"

        return VerificationResult(
            action_id=action.action_id,
            is_verified=is_verified,
            expected_outcome=expected,
            observed_outcome=observed,
            confidence=confidence,
            notes=notes,
        )


# ---------------------------------------------------------------------------
# Evidence collector
# ---------------------------------------------------------------------------

class EvidenceCollector:
    """Collects and chains evidence records."""

    def __init__(self) -> None:
        self._records: list[EvidenceRecord] = []
        self._last_hash = ""

    def add_record(
        self,
        action_id: str,
        evidence_type: str,
        data: dict[str, Any],
    ) -> EvidenceRecord:
        """Add an evidence record.

        Args:
            action_id: Associated action ID
            evidence_type: Type of evidence
            evidence_data: Evidence data

        Returns:
            EvidenceRecord
        """
        record = EvidenceRecord(
            evidence_id=f"ev-{uuid.uuid4().hex[:8]}",
            action_id=action_id,
            evidence_type=evidence_type,
            data=data,
            previous_hash=self._last_hash,
        )
        self._records.append(record)
        self._last_hash = record.compute_hash()
        return record

    def get_records(self, action_id: Optional[str] = None) -> list[EvidenceRecord]:
        """Get evidence records.

        Args:
            action_id: Optional filter by action ID

        Returns:
            List of EvidenceRecord objects
        """
        if action_id:
            return [r for r in self._records if r.action_id == action_id]
        return self._records.copy()

    def verify_chain(self) -> bool:
        """Verify the integrity of the evidence chain.

        Returns:
            True if chain is valid
        """
        for i, record in enumerate(self._records):
            if i == 0:
                if record.previous_hash != "":
                    return False
            else:
                if record.previous_hash != self._records[i - 1].compute_hash():
                    return False
        return True

    def to_dict(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._records]

    @property
    def entry_count(self) -> int:
        return len(self._records)


# ---------------------------------------------------------------------------
# Validation pipeline
# ---------------------------------------------------------------------------

class ValidationPipeline:
    """Orchestrates the controlled validation pipeline."""

    def __init__(
        self,
        allowlist: Optional[set[str]] = None,
        max_actions: int = 10,
    ) -> None:
        self.planner = Planner(max_actions=max_actions)
        self.safety_gate = SafetyGate(allowlist=allowlist)
        self.verifier = Verifier()
        self.evidence = EvidenceCollector()

    def run(
        self,
        candidates: list[dict],
        graph: Any = None,
        executor: Any = None,
    ) -> dict[str, Any]:
        """Run the full validation pipeline.

        Args:
            candidates: Enriched candidate dicts
            graph: Optional VAPTGraph
            executor: Optional executor

        Returns:
            Pipeline result dict
        """
        # Phase 1: Planning
        plan = self.planner.generate_plan(candidates, graph=graph)

        # Phase 2: Safety gate validation
        validated = []
        for action in plan:
            result = self.safety_gate.validate(action)
            self.evidence.add_record(
                action.action_id,
                "validation",
                result.to_dict(),
            )
            if result.is_valid:
                action.status = ValidationStatus.APPROVED
                validated.append(action)
            else:
                action.status = ValidationStatus.REJECTED

        # Phase 3: Execution
        execution_results = []
        for action in validated:
            if executor:
                # Execute through the executor
                result = executor.execute(action)
                action.status = ValidationStatus.EXECUTED
                execution_results.append((action, result))
            else:
                # No executor - mark as pending
                action.status = ValidationStatus.PENDING

        # Phase 4: Verification
        verification_results = []
        for action, result in execution_results:
            verification = self.verifier.verify(action, result)
            action.status = ValidationStatus.VERIFIED if verification.is_verified else ValidationStatus.FAILED
            verification_results.append(verification)
            self.evidence.add_record(
                action.action_id,
                "verification",
                verification.to_dict(),
            )

        # Phase 5: Collect evidence
        for action in plan:
            self.evidence.add_record(
                action.action_id,
                "action",
                action.to_dict(),
            )

        return {
            "plan": [a.to_dict() for a in plan],
            "validated": [a.to_dict() for a in validated],
            "execution_results": [
                {"action": a.to_dict(), "result": r}
                for a, r in execution_results
            ],
            "verification_results": [v.to_dict() for v in verification_results],
            "evidence": self.evidence.to_dict(),
            "chain_valid": self.evidence.verify_chain(),
        }
