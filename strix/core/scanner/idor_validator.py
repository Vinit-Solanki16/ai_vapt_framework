"""Object-Level Authorization and IDOR Validation for Strix AI-VAPT.

Performs controlled, non-destructive verification of Insecure Direct Object
References (IDOR) and missing object-level access controls (BOLA).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from strix.core.scanner.auth_manager import redact_credential


logger = logging.getLogger(__name__)


class IDORValidationResult:
    """Result of object-level authorization testing."""

    def __init__(
        self,
        tested_endpoint: str,
        user_own_id: Any,
        target_foreign_id: Any,
        is_idor: bool,
        http_status: int,
        summary: str,
        evidence_snippet: str,
        reproducible_request: str,
    ):
        self.tested_endpoint = tested_endpoint
        self.user_own_id = user_own_id
        self.target_foreign_id = target_foreign_id
        self.is_idor = is_idor
        self.http_status = http_status
        self.summary = summary
        self.evidence_snippet = evidence_snippet
        self.reproducible_request = reproducible_request

    def to_dict(self) -> dict[str, Any]:
        return {
            "tested_endpoint": self.tested_endpoint,
            "user_own_id": self.user_own_id,
            "target_foreign_id": self.target_foreign_id,
            "is_idor": self.is_idor,
            "http_status": self.http_status,
            "summary": self.summary,
            "evidence_snippet": self.evidence_snippet,
            "reproducible_request": self.reproducible_request,
        }


class IDORValidator:
    """Performs controlled IDOR testing across tenant object boundaries."""

    @classmethod
    def test_idor(
        cls,
        target_base_url: str,
        auth_token: str,
        endpoint_template: str = "/api/BasketItems/{id}",
        user_own_id: Any = 6,
        foreign_id: Any = 1,
        header_name: str = "Authorization",
    ) -> IDORValidationResult:
        """Test whether accessing another user's object succeeds and leaks foreign data."""
        base = target_base_url.rstrip("/")
        foreign_path = endpoint_template.format(id=foreign_id)
        foreign_url = f"{base}{foreign_path}"

        auth_val = (
            auth_token if auth_token.lower().startswith("bearer ") else f"Bearer {auth_token}"
        )
        headers = {
            header_name: auth_val,
            "User-Agent": "Strix-IDOR-Validator/1.7.0",
            "Accept": "application/json",
        }

        repro_req = (
            f"GET {foreign_path} HTTP/1.1\n"
            f"Host: {urllib.parse.urlsplit(target_base_url).netloc}\n"
            f"{header_name}: Bearer {redact_credential(auth_token)}\n"
            f"Accept: application/json"
        )

        try:
            req = urllib.request.Request(foreign_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                status = resp.status
                body_raw = resp.read(10000).decode("utf-8", errors="ignore")

                if status == 200:
                    try:
                        data = json.loads(body_raw)
                        data_obj = data.get("data", {})
                        # Check ownership attributes
                        obj_basket_id = data_obj.get("BasketId")
                        obj_user_id = data_obj.get("UserId")

                        # If returned object's owner id does not match user's own id
                        owner_mismatch = (
                            (obj_basket_id is not None and str(obj_basket_id) != str(user_own_id))
                            or (obj_user_id is not None and str(obj_user_id) != str(user_own_id))
                            or (str(foreign_id) != str(user_own_id))
                        )

                        if owner_mismatch:
                            summary = (
                                f"Cross-authorization boundary exposure: object-level authorization absent on "
                                f"{foreign_path}. Authenticated user (own ID {user_own_id}) retrieved resource "
                                f"belonging to owner ID {obj_basket_id or obj_user_id or foreign_id}."
                            )
                            evidence = (
                                f"HTTP/1.1 200 OK\n"
                                f"Content-Type: application/json\n\n"
                                f"{json.dumps(data, indent=2)[:400]}"
                            )
                            return IDORValidationResult(
                                tested_endpoint=foreign_path,
                                user_own_id=user_own_id,
                                target_foreign_id=foreign_id,
                                is_idor=True,
                                http_status=status,
                                summary=summary,
                                evidence_snippet=evidence,
                                reproducible_request=repro_req,
                            )
                    except json.JSONDecodeError:
                        pass

                    return IDORValidationResult(
                        tested_endpoint=foreign_path,
                        user_own_id=user_own_id,
                        target_foreign_id=foreign_id,
                        is_idor=False,
                        http_status=status,
                        summary="HTTP 200 returned but could not confirm cross-ownership mismatch",
                        evidence_snippet=body_raw[:200],
                        reproducible_request=repro_req,
                    )
        except urllib.error.HTTPError as he:
            # 401 Unauthorized or 403 Forbidden indicates ownership/access enforcement
            return IDORValidationResult(
                tested_endpoint=foreign_path,
                user_own_id=user_own_id,
                target_foreign_id=foreign_id,
                is_idor=False,
                http_status=he.code,
                summary=f"Object-level authorization enforced: server returned HTTP {he.code}",
                evidence_snippet=f"HTTP/1.1 {he.code} Access Denied",
                reproducible_request=repro_req,
            )
        except Exception as exc:
            return IDORValidationResult(
                tested_endpoint=foreign_path,
                user_own_id=user_own_id,
                target_foreign_id=foreign_id,
                is_idor=False,
                http_status=0,
                summary=f"Connection failure during IDOR probe: {exc}",
                evidence_snippet="",
                reproducible_request=repro_req,
            )

        return IDORValidationResult(
            tested_endpoint=foreign_path,
            user_own_id=user_own_id,
            target_foreign_id=foreign_id,
            is_idor=False,
            http_status=0,
            summary="IDOR probe inconclusive",
            evidence_snippet="",
            reproducible_request=repro_req,
        )
