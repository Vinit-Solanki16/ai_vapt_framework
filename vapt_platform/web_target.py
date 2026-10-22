"""Authorized web-target model for live VAPT assessments (Phase 32).

Provides the smallest clean representation needed for a web target plus
strict, fail-closed authorization and a safe preflight check.

Safety model:
    - Local loopback hosts (127.0.0.1, localhost) remain authorized on the
      explicitly authorized local ports (default: 9191, override via
      AI_VAPT_AUTHORIZED_WEB_PORTS).
    - EXTERNAL targets are authorized ONLY through exact ``host:port``
      entries in the ``VAPT_AUTHORIZED_WEB_SCOPES`` environment variable
      (comma-delimited, e.g. ``pentest-ground.com:4280``). Empty/unset
      configuration preserves the local-only default. There are no
      wildcard domains, no CIDR ranges, and no silently permitted public
      hosts.
    - URL scheme must be http or https.
    - URLs with embedded credentials are rejected.
    - Hostnames are normalized strictly (ASCII, no percent-encoding, no
      ambiguous numeric IP spellings) and matched EXACTLY — a path, query
      string or fragment never broadens the authorized scope.
    - Hostname authorization, port authorization and resolved-address
      validation are three separate, individually testable checks.
    - Hostnames are resolved and, for EXTERNAL scopes, EVERY resolved
      address must be a public destination address (loopback, private,
      link-local, CGNAT, multicast, documentation and other non-public
      ranges are rejected, and mixed safe/unsafe result sets fail closed).
    - Localhost DNS-rebinding protections are preserved: every resolved
      address must be loopback.
    - The preflight probe connects to the VALIDATED resolved address
      (pinned destination), never follows redirects, and for HTTPS uses
      the original hostname for SNI/certificate verification.
    - Frontend validation is UX only; this module is the security
      enforcement.

This module does NOT modify the research core and does NOT bypass
AuthorizationTracker / ScopeEnforcer / SafetyGate — it feeds them.
"""
from __future__ import annotations

from datetime import datetime, timezone
import http.client
import ipaddress
import os
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin, urlparse


# ---------------------------------------------------------------------------
# Authorized scope (fail-closed defaults for the local mentor demo)
# ---------------------------------------------------------------------------

#: Hosts explicitly authorized for web-target assessments (local policy).
AUTHORIZED_WEB_HOSTS: set[str] = {"127.0.0.1", "localhost"}

#: Ports explicitly authorized for LOCAL web-target assessments.
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

#: IPs that a LOCAL hostname is allowed to resolve to (loopback only).
LOOPBACK_IPS: set[str] = {"127.0.0.1", "::1"}

_DEFAULT_PORTS = {"http": 80, "https": 443}


# ---------------------------------------------------------------------------
# Configurable external web scope: VAPT_AUTHORIZED_WEB_SCOPES
# ---------------------------------------------------------------------------
#
# Format (documented in .env.example and README):
#     VAPT_AUTHORIZED_WEB_SCOPES="host:port[,host:port...]"
#
# Examples:
#     VAPT_AUTHORIZED_WEB_SCOPES="pentest-ground.com:4280"
#     VAPT_AUTHORIZED_WEB_SCOPES="pentest-ground.com:4280,app.example.org:8443"
#     VAPT_AUTHORIZED_WEB_SCOPES="[2001:db8::10]:8443"   (IPv6 in brackets)
#
# Rules (fail closed):
#     - Exactly one comma-delimited entry per authorized host AND port.
#     - The port is REQUIRED and must match exactly.
#     - No schemes, paths, queries, fragments, credentials or wildcards.
#     - No wildcard domains, no CIDR ranges: exact host matching only,
#       after safe hostname normalization (lowercase, no trailing dot,
#       strict ASCII label rules, no percent-encoding).
#     - Ambiguous numeric spellings that some resolvers treat as IPs
#       (e.g. "2130706433", "127.1") are rejected at configuration time.
#     - Empty/unset configuration authorizes ONLY the local loopback
#       policy above. There is no global bypass and no "allow all".
#
#: Environment variable holding the external authorized web scope.
SCOPE_ENV_VAR = "VAPT_AUTHORIZED_WEB_SCOPES"
#: Delimiter between scope entries.
SCOPE_DELIMITER = ","
#: Canonical example shown in error messages / docs.
SCOPE_ENTRY_EXAMPLE = "pentest-ground.com:4280"

#: Scope kinds recorded on validated targets.
SCOPE_KIND_LOCAL = "LOCAL_LOOPBACK"
SCOPE_KIND_EXTERNAL = "EXTERNAL_SCOPE"

