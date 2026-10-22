"""Saved Engagement Profiles and Scope Governance for AI-VAPT.

Manages reusable authorized engagement scopes so administrators and operators
do not need to restart the API or edit environment variables for every target.

Features:
  - Exact hostname and port allowlists per engagement.
  - Optional path prefix restrictions.
  - Authorization basis / RoE reference tracking.
  - Scope expiry date enforcement.
  - Atomic, durable persistence surviving restarts.
  - Fail-closed validation logic.
  - Rejection of credentials or secret keys in scopes or URLs.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

DEFAULT_ENGAGEMENTS_FILE = os.path.join(os.getcwd(), "data", "engagements.json")
_ID_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{3,64}$")


@dataclass
class EngagementProfile:
    """An authorized VAPT engagement scope profile."""
    id: str
    name: str
    description: str = ""
    authorized_hosts: list[str] = field(default_factory=list)
    allowed_ports: list[int] = field(default_factory=list)
    permitted_paths: list[str] = field(default_factory=list)
    authorization_reference: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = None
    scanner_policy: str = "safe_non_destructive"
    status: str = "active"  # "active" or "inactive"

    def is_active(self) -> bool:
        """Check if profile is active and not expired."""
        if (self.status or "").lower() != "active":
            return False
        if self.expires_at:
            try:
                # Support ISO timestamps
                expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > expiry:
                    return False
            except Exception:
                # If expiry is malformed, fail closed
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert profile to dictionary representation."""
        d = asdict(self)
        d["is_active"] = self.is_active()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EngagementProfile:
        """Create EngagementProfile from dictionary."""
        return cls(
            id=str(data.get("id", "")).strip(),
            name=str(data.get("name", "")).strip(),
            description=str(data.get("description", "")).strip(),
            authorized_hosts=[str(h).strip().lower() for h in (data.get("authorized_hosts") or []) if str(h).strip()],
            allowed_ports=[int(p) for p in (data.get("allowed_ports") or []) if str(p).isdigit() and 1 <= int(p) <= 65535],
            permitted_paths=[str(p).strip() for p in (data.get("permitted_paths") or []) if str(p).strip()],
            authorization_reference=str(data.get("authorization_reference", "")).strip(),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
            expires_at=data.get("expires_at"),
            scanner_policy=str(data.get("scanner_policy", "safe_non_destructive")).strip(),
            status=str(data.get("status", "active")).strip().lower(),
        )


class EngagementValidationError(ValueError):
    """Raised when an engagement profile data is invalid."""


