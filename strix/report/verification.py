"""Structured finding verification — states, evidence blocks, and report consistency.

Findings answer "what did we find". Verification is what proves a finding is real:

    Discovered -> Candidate -> Under investigation -> Exploitation attempted
    -> Verified | Unconfirmed | False positive | Blocked | Inconclusive

A confirmed finding must carry a reproducible request, an independent
verification procedure, demonstrated impact, an evidence timestamp, and
confidence/severity. A scanner alert or suspicious response alone is never a
confirmed finding.

This module also carries the category test ledger: for every vulnerability
category actually exercised by the engine, record whether it was tested and
how it closed (passed / failed / blocked / untested), so reports can never
present an untested category as "passed".
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Verification states
# ---------------------------------------------------------------------------


class VerificationState(str, Enum):
    """Every finding carries exactly one of these.

    The ordering is the lifecycle: discovered is the initial state, Verified
    is the only terminal "confirmed" state, and the rest are terminal in the
    sense that they stop a finding from being presented as confirmed.
    """

    DISCOVERED = "discovered"
    CANDIDATE = "candidate"
    UNDER_INVESTIGATION = "under_investigation"
    EXPLOITATION_ATTEMPTED = "exploitation_attempted"
    VERIFIED = "verified"
    UNCONFIRMED = "unconfirmed"
    FALSE_POSITIVE = "false_positive"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"


# Terminal, non-confirmed states (cannot be presented as a confirmed vuln).
TERMINAL_NON_CONFIRMED = frozenset(
    {
        VerificationState.UNCONFIRMED,
        VerificationState.FALSE_POSITIVE,
        VerificationState.BLOCKED,
        VerificationState.INCONCLUSIVE,
    }
)

# Terminal, confirmed state.
TERMINAL_CONFIRMED = frozenset({VerificationState.VERIFIED})

# Any state that is no longer being investigated.
NOT_INVESTIGATING = TERMINAL_NON_CONFIRMED | TERMINAL_CONFIRMED

# States that a finding can be "moved up" out of when new evidence arrives.
INVESTIGATING_STATES = frozenset(
    {
        VerificationState.DISCOVERED,
        VerificationState.CANDIDATE,
        VerificationState.UNDER_INVESTIGATION,
        VerificationState.EXPLOITATION_ATTEMPTED,
        VerificationState.INCONCLUSIVE,
    }
)


# ---------------------------------------------------------------------------
# The verification evidence block (the "actual verification procedure")
# ---------------------------------------------------------------------------


@dataclass
class VerificationBlock:
    """Structured, independently reproducible evidence for one finding.

    All fields are optional so a finding can start as a candidate and grow.
    ``verification_state`` defaults to "discovered" and is the only field the
    caller may not leave on a value that implies confirmation without evidence.
    """

    verification_state: str = VerificationState.DISCOVERED.value
    reproducible_request: str = ""  # exact HTTP request/proxy exchange that reproduces
    verification_response: str = ""  # response body / status the procedure produced
    verification_procedure: str = ""  # what you actually did to confirm (not a guess)
    demonstrated_impact: str = ""  # the concrete, observed impact (not hypothetical)
    evidence_timestamp: str = ""  # ISO-8601 UTC when the evidence was captured
    confidence: str = ""  # high | medium | low | none
    confidence_rationale: str = ""  # required when confidence != high
    severity: str = ""  # critical | high | medium | low | info
    remediation: str = ""  # the remediation the finding leads to

    def satisfies_verification_contract(self) -> bool:
        """A finding satisfies the verification contract only if it possesses:
        1. Non-empty reproducible_request (an actual captured HTTP/network request).
        2. Non-empty verification_response (actual observed HTTP response data).
        3. Non-empty verification_procedure (concrete verification steps executed).
        4. Non-empty demonstrated_impact (concrete, observed impact, not generic text).
        5. Non-empty evidence_timestamp.
        """
        return bool(
            self.reproducible_request
            and str(self.reproducible_request).strip()
            and str(self.reproducible_request).strip() != "N/A"
            and self.verification_response
            and str(self.verification_response).strip()
            and self.verification_procedure
            and str(self.verification_procedure).strip()
            and self.demonstrated_impact
            and str(self.demonstrated_impact).strip()
            and self.evidence_timestamp
            and str(self.evidence_timestamp).strip()
        )

    def __post_init__(self) -> None:
        # Normalize severity/confidence case for contract use.
        self.verification_state = (
            (self.verification_state or VerificationState.DISCOVERED.value).strip().lower()
        )
        if self.verification_state not in VerificationState.__members__.values():
            raise ValueError(
                f"verification_state must be one of "
                f"{sorted(VerificationState.__members__.values())}, got {self.verification_state!r}"
            )
        self.confidence = (self.confidence or "").strip().lower()
        self.severity = (self.severity or "").strip().lower()
        self.evidence_timestamp = self.evidence_timestamp or _dt.datetime.now(_dt.UTC).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        if self.verification_state == VerificationState.VERIFIED.value:
            if not self.satisfies_verification_contract():
                self.verification_state = VerificationState.UNCONFIRMED.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_state": self.verification_state,
            "reproducible_request": self.reproducible_request,
            "verification_response": self.verification_response,
            "verification_procedure": self.verification_procedure,
            "demonstrated_impact": self.demonstrated_impact,
            "evidence_timestamp": self.evidence_timestamp,
            "confidence": self.confidence,
            "confidence_rationale": self.confidence_rationale,
            "severity": self.severity,
            "remediation": self.remediation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationBlock:
        return cls(
            verification_state=str(
                data.get("verification_state", VerificationState.DISCOVERED.value)
            ),
            reproducible_request=str(data.get("reproducible_request", "")),
            verification_response=str(data.get("verification_response", "")),
            verification_procedure=str(data.get("verification_procedure", "")),
            demonstrated_impact=str(data.get("demonstrated_impact", "")),
            evidence_timestamp=str(data.get("evidence_timestamp", "")),
            confidence=str(data.get("confidence", "")),
            confidence_rationale=str(data.get("confidence_rationale", "")),
            severity=str(data.get("severity", "")),
            remediation=str(data.get("remediation", "")),
        )


# ---------------------------------------------------------------------------
# Category test ledger (the negative space a client report needs)
# ---------------------------------------------------------------------------


@dataclass
class CategoryTest:
    """How one vulnerability category closed on one target.

    A category is "tested" only when a skill/tool actually ran it. Below that,
    it is untested. Failed and blocked are distinct: a failed test produced a
    result that argues against the finding; a blocked test could not run and
    must never be reported as "no vulnerability found".
    """

    category: str
    title: str
    tested: bool = False
    outcome: str = "untested"  # passed | failed | blocked | untested
    test_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    evidence: str = ""
    last_run_at: str = ""

    def update(
        self,
        *,
        tested: bool,
        outcome: str,
        test_count: int = 0,
        passed_count: int = 0,
        failed_count: int = 0,
        blocked_count: int = 0,
        evidence: str = "",
        last_run_at: str = "",
    ) -> None:
        self.tested = tested
        self.outcome = outcome
        self.test_count += test_count
        self.passed_count += passed_count
        self.failed_count += failed_count
        self.blocked_count += blocked_count
        if evidence:
            self.evidence = evidence
        if last_run_at:
            self.last_run_at = last_run_at

    @property
    def is_passed(self) -> bool:
        return self.tested and self.outcome == "passed"

    @property
    def is_failed(self) -> bool:
        return self.tested and self.outcome == "failed"

    @property
    def is_blocked(self) -> bool:
        return self.tested and self.outcome == "blocked"

    @property
    def is_untested(self) -> bool:
        return not self.tested

    @property
    def summary(self) -> str:
        return (
            f"{self.outcome} (tested={self.tested}, "
            f"passes={self.passed_count}, fails={self.failed_count}, "
            f"blocked={self.blocked_count})"
        )


def evaluate_verification(block: VerificationBlock) -> VerificationBlock:
    """Evaluate whether a verification block meets the contract to become verified."""
    if block.satisfies_verification_contract():
        block.verification_state = VerificationState.VERIFIED.value
    elif block.verification_state == VerificationState.VERIFIED.value:
        block.verification_state = VerificationState.CANDIDATE.value
    return block


_VALID_CATEGORY_OUTCOMES = frozenset({"passed", "failed", "blocked", "untested"})


def validate_category_outcome(outcome: str) -> str:
    """Return outcome lowercased, or raise ValueError for an invalid value."""
    normalized = (outcome or "untested").strip().lower()
    if normalized not in _VALID_CATEGORY_OUTCOMES:
        raise ValueError(
            f"category outcome must be one of {sorted(_VALID_CATEGORY_OUTCOMES)}, got {outcome!r}"
        )
    return normalized


# ---------------------------------------------------------------------------
# Severity <-> CVSS consistency
# ---------------------------------------------------------------------------


_SEVERITY_TO_CVSS = {
    "critical": (9.0, 10.0),
    "high": (7.0, 9.0),
    "medium": (4.0, 7.0),
    "low": (0.0, 4.0),
    "info": (0.0, 0.0),
    "none": (0.0, 0.0),
}

_CVSS_TO_SEVERITY = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "info",
}


def cvss_to_severity(score: float) -> str:
    score = max(0.0, min(10.0, float(score)))
    if score == 0.0:
        return "info"
    for label, (lo, hi) in _SEVERITY_TO_CVSS.items():
        if lo <= score < hi or (hi == 10.0 and score == 10.0):
            return label
    return "none"


def severity_to_cvss(severity: str) -> float | None:
    label = (severity or "").strip().lower()
    return _SEVERITY_TO_CVSS.get(label, (0.0, 0.0))[0] if label in _SEVERITY_TO_CVSS else None


def validate_cvss(cvss: float | None) -> tuple[float, str]:
    """Return (score, severity) after enforcing the CVSS 0-10 contract."""
    if cvss is None:
        return 0.0, "info"
    score = max(0.0, min(10.0, float(cvss)))
    if score == 0.0:
        return 0.0, "info"
    sev = cvss_to_severity(score)
    return score, sev


def normalize_severity(severity: str) -> str:
    """Return a canonical severity; 'null' becomes 'info'."""
    label = (severity or "info").strip().lower()
    return label if label in _CVSS_TO_SEVERITY else "info"


def severity_label_cvss(score: float) -> str:
    return _CVSS_TO_SEVERITY.get(cvss_to_severity(score), "info")
