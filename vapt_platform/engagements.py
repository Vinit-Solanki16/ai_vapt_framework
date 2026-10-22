"""Saved Engagement Profiles and Scope Governance for AI-VAPT.

Manages reusable authorized engagement scopes so administrators and operators
do not need to restart the API or edit environment variables for every target.

Features:
  - Exact hostname and port allowlists per engagement.
  - Optional path prefix restrictions.
  - Authorization basis / RoE reference tracking.
  - Scope expiry date enforcement.
  - Atomic, durable persistence outside Git in a platform user-data directory.
  - Fail-closed validation logic: external profiles inactive by default.
  - Rejection of credentials or secret keys in scopes or URLs.
  - Corruption-safe persistence with automated backup and fail-closed isolation.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

# Template profiles file (read-only templates shipped with repository)
TEMPLATES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "engagement_templates.json",
)

LEGACY_REPO_ENGAGEMENTS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "engagements.json",
)

_ID_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{3,64}$")

# Disallowed placeholder references for active external scopes
PLACEHOLDER_REFS = frozenset({
    "",
    "PENDING_OPERATOR_AUTHORIZATION_REVIEW",
    "PENDING_REVIEW",
    "NONE",
    "N/A",
    "TODO",
    "TEST",
    "DEMO",
    "SAMPLE",
    "UNKNOWN",
    "UNAUTHORIZED",
})

# Secret detection patterns (prevent accidental leakage of credentials into profiles)
SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"sk-or-v1-[a-zA-Z0-9]{32,}"),
    re.compile(r"ghp_[a-zA-Z0-9]{20,}"),
    re.compile(r"(?:bearer|token|apikey|password|secret)[\s:=]+[\"']?[a-zA-Z0-9_\-\.]{12,}", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
]


def _scan_for_secrets(obj: Any, field_name: str = "") -> None:
    """Recursively scan data for API keys, tokens, or credentials."""
    if isinstance(obj, str):
        for pat in SECRET_PATTERNS:
            if pat.search(obj):
                raise EngagementValidationError(
                    f"Engagement profile field '{field_name or 'value'}' must not contain API keys, passwords, or credentials."
                )
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _scan_for_secrets(v, f"{field_name}.{k}" if field_name else k)
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            _scan_for_secrets(item, f"{field_name}[{i}]")


def _default_engagements_file() -> str:
    """Determine runtime engagement profiles persistence path outside git."""
    env_file = os.environ.get("VAPT_ENGAGEMENTS_FILE")
    if env_file:
        return env_file
    env_dir = (
        os.environ.get("VAPT_ENGAGEMENTS_DIR")
        or os.environ.get("VAPT_STORAGE_DIR")
        or os.environ.get("VAPT_DATA_DIR")
    )
    if env_dir:
        return os.path.join(env_dir, "engagements.json")

    user_home = os.path.expanduser("~")
    home_dir = os.path.join(user_home, ".ai_vapt_framework")
    try:
        os.makedirs(home_dir, exist_ok=True)
        return os.path.join(home_dir, "engagements.json")
    except OSError:
        tmp_dir = os.path.join(tempfile.gettempdir(), ".ai_vapt_framework")
        try:
            os.makedirs(tmp_dir, exist_ok=True)
        except OSError:
            pass
        return os.path.join(tmp_dir, "engagements.json")


DEFAULT_ENGAGEMENTS_FILE = _default_engagements_file()


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

    def is_external(self) -> bool:
        """Check if profile targets any external (non-loopback) host."""
        return any(
            h.lower() not in ("127.0.0.1", "localhost", "::1")
            for h in self.authorized_hosts
        )

    def is_active(self) -> bool:
        """Check if profile is active, not expired, and has valid authorization."""
        if (self.status or "").lower() != "active":
            return False

        # Fail-closed: external profiles cannot be active without a genuine RoE reference
        if self.is_external():
            ref = (self.authorization_reference or "").strip()
            if not ref or ref.upper() in PLACEHOLDER_REFS:
                return False

        if self.expires_at:
            try:
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
        d["is_external"] = self.is_external()
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


class EngagementStorageError(IOError):
    """Raised when an engagement storage read, write, or persistence fails."""


class EngagementManager:
    """Manages persistent engagement scope profiles."""

    def __init__(self, storage_path: Optional[str] = None) -> None:
        self.storage_path = storage_path or DEFAULT_ENGAGEMENTS_FILE
        self._profiles: dict[str, EngagementProfile] = {}
        self.storage_corrupted: bool = False
        self.last_storage_error: Optional[str] = None
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
        """Seed default engagement profiles.

        Local lab default is active.
        External training lab template is INACTIVE by default and requires
        explicit operator authorization reference before activation.
        """
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
                description="External web testing template for pentest-ground.com port 4280 (INACTIVE by default — requires operator review and authorization reference before activation)",
                authorized_hosts=["pentest-ground.com"],
                allowed_ports=[4280],
                permitted_paths=[],
                authorization_reference="PENDING_OPERATOR_AUTHORIZATION_REVIEW",
                created_at=now,
                updated_at=now,
                scanner_policy="safe_non_destructive",
                status="inactive",
            ),
        ]

    def _load(self) -> None:
        """Load profiles from JSON storage file; seed defaults or migrate if absent."""
        if not os.path.exists(self.storage_path) or os.path.getsize(self.storage_path) == 0:
            # Check for legacy file migration first
            legacy_file = LEGACY_REPO_ENGAGEMENTS_FILE
            if os.path.abspath(self.storage_path) != os.path.abspath(legacy_file) and os.path.exists(legacy_file):
                migrated = self._migrate_from_legacy(legacy_file)
                if migrated:
                    return

            # Seed clean defaults
            defaults = self._default_profiles()
            for prof in defaults:
                self._profiles[prof.id] = prof
            try:
                self._save()
            except EngagementStorageError as e:
                log.warning("Could not immediately persist initialized default profiles: %s", e)
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                raise ValueError("Engagements storage file is empty (0 bytes).")
            data = json.loads(content)

            profiles_dict: dict[str, EngagementProfile] = {}
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("id"):
                        prof = EngagementProfile.from_dict(item)
                        # Defense-in-depth: external profiles cannot be active with placeholder refs
                        if prof.is_external() and not prof.is_active():
                            prof.status = "inactive"
                        profiles_dict[prof.id] = prof
            elif isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, dict):
                        prof = EngagementProfile.from_dict(v)
                        if prof.is_external() and not prof.is_active():
                            prof.status = "inactive"
                        profiles_dict[k] = prof
            else:
                raise ValueError("Engagements JSON root is neither an array nor an object.")

            self._profiles = profiles_dict
            self.storage_corrupted = False
            self.last_storage_error = None
        except Exception as e:
            # CORRUPTED FILE: Do not overwrite! Preserve backup and fail closed.
            corrupt_backup = f"{self.storage_path}.corrupt.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            try:
                shutil.copy2(self.storage_path, corrupt_backup)
            except Exception as copy_err:
                log.error("Failed to copy corrupted storage file: %s", copy_err)

            self.storage_corrupted = True
            self.last_storage_error = (
                f"Engagement storage at {self.storage_path} is corrupted: {e}. "
                f"Backup preserved at {corrupt_backup}. External profiles disabled."
            )
            log.error(self.last_storage_error)

            # Fail closed: Only keep local lab default in memory; NEVER external profiles
            self._profiles = {p.id: p for p in self._default_profiles() if not p.is_external()}

    def _migrate_from_legacy(self, legacy_file: str) -> bool:
        """Migrate legacy profiles file into runtime storage.

        Guarantees:
          - Validates profile data.
          - Forces any external profile to status="inactive" pending operator review.
          - Leaves legacy file intact as a backup.
        """
        try:
            with open(legacy_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return False
            data = json.loads(content)
            items = data if isinstance(data, list) else list(data.values())

            migrated: dict[str, EngagementProfile] = {}
            for item in items:
                if isinstance(item, dict) and item.get("id"):
                    prof = EngagementProfile.from_dict(item)
                    # Requirement: Migration must NOT automatically activate external profiles
                    if prof.is_external():
                        prof.status = "inactive"
                        prof.description = (
                            f"{prof.description} (Migrated from legacy storage: operator review required before activation)"
                        ).strip()
                    migrated[prof.id] = prof

            # Ensure local lab default exists
            if "eng-local-lab" not in migrated:
                for def_prof in self._default_profiles():
                    if not def_prof.is_external():
                        migrated[def_prof.id] = def_prof

            self._profiles = migrated
            self._save()
            log.info("Migrated %d engagement profiles from %s to %s", len(migrated), legacy_file, self.storage_path)
            return True
        except Exception as e:
            log.warning("Could not safely migrate legacy profiles from %s: %s (falling back to clean defaults)", legacy_file, e)
            return False

    def _save(self) -> None:
        """Save profiles atomically to storage file."""
        if self.storage_corrupted:
            raise EngagementStorageError(
                f"Cannot save: storage is in corrupted state. "
                f"Operator must resolve the file at {self.storage_path} or restore from backup."
            )

        data = [p.to_dict() for p in self._profiles.values()]
        parent = os.path.dirname(self.storage_path) or "."
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError:
            pass

        temp_name = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=parent, delete=False, encoding="utf-8") as tf:
                json.dump(data, tf, indent=2)
                tf.write("\n")
                tf.flush()
                os.fsync(tf.fileno())
                temp_name = tf.name
            os.replace(temp_name, self.storage_path)
        except Exception as e:
            if temp_name and os.path.exists(temp_name):
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
            log.error("Failed to write engagements file %s: %s", self.storage_path, e)
            raise EngagementStorageError(f"Failed to persist engagement profiles to {self.storage_path}: {e}") from e

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

        # 1. Security scan: reject any embedded API keys, passwords, or credentials
        _scan_for_secrets(data)

        # 2. Name validation
        name = str(data.get("name", "")).strip()
        if not name:
            raise EngagementValidationError("Engagement 'name' is required.")

        # 3. Hostnames validation
        hosts = data.get("authorized_hosts")
        if not hosts or not isinstance(hosts, list):
            raise EngagementValidationError("Engagement must specify at least one authorized host in 'authorized_hosts'.")

        # 4. Ports validation
        ports = data.get("allowed_ports")
        if not ports or not isinstance(ports, list):
            raise EngagementValidationError("Engagement must specify at least one port in 'allowed_ports'.")

        for p in ports:
            try:
                p_int = int(p)
                if not (1 <= p_int <= 65535):
                    raise ValueError()
            except (ValueError, TypeError):
                raise EngagementValidationError(f"Invalid port {p!r}: must be an integer between 1 and 65535.")

        from vapt_platform.web_target import _normalize_host, _is_valid_hostname
        import ipaddress
        normalized_hosts = []
        is_external_profile = False
        for h in hosts:
            norm_h = _normalize_host(str(h))
            if not norm_h:
                raise EngagementValidationError("Host cannot be empty.")
            if any(ch in norm_h for ch in ("://", "/", "?", "#", "@", "*", "%")):
                raise EngagementValidationError(f"Invalid host {h!r}: cannot contain schemes, slashes, or wildcards.")
            is_ip = False
            try:
                ipaddress.ip_address(norm_h)
                is_ip = True
            except ValueError:
                pass
            if not is_ip and not _is_valid_hostname(norm_h) and norm_h != "localhost":
                raise EngagementValidationError(f"Invalid host {h!r}: must be a valid hostname or IP address.")
            normalized_hosts.append(norm_h)
            if norm_h not in ("127.0.0.1", "localhost", "::1"):
                is_external_profile = True

        # 5. Authorization Reference validation
        ref = str(data.get("authorization_reference", "")).strip()
        status = str(data.get("status", "active")).strip().lower()

        if is_external_profile:
            if status == "active":
                if not ref or ref.upper() in PLACEHOLDER_REFS:
                    raise EngagementValidationError(
                        "External engagement profiles cannot be active without a genuine recorded authorization reference (RoE document / ticket reference)."
                    )
        else:
            if not ref:
                raise EngagementValidationError("An 'authorization_reference' (e.g. RoE document or authorization ID) is required.")

    def create_profile(self, data: dict[str, Any]) -> EngagementProfile:
        """Create and persist a new engagement profile."""
        if self.storage_corrupted:
            raise EngagementStorageError(
                f"Cannot create profile: storage at {self.storage_path} is corrupted. "
                "Operator must repair the file or restore from backup before making changes."
            )

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
            authorization_reference=str(data.get("authorization_reference", "")).strip(),
            created_at=now,
            updated_at=now,
            expires_at=data.get("expires_at"),
            scanner_policy=str(data.get("scanner_policy", "safe_non_destructive")).strip(),
            status=str(data.get("status", "active")).strip().lower(),
        )

        backup = dict(self._profiles)
        self._profiles[prof_id] = profile
        try:
            self._save()
        except Exception:
            self._profiles = backup
            raise
        return profile

    def update_profile(self, profile_id: str, data: dict[str, Any]) -> EngagementProfile:
        """Update an existing engagement profile."""
        if self.storage_corrupted:
            raise EngagementStorageError(
                f"Cannot update profile: storage at {self.storage_path} is corrupted. "
                "Operator must repair the file or restore from backup before making changes."
            )

        self._load()
        existing = self._profiles.get(profile_id)
        if not existing:
            raise KeyError(f"Engagement profile {profile_id!r} not found.")

        # Support partial updates by merging with existing profile attributes
        merged_data = existing.to_dict()
        merged_data.update({k: v for k, v in data.items() if v is not None})

        self.validate_profile_payload(merged_data, is_update=True)

        backup_profile = copy.deepcopy(existing)

        existing.name = str(merged_data["name"]).strip()
        existing.description = str(merged_data.get("description", "")).strip()
        existing.authorized_hosts = [str(h).strip().lower() for h in merged_data["authorized_hosts"]]
        existing.allowed_ports = [int(p) for p in merged_data["allowed_ports"]]
        if "permitted_paths" in merged_data:
            existing.permitted_paths = [str(p).strip() for p in (merged_data.get("permitted_paths") or []) if str(p).strip()]
        existing.authorization_reference = str(merged_data.get("authorization_reference", "")).strip()
        existing.expires_at = merged_data.get("expires_at")
        existing.scanner_policy = str(merged_data.get("scanner_policy", "safe_non_destructive")).strip()
        if "status" in merged_data:
            existing.status = str(merged_data["status"]).strip().lower()
        existing.updated_at = datetime.now(timezone.utc).isoformat()

        try:
            self._save()
        except Exception:
            self._profiles[profile_id] = backup_profile
            raise
        return existing

    def delete_profile(self, profile_id: str) -> bool:
        """Delete an engagement profile."""
        if self.storage_corrupted:
            raise EngagementStorageError(
                f"Cannot delete profile: storage at {self.storage_path} is corrupted. "
                "Operator must repair the file or restore from backup before making changes."
            )

        self._load()
        if profile_id not in self._profiles:
            return False

        backup = dict(self._profiles)
        del self._profiles[profile_id]
        try:
            self._save()
        except Exception:
            self._profiles = backup
            raise
        return True

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
            extra = " (requires review and authorization reference before activation)" if profile.is_external() else ""
            return {
                "matched": False,
                "authorized": False,
                "reason": f"Engagement profile '{profile.name}' is inactive or expired{extra}.",
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

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic metadata without leaking sensitive data."""
        self._load()
        profiles_summary = []
        for p in self._profiles.values():
            profiles_summary.append({
                "id": p.id,
                "name": p.name,
                "status": p.status,
                "is_active": p.is_active(),
                "is_external": p.is_external(),
                "authorized_hosts": p.authorized_hosts,
                "allowed_ports": p.allowed_ports,
                "has_authorization_reference": bool(p.authorization_reference and p.authorization_reference not in PLACEHOLDER_REFS),
            })

        return {
            "storage_path": self.storage_path,
            "storage_exists": os.path.exists(self.storage_path),
            "storage_corrupted": self.storage_corrupted,
            "corrupted": self.storage_corrupted,
            "last_storage_error": self.last_storage_error,
            "total_profiles": len(self._profiles),
            "active_profiles": len([p for p in self._profiles.values() if p.is_active()]),
            "external_profiles": len([p for p in self._profiles.values() if p.is_external()]),
            "active_external_profiles": len([p for p in self._profiles.values() if p.is_active() and p.is_external()]),
            "profiles": profiles_summary,
        }


# Singleton manager
_engagement_manager: Optional[EngagementManager] = None


def get_engagement_manager(storage_path: Optional[str] = None) -> EngagementManager:
    """Get the singleton EngagementManager instance."""
    global _engagement_manager
    if storage_path is not None:
        if _engagement_manager is None or _engagement_manager.storage_path != storage_path:
            _engagement_manager = EngagementManager(storage_path=storage_path)
    elif _engagement_manager is None:
        _engagement_manager = EngagementManager(storage_path=DEFAULT_ENGAGEMENTS_FILE)
    return _engagement_manager


def set_engagement_manager(mgr: Optional[EngagementManager]) -> None:
    """Set or reset the singleton EngagementManager instance (useful for testing)."""
    global _engagement_manager
    _engagement_manager = mgr


def reset_engagement_manager() -> None:
    """Reset the singleton instance (for testing)."""
    global _engagement_manager
    _engagement_manager = None