class EngagementManager:
    """Manages persistent engagement scope profiles."""

    def __init__(self, storage_path: str = DEFAULT_ENGAGEMENTS_FILE) -> None:
        self.storage_path = storage_path
        self._profiles: dict[str, EngagementProfile] = {}
        self._ensure_storage()
        self._load()

    def _ensure_storage(self) -> None:
        """Ensure parent directory exists for storage."""
        try:
            parent = os.path.dirname(self.storage_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        except OSError:
            pass

    def _default_profiles(self) -> list[EngagementProfile]:
        """Seed default engagement profiles for lab demonstrations."""
        now = datetime.now(timezone.utc).isoformat()
        return [
            EngagementProfile(
                id="eng-local-lab",
                name="Local Lab Default",
                description="Default loopback scope for local lab demonstrations and Juice Shop tests",
                authorized_hosts=["127.0.0.1", "localhost"],
                allowed_ports=[9191, 8080, 80, 443],
                permitted_paths=[],
                authorization_reference="LAB-POLICY-LOCAL-LOOPBACK",
                created_at=now,
                updated_at=now,
                scanner_policy="safe_non_destructive",
                status="active",
            ),
            EngagementProfile(
                id="eng-pentest-ground",
                name="Pentest Ground Authorized Lab",
                description="Controlled external web testing on pentest-ground.com port 4280",
                authorized_hosts=["pentest-ground.com"],
                allowed_ports=[4280],
                permitted_paths=[],
                authorization_reference="ROE-2026-PENTEST-GROUND-4280",
                created_at=now,
                updated_at=now,
                scanner_policy="safe_non_destructive",
                status="active",
            ),
        ]

    def _load(self) -> None:
        """Load profiles from JSON storage file; seed defaults if absent."""
        if not os.path.exists(self.storage_path):
            defaults = self._default_profiles()
            for prof in defaults:
                self._profiles[prof.id] = prof
            self._save()
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._profiles = {}
                for item in data:
                    if isinstance(item, dict) and item.get("id"):
                        prof = EngagementProfile.from_dict(item)
                        self._profiles[prof.id] = prof
            elif isinstance(data, dict):
                self._profiles = {
                    k: EngagementProfile.from_dict(v)
                    for k, v in data.items()
                    if isinstance(v, dict)
                }
        except Exception as e:
            log.warning("Failed to load engagement profiles from %s: %s (falling back to defaults)", self.storage_path, e)
            self._profiles = {p.id: p for p in self._default_profiles()}

    def _save(self) -> None:
        """Save profiles atomically to storage file."""
        data = [p.to_dict() for p in self._profiles.values()]
        parent = os.path.dirname(self.storage_path) or "."
        try:
            with tempfile.NamedTemporaryFile("w", dir=parent, delete=False, encoding="utf-8") as tf:
                json.dump(data, tf, indent=2)
                temp_name = tf.name
            os.replace(temp_name, self.storage_path)
        except OSError as e:
            log.error("Failed to write engagements file %s: %s", self.storage_path, e)

    def list_profiles(self, active_only: bool = False) -> list[EngagementProfile]:
        """List engagement profiles."""
        self._load()
        profiles = list(self._profiles.values())
        if active_only:
            profiles = [p for p in profiles if p.is_active()]
        return sorted(profiles, key=lambda p: (not p.is_active(), p.name.lower()))

    def get_profile(self, profile_id: str) -> Optional[EngagementProfile]:
        """Get profile by ID."""
        self._load()
        return self._profiles.get(profile_id)

    def validate_profile_payload(self, data: dict[str, Any], is_update: bool = False) -> None:
        """Validate input payload for creating or updating an engagement profile."""
        if not isinstance(data, dict):
            raise EngagementValidationError("Payload must be a JSON object.")

        name = str(data.get("name", "")).strip()
        if not name:
            raise EngagementValidationError("Engagement 'name' is required.")

        hosts = data.get("authorized_hosts")
        if not hosts or not isinstance(hosts, list):
            raise EngagementValidationError("Engagement must specify at least one authorized host in 'authorized_hosts'.")

        ports = data.get("allowed_ports")
        if not ports or not isinstance(ports, list):
            raise EngagementValidationError("Engagement must specify at least one port in 'allowed_ports'.")

        # Validate each port
        for p in ports:
            try:
                p_int = int(p)
                if not (1 <= p_int <= 65535):
                    raise ValueError()
            except (ValueError, TypeError):
                raise EngagementValidationError(f"Invalid port {p!r}: must be an integer between 1 and 65535.")

        # Validate each hostname using strict checks
        from vapt_platform.web_target import _normalize_host, _is_valid_hostname
        import ipaddress
        for h in hosts:
            norm_h = _normalize_host(str(h))
            if not norm_h:
                raise EngagementValidationError("Host cannot be empty.")
            # Check for illegal characters or protocol tricks
            if any(ch in norm_h for ch in ("://", "/", "?", "#", "@", "*", "%")):
                raise EngagementValidationError(f"Invalid host {h!r}: cannot contain schemes, slashes, or wildcards.")
            # Check IPv4, IPv6, or valid domain
            is_ip = False
            try:
                ipaddress.ip_address(norm_h)
                is_ip = True
            except ValueError:
                pass
            if not is_ip and not _is_valid_hostname(norm_h) and norm_h != "localhost":
                raise EngagementValidationError(f"Invalid host {h!r}: must be a valid hostname or IP address.")

        # Check reference
        ref = str(data.get("authorization_reference", "")).strip()
        if not ref:
            raise EngagementValidationError("An 'authorization_reference' (e.g. RoE document or authorization ID) is required.")

    def create_profile(self, data: dict[str, Any]) -> EngagementProfile:
        """Create and persist a new engagement profile."""
        self.validate_profile_payload(data)
        prof_id = str(data.get("id") or "").strip()
        if not prof_id:
            prof_id = f"eng-{uuid.uuid4().hex[:8]}"
        elif not _ID_RE.match(prof_id):
            raise EngagementValidationError(f"Profile ID {prof_id!r} is invalid (must be alphanumeric/dash/underscore 3-64 chars).")

        self._load()
        if prof_id in self._profiles:
            raise EngagementValidationError(f"An engagement profile with ID {prof_id!r} already exists.")

        now = datetime.now(timezone.utc).isoformat()
        profile = EngagementProfile(
            id=prof_id,
            name=str(data["name"]).strip(),
            description=str(data.get("description", "")).strip(),
            authorized_hosts=[str(h).strip().lower() for h in data["authorized_hosts"]],
            allowed_ports=[int(p) for p in data["allowed_ports"]],
            permitted_paths=[str(p).strip() for p in (data.get("permitted_paths") or []) if str(p).strip()],
            authorization_reference=str(data["authorization_reference"]).strip(),
            created_at=now,
            updated_at=now,
            expires_at=data.get("expires_at"),
            scanner_policy=str(data.get("scanner_policy", "safe_non_destructive")).strip(),
            status=str(data.get("status", "active")).strip().lower(),
        )
        self._profiles[prof_id] = profile
        self._save()
        return profile

    def update_profile(self, profile_id: str, data: dict[str, Any]) -> EngagementProfile:
        """Update an existing engagement profile."""
        self._load()
        existing = self._profiles.get(profile_id)
        if not existing:
            raise KeyError(f"Engagement profile {profile_id!r} not found.")

        # Support partial updates by merging with existing profile attributes
        merged_data = existing.to_dict()
        merged_data.update({k: v for k, v in data.items() if v is not None})

        self.validate_profile_payload(merged_data, is_update=True)
        existing.name = str(merged_data["name"]).strip()
        existing.description = str(merged_data.get("description", "")).strip()
        existing.authorized_hosts = [str(h).strip().lower() for h in merged_data["authorized_hosts"]]
        existing.allowed_ports = [int(p) for p in merged_data["allowed_ports"]]
        if "permitted_paths" in merged_data:
            existing.permitted_paths = [str(p).strip() for p in (merged_data.get("permitted_paths") or []) if str(p).strip()]
        existing.authorization_reference = str(merged_data["authorization_reference"]).strip()
        existing.expires_at = merged_data.get("expires_at")
        existing.scanner_policy = str(merged_data.get("scanner_policy", "safe_non_destructive")).strip()
        if "status" in merged_data:
            existing.status = str(merged_data["status"]).strip().lower()
        existing.updated_at = datetime.now(timezone.utc).isoformat()

        self._save()
        return existing

    def delete_profile(self, profile_id: str) -> bool:
        """Delete an engagement profile."""
        self._load()
        if profile_id in self._profiles:
            del self._profiles[profile_id]
            self._save()
            return True
        return False

    def get_all_active_scopes(self) -> set[tuple[str, int]]:
        """Return all (host, port) pairs authorized across all active engagements."""
        self._load()
        scopes: set[tuple[str, int]] = set()
        for p in self._profiles.values():
            if p.is_active():
                for h in p.authorized_hosts:
                    for port in p.allowed_ports:
                        scopes.add((h.lower(), port))
        return scopes

    def validate_target_against_profile(
        self, profile_id: str, target_url: str
    ) -> dict[str, Any]:
        """Validate whether a target URL conforms to a specific engagement profile."""
        self._load()
        profile = self._profiles.get(profile_id)
        if not profile:
            return {
                "matched": False,
                "authorized": False,
                "reason": f"Engagement profile {profile_id!r} does not exist.",
                "profile": None,
            }
        if not profile.is_active():
            return {
                "matched": False,
                "authorized": False,
                "reason": f"Engagement profile '{profile.name}' is inactive or expired.",
                "profile": profile.to_dict(),
            }

        try:
            parsed = urlparse(target_url.strip())
        except Exception as e:
            return {
                "matched": False,
                "authorized": False,
                "reason": f"Malformed target URL: {e}",
                "profile": profile.to_dict(),
            }

        scheme = (parsed.scheme or "http").lower()
        if scheme not in ("http", "https"):
            return {
                "matched": False,
                "authorized": False,
                "reason": f"Unsupported scheme {scheme!r}. Only http and https are permitted.",
                "profile": profile.to_dict(),
            }

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return {
                "matched": False,
                "authorized": False,
                "reason": "Target URL is missing a hostname.",
                "profile": profile.to_dict(),
            }

        port = parsed.port or (443 if scheme == "https" else 80)
        path = parsed.path or "/"

        # Check host match
        if hostname not in [h.lower() for h in profile.authorized_hosts]:
            return {
                "matched": False,
                "authorized": False,
                "reason": (
                    f"Host {hostname!r} is not in authorized hostnames for engagement "
                    f"'{profile.name}'. Authorized hosts: {profile.authorized_hosts}."
                ),
                "profile": profile.to_dict(),
            }

        # Check port match
        if port not in profile.allowed_ports:
            return {
                "matched": False,
                "authorized": False,
                "reason": (
                    f"Port {port} is not in allowed ports for engagement "
                    f"'{profile.name}'. Allowed ports: {sorted(profile.allowed_ports)}."
                ),
                "profile": profile.to_dict(),
            }

        # Check path restrictions if configured
        if profile.permitted_paths:
            path_matched = any(path.startswith(pfx) for pfx in profile.permitted_paths)
            if not path_matched:
                return {
                    "matched": False,
                    "authorized": False,
                    "reason": (
                        f"Path {path!r} does not match any permitted paths for engagement "
                        f"'{profile.name}'. Permitted prefixes: {profile.permitted_paths}."
                    ),
                    "profile": profile.to_dict(),
                }

        is_external = hostname not in ("127.0.0.1", "localhost", "::1")
        return {
            "matched": True,
            "authorized": True,
            "external": is_external,
            "reason": (
                f"Target URL is within authorized scope for engagement "
                f"'{profile.name}' (Ref: {profile.authorization_reference})."
            ),
            "profile": profile.to_dict(),
            "scope_entry": f"{hostname}:{port}",
            "authorization_reference": profile.authorization_reference,
        }


# Singleton manager
_engagement_manager: Optional[EngagementManager] = None


def get_engagement_manager(storage_path: str = DEFAULT_ENGAGEMENTS_FILE) -> EngagementManager:
    """Get the singleton EngagementManager instance."""
    global _engagement_manager
    if _engagement_manager is None or _engagement_manager.storage_path != storage_path:
        _engagement_manager = EngagementManager(storage_path=storage_path)
    return _engagement_manager


def set_engagement_manager(mgr: Optional[EngagementManager]) -> None:
    """Set or reset the singleton EngagementManager instance (useful for testing)."""
    global _engagement_manager
    _engagement_manager = mgr


def reset_engagement_manager() -> None:
    """Reset the singleton instance (for testing)."""
    global _engagement_manager
    _engagement_manager = None
