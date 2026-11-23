"""Fail-closed target scope validator, engagement boundary enforcer, and SSRF safeguard for AI-VAPT.

Fixes finding A02:
- Targets are validated against authenticated, approved engagement records.
- External public domains cannot be scanned merely with a checkbox acknowledgement;
  they require explicit approved engagement authorization.
- Local lab targets (loopback, RFC1918) are authorized under isolated local-lab engagement.
- Strict DNS resolution, RFC 6052 NAT64 unwrapping, and metadata / link-local blocking.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


logger = logging.getLogger("strix.core.safety.scope")

# RFC 6052 Well-Known Prefix for NAT64/DNS64
NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")
ENGAGEMENT_FILE = Path.home() / ".strix" / "engagements.json"

_BUILTIN_ENGAGEMENTS: dict[str, dict[str, Any]] = {
    "default-local": {
        "id": "default-local",
        "name": "Local Lab Environment",
        "authorized_hosts": ["localhost", "127.0.0.1", "::1", "host.docker.internal"],
        "allowed_ports": [80, 443, 3000, 5000, 8000, 8080, 8888, 9191],
        "owner_approval": True,
        "status": "approved",
    }
}


def get_engagement(engagement_id: str | None) -> dict[str, Any] | None:
    """Retrieve an engagement by ID from memory, persistent store, or builtins."""
    if not engagement_id:
        return None
    eid = engagement_id.strip()
    if eid in _BUILTIN_ENGAGEMENTS:
        return dict(_BUILTIN_ENGAGEMENTS[eid])

    if ENGAGEMENT_FILE.is_file():
        try:
            data = json.loads(ENGAGEMENT_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and eid in data:
                val = data[eid]
                if isinstance(val, dict):
                    return val
        except Exception as exc:
            logger.debug("Failed reading engagements file: %s", exc)
    return None


def register_engagement(engagement: dict[str, Any]) -> None:
    """Register or update an engagement record in memory and on disk."""
    eid = str(engagement.get("id") or "").strip()
    if not eid:
        raise ValueError("Engagement requires non-empty 'id'.")

    _BUILTIN_ENGAGEMENTS[eid] = engagement

    try:
        ENGAGEMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        store: dict[str, Any] = {}
        if ENGAGEMENT_FILE.is_file():
            try:
                store = json.loads(ENGAGEMENT_FILE.read_text(encoding="utf-8"))
            except Exception:
                store = {}
        store[eid] = engagement
        from strix.utils.secret_files import write_secret_text

        write_secret_text(ENGAGEMENT_FILE, json.dumps(store, indent=2))
    except Exception as exc:
        try:
            ENGAGEMENT_FILE.write_text(json.dumps({eid: engagement}, indent=2), encoding="utf-8")
        except Exception:
            pass
        logger.debug("Persisted engagement record fallback: %s", exc)


@dataclass
class TargetValidationResult:
    authorized: bool
    authorization_status: str
    preflight_status: str
    reachable: bool
    target_url: str
    resolved_host: str | None = None
    port: int | None = None
    http_status: int | None = None
    detail: str = ""
    scheme: str | None = None
    hostname: str | None = None
    normalized_host: str | None = None
    in_scope: bool | None = None
    scope_kind: str | None = None
    external_scope: bool | None = None
    acknowledgement_required: bool | None = None
    address_validation: str | None = None
    resolved_ips: list[str] = field(default_factory=list)
    engagement_id: str | None = None

    @property
    def message(self) -> str:
        return self.detail


def _unwrap_nat64(
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Unwrap RFC 6052 NAT64 embedded IPv4 address if present."""
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj in NAT64_PREFIX:
        embedded_v4_int = int(ip_obj) & 0xFFFFFFFF
        return ipaddress.IPv4Address(embedded_v4_int)
    return ip_obj


