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


# ---------------------------------------------------------------------------
# Strict Verification Enforcement per Vulnerability Class
# ---------------------------------------------------------------------------


def evaluate_finding_verification(finding: dict[str, Any]) -> tuple[str, str, bool]:
    """Evaluate whether a finding genuinely satisfies verification requirements.

    Returns:
        (verification_state, rationale, is_verified)

    Rules:
    1. Reflected XSS: Input reflection alone (<script>alert(1)</script> in HTML body via curl)
       is NOT verified XSS. Requires active browser DOM execution, alert dialog interception,
       or headless browser proof. If only reflected input is observed -> UNCONFIRMED.
    2. Path Traversal / LFI: PHP include warning or 'Failed to open stream' error is NOT
       verified arbitrary file disclosure. Requires matching expected file contents
       (/etc/passwd, /etc/hosts, system tokens). If only warnings/errors -> UNCONFIRMED.
    3. PHPInfo / Diagnostic Disclosure: Unauthenticated HTTP 200 response containing full
       PHP configuration / system tables -> VERIFIED.
    4. Passive Header Observations: Missing headers without executable exploit -> UNCONFIRMED.
    5. Severity and verification state remain strictly separate concepts.
    """
    title = str(finding.get("title", "")).strip()
    title_lower = title.lower()
    description = str(finding.get("description", "")).lower()
    target = str(finding.get("target", "")).lower()
    procedure = str(
        finding.get("verification_procedure") or finding.get("validation_method") or ""
    ).lower()
    impact = str(finding.get("demonstrated_impact") or finding.get("impact") or "").lower()
    response = str(
        finding.get("reproducible_response")
        or finding.get("verification_response")
        or finding.get("evidence_snippet")
        or finding.get("evidence")
        or ""
    ).lower()
    request = str(
        finding.get("reproducible_request") or finding.get("poc_script_code") or ""
    ).lower()

    # Rule 1: Reflected Cross-Site Scripting (XSS)
    if (
        "xss" in title_lower
        or "cross-site scripting" in title_lower
        or "cwe-79" in str(finding.get("cwe_id", "")).lower()
    ):
        # Check for genuine DOM execution / browser alert proof
        has_dom_execution = any(
            marker in response or marker in procedure or marker in impact
            for marker in [
                "alert dialog intercepted",
                "alert(1) executed",
                "dialog text: 1",
                "browser execution confirmed",
                "dom sink executed",
                "playwright alert intercepted",
                "puppeteer dialog",
                "executed in chromium",
                "executed in browser",
            ]
        )
        if has_dom_execution:
            return (
                VerificationState.VERIFIED.value,
                "Client-side script execution confirmed in browser DOM runtime with active alert dialog trigger.",
                True,
            )

        # If only reflected input observed via curl / HTTP body
        return (
            VerificationState.UNCONFIRMED.value,
            "Reflected input observed in HTTP response body, but client-side script execution was not verified in an active browser/DOM runtime.",
            False,
        )

    # Rule 2: Path Traversal / Local File Inclusion (LFI)
    if (
        any(
            k in title_lower
            for k in ("path traversal", "local file inclusion", "file inclusion", "lfi")
        )
        or "cwe-22" in str(finding.get("cwe_id", "")).lower()
    ):
        # Check for genuine extracted system file contents
        has_file_content = any(
            marker in response
            for marker in [
                "root:x:0:0:",
                "root:*:0:0:",
                "/bin/bash",
                "/bin/sh",
                "127.0.0.1\tlocalhost",
                "127.0.0.1 localhost",
                "[extensions]",
                "[fonts]",
            ]
        )
        # Check if response is merely a PHP warning / include failure
        is_include_error = any(
            err in response
            for err in [
                "failed to open stream",
                "failed opening",
                "warning: include",
                "warning: require",
                "no such file or directory",
                "operation failed",
            ]
        )
        if has_file_content:
            return (
                VerificationState.VERIFIED.value,
                "Arbitrary system file disclosure confirmed with matching target file signatures.",
                True,
            )
        if is_include_error:
            return (
                VerificationState.UNCONFIRMED.value,
                "Server returned PHP include warning and internal path disclosure, but arbitrary file content extraction was not demonstrated.",
                False,
            )

        return (
            VerificationState.UNCONFIRMED.value,
            "File inclusion parameter probed, but access to requested file contents was not demonstrated.",
            False,
        )

    # Rule 3: PHPInfo Diagnostic Configuration Disclosure
    if "phpinfo" in title_lower or "diagnostic configuration" in title_lower:
        has_phpinfo_tables = any(
            marker in response
            for marker in [
                "php version",
                "system linux",
                "build date",
                "server api",
                "loaded configuration file",
                '<!doctype html public "-//w3c//dtd xhtml 1.0 transitional//en"',
            ]
        )
        if has_phpinfo_tables:
            return (
                VerificationState.VERIFIED.value,
                "Direct unauthenticated HTTP response exposes full server configuration and environment diagnostic tables.",
                True,
            )

    # Rule 4: Missing Defensive Headers / CSP / Hardening Observations
    if any(
        k in title_lower
        for k in (
            "missing-security-headers",
            "x-frame-options",
            "content security policy",
            "strict-transport-security",
            "cookie missing",
        )
    ):
        return (
            VerificationState.UNCONFIRMED.value,
            "Passive HTTP response header audit notes missing defensive directives; active exploit unverified.",
            False,
        )

    # Rule 5: Generic Verification Check via VerificationBlock contract
    vb_data = finding.get("verification") or {}
    vb = VerificationBlock(
        verification_state=str(
            vb_data.get("verification_state") or finding.get("verification_state") or "discovered"
        ),
        reproducible_request=str(vb_data.get("reproducible_request") or request or ""),
        verification_response=str(vb_data.get("verification_response") or response or ""),
        verification_procedure=str(vb_data.get("verification_procedure") or procedure or ""),
        demonstrated_impact=str(vb_data.get("demonstrated_impact") or impact or ""),
        evidence_timestamp=str(
            vb_data.get("evidence_timestamp") or finding.get("evidence_timestamp") or ""
        ),
        confidence=str(vb_data.get("confidence") or finding.get("confidence") or ""),
        severity=str(finding.get("severity") or ""),
    )
    if (
        vb.satisfies_verification_contract()
        and vb.verification_state == VerificationState.VERIFIED.value
    ):
        return (
            VerificationState.VERIFIED.value,
            "Full reproducible request, response, and demonstrated impact satisfied verification contract.",
            True,
        )

    raw_state = (
        str(finding.get("verification_state") or "unconfirmed").strip().lower().replace(" ", "_")
    )
    if raw_state == "verified":
        raw_state = "unconfirmed"
    if raw_state not in [s.value for s in VerificationState]:
        raw_state = "unconfirmed"
    return (raw_state, "Finding did not meet active exploit verification contract.", False)
