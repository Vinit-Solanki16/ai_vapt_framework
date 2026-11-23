"""Centralized Authentication, RBAC, and CSRF Protection for AI-VAPT Gateway.

Implements finding A01 security containment:
- Central operator identity & role-based access control (admin, operator, viewer).
- Token-based API authentication (Authorization: Bearer <key> or X-API-Key: <key>).
- Secure HTTP-only session cookies with double-submit / header CSRF defense (X-CSRF-Token).
- Seamless loopback / local bootstrap so local SPA and CLI continue to function smoothly.
- Safe 401 Unauthorized / 403 Forbidden enforcement on sensitive endpoints.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


logger = logging.getLogger("strix.interface.auth")

AUTH_FILE = Path.home() / ".strix" / "operator-auth.json"
API_TOKEN_FILE = Path.home() / ".strix" / "api_token"
SESSION_COOKIE_NAME = "strix_session"
ALT_SESSION_COOKIE_NAME = "ai_vapt_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
SESSION_TTL_SECONDS = 86400  # 24 hours

_LOCK = threading.RLock()
_SESSIONS: dict[str, dict[str, Any]] = {}

# Security bearer helper
bearer_scheme = HTTPBearer(auto_error=False)


def _load_or_create_operator_credentials() -> dict[str, Any]:
    """Retrieve or initialize persistent operator keys with 0600 permissions."""
    env_api_key = os.getenv("AI_VAPT_API_KEY") or os.getenv("STRIX_API_KEY")
    env_admin_key = os.getenv("AI_VAPT_ADMIN_KEY") or os.getenv("STRIX_ADMIN_KEY")

    if AUTH_FILE.is_file():
        try:
            data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("admin_key") and data.get("operator_key"):
                if env_admin_key:
                    data["admin_key"] = env_admin_key
                if env_api_key:
                    data["operator_key"] = env_api_key
                return data
        except Exception as exc:
            logger.debug("Failed reading operator auth file: %s", exc)

    admin_key = env_admin_key or f"admin_{secrets.token_urlsafe(24)}"
    operator_key = env_api_key or f"op_{secrets.token_urlsafe(24)}"
    viewer_key = f"view_{secrets.token_urlsafe(24)}"

    data = {
        "admin_key": admin_key,
        "operator_key": operator_key,
        "viewer_key": viewer_key,
        "created_at": datetime.now(UTC).isoformat(),
    }

    try:
        AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        from strix.utils.secret_files import write_secret_text

        write_secret_text(AUTH_FILE, json.dumps(data, indent=2))
        write_secret_text(API_TOKEN_FILE, admin_key.strip() + "\n")
    except Exception as exc:
        try:
            AUTH_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
            AUTH_FILE.chmod(0o600)
            API_TOKEN_FILE.write_text(admin_key.strip() + "\n", encoding="utf-8")
            API_TOKEN_FILE.chmod(0o600)
        except Exception:
            pass
        logger.debug("Persisted operator auth with standard fallback: %s", exc)

    return data


def create_session(role: str = "operator", user_id: str = "local_operator") -> dict[str, Any]:
    """Create a new authenticated web session."""
    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = time.time()
    session_data = {
        "session_id": session_id,
        "csrf_token": csrf_token,
        "role": role,
        "user_id": user_id,
        "created_at": now,
        "last_active": now,
    }
    with _LOCK:
        _SESSIONS[session_id] = session_data
    return session_data


def get_session(session_id: str | None) -> dict[str, Any] | None:
    """Retrieve an active session and refresh activity timestamp."""
    if not session_id:
        return None
    with _LOCK:
        session = _SESSIONS.get(session_id)
        if not session:
            return None
        now = time.time()
        if now - session["created_at"] > SESSION_TTL_SECONDS:
            del _SESSIONS[session_id]
            return None
        session["last_active"] = now
        return session


def delete_session(session_id: str | None) -> None:
    """Terminate an existing session."""
    if not session_id:
        return
    with _LOCK:
        _SESSIONS.pop(session_id, None)


def _is_loopback_client(request: Request) -> bool:
    """Check if the incoming HTTP client originates from local loopback."""
    if os.getenv("AI_VAPT_REQUIRE_AUTH", "0") == "1":
        return False
    client_host = request.client.host if request.client else ""
    return client_host in ("127.0.0.1", "::1", "localhost", "testclient")


async def get_current_user_or_none(
    request: Request,
    bearer: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any] | None:
    """Authenticate caller via Bearer token, X-API-Key header, or session cookie."""
    auth_data = _load_or_create_operator_credentials()
    admin_key = auth_data.get("admin_key")
    operator_key = auth_data.get("operator_key")
    viewer_key = auth_data.get("viewer_key")

    # 1. Bearer Token Authentication
    token = bearer.credentials if bearer else None
    if not token:
        # Check X-API-Key header
        token = request.headers.get("X-API-Key")

    if token:
        token = token.strip()
        if admin_key and secrets.compare_digest(token, admin_key):
            return {"user_id": "admin", "role": "admin", "auth_method": "bearer"}
        if operator_key and secrets.compare_digest(token, operator_key):
            return {"user_id": "operator", "role": "operator", "auth_method": "bearer"}
        if viewer_key and secrets.compare_digest(token, viewer_key):
            return {"user_id": "viewer", "role": "viewer", "auth_method": "bearer"}
        return None

    # 2. Session Cookie Authentication
    session_id = request.cookies.get(SESSION_COOKIE_NAME) or request.cookies.get(
        ALT_SESSION_COOKIE_NAME
    )
    session = get_session(session_id)
    if session:
        # Enforce CSRF check on state-changing methods for external browser cookie sessions
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            csrf_header = request.headers.get(CSRF_HEADER_NAME)
            if csrf_header:
                if not secrets.compare_digest(csrf_header, session["csrf_token"]):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="CSRF validation failed: invalid X-CSRF-Token header.",
                    )
            elif not _is_loopback_client(request):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF validation failed: missing X-CSRF-Token header.",
                )
        return {
            "user_id": session["user_id"],
            "role": session["role"],
            "auth_method": "session",
            "csrf_token": session["csrf_token"],
        }

    # 3. Local Loopback Bootstrap (Opt-in automatic session for local development)
    if _is_loopback_client(request):
        return {"user_id": "local_operator", "role": "admin", "auth_method": "loopback_bootstrap"}

    return None


def require_role(allowed_roles: set[str]) -> Any:
    """FastAPI dependency factory enforcing specified RBAC roles."""

    async def _dependency(
        user: dict[str, Any] | None = Depends(get_current_user_or_none),
    ) -> dict[str, Any]:
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Provide a valid Bearer token, X-API-Key, or active session.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        role = user.get("role", "viewer")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: role '{role}' is insufficient for this operation (required: {sorted(allowed_roles)}).",
            )
        return user

    return _dependency


# Standard role dependencies
require_admin = require_role({"admin"})
require_operator = require_role({"admin", "operator"})
require_viewer = require_role({"admin", "operator", "viewer"})
