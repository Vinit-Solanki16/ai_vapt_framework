"""Authorized web-target model for live VAPT assessments (Phase 32).

Provides the smallest clean representation needed for a web target plus
strict, fail-closed authorization and a safe preflight check.

Safety model (mentor demo):
    - Only explicit loopback hosts are authorized: 127.0.0.1, localhost.
    - Only explicitly authorized ports are allowed (default: 9191).
    - URL scheme must be http or https.
    - URLs with embedded credentials are rejected.
    - Hostnames are resolved and the resolved IP must be loopback.
    - URL fragments are stripped (never passed to scanners).
    - Frontend validation is UX only; this module is the security enforcement.

This module does NOT modify the research core and does NOT bypass
AuthorizationTracker / ScopeEnforcer / SafetyGate — it feeds them.
"""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Authorized scope (fail-closed defaults for the local mentor demo)
# ---------------------------------------------------------------------------

#: Hosts explicitly authorized for web-target assessments.
AUTHORIZED_WEB_HOSTS: set[str] = {"127.0.0.1", "localhost"}

#: Ports explicitly authorized for web-target assessments.
#: The OWASP Juice Shop demo runs on 9191. Override via
#: AI_VAPT_AUTHORIZED_WEB_PORTS="9191,8080" if the lab setup requires it.
def _default_web_ports() -> set[int]:
    raw = os.environ.get("AI_VAPT_AUTHORIZED_WEB_PORTS", "9191")
    ports: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            port = int(part)
        except ValueError:
            continue
        if 1 <= port <= 65535:
            ports.add(port)
    return ports or {9191}


AUTHORIZED_WEB_PORTS: set[int] = _default_web_ports()

#: IPs that a hostname is allowed to resolve to (loopback only).
LOOPBACK_IPS: set[str] = {"127.0.0.1", "::1"}

_DEFAULT_PORTS = {"http": 80, "https": 443}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class WebTargetError(ValueError):
    """Base error for web-target parsing/validation failures."""


class WebTargetAuthorizationError(WebTargetError):
    """Raised when a web target is outside the authorized scope (fail closed)."""


# ---------------------------------------------------------------------------
# Target model
# ---------------------------------------------------------------------------

@dataclass
class WebTarget:
    """Normalized representation of an authorized web target.

    Fields:
        scheme: "http" or "https"
        host: normalized hostname/IP as entered (e.g., "127.0.0.1")
        port: TCP port
        base_url: scheme://host:port (no path, query, fragment, credentials)
        normalized_url: canonical base URL used as the scanner target
        resolved_host: IP the host resolved to (e.g., "127.0.0.1")
    """
    scheme: str = "http"
    host: str = ""
    port: int = 80
    base_url: str = ""
    normalized_url: str = ""
    resolved_host: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "base_url": self.base_url,
            "normalized_url": self.normalized_url,
            "resolved_host": self.resolved_host,
        }


@dataclass
class WebTargetValidation:
    """Result of validating a raw URL string."""
    authorized: bool = False
    reason: str = ""
    target: Optional[WebTarget] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorized": self.authorized,
            "reason": self.reason,
            "target": self.target.to_dict() if self.target else None,
        }


# ---------------------------------------------------------------------------
# Parsing / validation
# ---------------------------------------------------------------------------

def _normalize_host(raw_host: str) -> str:
    """Normalize a hostname for allowlist comparison."""
    return (raw_host or "").strip().lower().rstrip(".")


