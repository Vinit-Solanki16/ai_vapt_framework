"""Finding verification, evidence reliability, and validation state governance.

Implements Part B of finding reliability:
- Clear separation between SCANNER_DETECTED, VALIDATION_NOT_AVAILABLE,
  VALIDATED_TRUE_POSITIVE, FALSE_POSITIVE, and INCONCLUSIVE.
- Active, safe re-probe verification for high-signal vulnerabilities (e.g. PHPInfo
  disclosure, Cookie security flags) that captures reproducible response evidence.
- Safe rejection of external target exploitation (fail-closed, assessment-only).
- Protection against AI-hallucinated verification (an AI model opinion NEVER
  confirms a vulnerability).
- Clear evidence provenance with timestamps, HTTP status codes, and redacted snippets.
"""
from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

log = logging.getLogger(__name__)


class ValidationStatus(str, Enum):
    """Authoritative validation state for a vulnerability finding."""
    #: Scanner matched template/signatures, but active verification has not been performed
    SCANNER_DETECTED = "SCANNER_DETECTED"
    #: Controlled verification is unavailable (e.g. external target policy, no safe test)
    VALIDATION_NOT_AVAILABLE = "VALIDATION_NOT_AVAILABLE"
    #: Active reproducible re-probe proved vulnerability/exposure on target
    VALIDATED_TRUE_POSITIVE = "VALIDATED_TRUE_POSITIVE"
    #: Active re-probe proved target is NOT vulnerable (e.g. 404, flags present)
    FALSE_POSITIVE = "FALSE_POSITIVE"
    #: Verification attempted but inconclusive due to timeout, 5xx, or network error
    INCONCLUSIVE = "INCONCLUSIVE"


def normalize_validation_status(status: Any) -> str:
    """Normalize any string representation to authoritative ValidationStatus value."""
    if not status or not isinstance(status, str):
        return ValidationStatus.VALIDATION_NOT_AVAILABLE.value
    raw = status.strip().upper().replace("-", "_").replace(" ", "_")
    if raw in ("VALIDATED_TRUE_POSITIVE", "VALIDATED", "TRUE_POSITIVE"):
        return ValidationStatus.VALIDATED_TRUE_POSITIVE.value
    if raw in ("FALSE_POSITIVE", "FP"):
        return ValidationStatus.FALSE_POSITIVE.value
    if raw in ("INCONCLUSIVE", "TIMEOUT", "ERROR"):
        return ValidationStatus.INCONCLUSIVE.value
    if raw in ("SCANNER_DETECTED", "DETECTED"):
        return ValidationStatus.SCANNER_DETECTED.value
    if raw in ("VALIDATION_NOT_AVAILABLE", "UNAVAILABLE", "NOT_AVAILABLE"):
        return ValidationStatus.VALIDATION_NOT_AVAILABLE.value
    return status


@dataclass
class VerificationEvidence:
    """Structured evidence captured during active finding verification."""
    rule_id: str
    target_url: str
    status: ValidationStatus
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    http_status: Optional[int] = None
    evidence_summary: str = ""
    redacted_evidence: str = ""
    reproducible_request: str = ""
    error: Optional[str] = None
    provenance: str = "Active Verifier (HTTP Re-probe)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "target_url": self.target_url,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "http_status": self.http_status,
            "evidence_summary": self.evidence_summary,
            "redacted_evidence": self.redacted_evidence,
            "reproducible_request": self.reproducible_request,
            "error": self.error,
            "provenance": self.provenance,
        }


# ---------------------------------------------------------------------------
# Redaction Helpers
# ---------------------------------------------------------------------------

def redact_sensitive_evidence(text: str) -> str:
    """Mask credentials, tokens, session IDs, and authorization headers in evidence."""
    if not text:
        return ""
    # Mask session IDs and tokens
    out = re.sub(
        r"(session(?:_id)?|token|auth(?:orization)?|key|jwt)=([^\s;&]+)",
        r"\1=***REDACTED***",
        text,
        flags=re.IGNORECASE,
    )
    # Mask bearer tokens
    out = re.sub(
        r"(Bearer\s+)[A-Za-z0-9_\-\.]+",
        r"\1***REDACTED***",
        out,
        flags=re.IGNORECASE,
    )
    return out


