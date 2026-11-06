"""Base active non-destructive validator with SHA-256 cryptographic evidence capture."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationResult:
    confirmed: bool
    status: str  # CONFIRMED, NOT_REPRODUCIBLE, INCONCLUSIVE
    evidence_hash: str
    evidence_snippet: str
    reproduction_command: str
    detail: str


class BaseValidator:
    """Base class for safe HTTP validation routines."""

    def compute_evidence_hash(self, raw_content: bytes | str) -> str:
        """Compute tamper-proof SHA-256 hash of response evidence."""
        if isinstance(raw_content, str):
            raw_content = raw_content.encode("utf-8")
        return hashlib.sha256(raw_content).hexdigest()

    def validate(self, target_url: str, candidate: dict[str, Any]) -> ValidationResult:
        raise NotImplementedError