def parse_web_target(raw_url: str) -> WebTarget:
    """Parse and strictly validate a web-target URL.

    Raises:
        WebTargetAuthorizationError: if the URL is malformed or outside the
            authorized scope. Always fail closed.
    """
    if raw_url is None or not str(raw_url).strip():
        raise WebTargetAuthorizationError("Target URL is required.")

    text = str(raw_url).strip()
    try:
        parsed = urlparse(text)
    except Exception as e:
        raise WebTargetAuthorizationError(f"Malformed URL: {e}")

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise WebTargetAuthorizationError(
            f"URL scheme must be http or https, got {scheme!r}."
        )

    # Reject embedded credentials (username/password or stray userinfo).
    if parsed.username or parsed.password:
        raise WebTargetAuthorizationError(
            "URLs containing embedded credentials are rejected."
        )
    if "@" in (parsed.netloc or ""):
        raise WebTargetAuthorizationError(
            "URLs containing userinfo are rejected."
        )

    host = _normalize_host(parsed.hostname or "")
    if not host:
        raise WebTargetAuthorizationError("URL must contain a valid host.")

    if host not in AUTHORIZED_WEB_HOSTS:
        raise WebTargetAuthorizationError(
            f"Host {host!r} is not authorized. "
            f"Authorized hosts: {sorted(AUTHORIZED_WEB_HOSTS)}."
        )

    # Resolve safely; the resolved IP must be loopback (DNS-rebinding guard).
    try:
        resolved = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        resolved_host = resolved[0][4][0] if resolved else ""
    except Exception as e:
        raise WebTargetAuthorizationError(
            f"Could not resolve host {host!r}: {e}"
        )
    # Normalize IPv6-mapped IPv4 (e.g. ::ffff:127.0.0.1).
    normalized_ip = resolved_host.lower()
    if normalized_ip.startswith("::ffff:"):
        normalized_ip = normalized_ip[len("::ffff:"):]
    if normalized_ip not in LOOPBACK_IPS:
        raise WebTargetAuthorizationError(
            f"Host {host!r} resolved to {resolved_host!r}, which is not loopback. "
            "Only local targets are authorized."
        )

    # Port: explicit or scheme default; must be in the authorized set.
    try:
        port = parsed.port or _DEFAULT_PORTS[scheme]
    except ValueError:
        raise WebTargetAuthorizationError("URL contains an invalid port.")
    if port not in AUTHORIZED_WEB_PORTS:
        raise WebTargetAuthorizationError(
            f"Port {port} is not authorized. "
            f"Authorized ports: {sorted(AUTHORIZED_WEB_PORTS)}."
        )

    base_url = f"{scheme}://{host}:{port}"
    return WebTarget(
        scheme=scheme,
        host=host,
        port=port,
        base_url=base_url,
        normalized_url=base_url,  # fragments/query never preserved
        resolved_host=resolved_host,
    )


def validate_web_target(raw_url: str) -> WebTargetValidation:
    """Validate a URL without raising (for UX preflight + API responses)."""
    try:
        target = parse_web_target(raw_url)
    except WebTargetAuthorizationError as e:
        return WebTargetValidation(authorized=False, reason=str(e))
    return WebTargetValidation(
        authorized=True,
        reason=f"AUTHORIZED LOCAL TARGET ({target.host}:{target.port})",
        target=target,
    )


# ---------------------------------------------------------------------------
# Preflight: authorization + scope + safe connectivity check
# ---------------------------------------------------------------------------

def preflight_web_target(raw_url: str, timeout: float = 5.0) -> dict[str, Any]:
    """Run target preflight: parse, authorize, scope-check, connectivity.

    The connectivity check opens a plain TCP connection and performs a
    single minimal HTTP GET / (no scanning, no payloads). Never raises for
    authorization failures — they are reported in the result dict.

    Returns dict with: target_url, resolved_host, port,
    authorization_status, preflight_status, reachable, http_status, detail.
    """
    validation = validate_web_target(raw_url)
    if not validation.authorized or validation.target is None:
        return {
            "target_url": str(raw_url).strip() if raw_url else "",
            "resolved_host": "",
            "port": 0,
            "authorization_status": "REJECTED",
            "preflight_status": "NOT AUTHORIZED",
            "reachable": False,
            "http_status": 0,
            "detail": validation.reason,
        }

    target = validation.target
    try:
        import http.client

        conn = http.client.HTTPConnection(
            target.resolved_host, target.port, timeout=timeout
        )
        # Preserve original hostname for virtual-host routing.
        conn.request("GET", "/", headers={"Host": f"{target.host}:{target.port}"})
        resp = conn.getresponse()
        # Drain a small prefix only; this is a reachability probe.
        resp.read(4096)
        status = resp.status
        conn.close()
        reachable = 100 <= status < 600
        return {
            "target_url": target.normalized_url,
            "resolved_host": target.resolved_host,
            "port": target.port,
            "authorization_status": "AUTHORIZED",
            "preflight_status": "TARGET REACHABLE" if reachable else "TARGET UNREACHABLE",
            "reachable": reachable,
            "http_status": status,
            "detail": f"HTTP {status} from {target.normalized_url}",
        }
    except Exception as e:
        return {
            "target_url": target.normalized_url,
            "resolved_host": target.resolved_host,
            "port": target.port,
            "authorization_status": "AUTHORIZED",
            "preflight_status": "TARGET UNREACHABLE",
            "reachable": False,
            "http_status": 0,
            "detail": f"Connectivity check failed: {e}",
        }
