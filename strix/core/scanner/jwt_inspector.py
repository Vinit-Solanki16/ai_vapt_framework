"""Safe JWT Token Inspection for Strix AI-VAPT.

Decodes and inspects JSON Web Tokens (JWT) for information disclosure,
unhashed/weakly hashed password leakage, and sensitive claim exposure.
NOTE: Decoding payload claims does NOT verify or validate cryptographic signatures.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from strix.core.scanner.auth_manager import redact_credential

logger = logging.getLogger(__name__)


class JWTInspectionResult:
    """Result of safe JWT token inspection."""

    def __init__(
        self,
        is_jwt: bool,
        algorithm: Optional[str] = None,
        header: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        sensitive_claims: Optional[List[Dict[str, Any]]] = None,
        vulnerable: bool = False,
        summary: str = "",
        evidence_snippet: str = "",
    ):
        self.is_jwt = is_jwt
        self.algorithm = algorithm
        self.header = header or {}
        self.payload = payload or {}
        self.sensitive_claims = sensitive_claims or []
        self.vulnerable = vulnerable
        self.summary = summary
        self.evidence_snippet = evidence_snippet

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_jwt": self.is_jwt,
            "algorithm": self.algorithm,
            "signature_verified": False,
            "signature_disclaimer": "Payload decoded without cryptographic signature verification (RFC 7519)",
            "sensitive_claims_count": len(self.sensitive_claims),
            "sensitive_claims": self.sensitive_claims,
            "vulnerable": self.vulnerable,
            "summary": self.summary,
            "evidence_snippet": self.evidence_snippet,
        }


class JWTInspector:
    """Performs safe, non-destructive JWT analysis."""

    SENSITIVE_CLAIM_NAMES = {
        "password", "pwd", "hash", "secret", "private_key",
        "ssn", "credit_card", "pin", "auth_secret"
    }

    @staticmethod
    def is_jwt_format(token: str) -> bool:
        """Check if string matches standard 3-part base64url JWT format."""
        if not token or not isinstance(token, str):
            return False
        parts = token.strip().split(".")
        return len(parts) == 3

    @staticmethod
    def _b64url_decode(s: str) -> Optional[Dict[str, Any]]:
        """Decode base64url JSON segment safely."""
        try:
            padded = s + "=" * (-len(s) % 4)
            raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="ignore")
            return json.loads(raw)
        except Exception:
            return None

    @classmethod
    def inspect(cls, token: str) -> JWTInspectionResult:
        """Safely inspect a JWT token without verifying cryptographic signature."""
        if not token or not isinstance(token, str):
            return JWTInspectionResult(is_jwt=False, summary="Empty or invalid token type")

        clean_token = token.strip()
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()

        parts = clean_token.split(".")
        if len(parts) != 3:
            return JWTInspectionResult(
                is_jwt=False,
                summary=f"Token format error: expected 3 dot-separated segments, got {len(parts)}",
            )

        header = cls._b64url_decode(parts[0]) or {}
        payload = cls._b64url_decode(parts[1]) or {}
        algo = header.get("alg", "unknown")

        sensitive_claims: List[Dict[str, Any]] = []

        # Recursively search payload for sensitive keys
        def search_claims(data: Any, path: str = ""):
            if isinstance(data, dict):
                for k, v in data.items():
                    current_path = f"{path}.{k}" if path else k
                    if any(sk in k.lower() for sk in cls.SENSITIVE_CLAIM_NAMES):
                        val_str = str(v)
                        claim_type = "unknown"
                        if re.fullmatch(r"[a-fA-F0-9]{32}", val_str):
                            claim_type = "MD5 password hash (unsalted, reversal-vulnerable)"
                        elif re.fullmatch(r"[a-fA-F0-9]{40}", val_str):
                            claim_type = "SHA-1 hash"
                        elif val_str.startswith("$2") or val_str.startswith("$argon2"):
                            claim_type = "Cryptographic password hash"
                        else:
                            claim_type = "Plaintext credential or secret token"

                        sensitive_claims.append({
                            "claim_path": current_path,
                            "type": claim_type,
                            "masked_value": redact_credential(val_str),
                            "length": len(val_str),
                        })
                    else:
                        search_claims(v, current_path)
            elif isinstance(data, list):
                for idx, item in enumerate(data):
                    search_claims(item, f"{path}[{idx}]")

        search_claims(payload)

        vulnerable = len(sensitive_claims) > 0
        if vulnerable:
            first_c = sensitive_claims[0]
            summary = (
                f"Sensitive data exposure in JWT payload claim '{first_c['claim_path']}': "
                f"embeds {first_c['type']}."
            )
            evidence_snippet = (
                f"Decoded JWT Payload (RFC 7519, signature unverified):\n"
                f"Claim: {first_c['claim_path']} = {first_c['masked_value']}\n"
                f"Hash type: {first_c['type']}\n"
                f"Algorithm: {algo}"
            )
        else:
            summary = "JWT payload contains standard non-sensitive claims (no credential/hash leakage detected)."
            evidence_snippet = f"Decoded JWT (Algorithm: {algo}); zero password or secret claims exposed."

        return JWTInspectionResult(
            is_jwt=True,
            algorithm=algo,
            header=header,
            payload=payload,
            sensitive_claims=sensitive_claims,
            vulnerable=vulnerable,
            summary=summary,
            evidence_snippet=evidence_snippet,
        )