_HOSTNAME_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_NUMERIC_OR_DOTTED_RE = re.compile(r"^[0-9.]+$")
_SCHEME_OR_UNSAFE_CHARS = ("://", "/", "?", "#", "@", "*", "%")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class WebTargetError(ValueError):
    """Base error for web-target parsing/validation failures."""


class WebTargetAuthorizationError(WebTargetError):
    """Raised when a web target is outside the authorized scope (fail closed)."""


class AuthorizedScopeConfigurationError(WebTargetAuthorizationError):
    """Raised when VAPT_AUTHORIZED_WEB_SCOPES contains an invalid entry.

    Subclasses WebTargetAuthorizationError so every enforcement point
    (API, application, scanners, SafetyGate) fails closed with the same
    clear configuration message instead of silently ignoring a broken
    allowlist.
    """


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
        resolved_host: preferred validated destination IP for scanner argv
        resolved_ips: ALL validated destination IPs (fail-closed set)
        scope_kind: SCOPE_KIND_LOCAL or SCOPE_KIND_EXTERNAL
        scope_entry: the exact authorized scope entry (e.g. "localhost:9191")
        external: True when authorization came from VAPT_AUTHORIZED_WEB_SCOPES or Engagement
        engagement_id: Optional ID of authorizing EngagementProfile
        engagement_name: Optional name of authorizing EngagementProfile
        authorization_reference: Optional authorization document/RoE reference
    """
    scheme: str = "http"
    host: str = ""
    port: int = 80
    base_url: str = ""
    normalized_url: str = ""
    resolved_host: str = ""
    resolved_ips: list[str] = field(default_factory=list)
    scope_kind: str = ""
    scope_entry: str = ""
    external: bool = False
    engagement_id: Optional[str] = None
    engagement_name: Optional[str] = None
    authorization_reference: Optional[str] = None
    engagement_snapshot: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "base_url": self.base_url,
            "normalized_url": self.normalized_url,
            "resolved_host": self.resolved_host,
            "resolved_ips": list(self.resolved_ips),
            "scope_kind": self.scope_kind,
            "scope_entry": self.scope_entry,
            "external": self.external,
            "engagement_id": self.engagement_id,
            "engagement_name": self.engagement_name,
            "authorization_reference": self.authorization_reference,
            "engagement_snapshot": self.engagement_snapshot,
        }


@dataclass
class WebTargetValidation:
    """Result of validating a raw URL string.

    The individual check flags make the three enforcement stages visible
    to the GUI/API without ever claiming "authorized" before the backend
    has completed every stage.
    """
    authorized: bool = False
    reason: str = ""
    target: Optional[WebTarget] = None
    hostname_authorized: bool = False
    port_authorized: bool = False
    addresses_validated: bool = False
    in_configured_scope: bool = False
    engagement_id: Optional[str] = None
    engagement_name: Optional[str] = None
    authorization_reference: Optional[str] = None
    engagement_snapshot: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorized": self.authorized,
            "reason": self.reason,
            "target": self.target.to_dict() if self.target else None,
            "hostname_authorized": self.hostname_authorized,
            "port_authorized": self.port_authorized,
            "addresses_validated": self.addresses_validated,
            "in_configured_scope": self.in_configured_scope,
            "engagement_id": self.engagement_id,
            "engagement_name": self.engagement_name,
            "authorization_reference": self.authorization_reference,
            "engagement_snapshot": self.engagement_snapshot,
        }


# ---------------------------------------------------------------------------
# Hostname normalization / strict validation
# ---------------------------------------------------------------------------

def _normalize_host(raw_host: str) -> str:
    """Normalize a hostname for allowlist comparison."""
    return (raw_host or "").strip().lower().rstrip(".")


def _is_valid_hostname(host: str) -> bool:
    """Strict RFC-1123-style hostname check (lowercase ASCII only)."""
    if not host or len(host) > 253:
        return False
    labels = host.split(".")
    if any(not label for label in labels):
        return False
    return all(_HOSTNAME_LABEL_RE.match(label) for label in labels)


def _normalize_url_host(raw_host: str) -> str:
    """Normalize and strictly validate the host taken from a user URL.

    Rejects (fail closed) anything that could be an encoding or parsing
    trick: non-ASCII/punycode-lookalike input, whitespace/control chars,
    percent-encoded hosts, empty DNS labels, and ambiguous numeric
    spellings that some resolvers treat as IP addresses
    (e.g. ``2130706433``, ``0x7f.0.0.1`` is caught by the exact-match
    allowlist, ``127.1`` is rejected here).

    Returns the normalized host (lowercase, no trailing dot, compressed
    IPv6 without brackets, canonical dotted-quad IPv4).

    Raises:
        WebTargetAuthorizationError: when the host is unsafe or ambiguous.
    """
    host = _normalize_host(raw_host)
    if not host:
        return ""

    if not host.isascii() or any(ch.isspace() or ord(ch) < 32 for ch in host):
        raise WebTargetAuthorizationError(
            f"URL host {raw_host!r} contains whitespace, control or "
            "non-ASCII characters."
        )
    if "%" in host:
        raise WebTargetAuthorizationError(
            f"URL host {raw_host!r} contains percent-encoding, which is "
            "rejected to prevent normalization tricks."
        )

    if ":" in host:
        # IPv6 literal (urlparse strips the brackets).
        try:
            return ipaddress.IPv6Address(host).compressed
        except ValueError:
            raise WebTargetAuthorizationError(
                f"URL host {raw_host!r} is not a valid IPv6 address."
            )

    if _NUMERIC_OR_DOTTED_RE.match(host):
        # All-numeric/dotted values must be EXACT dotted-quad IPv4.
        try:
            return str(ipaddress.IPv4Address(host))
        except ValueError:
            raise WebTargetAuthorizationError(
                f"URL host {raw_host!r} is an ambiguous numeric value, not a "
                "dotted-quad IPv4 address. Only exact addresses or strict "
                "hostnames are accepted."
            )

    if not _is_valid_hostname(host):
        raise WebTargetAuthorizationError(
            f"URL host {raw_host!r} is not a valid hostname."
        )
    return host


# ---------------------------------------------------------------------------
# Configurable scope parsing / validation
# ---------------------------------------------------------------------------

def _validate_scope_host(raw_host: str) -> str:
    """Validate + normalize the host part of a scope configuration entry."""
    host = _normalize_host(raw_host)
    if not host:
        raise AuthorizedScopeConfigurationError(
            f"Invalid {SCOPE_ENV_VAR} entry: empty host."
        )
    if not host.isascii() or any(ch.isspace() or ord(ch) < 32 for ch in host):
        raise AuthorizedScopeConfigurationError(
            f"Invalid {SCOPE_ENV_VAR} entry: host {raw_host!r} contains "
            "whitespace, control or non-ASCII characters."
        )
    if "%" in host:
        raise AuthorizedScopeConfigurationError(
            f"Invalid {SCOPE_ENV_VAR} entry: host {raw_host!r} must not "
            "contain percent-encoding or IPv6 zone identifiers."
        )
    if ":" in host:
        try:
            return ipaddress.IPv6Address(host).compressed
        except ValueError:
            raise AuthorizedScopeConfigurationError(
                f"Invalid {SCOPE_ENV_VAR} entry: {raw_host!r} is not a "
                "valid IPv6 address."
            )
    if _NUMERIC_OR_DOTTED_RE.match(host):
        try:
            return str(ipaddress.IPv4Address(host))
        except ValueError:
            raise AuthorizedScopeConfigurationError(
                f"Invalid {SCOPE_ENV_VAR} entry: {raw_host!r} is an "
                "ambiguous numeric value, not a dotted-quad IPv4 address."
            )
    if not _is_valid_hostname(host):
        raise AuthorizedScopeConfigurationError(
            f"Invalid {SCOPE_ENV_VAR} entry: {raw_host!r} is not a valid "
            "hostname."
        )
    return host


def _parse_scope_entry(entry: str) -> tuple[str, int]:
    """Parse one exact ``host:port`` scope entry.

    Raises:
        AuthorizedScopeConfigurationError: on any invalid entry, with a
        message naming the offending value and the expected format.
    """
    text = (entry or "").strip()
    if not text:
        raise AuthorizedScopeConfigurationError(
            f"Invalid {SCOPE_ENV_VAR} entry: empty entry. "
            f"Expected exact host:port values such as {SCOPE_ENTRY_EXAMPLE!r}."
        )
    for bad in _SCHEME_OR_UNSAFE_CHARS:
        if bad in text:
            raise AuthorizedScopeConfigurationError(
                f"Invalid {SCOPE_ENV_VAR} entry {text!r}: scope entries are "
                "exact host:port values only — no scheme, path, query, "
                "fragment, credentials or wildcards. "
                f"Example: {SCOPE_ENTRY_EXAMPLE!r}."
            )

    if text.startswith("["):
        end = text.find("]")
        if end == -1:
            raise AuthorizedScopeConfigurationError(
                f"Invalid {SCOPE_ENV_VAR} entry {text!r}: unterminated "
                "IPv6 bracket."
            )
        raw_host, rest = text[1:end], text[end + 1:]
        if not rest.startswith(":"):
            raise AuthorizedScopeConfigurationError(
                f"Invalid {SCOPE_ENV_VAR} entry {text!r}: IPv6 entries must "
                "use [address]:port."
            )
        port_text = rest[1:]
    else:
        if text.count(":") == 0:
            raise AuthorizedScopeConfigurationError(
                f"Invalid {SCOPE_ENV_VAR} entry {text!r}: missing port. "
                f"Expected exact host:port values such as {SCOPE_ENTRY_EXAMPLE!r}."
            )
        if text.count(":") > 1:
            raise AuthorizedScopeConfigurationError(
                f"Invalid {SCOPE_ENV_VAR} entry {text!r}: IPv6 addresses must "
                "be written as [address]:port."
            )
        raw_host, port_text = text.split(":", 1)

    host = _validate_scope_host(raw_host)
    try:
        port = int(port_text.strip())
    except ValueError:
        raise AuthorizedScopeConfigurationError(
            f"Invalid {SCOPE_ENV_VAR} entry {text!r}: port {port_text!r} is "
            "not an integer."
        )
    if not 1 <= port <= 65535:
        raise AuthorizedScopeConfigurationError(
            f"Invalid {SCOPE_ENV_VAR} entry {text!r}: port {port} is out of "
            "range 1-65535."
        )
    return host, port


def parse_authorized_web_scopes(raw: Optional[str]) -> frozenset[tuple[str, int]]:
    """Parse a ``VAPT_AUTHORIZED_WEB_SCOPES`` value into exact (host, port) pairs.

    Empty/None yields an empty set (local-only default). Any invalid
    entry raises ``AuthorizedScopeConfigurationError`` — a broken
    allowlist is never silently ignored.
    """
    if raw is None:
        return frozenset()
    entries: set[tuple[str, int]] = set()
    for part in str(raw).split(SCOPE_DELIMITER):
        part = part.strip()
        if not part:
            continue
        entries.add(_parse_scope_entry(part))
    return frozenset(entries)


def configured_external_web_scopes() -> frozenset[tuple[str, int]]:
    """Read and validate the external scope from the process environment."""
    return parse_authorized_web_scopes(os.environ.get(SCOPE_ENV_VAR, ""))


def authorized_external_scope_strings() -> list[str]:
    """Human-readable sorted list of configured external scope entries."""
    return sorted(f"{h}:{p}" for h, p in configured_external_web_scopes())


# ---------------------------------------------------------------------------
# Stage 1 — hostname authorization
# ---------------------------------------------------------------------------

def authorize_hostname(host: str, engagement_id: Optional[str] = None) -> str:
    """Authorize an already-normalized hostname. Returns the scope kind.

    Local policy: exact membership in AUTHORIZED_WEB_HOSTS.
    Engagement policy: if engagement_id is specified.
    External policy: the host must appear in at least one EXACT
    ``host:port`` entry of VAPT_AUTHORIZED_WEB_SCOPES (port checked in
    the next, separate stage).
    """
    # Validate the external scope configuration first: a broken allowlist
    # must fail closed for EVERY target with a clear configuration error,
    # never be silently ignored.
    scopes = configured_external_web_scopes()
    if host in AUTHORIZED_WEB_HOSTS:
        return SCOPE_KIND_LOCAL

    if engagement_id:
        try:
            from vapt_platform.engagements import get_engagement_manager
            profile = get_engagement_manager().get_profile(engagement_id)
            if not profile:
                raise WebTargetAuthorizationError(
                    f"Engagement profile {engagement_id!r} not found."
                )
            if not profile.is_active():
                raise WebTargetAuthorizationError(
                    f"Engagement profile '{profile.name}' is inactive or expired. "
                    f"An operator must review and activate it with a genuine recorded authorization reference before use."
                )
            if host in [h.lower() for h in profile.authorized_hosts]:
                return SCOPE_KIND_EXTERNAL
            raise WebTargetAuthorizationError(
                f"Host {host!r} is not authorized under engagement '{profile.name}'. "
                f"Authorized hosts in profile: {profile.authorized_hosts}."
            )
        except ImportError:
            pass

    if any(h == host for h, _port in scopes):
        return SCOPE_KIND_EXTERNAL

    scope_list = ", ".join(sorted(f"{h}:{p}" for h, p in scopes)) or "none"
    raise WebTargetAuthorizationError(
        f"Host {host!r} is not authorized. Local hosts: "
        f"{sorted(AUTHORIZED_WEB_HOSTS)}. Configured external scopes "
        f"({SCOPE_ENV_VAR}): {scope_list}. An administrator must add the "
        f"exact host:port to {SCOPE_ENV_VAR} (for example "
        f"{SCOPE_ENTRY_EXAMPLE!r}) to authorize an external target."
    )


# ---------------------------------------------------------------------------
# Stage 2 — port authorization
# ---------------------------------------------------------------------------

def authorize_port(
    host: str, port: int, scope_kind: str, engagement_id: Optional[str] = None
) -> None:
    """Authorize a port for an already-authorized host (separate check)."""
    if scope_kind == SCOPE_KIND_LOCAL:
        if port not in AUTHORIZED_WEB_PORTS:
            raise WebTargetAuthorizationError(
                f"Port {port} is not authorized for local host {host!r}. "
                f"Authorized local ports: {sorted(AUTHORIZED_WEB_PORTS)}."
            )
        return

    if engagement_id:
        try:
            from vapt_platform.engagements import get_engagement_manager
            profile = get_engagement_manager().get_profile(engagement_id)
            if profile and profile.is_active():
                if port not in profile.allowed_ports:
                    raise WebTargetAuthorizationError(
                        f"Port {port} is not authorized for host {host!r} under engagement "
                        f"'{profile.name}'. Allowed ports: {sorted(profile.allowed_ports)}."
                    )
                return
        except ImportError:
            pass

    scopes = configured_external_web_scopes()
    if (host, port) in scopes:
        return

    allowed = sorted(
        f"{h}:{p}" for h, p in scopes if h == host
    ) or "none"
    raise WebTargetAuthorizationError(
        f"Port {port} is not authorized for host {host!r}. Authorized "
        f"host:port entries for this host: {allowed}. Configure the "
        f"exact entry via {SCOPE_ENV_VAR}."
    )


# ---------------------------------------------------------------------------
# Stage 3 — resolution + destination-address validation
# ---------------------------------------------------------------------------

def _normalize_resolved_ip(raw_ip: str) -> str:
    """Normalize a resolved IP for allowlist comparison.

    Handles IPv6-mapped IPv4 (``::ffff:127.0.0.1``) and IPv6 zone ids
    (``::1%lo``) so allowlist checks are portable across platforms.
    """
    text = (raw_ip or "").strip().lower()
    # Strip IPv6 zone id if present (e.g. "::1%lo0").
    if "%" in text:
        text = text.split("%", 1)[0]
    if text.startswith("::ffff:"):
        text = text[len("::ffff:"):]
    return text


def resolve_addresses(host: str) -> list[str]:
    """Resolve *host* and return ALL normalized addresses (no filtering).

    Raises:
        WebTargetAuthorizationError: on resolution failure or when any
            result is not a parseable IP address.
    """
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except Exception as e:
        raise WebTargetAuthorizationError(
            f"Could not resolve host {host!r}: {e}"
        )
    raw_ips = [info[4][0] for info in infos if info[4] and info[4][0]]
    if not raw_ips:
        raise WebTargetAuthorizationError(
            f"Could not resolve host {host!r}: no addresses returned."
        )
    normalized: list[str] = []
    for raw in raw_ips:
        norm = _normalize_resolved_ip(raw)
        try:
            normalized.append(ipaddress.ip_address(norm).compressed)
        except ValueError:
            raise WebTargetAuthorizationError(
                f"Host {host!r} resolved to invalid address {raw!r}."
            )
    return normalized


def _is_public_destination(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for global, routable destination addresses.

    Rejects loopback, private (RFC1918 / ULA), link-local, unspecified,
    multicast, reserved, CGNAT (100.64/10), documentation/TEST-NET and
    every other non-public range. Fail closed.
    """
    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    ):
        return False
    # is_global is False for CGNAT, documentation ranges, 6to4 relays etc.
    return bool(ip.is_global)


