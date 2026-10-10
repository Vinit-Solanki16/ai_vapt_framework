"""Runtime OpenRouter credential validation and model catalogue.

This module backs the in-GUI OpenRouter setup flow so a user can supply an
API key at runtime instead of configuring ``OPENROUTER_API_KEY`` in a shell,
a Codespaces secret or a ``.env`` file.

Design rules:

* **No paid completion is ever issued.** Validation uses OpenRouter's
  authenticated *model catalogue* endpoint, which is free and returns the
  same model objects the selector needs — one round trip does both jobs.
* **The key never leaves this call.** It is sent as an ``Authorization:
  Bearer`` header straight to OpenRouter and is never returned, logged,
  stored or placed in an environment variable by this module.
* **Nothing is invented.** Endpoint paths, response fields and pricing
  semantics come from the published OpenRouter API reference:

  - ``GET /api/v1/models/user`` — authenticated catalogue
    (``security: bearer``; 401 = bad credentials, 403 = key valid but not
    management-scoped).
  - ``GET /api/v1/auth/key``     — authenticated key metadata (401 = bad key).
  - ``GET /api/v1/models``       — public catalogue, used only as a
    fallback when ``/models/user`` rejects a perfectly good ordinary key.

  A model is treated as free exactly when the documented ``pricing.prompt``
  and ``pricing.completion`` fields are both ``"0"`` — never inferred from
  the model's name.

Free availability, quotas and pricing change without notice; the catalogue is
fetched fresh on every validation rather than cached or hard-coded.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Iterable, Optional

# --- Public contract -------------------------------------------------------

OPENROUTER_API_BASE = os.getenv(
    "OPENROUTER_API_BASE", "https://openrouter.ai/api/v1"
).rstrip("/")

#: Header the frontend uses to carry the runtime key. Kept out of the JSON
#: body on purpose so the secret never lands in a serialized request payload.
RUNTIME_KEY_HEADER = "X-OpenRouter-API-Key"

# Setup states surfaced by the GUI (Phase 2C).
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_VALIDATING = "validating"
STATUS_CONFIGURED = "configured"
STATUS_INVALID_CREDENTIALS = "invalid_credentials"
STATUS_MODEL_UNAVAILABLE = "model_unavailable"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_UNREACHABLE = "unreachable"

SETUP_STATUSES = (
    STATUS_NOT_CONFIGURED,
    STATUS_VALIDATING,
    STATUS_CONFIGURED,
    STATUS_INVALID_CREDENTIALS,
    STATUS_MODEL_UNAVAILABLE,
    STATUS_RATE_LIMITED,
    STATUS_UNREACHABLE,
)

#: How many catalogue entries are handed to the UI. Large enough to cover
#: every current free model plus a useful paid selection, small enough that
#: the payload stays responsive.
MAX_MODELS_RETURNED = 1000

DEFAULT_TIMEOUT_S = 15.0

# Actionable, user-facing guidance per state. Never includes the key.
HELP_TEXT = {
    STATUS_NOT_CONFIGURED: (
        "No OpenRouter key in this session yet. Paste your key below, then "
        "press Validate Connection. The key stays in this browser tab's "
        "memory only."
    ),
    STATUS_VALIDATING: "Checking the credential against OpenRouter…",
    STATUS_CONFIGURED: (
        "Configured for this session. You can start assessments now; the key "
        "will be asked for again only after a page reload."
    ),
    STATUS_INVALID_CREDENTIALS: (
        "OpenRouter rejected the key (401). Copy the key from "
        "openrouter.ai/settings/keys — check for missing characters or a "
        "revoked/rotated key, then press Validate Connection again."
    ),
    STATUS_MODEL_UNAVAILABLE: (
        "The selected model is not in OpenRouter's current catalogue. It may "
        "have been removed or renamed. Pick another model from the list, "
        "enter a custom model ID, or refresh the catalogue."
    ),
    STATUS_RATE_LIMITED: (
        "OpenRouter rate-limited the validation request (429). Wait a moment "
        "and press Validate Connection again. Free models have their own, "
        "much lower per-day request limits."
    ),
    STATUS_UNREACHABLE: (
        "OpenRouter could not be reached (network, timeout or server error). "
        "This is not necessarily a bad key — check connectivity and try "
        "again. Nothing was changed."
    ),
}


# --- HTTP seam ---------------------------------------------------------------

#: Injectable transport: ``(method, url, headers, timeout) ->
#: (status_code, json_payload_or_None)``. Tests replace this; no test ever
#: performs a real network call.
Transport = Callable[[str, str, dict, float], tuple[int, Optional[dict]]]


def _http_transport(method: str, url: str, headers: dict,
                    timeout: float) -> tuple[int, Optional[dict]]:
    import httpx

    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        response = client.request(method, url, headers=headers)
        try:
            payload = response.json()
        except Exception:
            payload = None
        if not isinstance(payload, dict):
            payload = None
        return response.status_code, payload


# --- Catalogue parsing -------------------------------------------------------

def _price(value: Any) -> Optional[str]:
    """Return a documented pricing string as-is, or None when unusable."""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    return None


def is_free_pricing(pricing: Any) -> bool:
    """True when the DOCUMENTED pricing says input and output are both free.

    OpenRouter publishes ``pricing`` as USD-per-token strings; ``"0"`` means
    the feature is free. Name suffixes such as ``:free`` are a *catalogue
    variant* marker, not the source of truth, so they are only used to break
    ties for display — never to decide cost.
    """
    if not isinstance(pricing, dict):
        return False
    prompt = _price(pricing.get("prompt"))
    completion = _price(pricing.get("completion"))
    if prompt is None or completion is None:
        return False
    try:
        return float(prompt) == 0.0 and float(completion) == 0.0
    except ValueError:
        return False


def _per_million(value: Optional[str]) -> Optional[str]:
    """USD-per-token -> USD-per-million-tokens, for display only."""
    if value is None:
        return None
    try:
        return f"{float(value) * 1_000_000:g}"
    except ValueError:
        return None


def parse_catalogue(payload: Any) -> list[dict]:
    """Normalize a ModelsListResponse into selector-ready entries.

    Accepts the documented ``{"data": [...]}`` envelope and tolerates a bare
    list or a malformed body (returning ``[]`` rather than raising), so an
    empty or broken catalogue degrades into a clear UI state instead of a
    backend stack trace.
    """
    if isinstance(payload, dict):
        raw = payload.get("data")
    else:
        raw = payload
    if not isinstance(raw, list):
        return []

    models: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        model_id = model_id.strip()
        pricing = entry.get("pricing") if isinstance(entry.get("pricing"), dict) else {}
        prompt = _price(pricing.get("prompt"))
        completion = _price(pricing.get("completion"))
        free = is_free_pricing(pricing)
        context = entry.get("context_length")
        models.append({
            "id": model_id,
            "name": (entry.get("name") or model_id).strip()
                    if isinstance(entry.get("name"), str) else model_id,
            "free": free,
            "pricing": {
                "prompt": prompt,
                "completion": completion,
                "prompt_per_million": _per_million(prompt),
                "completion_per_million": _per_million(completion),
            },
            "context_length": context if isinstance(context, int) else None,
            # Priced entries are never silently chosen; the UI must ask.
            "paid": not free,
        })
    return models


def sort_models(models: Iterable[dict]) -> list[dict]:
    """Free models first, then paid — each group alphabetically by id."""
    models = list(models)
    free = sorted((m for m in models if m.get("free")), key=lambda m: m["id"])
    paid = sorted((m for m in models if not m.get("free")), key=lambda m: m["id"])
    return free + paid


# --- Validation --------------------------------------------------------------

def _result(status: str, *, message: Optional[str] = None,
            models: Optional[list] = None, model: Optional[str] = None,
            model_available: Optional[bool] = None,
            catalogue_count: int = 0,
            **extra: Any) -> dict:
    body = {
        "status": status,
        "message": message or HELP_TEXT.get(status, ""),
        "models": models or [],
        "model": model,
        "model_available": model_available,
        "catalogue_count": catalogue_count,
    }
    body.update(extra)
    # Defence in depth: whatever a caller passes, a key-shaped value never
    # leaves this function.
    from vapt_platform.provider_errors import redact
    if body.get("message"):
        body["message"] = redact(body["message"])
    return body


def _key_looks_wellformed(key: str) -> bool:
    """True when a pasted key has no stray whitespace/control characters.

    Bounded in length so a runaway paste is rejected before it is sent.
    Applied AFTER stripping, so harmless leading/trailing whitespace from a
    copy-paste is forgiven but an embedded newline is not.
    """
    if not key or len(key) > 512:
        return False
    if any(ch.isspace() for ch in key):
        return False
    return not any(ord(ch) < 32 or ord(ch) == 127 for ch in key)


def validate_runtime_key(
    api_key: Optional[str],
    requested_model: Optional[str] = None,
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
    transport: Optional[Transport] = None,
) -> dict:
    """Validate a runtime OpenRouter key and return its current catalogue.

    Never performs a completion. Never returns, stores or logs the key.
    Never touches ``os.environ``.

    Args:
        api_key: the user's runtime key (may be blank/None).
        requested_model: model the user wants, checked for availability.
        timeout: per-request timeout in seconds (clamped).
        transport: override the HTTP seam (tests only).

    Returns:
        A dict with ``status`` (see :data:`SETUP_STATUSES`), ``message``,
        ``models`` (free first), ``model``, ``model_available`` and
        ``catalogue_count``.
    """
    from vapt_platform.model_config import is_valid_model_name

    key = (api_key or "").strip()
    if not key:
        return _result(STATUS_NOT_CONFIGURED, model=requested_model)

    if not _key_looks_wellformed(key):
        # A key pasted with stray whitespace/newlines is a user mistake, not
        # an auth failure — say so before making a pointless network call.
        return _result(
            STATUS_INVALID_CREDENTIALS,
            model=requested_model,
            message=(
                "The pasted key contains whitespace or control characters, so "
                "it was not sent. Re-copy the whole key with no extra spaces "
                "or line breaks, then press Validate Connection again."
            ),
        )

    try:
        timeout = max(1.0, min(float(timeout), 600.0))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_S

    fetch = transport or _http_transport
    headers = {"Authorization": f"Bearer {key}"}

    # 1) Preferred: an AUTHENTICATED model-catalogue request. It proves the
    #    key works and returns the selector data in one free round trip.
    try:
        status, payload = fetch(
            "GET", f"{OPENROUTER_API_BASE}/models/user", headers, timeout
        )
    except Exception:
        return _result(STATUS_UNREACHABLE, model=requested_model)

    catalogue: Optional[list[dict]] = None

    if status == 401:
        return _result(STATUS_INVALID_CREDENTIALS, model=requested_model)
    if status == 429:
        return _result(STATUS_RATE_LIMITED, model=requested_model)
    if status == 200:
        catalogue = parse_catalogue(payload)
        if not catalogue:
            # 200 but an unusable body: treat as unreachable rather than
            # "configured with zero models", which would be a lie.
            return _result(STATUS_UNREACHABLE, model=requested_model)
    else:
        # 403 is documented as "only management keys can perform this
        # operation" — a perfectly ordinary user key hits it. Fall back to
        # the dedicated authenticated key check plus the public catalogue.
        if status != 403:
            return _result(STATUS_UNREACHABLE, model=requested_model)
        try:
            key_status, _ = fetch(
                "GET", f"{OPENROUTER_API_BASE}/auth/key", headers, timeout
            )
        except Exception:
            return _result(STATUS_UNREACHABLE, model=requested_model)
        if key_status == 401:
            return _result(STATUS_INVALID_CREDENTIALS, model=requested_model)
        if key_status == 429:
            return _result(STATUS_RATE_LIMITED, model=requested_model)
        if key_status != 200:
            return _result(STATUS_UNREACHABLE, model=requested_model)
        try:
            public_status, public_payload = fetch(
                "GET", f"{OPENROUTER_API_BASE}/models", {}, timeout
            )
        except Exception:
            return _result(STATUS_UNREACHABLE, model=requested_model)
        if public_status != 200:
            return _result(STATUS_UNREACHABLE, model=requested_model)
        catalogue = parse_catalogue(public_payload)
        if not catalogue:
            return _result(STATUS_UNREACHABLE, model=requested_model)

    models = sort_models(catalogue)[:MAX_MODELS_RETURNED]
    ids = {m["id"] for m in models}

    model = (requested_model or "").strip() or None
    if model is None:
        return _result(STATUS_CONFIGURED, models=models,
                       catalogue_count=len(catalogue))

    if is_valid_model_name(model) and model in ids:
        return _result(STATUS_CONFIGURED, models=models, model=model,
                       model_available=True, catalogue_count=len(catalogue))

    return _result(
        STATUS_MODEL_UNAVAILABLE,
        models=models,
        model=model,
        model_available=False,
        catalogue_count=len(catalogue),
    )


def pick_default_model(models: Iterable[dict]) -> Optional[str]:
    """Best free default for the free-model workflow.

    Prefers OpenRouter's own Free Models Router when it is in the catalogue,
    otherwise the first free entry (the list is already free-first). Returns
    None when nothing free is available, so a paid model is NEVER selected
    implicitly.
    """
    models = list(models)
    for entry in models:
        if entry.get("id") == "openrouter/free":
            return "openrouter/free"
    for entry in models:
        if entry.get("free"):
            return entry["id"]
    return None