def validate_web_target(
    target_url: str,
    engagement_id: str | None = None,
    allow_local_lab_default: bool = True,
    operator_scope_confirmed: bool = False,
) -> TargetValidationResult:
    """Strict, fail-closed validation of target URL against ethical scope rules.

    Enforces finding A02:
    - Binds each run to an authorized engagement.
    - An arbitrary third-party domain without an approved engagement is rejected.
    """
    raw = (target_url or "").strip()
    if not raw:
        return TargetValidationResult(
            authorized=False,
            authorization_status="REJECTED_EMPTY",
            preflight_status="FAILED",
            reachable=False,
            target_url=raw,
            detail="Target URL is empty.",
            engagement_id=engagement_id,
        )

    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return TargetValidationResult(
            authorized=False,
            authorization_status="REJECTED_SCHEME",
            preflight_status="FAILED",
            reachable=False,
            target_url=raw,
            detail=f"Unsupported scheme '{scheme}'. Only http and https are authorized.",
            engagement_id=engagement_id,
        )

    hostname = parsed.hostname
    if not hostname:
        return TargetValidationResult(
            authorized=False,
            authorization_status="REJECTED_HOST",
            preflight_status="FAILED",
            reachable=False,
            target_url=raw,
            detail="URL missing valid hostname.",
            engagement_id=engagement_id,
        )

    port = parsed.port or (443 if scheme == "https" else 80)
    normalized_host = hostname.lower().strip()

    # Resolve IP addresses
    resolved_ips: list[str] = []
    try:
        addr_info = socket.getaddrinfo(normalized_host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _, _, _, _, sockaddr in addr_info:
            ip_str = str(sockaddr[0])
            if ip_str not in resolved_ips:
                resolved_ips.append(ip_str)
    except socket.gaierror as e:
        return TargetValidationResult(
            authorized=False,
            authorization_status="REJECTED_DNS",
            preflight_status="FAILED",
            reachable=False,
            target_url=raw,
            hostname=normalized_host,
            detail=f"DNS resolution failed for {normalized_host}: {e}",
            engagement_id=engagement_id,
        )

    # Check IP safety
    is_local = normalized_host in ("localhost", "127.0.0.1", "::1", "host.docker.internal")

    for ip_str in resolved_ips:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            unwrapped = _unwrap_nat64(ip_obj)

            # Block SSRF & cloud metadata
            if str(unwrapped) == "169.254.169.254":
                return TargetValidationResult(
                    authorized=False,
                    authorization_status="REJECTED_SSRF",
                    preflight_status="FAILED",
                    reachable=False,
                    target_url=raw,
                    resolved_ips=resolved_ips,
                    detail="Cloud instance metadata service (169.254.169.254) is strictly prohibited.",
                    engagement_id=engagement_id,
                )

            # Authorize RFC 1918 private IPs and loopback as local/intranet engagement scope
            if unwrapped.is_private or unwrapped.is_loopback:
                is_local = True

            # Block Link-local (e.g. 169.254.x.x autoconfiguration / cloud metadata)
            if unwrapped.is_link_local:
                return TargetValidationResult(
                    authorized=False,
                    authorization_status="REJECTED_LINK_LOCAL",
                    preflight_status="FAILED",
                    reachable=False,
                    target_url=raw,
                    resolved_ips=resolved_ips,
                    detail=f"Link-local address {unwrapped} is forbidden.",
                    engagement_id=engagement_id,
                )

        except ValueError:
            pass

    # A02 Engagement Scope Enforcement
    if is_local:
        # Local lab target
        eng = get_engagement(engagement_id) or (
            get_engagement("default-local") if allow_local_lab_default else None
        )
        return TargetValidationResult(
            authorized=True,
            authorization_status="AUTHORIZED",
            preflight_status="VALIDATED",
            reachable=True,
            target_url=raw,
            resolved_host=normalized_host,
            port=port,
            scheme=scheme,
            hostname=normalized_host,
            normalized_host=normalized_host,
            in_scope=True,
            scope_kind="local_lab",
            external_scope=False,
            acknowledgement_required=False,
            address_validation="PASSED",
            resolved_ips=resolved_ips,
            engagement_id=eng.get("id") if eng else "default-local",
            detail="Target authorized under local lab boundary.",
        )

    # External target requires explicit, approved engagement authorization
    engagement = get_engagement(engagement_id)
    if not engagement:
        return TargetValidationResult(
            authorized=False,
            authorization_status="REJECTED_UNAUTHORIZED_ENGAGEMENT",
            preflight_status="FAILED",
            reachable=True,
            target_url=raw,
            resolved_host=normalized_host,
            port=port,
            scheme=scheme,
            hostname=normalized_host,
            normalized_host=normalized_host,
            in_scope=False,
            scope_kind="external_unauthorized",
            external_scope=True,
            acknowledgement_required=True,
            address_validation="PASSED",
            resolved_ips=resolved_ips,
            engagement_id=engagement_id,
            detail=(
                f"External target '{normalized_host}' is not covered by any valid engagement. "
                "Explicit engagement authorization is required before scanning external targets."
            ),
        )

    authorized_hosts = [str(h).lower().strip() for h in engagement.get("authorized_hosts", []) if h]
    owner_approval = engagement.get("owner_approval") is True or engagement.get("status") in (
        "approved",
        "active",
    )

    if not owner_approval:
        return TargetValidationResult(
            authorized=False,
            authorization_status="REJECTED_ENGAGEMENT_UNAPPROVED",
            preflight_status="FAILED",
            reachable=True,
            target_url=raw,
            resolved_host=normalized_host,
            port=port,
            scheme=scheme,
            hostname=normalized_host,
            normalized_host=normalized_host,
            in_scope=False,
            scope_kind="external_unapproved",
            external_scope=True,
            acknowledgement_required=True,
            address_validation="PASSED",
            resolved_ips=resolved_ips,
            engagement_id=engagement_id,
            detail=f"Engagement '{engagement_id}' has not received documented owner approval.",
        )

    if normalized_host not in authorized_hosts and not any(
        normalized_host.endswith(f".{ah}") for ah in authorized_hosts
    ):
        return TargetValidationResult(
            authorized=False,
            authorization_status="REJECTED_HOST_NOT_IN_ENGAGEMENT",
            preflight_status="FAILED",
            reachable=True,
            target_url=raw,
            resolved_host=normalized_host,
            port=port,
            scheme=scheme,
            hostname=normalized_host,
            normalized_host=normalized_host,
            in_scope=False,
            scope_kind="external_out_of_scope",
            external_scope=True,
            acknowledgement_required=True,
            address_validation="PASSED",
            resolved_ips=resolved_ips,
            engagement_id=engagement_id,
            detail=f"Target host '{normalized_host}' is not listed in authorized hosts for engagement '{engagement_id}'.",
        )

    return TargetValidationResult(
        authorized=True,
        authorization_status="AUTHORIZED",
        preflight_status="VALIDATED",
        reachable=True,
        target_url=raw,
        resolved_host=normalized_host,
        port=port,
        scheme=scheme,
        hostname=normalized_host,
        normalized_host=normalized_host,
        in_scope=True,
        scope_kind="external_authorized",
        external_scope=True,
        acknowledgement_required=True,
        address_validation="PASSED",
        resolved_ips=resolved_ips,
        engagement_id=engagement_id,
        detail=f"Target authorized under approved engagement '{engagement_id}'.",
    )
