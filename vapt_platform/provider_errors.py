"""Provider error classification + credential redaction for hosted LLM calls.

Two jobs, both required for an *optional* hosted provider (OpenRouter):

1. **Visibility** — a timeout, a rate-limit, a bad key and a malformed
   structured payload are different operational facts. Collapsing them into
   a generic "AI unavailable" hides which one happened. ``classify_error``
   maps any provider/SDK exception onto a small, stable category string that
   is safe to surface in logs, API responses and the UI.

2. **Redaction** — hosted providers authenticate with a secret. No error
   message, log line or API payload may ever echo that secret. ``redact``
   strips known secret values and well-known key shapes from any text that
   leaves the process.

This module is deliberately dependency-light: classification is by exception
*class name* (plus optional ``status_code``), so it works whether the caller
is using ``langchain-openrouter``, ``openai``, ``httpx`` or a test stub, and
it never imports an optional SDK at import time.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

# --- Categories -------------------------------------------------------------
# Stable strings surfaced to logs / API / UI. Keep this list small: each value
# must mean something operationally distinct.
ERROR_CATEGORIES: tuple[str, ...] = (
    "timeout",          # request exceeded the configured deadline
    "rate_limit",       # provider throttled us (HTTP 429)
    "auth",             # missing/invalid key (HTTP 401/403)
    "quota",            # out of credit (HTTP 402)
    "bad_request",      # provider rejected the request payload (HTTP 400/422)
    "not_found",        # unknown model slug (HTTP 404)
    "unavailable",      # provider-side outage (HTTP 5xx / 502/503/529)
    "connection",       # could not reach the provider at all
    "malformed_output", # model replied but the structured payload is invalid
    "api_error",        # any other provider/API failure
    "unknown",          # unrecognised exception
)

# Class-name fragments -> category. Evaluated in order; first match wins, so
# more specific fragments MUST come before more generic ones.
_NAME_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("timeout", (
        "Timeout", "APITimeout", "RequestTimeout", "EdgeNetworkTimeout",
        "ReadTimeout", "ConnectTimeout", "WriteTimeout", "PoolTimeout",
    )),
    ("rate_limit", ("RateLimit", "TooManyRequests")),
    ("quota", ("PaymentRequired", "InsufficientQuota", "Billing")),
    ("auth", (
        "Authentication", "PermissionDenied", "Unauthorized", "Forbidden",
        "InvalidAPIKey", "IncorrectApiKey",
    )),
    ("not_found", ("NotFound", "ModelNotFound")),
    ("bad_request", ("BadRequest", "UnprocessableEntity", "ValidationError",
                     "ValidationException", "PayloadTooLarge")),
    ("unavailable", (
        "ServiceUnavailable", "InternalServer", "BadGateway",
        "ProviderOverloaded", "Overloaded", "APIStatusError",
    )),
    ("connection", (
        "ConnectionError", "ConnectError", "APIConnection", "NetworkError",
        "ProxyError", "NoResponse", "RemoteProtocol", "TransportError",
    )),
    ("api_error", ("APIError", "OpenRouterDefault", "APIResponseValidation",
                   "ResponseValidation", "HTTPStatusError")),
)


def _exc_names(exc: BaseException) -> str:
    """Joined MRO class names for an exception (stable, SDK-agnostic)."""
    return " ".join(cls.__name__ for cls in type(exc).__mro__)


def _is_pydantic_validation_error(exc: BaseException) -> bool:
    """True for a LOCAL pydantic schema-validation failure.

    Distinct from a provider-side ``ResponseValidationError``: this one means
    the model replied but the structured payload did not satisfy the contract,
    so it must be reported as ``malformed_output`` rather than a generic
    provider error.
    """
    return (
        "ValidationError" in type(exc).__name__
        and "pydantic" in getattr(type(exc), "__module__", "")
    )


#: Env-var / key phrases that identify a missing-credential failure.
_MISSING_KEY_PHRASES: tuple[str, ...] = (
    "api key is not set",
    "api_key is not set",
    "not set. export",
    "missing api key",
    "api key not configured",
    "api key is required",
)


def _looks_like_missing_credential(exc: BaseException) -> bool:
    """True when *exc* reports a missing/unconfigured credential.

    Credential failures are raised as a plain RuntimeError by our own
    configuration guard (they carry no HTTP status), so the message is the
    only signal available.
    """
    message = str(exc).lower()
    if "api_key" in message or "api key" in message:
        return any(phrase in message for phrase in _MISSING_KEY_PHRASES)
    return False


def _status_code(exc: BaseException) -> Optional[int]:
    """Best-effort HTTP status extraction without importing an SDK."""
    for attr in ("status_code", "code", "http_status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def classify_error(exc: BaseException) -> str:
    """Map an exception onto one of :data:`ERROR_CATEGORIES`.

    An explicit HTTP status code outranks the class name (a generic
    ``APIStatusError`` carrying 429 is a rate-limit, not a generic API error).
    """
    status = _status_code(exc)
    if status is not None:
        if status == 429:
            return "rate_limit"
        if status == 401 or status == 403:
            return "auth"
        if status == 402:
            return "quota"
        if status == 404:
            return "not_found"
        if status in (400, 422):
            return "bad_request"
        if status == 408:
            return "timeout"
        if status >= 500:
            return "unavailable"

    # Local structured-output failures outrank the generic name rules, which
    # would otherwise bucket a pydantic ValidationError as "bad_request".
    if _is_pydantic_validation_error(exc):
        return "malformed_output"

    names = _exc_names(exc)
    for category, fragments in _NAME_RULES:
        if any(fragment in names for fragment in fragments):
            return category

    # Configuration failures raised as a plain RuntimeError carry no HTTP
    # status, so classify them from the message. A missing/misconfigured
    # credential is an "auth" fact, not an opaque "unknown" one — this is
    # what makes a missing-key error actionable in the UI.
    if _looks_like_missing_credential(exc):
        return "auth"

    return "unknown"


# --- Redaction --------------------------------------------------------------
#: Well-known secret shapes redacted even when we do not hold the value, e.g.
#: a key echoed back inside a provider error body.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # sk-or-... (OpenRouter), sk-... (OpenAI-style), generic Bearer tokens.
    re.compile(r"\bsk-or-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9_\-\.]{8,}"),
    # OPENROUTER_API_KEY=... / api_key="..." style assignments.
    re.compile(r"(?i)\b((?:openrouter|openai)_api_key\s*[=:]\s*)(\S+)"),
    re.compile(r"(?i)\b(api[_-]?key\s*[=:]\s*)(\"[^\"]+\"|'[^']+'|\S+)"),
)

REDACTED = "***REDACTED***"


def redact(text: Optional[str], secrets: Iterable[Any] = ()) -> str:
    """Strip known secret *values* and key-shaped substrings from *text*.

    Two layers, both needed:
      - literal values passed in ``secrets`` (the key we actually hold);
      - generic key patterns, for keys echoed inside provider error bodies
        we never saw.
    """
    out = "" if text is None else str(text)
    for secret in secrets:
        value = getattr(secret, "get_secret_value", None)
        if callable(value):            # tolerate pydantic SecretStr
            value = value()
        if not value:
            continue
        literal = str(value)
        if len(literal) >= 4:          # never blank out 1-3 char noise
            out = out.replace(literal, REDACTED)
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            out = pattern.sub(lambda m: f"{m.group(1)}{REDACTED}", out)
        elif pattern.groups == 1:
            out = pattern.sub(lambda m: f"{m.group(1)}{REDACTED}", out)
        else:
            out = pattern.sub(REDACTED, out)
    return out


def describe_error(
    exc: BaseException, secrets: Iterable[Any] = (), provider: str = "",
) -> str:
    """One-line, redacted, category-tagged description of *exc*.

    Always safe to put in a log line, an API response or the UI: it carries
    the category, the provider name and a redacted message — never a key.
    """
    category = classify_error(exc)
    prefix = f"{provider} " if provider else ""
    message = redact(f"{type(exc).__name__}: {exc}", secrets)
    return f"{prefix}{category}: {message}"


def is_retryable(exc: BaseException) -> bool:
    """True when the failure is transient (worth retrying / backing off)."""
    return classify_error(exc) in ("timeout", "rate_limit", "unavailable",
                                   "connection")