# ---------------------------------------------------------------------------
# HTTP Client Abstraction
# ---------------------------------------------------------------------------

@dataclass
class HttpResponse:
    """Lightweight HTTP response envelope for verification checks."""
    status: int
    headers: dict[str, list[str]] = field(default_factory=dict)
    body: str = ""

    def get_header_all(self, name: str) -> list[str]:
        return self.headers.get(name.lower(), [])


def default_http_client(url: str, timeout: float = 5.0) -> HttpResponse:
    """Standard HTTP GET client using urllib."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-VAPT-Framework-Verifier/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        headers_dict: dict[str, list[str]] = {}
        for k, v in resp.headers.items():
            headers_dict.setdefault(k.lower(), []).append(v)
        set_cookies = resp.headers.get_all("Set-Cookie") or []
        if set_cookies:
            headers_dict["set-cookie"] = list(set_cookies)
        body = resp.read().decode("utf-8", errors="replace")
        return HttpResponse(status=resp.status, headers=headers_dict, body=body)


# ---------------------------------------------------------------------------
# Active Verifiers (Safe, Non-Destructive HTTP Checks)
# ---------------------------------------------------------------------------

PHPINFO_MARKERS = (
    "<title>phpinfo()</title>",
    "phpinfo()",
    "PHP Version",
    "Configuration File (php.ini) Path",
    "Zend Extension Build",
    "Server API",
)


def verify_phpinfo(
    target_url: str,
    path: Optional[str] = None,
    timeout: float = 5.0,
    client: Optional[Callable[[str, float], HttpResponse]] = None,
) -> VerificationEvidence:
    """Verify PHPInfo disclosure by testing for genuine PHP configuration tables.

    A Nuclei matcher alone is NOT proof of information disclosure. We require
    a reproducible HTTP 200 response containing concrete PHPInfo structure.
    """
    url = target_url
    if path:
        url = urljoin(target_url, path)

    http_get = client or default_http_client

    try:
        resp = http_get(url, timeout)
        http_status = resp.status
        content = resp.body
    except urllib.error.HTTPError as e:
        http_status = e.code
        if e.code in (404, 403, 401, 410):
            return VerificationEvidence(
                rule_id="phpinfo-disclosure",
                target_url=url,
                status=ValidationStatus.FALSE_POSITIVE,
                http_status=http_status,
                evidence_summary=f"Endpoint returned HTTP {http_status}; PHPInfo not exposed.",
                reproducible_request=f"GET {url}",
            )
        return VerificationEvidence(
            rule_id="phpinfo-disclosure",
            target_url=url,
            status=ValidationStatus.INCONCLUSIVE,
            http_status=http_status,
            evidence_summary=f"HTTP {e.code} error encountered during verification.",
            error=str(e),
            reproducible_request=f"GET {url}",
        )
    except (urllib.error.URLError, TimeoutError) as e:
        return VerificationEvidence(
            rule_id="phpinfo-disclosure",
            target_url=url,
            status=ValidationStatus.INCONCLUSIVE,
            http_status=None,
            evidence_summary="Connection error or timeout during verification.",
            error=str(e),
            reproducible_request=f"GET {url}",
        )
    except Exception as e:
        return VerificationEvidence(
            rule_id="phpinfo-disclosure",
            target_url=url,
            status=ValidationStatus.INCONCLUSIVE,
            http_status=None,
            evidence_summary="Unexpected error during verification.",
            error=str(e),
            reproducible_request=f"GET {url}",
        )

    if http_status != 200:
        return VerificationEvidence(
            rule_id="phpinfo-disclosure",
            target_url=url,
            status=ValidationStatus.FALSE_POSITIVE,
            http_status=http_status,
            evidence_summary=f"Response status {http_status} != 200.",
            reproducible_request=f"GET {url}",
        )

    # Check for genuine PHPInfo markers
    matched_markers = [m for m in PHPINFO_MARKERS if m.lower() in content.lower()]
    if len(matched_markers) >= 2 or "<title>phpinfo()</title>" in content:
        # Extract a short preview line (e.g. PHP Version)
        m = re.search(r"PHP Version\s*([0-9\.\w\-_]+)", content, re.IGNORECASE)
        version_snippet = f" (detected {m.group(0)})" if m else ""
        return VerificationEvidence(
            rule_id="phpinfo-disclosure",
            target_url=url,
            status=ValidationStatus.VALIDATED_TRUE_POSITIVE,
            http_status=http_status,
            evidence_summary=f"Confirmed PHPInfo disclosure: found {len(matched_markers)} configuration table markers{version_snippet}.",
            redacted_evidence=redact_sensitive_evidence(f"HTTP 200 OK: {matched_markers[0]} present"),
            reproducible_request=f"GET {url}",
        )

    return VerificationEvidence(
        rule_id="phpinfo-disclosure",
        target_url=url,
        status=ValidationStatus.FALSE_POSITIVE,
        http_status=http_status,
        evidence_summary="HTTP 200 OK received, but response lacks PHPInfo configuration tables.",
        reproducible_request=f"GET {url}",
    )


def verify_cookie_security(
    target_url: str,
    check_httponly: bool = True,
    check_secure: bool = False,
    cookie_name: Optional[str] = None,
    timeout: float = 5.0,
    client: Optional[Callable[[str, float], HttpResponse]] = None,
) -> VerificationEvidence:
    """Verify cookie security flags (HttpOnly / Secure) by inspecting Set-Cookie headers.

    If a scanner claimed 'Missing HttpOnly' but the cookie actually includes HttpOnly,
    this actively marks the finding FALSE_POSITIVE.
    """
    rule_id = "cookie-missing-httponly" if check_httponly else "cookie-missing-secure"
    http_get = client or default_http_client

    try:
        resp = http_get(target_url, timeout)
        http_status = resp.status
        headers = resp.get_header_all("Set-Cookie")
    except urllib.error.HTTPError as e:
        http_status = e.code
        headers = e.headers.get_all("Set-Cookie") or []
    except (urllib.error.URLError, TimeoutError) as e:
        return VerificationEvidence(
            rule_id=rule_id,
            target_url=target_url,
            status=ValidationStatus.INCONCLUSIVE,
            evidence_summary=f"Connection failed or timed out: {e}",
            error=str(e),
            reproducible_request=f"GET {target_url}",
        )
    except Exception as e:
        return VerificationEvidence(
            rule_id=rule_id,
            target_url=target_url,
            status=ValidationStatus.INCONCLUSIVE,
            evidence_summary=f"Unexpected error: {e}",
            error=str(e),
            reproducible_request=f"GET {target_url}",
        )

    if not headers:
        return VerificationEvidence(
            rule_id=rule_id,
            target_url=target_url,
            status=ValidationStatus.INCONCLUSIVE,
            http_status=http_status,
            evidence_summary="No Set-Cookie headers returned by target during verification probe.",
            reproducible_request=f"GET {target_url}",
        )

    # Inspect cookies
    vulnerable_cookies = []
    secured_cookies = []

    for raw_cookie in headers:
        parts = [p.strip() for p in raw_cookie.split(";")]
        if not parts:
            continue
        c_name = parts[0].split("=")[0].strip() if "=" in parts[0] else parts[0].strip()
        if cookie_name and c_name.lower() != cookie_name.lower():
            continue

        lower_attrs = [p.lower() for p in parts[1:]]
        has_httponly = "httponly" in lower_attrs
        has_secure = "secure" in lower_attrs

        if check_httponly:
            if not has_httponly:
                vulnerable_cookies.append(c_name)
            else:
                secured_cookies.append(c_name)
        elif check_secure:
            if not has_secure:
                vulnerable_cookies.append(c_name)
            else:
                secured_cookies.append(c_name)

    if vulnerable_cookies:
        flag_name = "HttpOnly" if check_httponly else "Secure"
        return VerificationEvidence(
            rule_id=rule_id,
            target_url=target_url,
            status=ValidationStatus.VALIDATED_TRUE_POSITIVE,
            http_status=http_status,
            evidence_summary=f"Confirmed missing {flag_name} on cookie(s): {', '.join(vulnerable_cookies)}.",
            redacted_evidence=redact_sensitive_evidence(f"Set-Cookie: {headers[0]}"),
            reproducible_request=f"GET {target_url}",
        )

    if secured_cookies:
        flag_name = "HttpOnly" if check_httponly else "Secure"
        return VerificationEvidence(
            rule_id=rule_id,
            target_url=target_url,
            status=ValidationStatus.FALSE_POSITIVE,
            http_status=http_status,
            evidence_summary=f"Cookie(s) {', '.join(secured_cookies)} already have {flag_name} flag set; scanner finding is a false positive.",
            redacted_evidence=redact_sensitive_evidence(f"Set-Cookie: {headers[0]}"),
            reproducible_request=f"GET {target_url}",
        )

    return VerificationEvidence(
        rule_id=rule_id,
        target_url=target_url,
        status=ValidationStatus.INCONCLUSIVE,
        http_status=http_status,
        evidence_summary="Could not isolate target cookie from Set-Cookie headers.",
        reproducible_request=f"GET {target_url}",
    )


# ---------------------------------------------------------------------------
# Candidate Verification Dispatcher
# ---------------------------------------------------------------------------

def verify_candidate(
    candidate: dict[str, Any],
    target_url: str,
    external: bool = False,
    timeout: float = 5.0,
    client: Optional[Callable[[str, float], HttpResponse]] = None,
) -> VerificationEvidence:
    """Perform controlled active verification on a candidate finding.

    Strict Safety Rules:
    1. If external=True: active exploitation/verification is refused (fail closed).
       Status is VALIDATION_NOT_AVAILABLE.
    2. Informational/Service Discovery: Never verified or promoted to vulnerability.
    3. AI models CANNOT confirm vulnerabilities: verification requires reproducible
       evidence from the target system.
    """
    rule_id = str(candidate.get("rule_id", "") or candidate.get("id", "")).lower()
    title = str(candidate.get("title", "")).lower()

    # Rule 1: External target safeguard
    if external:
        return VerificationEvidence(
            rule_id=rule_id,
            target_url=target_url,
            status=ValidationStatus.VALIDATION_NOT_AVAILABLE,
            evidence_summary=(
                "External target safety policy: active exploit validation is prohibited; "
                "findings remain in assessment-only mode."
            ),
            provenance="Safety Policy Engine",
        )

    # Rule 2: Informational / Service Discovery filter
    eligibility = str(candidate.get("candidate_eligibility", "")).upper()
    finding_kind = str(candidate.get("finding_kind", "")).upper()
    if "INFORMATIONAL" in eligibility or "DISCOVERY" in eligibility or "DISCOVERY" in finding_kind:
        return VerificationEvidence(
            rule_id=rule_id,
            target_url=target_url,
            status=ValidationStatus.VALIDATION_NOT_AVAILABLE,
            evidence_summary="Informational observation / asset context; no active exploit validation applicable.",
            provenance="Finding Normalization Engine",
        )

    # Rule 3: Check finding type for safe active verification
    # PHPInfo check
    if "phpinfo" in rule_id or "phpinfo" in title:
        cand_path = candidate.get("path") or "/phpinfo.php"
        return verify_phpinfo(target_url, path=cand_path, timeout=timeout, client=client)

    # Cookie HttpOnly check
    if "httponly" in rule_id or "httponly" in title:
        return verify_cookie_security(
            target_url, check_httponly=True, check_secure=False, timeout=timeout, client=client,
        )

    # Cookie Secure check
    if ("cookie" in rule_id and "secure" in rule_id) or "secure" in title or "cookie-missing-secure" in rule_id:
        return verify_cookie_security(
            target_url, check_httponly=False, check_secure=True, timeout=timeout, client=client,
        )

    # Default: No safe verifier implemented
    return VerificationEvidence(
        rule_id=rule_id,
        target_url=target_url,
        status=ValidationStatus.VALIDATION_NOT_AVAILABLE,
        evidence_summary=(
            f"No safe automated verifier registered for '{rule_id}': finding preserved "
            "with scanner match evidence; active exploit validation unavailable."
        ),
        provenance="Verification Registry",
    )
