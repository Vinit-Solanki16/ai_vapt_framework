"""Active validator for missing HTTP security hardening headers."""
from __future__ import annotations

import urllib.request
from typing import Any, Dict

from .base import BaseValidator, ValidationResult


class SecurityHeadersValidator(BaseValidator):
    """Safely checks for missing defense-in-depth HTTP security headers."""

    RECOMMENDED_HEADERS = [
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Content-Security-Policy",
    ]

    def validate(self, target_url: str, candidate: Dict[str, Any]) -> ValidationResult:
        try:
            req = urllib.request.Request(
                target_url,
                headers={"User-Agent": "STRIX-SafeValidator/1.0"},
                method="HEAD",
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                headers = dict(resp.headers)
                missing = [h for h in self.RECOMMENDED_HEADERS if h.lower() not in [k.lower() for k in headers.keys()]]

                header_dump = "\n".join(f"{k}: {v}" for k, v in headers.items())
                ev_hash = self.compute_evidence_hash(header_dump)

                if missing:
                    return ValidationResult(
                        confirmed=True,
                        status="CONFIRMED",
                        evidence_hash=ev_hash,
                        evidence_snippet=f"Missing: {', '.join(missing)}",
                        reproduction_command=f"curl -s -I {target_url}",
                        detail=f"Target lacks hardening headers: {', '.join(missing)}",
                    )
                return ValidationResult(
                    confirmed=False,
                    status="NOT_REPRODUCIBLE",
                    evidence_hash=ev_hash,
                    evidence_snippet="All recommended headers present",
                    reproduction_command=f"curl -s -I {target_url}",
                    detail="All standard security hardening headers are configured.",
                )
        except Exception as e:
            return ValidationResult(
                confirmed=False,
                status="INCONCLUSIVE",
                evidence_hash="",
                evidence_snippet="",
                reproduction_command=f"curl -s -I {target_url}",
                detail=f"Target unreachable: {e}",
            )