def validate_resolved_addresses(
    host: str, ips: list[str], scope_kind: str
) -> None:
    """Validate a complete resolution result for the given scope kind.

    Fail-closed rules:
      - Resolution must yield at least one address.
      - LOCAL scope: EVERY address must be loopback (DNS-rebinding guard
        over the whole result set).
      - EXTERNAL scope: EVERY address must be a public destination
        address; mixed safe/unsafe result sets are rejected.
    """
    if not ips:
        raise WebTargetAuthorizationError(
            f"Could not resolve host {host!r}: no addresses returned."
        )
    if scope_kind == SCOPE_KIND_LOCAL:
        for norm in ips:
            if norm not in LOOPBACK_IPS:
                raise WebTargetAuthorizationError(
                    f"Host {host!r} resolved to {norm!r}, which is not "
                    "loopback. Only local targets are authorized."
                )
        return
    for norm in ips:
        try:
            ip = ipaddress.ip_address(norm)
        except ValueError:
            raise WebTargetAuthorizationError(
                f"Host {host!r} resolved to invalid address {norm!r}."
            )
        if not _is_public_destination(ip):
            raise WebTargetAuthorizationError(
                f"Host {host!r} resolved to {norm!r}, which is not a public "
                "destination address. External scopes may only target "
                "publicly routable addresses (loopback, private, "
                "link-local, CGNAT and other non-public ranges are "
                "rejected)."
            )


