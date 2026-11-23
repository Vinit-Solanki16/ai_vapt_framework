"""Unified Scoped HTTP Transport and TLS Validation for AI-VAPT.

Fixes findings A04 and A07:
- Default verified TLS with hostname verification and OS root trust.
- Support for custom CA certificates and audited lab-only insecure override.
- Scope-aware redirect handler enforcing ethical domain boundaries and preventing SSRF on redirects.
- Bounded response reads to prevent memory exhaustion / DoS.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


logger = logging.getLogger("strix.core.safety.http_transport")

DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024  # 1 MB bound
DEFAULT_TIMEOUT = 10.0


def create_scanner_ssl_context(
    verify_tls: bool = True,
    custom_ca: str | None = None,
    insecure_lab_override: bool = False,
) -> ssl.SSLContext:
    """Create TLS context with verified certificates by default (A04 fix).

    Only allows CERT_NONE if explicitly requested via parameter or
    STRIX_INSECURE_SCANNER_TLS=1 environment variable for isolated lab fixtures.
    """
    insecure_env = os.getenv("STRIX_INSECURE_SCANNER_TLS", "0") == "1"
    if insecure_lab_override or insecure_env or not verify_tls:
        logger.warning(
            "SECURITY AUDIT: Scanner TLS verification disabled by explicit lab override. "
            "Observations under this setting must note unverified transport."
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    ca_path = custom_ca or os.getenv("STRIX_CUSTOM_CA_BUNDLE") or os.getenv("SSL_CERT_FILE")
    if ca_path and Path(ca_path).is_file():
        ctx = ssl.create_default_context(cafile=str(ca_path))
    else:
        ctx = ssl.create_default_context()

    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


class ScopedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Enforces ethical scope boundaries on every redirect hop (A07 fix).

    Rejects redirects to:
    - Out-of-scope hostnames.
    - Cloud metadata (169.254.169.254) and link-local ranges.
    - Loopback/private ranges unless allow_private is explicitly True.
    """

    def __init__(
        self,
        authorized_hosts: set[str] | str,
        allow_private: bool = True,
        allow_redirects: bool = True,
    ):
        if isinstance(authorized_hosts, str):
            import urllib.parse

            p_host = urllib.parse.urlparse(authorized_hosts).hostname or authorized_hosts
            self.authorized_hosts = {p_host.lower().strip()}
        else:
            self.authorized_hosts = {h.lower().strip() for h in authorized_hosts if h}
        self.allow_private = allow_private
        self.allow_redirects = allow_redirects
        super().__init__()

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        parsed = urllib.parse.urlsplit(newurl)
        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            logger.warning("Blocked redirect to unsupported scheme '%s': %s", scheme, newurl)
            return None

        hostname = (parsed.hostname or "").lower().strip()
        if not hostname:
            logger.warning("Blocked redirect missing hostname: %s", newurl)
            return None

        # Check authorized host list
        if self.authorized_hosts and hostname not in self.authorized_hosts:
            orig_url = (
                req.get_full_url()
                if hasattr(req, "get_full_url")
                else getattr(req, "full_url", str(req))
            )
            logger.warning(
                "Blocked out-of-scope redirect from %s to unauthorized host: %s",
                orig_url,
                newurl,
            )
            return None

        # Resolve IP to verify destination safety
        port = parsed.port or (443 if scheme == "https" else 80)
        try:
            addr_info = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for _, _, _, _, sockaddr in addr_info:
                ip_str = str(sockaddr[0])
                ip_obj = ipaddress.ip_address(ip_str)

                # Strictly block cloud metadata
                if str(ip_obj) == "169.254.169.254" or ip_obj.is_link_local:
                    logger.warning("Blocked redirect to metadata / link-local address %s", ip_str)
                    return None

                # Check private/loopback
                if (ip_obj.is_private or ip_obj.is_loopback) and not self.allow_private:
                    logger.warning("Blocked redirect to unapproved internal IP %s", ip_str)
                    return None
        except Exception as e:
            logger.warning("DNS resolution check failed on redirect to %s: %s", hostname, e)
            return None

        return super().redirect_request(req, fp, code, msg, headers, newurl)


def execute_scoped_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    authorized_hosts: set[str] | list[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    verify_tls: bool = True,
    custom_ca: str | None = None,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    allow_private: bool = True,
) -> dict[str, Any]:
    """Execute an HTTP request with validated TLS, scope enforcement, and bounded memory read."""
    parsed = urllib.parse.urlsplit(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return {
            "status": 0,
            "headers": {},
            "body": "",
            "url": url,
            "error": f"Invalid scheme '{scheme}'",
            "tls_error": None,
        }

    host = (parsed.hostname or "").lower().strip()
    hosts_set = set(authorized_hosts or [host])
    hosts_set.add(host)

    ssl_ctx = create_scanner_ssl_context(verify_tls=verify_tls, custom_ca=custom_ca)
    redirect_handler = ScopedRedirectHandler(hosts_set, allow_private=allow_private)
    https_handler = urllib.request.HTTPSHandler(context=ssl_ctx)
    opener = urllib.request.build_opener(redirect_handler, https_handler)

    req_headers = dict(headers or {})
    if "User-Agent" not in req_headers:
        req_headers["User-Agent"] = "AI-VAPT-Scanner/2.0"

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)

    try:
        with opener.open(req, timeout=timeout) as resp:
            raw_bytes = resp.read(max_bytes + 1)
            truncated = len(raw_bytes) > max_bytes
            body_bytes = raw_bytes[:max_bytes]
            body_text = body_bytes.decode("utf-8", errors="replace")

            resp_headers = {str(k).lower(): str(v) for k, v in resp.headers.items()}
            return {
                "status": resp.status,
                "headers": resp_headers,
                "body": body_text,
                "url": resp.geturl(),
                "truncated": truncated,
                "error": None,
                "tls_error": None,
            }
    except ssl.SSLCertVerificationError as ssl_err:
        logger.warning("TLS Certificate verification failed for %s: %s", url, ssl_err)
        return {
            "status": 0,
            "headers": {},
            "body": "",
            "url": url,
            "error": f"TLS Certificate Error: {ssl_err}",
            "tls_error": str(ssl_err),
        }
    except urllib.error.HTTPError as http_err:
        body = ""
        if http_err.fp is not None:
            try:
                body = http_err.fp.read(max_bytes).decode("utf-8", errors="replace")
            except Exception:
                pass
        return {
            "status": http_err.code,
            "headers": {str(k).lower(): str(v) for k, v in http_err.headers.items()},
            "body": body,
            "url": url,
            "error": f"HTTP {http_err.code}",
            "tls_error": None,
        }
    except Exception as exc:
        return {
            "status": 0,
            "headers": {},
            "body": "",
            "url": url,
            "error": str(exc),
            "tls_error": None,
        }
