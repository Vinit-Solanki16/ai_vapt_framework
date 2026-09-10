"""Authorization and audit framework (M9).

Provides authorization tracking, scope enforcement, and audit logging
for the VAPT platform.

This module extends the existing safety model (prototype/lab_runner.py)
and does NOT modify any research-protected components.

Architecture:
    AuthorizationTracker -> validates target authorization
    ScopeEnforcer         -> enforces target scope
    AuditLogger           -> logs all operations
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class AuthorizationStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    PENDING = "PENDING"


class AuditAction(str, Enum):
    AUTHORIZE = "AUTHORIZE"
    DENY = "DENY"
    EXECUTE = "EXECUTE"
    VALIDATE = "VALIDATE"
    PIVOT = "PIVOT"
    REPORT = "REPORT"
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"


@dataclass
class AuthorizationRecord:
    """Records authorization for a target."""
    target: str
    authorized_by: str
    authorized_at: str
    expires_at: Optional[str] = None
    scope: List[str] = field(default_factory=list)
    notes: str = ""
    status: AuthorizationStatus = AuthorizationStatus.AUTHORIZED


@dataclass
class AuditEntry:
    """A single audit log entry."""
    timestamp: str
    actor: str
    action: str
    target: str
    result: str
    details: Dict[str, Any] = field(default_factory=dict)


class AuthorizationTracker:
    """Tracks and validates target authorization."""

    def __init__(self, allowlist: Optional[List[str]] = None) -> None:
        self._allowlist: Set[str] = set(allowlist or [])
        self._authorizations: Dict[str, AuthorizationRecord] = {}
        self._load_default_allowlist()

    def _load_default_allowlist(self) -> None:
        """Load default allowlist from existing lab configuration."""
        try:
            from prototype.lab_runner import LAB_TARGET_ALLOWLIST
            self._allowlist.update(LAB_TARGET_ALLOWLIST)
        except ImportError:
            pass

    @property
    def allowlist(self) -> Set[str]:
        return self._allowlist.copy()

    def authorize(
        self,
        target: str,
        authorized_by: str,
        scope: Optional[List[str]] = None,
        expires_at: Optional[str] = None,
        notes: str = "",
    ) -> AuthorizationRecord:
        """Authorize a target.

        Args:
            target: Target identifier (IP, hostname, CIDR)
            authorized_by: Who authorized this target
            scope: List of authorized ports/protocols
            expires_at: ISO datetime when authorization expires
            notes: Additional notes

        Returns:
            AuthorizationRecord
        """
        record = AuthorizationRecord(
            target=target,
            authorized_by=authorized_by,
            authorized_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            expires_at=expires_at,
            scope=scope or [],
            notes=notes,
            status=AuthorizationStatus.AUTHORIZED,
        )
        self._authorizations[target] = record
        self._allowlist.add(target)
        return record

    def is_authorized(self, target: str) -> bool:
        """Check if a target is authorized.

        Args:
            target: Target to check

        Returns:
            True if authorized
        """
        # Check explicit authorizations first (they override allowlist)
        if target in self._authorizations:
            record = self._authorizations[target]
            if record.status == AuthorizationStatus.DENIED:
                return False
            if record.status == AuthorizationStatus.EXPIRED:
                return False
            if record.status == AuthorizationStatus.AUTHORIZED:
                if record.expires_at:
                    now = datetime.datetime.now(datetime.timezone.utc)
                    expires = datetime.datetime.fromisoformat(record.expires_at)
                    if now > expires:
                        record.status = AuthorizationStatus.EXPIRED
                        return False
                return True

        # Fall back to static allowlist
        if target in self._allowlist:
            return True

        return False

    def get_authorization(self, target: str) -> Optional[AuthorizationRecord]:
        """Get authorization record for a target."""
        return self._authorizations.get(target)

    def revoke(self, target: str) -> bool:
        """Revoke authorization for a target."""
        if target in self._authorizations:
            self._authorizations[target].status = AuthorizationStatus.DENIED
            return True
        return False

    def get_all_authorizations(self) -> List[AuthorizationRecord]:
        """Get all authorization records."""
        return list(self._authorizations.values())


class ScopeEnforcer:
    """Enforces target scope (no out-of-bounds scanning)."""

    def __init__(self, tracker: AuthorizationTracker) -> None:
        self.tracker = tracker

    def validate_target(self, target: str) -> bool:
        """Validate a target is within authorized scope.

        Args:
            target: Target to validate

        Returns:
            True if within scope

        Raises:
            ValueError: If target is not authorized
        """
        if not self.tracker.is_authorized(target):
            raise ValueError(
                f"Target '{target}' is not authorized. "
                f"Authorized targets: {self.tracker.allowlist}"
            )
        return True

    def validate_scope(
        self,
        target: str,
        ports: Optional[List[int]] = None,
        protocols: Optional[List[str]] = None,
    ) -> bool:
        """Validate that ports and protocols are within authorized scope.

        Args:
            target: Target to validate
            ports: List of ports to check
            protocols: List of protocols to check

        Returns:
            True if within scope

        Raises:
            ValueError: If scope is exceeded
        """
        self.validate_target(target)

        record = self.tracker.get_authorization(target)
        if record and record.scope:
            authorized_scope = set(record.scope)
            if ports:
                port_strs = [str(p) for p in ports]
                unauthorized = [p for p in port_strs if p not in authorized_scope]
                if unauthorized:
                    raise ValueError(
                        f"Ports {unauthorized} not in authorized scope for {target}. "
                        f"Authorized scope: {authorized_scope}"
                    )

        return True


class AuditLogger:
    """Logs all operations with immutable audit trail."""

    def __init__(self, log_file: Optional[str] = None) -> None:
        self._entries: List[AuditEntry] = []
        self._log_file = log_file

    def log(
        self,
        actor: str,
        action: AuditAction,
        target: str,
        result: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Log an operation.

        Args:
            actor: Who performed the action
            action: What action was performed
            target: What target was affected
            result: Outcome of the action
            details: Additional details

        Returns:
            AuditEntry
        """
        entry = AuditEntry(
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            actor=actor,
            action=action.value,
            target=target,
            result=result,
            details=details or {},
        )
        self._entries.append(entry)

        if self._log_file:
            self._append_to_file(entry)

        logger.info(f"AUDIT: {actor} {action.value} {target} -> {result}")
        return entry

    def _append_to_file(self, entry: AuditEntry) -> None:
        """Append entry to audit log file."""
        if not self._log_file:
            return
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": entry.timestamp,
                    "actor": entry.actor,
                    "action": entry.action,
                    "target": entry.target,
                    "result": entry.result,
                    "details": entry.details,
                }) + "\n")
        except OSError as e:
            logger.error(f"Failed to write audit log: {e}")

    def get_entries(
        self,
        target: Optional[str] = None,
        action: Optional[AuditAction] = None,
        actor: Optional[str] = None,
    ) -> List[AuditEntry]:
        """Get audit entries with optional filtering."""
        entries = self._entries
        if target:
            entries = [e for e in entries if e.target == target]
        if action:
            entries = [e for e in entries if e.action == action.value]
        if actor:
            entries = [e for e in entries if e.actor == actor]
        return entries

    def export(self, file_path: str) -> str:
        """Export audit log to file."""
        with open(file_path, "w", encoding="utf-8") as f:
            for entry in self._entries:
                f.write(json.dumps({
                    "timestamp": entry.timestamp,
                    "actor": entry.actor,
                    "action": entry.action,
                    "target": entry.target,
                    "result": entry.result,
                    "details": entry.details,
                }) + "\n")
        return file_path

    @property
    def entry_count(self) -> int:
        return len(self._entries)
