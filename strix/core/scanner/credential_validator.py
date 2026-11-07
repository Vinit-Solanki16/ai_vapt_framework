"""Controlled Default Credential Validation for Strix AI-VAPT.

Validates explicitly configured test credentials (such as well-known
application defaults like admin@juice-sh.op / admin123) in a controlled,
non-destructive manner with zero uncontrolled brute forcing.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from strix.core.scanner.auth_manager import redact_credential
from strix.core.scanner.jwt_inspector import JWTInspector


logger = logging.getLogger(__name__)


class CredentialValidationResult:
    """Result of controlled default credential verification."""

    def __init__(
        self,
        username: str,
        password_masked: str,
        login_url: str,
        authenticated: bool,
        role: str | None = None,
        is_admin: bool = False,
        summary: str = "",
        evidence_snippet: str = "",
        jwt_findings: dict[str, Any] | None = None,
    ):
        self.username = username
        self.password_masked = password_masked
        self.login_url = login_url
        self.authenticated = authenticated
        self.role = role
        self.is_admin = is_admin
        self.summary = summary
        self.evidence_snippet = evidence_snippet
        self.jwt_findings = jwt_findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "password_masked": self.password_masked,
            "login_url": self.login_url,
            "authenticated": self.authenticated,
            "role": self.role,
            "is_admin": self.is_admin,
            "summary": self.summary,
            "evidence_snippet": self.evidence_snippet,
            "jwt_findings": self.jwt_findings,
        }


class CredentialValidator:
    """Tests authorized credential pairs deliberately."""

    @classmethod
    def test_single_credential(
        cls,
        target_base_url: str,
        username: str,
        password: str,
        login_path: str = "/rest/user/login",
    ) -> CredentialValidationResult:
        """Test a single credential pair without brute forcing."""
        base = target_base_url.rstrip("/")
        full_login_url = f"{base}{login_path if login_path.startswith('/') else '/' + login_path}"
        masked_pwd = redact_credential(password)

        payload = {"email": username, "password": password}
        try:
            req = urllib.request.Request(
                full_login_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "Strix-CredTest/1.7.0"},
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    auth_obj = data.get("authentication", {})
                    token = auth_obj.get("token")

                    role = "unknown"
                    jwt_findings = None
                    if token and JWTInspector.is_jwt_format(token):
                        jwt_res = JWTInspector.inspect(token)
                        payload_claims = jwt_res.payload
                        data_claims = payload_claims.get("data", {})
                        role = data_claims.get("role") or payload_claims.get("role", "customer")
                        jwt_findings = jwt_res.to_dict()

                    is_admin = role.lower() == "admin"
                    summary = (
                        f"Default credential validation confirmed for '{username}': "
                        f"authenticates successfully with role '{role}'."
                        + (
                            " (HIGH SEVERITY: Grants full administrative privileges)"
                            if is_admin
                            else ""
                        )
                    )
                    evidence = (
                        f"POST {login_path} HTTP/1.1\n"
                        f'Payload: {{"email":"{username}","password":"{masked_pwd}"}}\n'
                        f"Response: HTTP 200 OK\n"
                        f"Assigned Role: {role}\n"
                        f"Token Issued: Yes (Redacted)"
                    )
                    return CredentialValidationResult(
                        username=username,
                        password_masked=masked_pwd,
                        login_url=full_login_url,
                        authenticated=True,
                        role=role,
                        is_admin=is_admin,
                        summary=summary,
                        evidence_snippet=evidence,
                        jwt_findings=jwt_findings,
                    )
        except urllib.error.HTTPError as he:
            return CredentialValidationResult(
                username=username,
                password_masked=masked_pwd,
                login_url=full_login_url,
                authenticated=False,
                summary=f"Authentication rejected by target (HTTP {he.code})",
                evidence_snippet=f"HTTP/1.1 {he.code} Unauthorized",
            )
        except Exception as exc:
            return CredentialValidationResult(
                username=username,
                password_masked=masked_pwd,
                login_url=full_login_url,
                authenticated=False,
                summary=f"Connection failure testing credential: {exc}",
                evidence_snippet="",
            )

        return CredentialValidationResult(
            username=username,
            password_masked=masked_pwd,
            login_url=full_login_url,
            authenticated=False,
            summary="Credential probe inconclusive",
            evidence_snippet="",
        )