def _resolve_to_loopback_ip(host: str) -> str:
    """Resolve *host* to a deterministic loopback IP (local policy).

    Portable behavior:
      - Queries ``socket.getaddrinfo`` (all results, not just the first,
        because ordering is platform-dependent — e.g. Ubuntu 24.04 /
        Codespaces returns ``::1`` first for ``localhost`` while other
        systems return ``127.0.0.1`` first).
      - Fails closed unless at least one address resolves AND every
        resolved address is loopback (DNS-rebinding guard over ALL
        results, strictly stronger than first-result-only checks).
      - Deterministically prefers IPv4 ``127.0.0.1`` when present so
        scanner argv / preflight connections are stable across IPv6-first
        and IPv4-first resolvers. Falls back to ``::1`` only when it is
        the sole loopback result.

    Raises:
        WebTargetAuthorizationError: on resolution failure or when any
            resolved address is not loopback.
    """
    ips = resolve_addresses(host)
    validate_resolved_addresses(host, ips, SCOPE_KIND_LOCAL)
    # Deterministic preference: IPv4 loopback first for scanner portability.
    if "127.0.0.1" in ips:
        return "127.0.0.1"
    if "::1" in ips:
        return "::1"
    # Unreachable given LOOPBACK_IPS, but fail closed deterministically.
    return sorted(set(ips))[0]


