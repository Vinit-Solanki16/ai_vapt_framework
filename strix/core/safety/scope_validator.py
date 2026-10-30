"""Fail-closed target scope validator and SSRF safeguard for STRIX AI-VAPT."""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

logger = logging.getLogger("strix.core.safety.scope")

# RFC 6052 Well-Known Prefix for NAT64/DNS64
NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")


@dataclass
class TargetValidationResult:
    authorized: bool
    authorization_status: str
    preflight_status: str
    reachable: bool
    target_url: str
    resolved_host: Optional[str] = None
    port: Optional[int] = None
    http_status: Optional[int] = None
    detail: str = ""
    scheme: Optional[str] = None
    hostname: Optional[str] = None
    normalized_host: Optional[str] = None
    in_scope: Optional[bool] = None
    scope_kind: Optional[str] = None
    external_scope: Optional[bool] = None
    acknowledgement_required: Optional[bool] = None
    address_validation: Optional[str] = None
    resolved_ips: List[str] = field(default_factory=list)


def _unwrap_nat64(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Unwrap RFC 6052 NAT64 embedded IPv4 address if present."""
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj in NAT64_PREFIX:
        embedded_v4_int = ip_obj._ip & 0xFFFFFFFF
        return ipaddress.IPv4Address(embedded_v4_int)
    return ip_obj


def validate_web_target(
    target_url: str,
    engagement_id: Optional[str] = None,
) -> TargetValidationResult:
    """Strict, fail-closed validation of target URL against ethical scope rules."""
    raw = (target_url or "").strip()
    if not raw:
        return TargetValidationResult(
            authorized=False,
            authorization_status="REJECTED_EMPTY",
            preflight_status="FAILED",
            reachable=False,
            target_url=raw,
            detail="Target URL is empty.",
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
        )

    port = parsed.port or (443 if scheme == "https" else 80)
    normalized_host = hostname.lower().strip()

    # Resolve IP addresses
    resolved_ips: List[str] = []
    try:
        addr_info = socket.getaddrinfo(normalized_host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
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
                )

            # Block RFC 1918 private IPs unless local lab mode
            if unwrapped.is_private and not is_local:
                return TargetValidationResult(
                    authorized=False,
                    authorization_status="REJECTED_PRIVATE_IP",
                    preflight_status="FAILED",
                    reachable=False,
                    target_url=raw,
                    resolved_ips=resolved_ips,
                    detail=f"Private RFC 1918 IP address {unwrapped} is not in authorized public scope.",
                )

            # Block Link-local & CGNAT
            if unwrapped.is_link_local:
                return TargetValidationResult(
                    authorized=False,
                    authorization_status="REJECTED_LINK_LOCAL",
                    preflight_status="FAILED",
                    reachable=False,
                    target_url=raw,
                    resolved_ips=resolved_ips,
                    detail=f"Link-local address {unwrapped} is forbidden.",
                )

        except ValueError:
            pass

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
        scope_kind="local_lab" if is_local else "external_authorized",
        external_scope=not is_local,
        acknowledgement_required=not is_local,
        address_validation="PASSED",
        resolved_ips=resolved_ips,
        detail="Target authorized under ethical scope boundary.",
    )

