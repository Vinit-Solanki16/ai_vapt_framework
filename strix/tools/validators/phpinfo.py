"""Active non-destructive validator for exposed phpinfo / diagnostic pages."""

from __future__ import annotations

import urllib.request
from typing import Any
from urllib.parse import urljoin

from .base import BaseValidator, ValidationResult


class PhpInfoValidator(BaseValidator):
    """Safely checks for exposed phpinfo() diagnostic pages."""

    COMMON_PATHS = ["/phpinfo.php", "/info.php", "/test.php", "/php_info.php"]

    def validate(self, target_url: str, candidate: dict[str, Any]) -> ValidationResult:
        base = target_url.rstrip("/")
        for path in self.COMMON_PATHS:
            test_url = urljoin(base, path)
            try:
                req = urllib.request.Request(
                    test_url,
                    headers={"User-Agent": "STRIX-SafeValidator/1.0"},
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    if resp.status == 200:
                        content = resp.read(4096)
                        text = content.decode("utf-8", errors="replace")
                        if (
                            "PHP Version" in text
                            or "phpinfo()" in text
                            or "<title>phpinfo()</title>" in text
                        ):
                            ev_hash = self.compute_evidence_hash(content)
                            return ValidationResult(
                                confirmed=True,
                                status="CONFIRMED",
                                evidence_hash=ev_hash,
                                evidence_snippet=text[:250],
                                reproduction_command=f"curl -s -I {test_url}",
                                detail=f"Confirmed exposed phpinfo() diagnostic page at {test_url}",
                            )
            except Exception:
                continue

        return ValidationResult(
            confirmed=False,
            status="NOT_REPRODUCIBLE",
            evidence_hash="",
            evidence_snippet="",
            reproduction_command=f"curl -s -I {target_url}/phpinfo.php",
            detail="No exposed phpinfo() diagnostic page detected.",
        )