def _preferred_destination(ips: list[str], scope_kind: str) -> str:
    """Deterministic scanner destination for a validated resolution set."""
    if scope_kind == SCOPE_KIND_LOCAL:
        # Preserve the historic IPv4-first preference for loopback targets.
        if "127.0.0.1" in ips:
            return "127.0.0.1"
        if "::1" in ips:
            return "::1"
    # External: prefer IPv4 for scanner argv stability, else first entry.
    ipv4 = [ip for ip in ips if ":" not in ip]
    if ipv4:
        return sorted(ipv4)[0]
    return sorted(ips)[0]


# ---------------------------------------------------------------------------
# Parsing / validation
# ---------------------------------------------------------------------------

def parse_web_target(raw_url: str, engagement_id: Optional[str] = None) -> WebTarget:
    """Parse and strictly validate a web-target URL.

    Three separate enforcement stages, in order:
      1. hostname authorization (local policy, external scope, or engagement profile),
      2. port authorization for that host,
      3. resolution + destination-address validation for the scope kind.
    A URL's path, query and fragment are stripped from the normalized scanner target,
    though path prefixes may be verified against engagement restrictions.

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

    host = _normalize_url_host(parsed.hostname or "")
    if not host:
        raise WebTargetAuthorizationError("URL must contain a valid host.")

    # --- Stage 1: hostname authorization ---------------------------------
    scope_kind = authorize_hostname(host, engagement_id=engagement_id)

    # Port: explicit or scheme default (invalid ports fail closed).
    try:
        port = parsed.port or _DEFAULT_PORTS[scheme]
    except ValueError:
        raise WebTargetAuthorizationError("URL contains an invalid port.")

    # --- Stage 2: port authorization -------------------------------------
    authorize_port(host, port, scope_kind, engagement_id=engagement_id)

    # Check engagement path restrictions if applicable
    matched_profile = None
    try:
        from vapt_platform.engagements import get_engagement_manager
        mgr = get_engagement_manager()
        if engagement_id:
            matched_profile = mgr.get_profile(engagement_id)
        else:
            for p in mgr.list_profiles(active_only=True):
                if host in [h.lower() for h in p.authorized_hosts] and port in p.allowed_ports:
                    matched_profile = p
                    break
    except ImportError:
        pass

    if matched_profile and matched_profile.permitted_paths:
        path = parsed.path or "/"
        if not any(path.startswith(prefix) for prefix in matched_profile.permitted_paths):
            raise WebTargetAuthorizationError(
                f"Target path {path!r} is outside permitted paths for engagement "
                f"'{matched_profile.name}'. Permitted prefixes: {matched_profile.permitted_paths}."
            )

    # --- Stage 3: resolution + destination-address validation ------------
    resolved_ips = resolve_addresses(host)
    validate_resolved_addresses(host, resolved_ips, scope_kind)
    resolved_host = _preferred_destination(resolved_ips, scope_kind)

    external = scope_kind == SCOPE_KIND_EXTERNAL
    scope_entry = f"{host}:{port}"
    base_url = f"{scheme}://{host}:{port}"

    engagement_snapshot = None
    if matched_profile:
        engagement_snapshot = {
            "id": matched_profile.id,
            "name": matched_profile.name,
            "authorized_hosts": list(matched_profile.authorized_hosts),
            "allowed_ports": list(matched_profile.allowed_ports),
            "permitted_paths": list(matched_profile.permitted_paths),
            "authorization_reference": matched_profile.authorization_reference,
            "scanner_policy": matched_profile.scanner_policy,
            "status": matched_profile.status,
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
        }

    return WebTarget(
        scheme=scheme,
        host=host,
        port=port,
        base_url=base_url,
        normalized_url=base_url,  # fragments/query never preserved
        resolved_host=resolved_host,
        resolved_ips=resolved_ips,
        scope_kind=scope_kind,
        scope_entry=scope_entry,
        external=external,
        engagement_id=matched_profile.id if matched_profile else None,
        engagement_name=matched_profile.name if matched_profile else None,
        authorization_reference=matched_profile.authorization_reference if matched_profile else None,
        engagement_snapshot=engagement_snapshot,
    )


def validate_web_target(raw_url: str, engagement_id: Optional[str] = None) -> WebTargetValidation:
    """Validate a URL without raising (for UX preflight + API responses)."""
    try:
        target = parse_web_target(raw_url, engagement_id=engagement_id)
    except WebTargetAuthorizationError as e:
        return WebTargetValidation(authorized=False, reason=str(e))
    if target.external:
        if target.engagement_name:
            reason = (
                f"AUTHORIZED ENGAGEMENT TARGET ({target.host}:{target.port}) — "
                f"covered by engagement '{target.engagement_name}' (Ref: {target.authorization_reference or 'N/A'})"
            )
        else:
            reason = (
                f"AUTHORIZED EXTERNAL TARGET ({target.host}:{target.port}) — "
                f"covered by {SCOPE_ENV_VAR} entry {target.scope_entry}"
            )
    else:
        reason = f"AUTHORIZED LOCAL TARGET ({target.host}:{target.port})"
    return WebTargetValidation(
        authorized=True,
        reason=reason,
        target=target,
        hostname_authorized=True,
        port_authorized=True,
        addresses_validated=True,
        in_configured_scope=True,
        engagement_id=target.engagement_id,
        engagement_name=target.engagement_name,
        authorization_reference=target.authorization_reference,
        engagement_snapshot=target.engagement_snapshot,
    )


# ---------------------------------------------------------------------------
# Preflight: authorization + scope + safe connectivity check
# ---------------------------------------------------------------------------

def _host_for_header(host: str, port: int) -> str:
    """Host header value (IPv6 bracketed)."""
    if ":" in host and not host.startswith("["):
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def _conn_host(resolved_host: str) -> str:
    """Connection host for http.client (IPv6 bracketed)."""
    if ":" in resolved_host and not resolved_host.startswith("["):
        return f"[{resolved_host}]"
    return resolved_host


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to a validated IP with correct SNI.

    ``http.client.HTTPSConnection`` derives the TLS SNI / certificate
    hostname from the connection host. When we pin the destination to the
    already-validated IP (DNS-rebinding defense), the certificate would
    otherwise be verified against the IP. This subclass connects to the
    pinned IP while verifying the certificate against the ORIGINAL
    authorized hostname.
    """

    def __init__(
        self,
        host: str,
        port: int,
        server_hostname: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(_conn_host(host), port, **kwargs)
        self._server_hostname = server_hostname

    def connect(self) -> None:  # type: ignore[override]
        # ``self.host`` is already unbracketed by HTTPConnection._get_hostport.
        sock = socket.create_connection(
            (self.host, self.port), self.timeout, self.source_address
        )
        self.sock = self._context.wrap_socket(
            sock, server_hostname=self._server_hostname or self.host
        )


def _probe_target(target: WebTarget, timeout: float) -> dict[str, Any]:
    """Single minimal HTTP GET / against the pinned, validated destination.

    Safety properties:
      - Connects to ``target.resolved_host`` (the validated destination),
        never re-resolving a user-controlled hostname at probe time.
      - NEVER follows redirects (``http.client`` does not follow them and
        no redirect handling is added). A redirect response is recorded
        and its Location target is checked against the authorized scope
        for reporting only.
      - For HTTPS, the original hostname is used for SNI/certificate
        verification while the socket stays pinned to the validated IP.

    Returns dict with http_status, location, detail. Raises on failure.
    """
    headers = {
        "Host": _host_for_header(target.host, target.port),
        "User-Agent": "ai-vapt-preflight/1.0",
        "Accept": "*/*",
        "Connection": "close",
    }
    if target.scheme == "https":
        conn = _PinnedHTTPSConnection(  # type: ignore[call-arg]
            target.resolved_host, target.port,
            server_hostname=target.host, timeout=timeout,
        )
    else:
        conn = http.client.HTTPConnection(
            _conn_host(target.resolved_host), target.port, timeout=timeout
        )
    try:
        conn.request("GET", "/", headers=headers)
        resp = conn.getresponse()
        # Drain a small prefix only; this is a reachability probe.
        resp.read(4096)
        return {
            "http_status": resp.status,
            "location": resp.getheader("Location") or "",
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _evaluate_redirect(target: WebTarget, location: str) -> dict[str, Any]:
    """Classify a redirect WITHOUT following it.

    Returns a dict stating whether the redirect target stays on the
    authorized host:port. Redirects are never followed by this platform.
    """
    info: dict[str, Any] = {
        "location": location,
        "followed": False,
        "host": "",
        "port": 0,
        "in_scope": False,
        "note": "Redirects are never followed by the preflight probe.",
    }
    if not location:
        return info
    try:
        absolute = urljoin(target.base_url + "/", location)
        parsed = urlparse(absolute)
        red_host = _normalize_host(parsed.hostname or "")
        red_port = parsed.port or _DEFAULT_PORTS.get((parsed.scheme or "").lower(), 0)
    except Exception as e:
        info["note"] = f"Redirect Location could not be parsed ({e}); not followed."
        return info
    info["host"] = red_host
    info["port"] = red_port
    info["in_scope"] = (red_host == target.host and red_port == target.port)
    if not info["in_scope"]:
        info["note"] = (
            f"Redirect to {red_host}:{red_port} is OUTSIDE the authorized "
            f"scope {target.host}:{target.port}; it was NOT followed."
        )
    else:
        info["note"] = (
            f"Redirect to {red_host}:{red_port} stays inside the authorized "
            "scope but was NOT followed (probe only)."
        )
    return info


def preflight_web_target(
    raw_url: str,
    timeout: float = 5.0,
    engagement_id: Optional[str] = None,
) -> dict[str, Any]:
    """Run target preflight: parse, authorize, scope-check, connectivity.

    The connectivity check opens a plain TCP connection to the VALIDATED
    destination and performs a single minimal HTTP GET / (no scanning, no
    payloads, no redirect following). Never raises for authorization
    failures — they are reported in the result dict.

    Returns dict with: target_url, resolved_host, port, scheme, hostname,
    scope_kind, scope_entry, external, in_scope, address_validation,
    authorization_status, preflight_status, reachable, http_status,
    redirect, detail.
    """
    validation = validate_web_target(raw_url, engagement_id=engagement_id)
    if not validation.authorized or validation.target is None:
        return {
            "target_url": str(raw_url).strip() if raw_url else "",
            "resolved_host": "",
            "port": 0,
            "scheme": "",
            "hostname": "",
            "scope_kind": "",
            "scope_entry": "",
            "external": False,
            "in_scope": False,
            "address_validation": "NOT VALIDATED",
            "authorization_status": "REJECTED",
            "preflight_status": "NOT AUTHORIZED",
            "reachable": False,
            "http_status": 0,
            "redirect": None,
            "detail": validation.reason,
        }

    target = validation.target
    address_validation = (
        "LOOPBACK — every resolved address is loopback"
        if target.scope_kind == SCOPE_KIND_LOCAL
        else "PUBLIC — every resolved address is a public destination"
    )
    base = {
        "target_url": target.normalized_url,
        "resolved_host": target.resolved_host,
        "resolved_ips": list(target.resolved_ips),
        "port": target.port,
        "scheme": target.scheme,
        "hostname": target.host,
        "scope_kind": target.scope_kind,
        "scope_entry": target.scope_entry,
        "external": target.external,
        "in_scope": True,
        "address_validation": address_validation,
        "authorization_status": "AUTHORIZED",
    }
    try:
        probe = _probe_target(target, timeout)
        status = probe["http_status"]
        reachable = 100 <= status < 600
        redirect = None
        detail = f"HTTP {status} from {target.normalized_url}"
        if 300 <= status < 400:
            redirect = _evaluate_redirect(target, probe.get("location", ""))
            detail = f"HTTP {status} from {target.normalized_url}. {redirect['note']}"
        return {
            **base,
            "preflight_status": "TARGET REACHABLE" if reachable else "TARGET UNREACHABLE",
            "reachable": reachable,
            "http_status": status,
            "redirect": redirect,
            "detail": detail,
        }
    except Exception as e:
        return {
            **base,
            "preflight_status": "TARGET UNREACHABLE",
            "reachable": False,
            "http_status": 0,
            "redirect": None,
            "detail": f"Connectivity check failed: {e}",
        }
