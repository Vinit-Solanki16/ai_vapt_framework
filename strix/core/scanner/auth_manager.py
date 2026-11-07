"""Authentication and Session Management for Strix AI-VAPT.

Provides explicit, safe credential handling, session establishment,
and token/session context propagation for root and child agents.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


logger = logging.getLogger(__name__)


def redact_credential(val: Any) -> str:
    """Mask sensitive string or token for safe logging and reporting."""
    if not val or not isinstance(val, str):
        return "***[REDACTED]***"
    s = val.strip()
    if len(s) <= 8:
        return "***[REDACTED]***"
    return f"{s[:4]}...[REDACTED]...{s[-4:]}"


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive keys in a dictionary."""
    redacted: dict[str, Any] = {}
    sensitive_keys = {
        "password",
        "token",
        "secret",
        "key",
        "api_key",
        "authorization",
        "hash",
        "jwt",
    }
    for k, v in data.items():
        if any(sk in k.lower() for sk in sensitive_keys):
            if isinstance(v, str):
                redacted[k] = redact_credential(v)
            else:
                redacted[k] = "***[REDACTED]***"
        elif isinstance(v, dict):
            redacted[k] = redact_dict(v)
        elif isinstance(v, list):
            redacted[k] = [redact_dict(i) if isinstance(i, dict) else i for i in v]
        else:
            redacted[k] = v
    return redacted


class AuthSession:
    """Represents a verified authentication context."""

    def __init__(
        self,
        authenticated: bool = False,
        auth_type: str = "none",
        token: str | None = None,
        username: str | None = None,
        role: str | None = None,
        user_id: int | None = None,
        basket_id: int | None = None,
        header_name: str = "Authorization",
        error_message: str | None = None,
    ):
        self.authenticated = authenticated
        self.auth_type = auth_type
        self.token = token
        self.username = username
        self.role = role
        self.user_id = user_id
        self.basket_id = basket_id
        self.header_name = header_name
        self.error_message = error_message

    def get_auth_header(self) -> dict[str, str]:
        """Return HTTP header dict for authenticated requests."""
        if not self.authenticated or not self.token:
            return {}
        if self.token.lower().startswith("bearer "):
            return {self.header_name: self.token}
        return {self.header_name: f"Bearer {self.token}"}

    def to_safe_dict(self) -> dict[str, Any]:
        """Safe serialized representation without secrets."""
        return {
            "authenticated": self.authenticated,
            "auth_type": self.auth_type,
            "username": self.username,
            "role": self.role,
            "user_id": self.user_id,
            "basket_id": self.basket_id,
            "masked_token": redact_credential(self.token) if self.token else None,
            "header_name": self.header_name,
            "error_message": self.error_message,
        }


class AuthManager:
    """Manages authentication validation and session lifecycle."""

    @staticmethod
    def establish_session(
        target_url: str,
        auth_config: dict[str, Any] | None = None,
    ) -> AuthSession:
        """Establish and verify a session using explicitly provided credentials."""
        if not auth_config or not auth_config.get("enabled"):
            return AuthSession(authenticated=False, auth_type="none")

        auth_type = (auth_config.get("auth_type") or "login").lower()
        base = target_url.rstrip("/")

        # 1. Pre-supplied Bearer token
        if auth_type == "bearer" or auth_config.get("token"):
            token = auth_config.get("token", "").strip()
            if not token:
                return AuthSession(authenticated=False, error_message="Empty bearer token provided")
            # Verify token on a protected endpoint
            session = AuthSession(authenticated=True, auth_type="bearer", token=token)
            verified, user_info = AuthManager.verify_session(base, session)
            if verified:
                session.username = user_info.get("username")
                session.role = user_info.get("role")
                session.user_id = user_info.get("user_id")
                session.basket_id = user_info.get("basket_id")
                return session
            return AuthSession(
                authenticated=False, error_message="Pre-supplied bearer token failed verification"
            )

        # 2. Login credentials (JSON POST)
        creds = auth_config.get("credentials") or {}
        email = creds.get("email") or creds.get("username") or ""
        password = creds.get("password") or ""
        login_path = auth_config.get("login_path") or "/rest/user/login"

        if not email or not password:
            return AuthSession(
                authenticated=False,
                error_message="Missing username/email or password in credentials",
            )

        login_url = f"{base}{login_path if login_path.startswith('/') else '/' + login_path}"
        payload = {"email": email, "password": password}

        try:
            req = urllib.request.Request(
                login_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "Strix-Auth/1.7.0"},
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    auth_obj = data.get("authentication", {})
                    token = auth_obj.get("token")
                    bid = auth_obj.get("bid")
                    umail = auth_obj.get("umail") or email

                    if token:
                        session = AuthSession(
                            authenticated=True,
                            auth_type="login",
                            token=token,
                            username=umail,
                            basket_id=bid,
                        )
                        # Verify on /rest/user/whoami or /api/Users
                        verified, user_info = AuthManager.verify_session(base, session)
                        if verified:
                            session.role = user_info.get("role", "customer")
                            session.user_id = user_info.get("user_id")
                        return session
                    return AuthSession(
                        authenticated=False, error_message="Login 200 but token missing in response"
                    )
        except urllib.error.HTTPError as he:
            return AuthSession(authenticated=False, error_message=f"Login failed HTTP {he.code}")
        except Exception as exc:
            return AuthSession(authenticated=False, error_message=f"Login connection error: {exc}")

        return AuthSession(
            authenticated=False, error_message="Unable to establish authenticated session"
        )

    @staticmethod
    def verify_session(target_base: str, session: AuthSession) -> tuple[bool, dict[str, Any]]:
        """Verify that authenticated requests reach protected endpoints and determine role."""
        if not session.token:
            return False, {}

        headers = session.get_auth_header()
        headers["User-Agent"] = "Strix-Auth-Verify/1.7.0"

        # Check whoami
        user_info = {}
        try:
            whoami_url = f"{target_base}/rest/user/whoami"
            req = urllib.request.Request(whoami_url, headers=headers)
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    user = body.get("user", {})
                    if user:
                        user_info["username"] = user.get("email")
                        user_info["role"] = user.get("role", "customer")
                        user_info["user_id"] = user.get("id")
                        return True, user_info
        except Exception:
            pass

        # Check /api/Users with token
        try:
            users_url = f"{target_base}/api/Users"
            req = urllib.request.Request(users_url, headers=headers)
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    if body.get("status") == "success":
                        # Valid authenticated access to /api/Users
                        return True, user_info
        except Exception:
            pass

        return session.authenticated, user_info
