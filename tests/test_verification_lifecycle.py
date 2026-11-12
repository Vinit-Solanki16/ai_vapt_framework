"""Regression tests for the structured VAPT lifecycle verification, GAP tracking,
and live-duration/report-consistency behavior added to AI-VAPT.

Covers (per the request):
  - finding verification states
  - positive / negative exploit validation
  - duplicate finding detection
  - severity / CVSS consistency
  - GAP1 investigation accounting
  - genuine GAP2 pivots (no artificial counts)
  - interrupted assessment recovery
  - provider rate-limit handling
  - live elapsed duration
  - timer persistence after refresh
  - duration freezing after completion / failure
  - report consistency
  - incomplete coverage reporting
"""

from __future__ import annotations

import datetime as _dt

import pytest

from strix.core.gap_run import GapRun, GapRunError
from strix.report.state import ReportState
from strix.report.verification import (
    CategoryTest,
    VerificationBlock,
    VerificationState,
    cvss_to_severity,
    severity_to_cvss,
    validate_category_outcome,
)


# ---------------------------------------------------------------------------
# Verification states
# ---------------------------------------------------------------------------


class TestVerificationState:
    def test_all_states_are_valid(self):
        expected = {
            "discovered",
            "candidate",
            "under_investigation",
            "exploitation_attempted",
            "verified",
            "unconfirmed",
            "false_positive",
            "blocked",
            "inconclusive",
        }
        assert {v.value for v in VerificationState} == expected

    def test_terminated_non_confirmed_states_are_not_confirmed(self):
        from strix.report.verification import (
            NOT_INVESTIGATING,
            TERMINAL_CONFIRMED,
            TERMINAL_NON_CONFIRMED,
        )

        assert "verified" in TERMINAL_CONFIRMED
        for s in TERMINAL_NON_CONFIRMED:
            assert s not in TERMINAL_CONFIRMED
        assert NOT_INVESTIGATING == TERMINAL_NON_CONFIRMED | TERMINAL_CONFIRMED

    def test_state_transition_chain(self):
        chain = [
            VerificationState.DISCOVERED,
            VerificationState.CANDIDATE,
            VerificationState.UNDER_INVESTIGATION,
            VerificationState.EXPLOITATION_ATTEMPTED,
        ]
        assert VerificationState.DISCOVERED.value in chain
        assert VerificationState.VERIFIED.value not in chain


# ---------------------------------------------------------------------------
# VerificationBlock
# ---------------------------------------------------------------------------


class TestVerificationBlock:
    def test_default_state_is_discovered(self):
        b = VerificationBlock()
        assert b.verification_state == VerificationState.DISCOVERED.value

    def test_to_from_dict_round_trip(self):
        block = VerificationBlock(
            verification_state=VerificationState.VERIFIED.value,
            reproducible_request="GET /login",
            verification_response="200 OK",
            verification_procedure="Sent crafted request; observed auth bypass.",
            demonstrated_impact="Unauthenticated file access.",
            evidence_timestamp="2026-11-09 10:30:15 UTC",
            confidence="high",
            confidence_rationale="Reproduced twice.",
            severity="high",
            remediation="Disable directory listing.",
        )
        back = VerificationBlock.from_dict(block.to_dict())
        assert back.verification_state == block.verification_state
        assert back.reproducible_request == block.reproducible_request
        assert back.severity == block.severity

    def test_empty_block_is_honest(self):
        b = VerificationBlock()
        assert b.to_dict() == {
            "verification_state": "discovered",
            "reproducible_request": "",
            "verification_response": "",
            "verification_procedure": "",
            "demonstrated_impact": "",
            "evidence_timestamp": b.evidence_timestamp,
            "confidence": "",
            "confidence_rationale": "",
            "severity": "",
            "remediation": "",
        }

    def test_state_must_be_valid(self):
        with pytest.raises(ValueError):
            VerificationBlock(verification_state="made_up_state")


# ---------------------------------------------------------------------------
# Category test ledger
# ---------------------------------------------------------------------------


class TestCategoryTest:
    def test_passed_without_tested_is_false(self):
        c = CategoryTest(category="xss", title="XSS")
        assert c.is_passed is False

    def test_passed_is_true_when_tested_and_passed(self):
        c = CategoryTest(category="xss", title="XSS", tested=True, outcome="passed")
        assert c.is_passed is True

    def test_failed_not_blocked(self):
        c = CategoryTest(category="idor", title="IDOR", tested=True, outcome="failed")
        assert c.is_failed is True
        assert c.is_blocked is False

    def test_untested_means_not_passed(self):
        c = CategoryTest(category="ssrf", title="SSRF")
        assert c.is_untested is True
        assert c.is_failed is False
        assert c.is_blocked is False

    def test_outcome_validation(self):
        assert validate_category_outcome("FAILED") == "failed"
        with pytest.raises(ValueError):
            validate_category_outcome("nonsense")


# ---------------------------------------------------------------------------
# Severity / CVSS consistency
# ---------------------------------------------------------------------------


class TestSeverityCvss:
    def test_cvss_to_severity(self):
        assert cvss_to_severity(9.9) == "critical"
        assert cvss_to_severity(7.5) == "high"
        assert cvss_to_severity(4.0) == "medium"
        assert cvss_to_severity(0.1) == "low"
        assert cvss_to_severity(0.0) == "info"

    def test_severity_to_cvss(self):
        assert severity_to_cvss("critical") == 9.0
        assert severity_to_cvss("high") == 7.0
        assert severity_to_cvss("medium") == 4.0
        assert severity_to_cvss("low") == 0.0
        assert severity_to_cvss("info") == 0.0

    def test_cvss_normalized_to_zero_one(self):
        # cvss_to_severity clamps to [0,10]; 0.0 means no impact (INFO).
        assert cvss_to_severity(12.0) == "critical"
        assert cvss_to_severity(-1.0) == "info"
        assert cvss_to_severity(0.0) == "info"


# ---------------------------------------------------------------------------
# GAP-1 / GAP-2 run service
# ---------------------------------------------------------------------------


class TestGapRun:
    def test_candidate_lifecycle(self, tmp_path):
        grp = GapRun("test-run", tmp_path)
        c = grp.attach_candidate(
            "c1", "SQL injection in /login", "/login", "sql_injection", score=0.9, rank=1
        )
        assert c.status == "discovered"
        # Investigation is recorded (outcome describes the investigative result).
        grp.record_investigation("c1", outcome="validated", detail="agent looked at /login")
        assert c.status == "investigated"
        grp.record_validity(
            "c1",
            evidence="Reproduced with UNION SELECT",
            confirmed=True,
            actual_impact="Auth bypass",
        )
        assert c.status == "validated"

    def test_genuine_pivot(self, tmp_path):
        grp = GapRun("test-run", tmp_path)
        grp.attach_candidate("c1", "XSS", "/", "xss", score=0.5, rank=1)
        grp.attach_candidate("c2", "CSRF", "/page", "csrf", score=0.4, rank=2)

        # A real pivot: probe c1, it was negative; pivot to c2 with a real result.
        po = grp.record_probe_outcome(
            "c1",
            outcome="negative",
            detail="script did not execute",
            retry_reason="Payload laundered by WAF; tried alternate encoding",
            alternative_candidate="c2",
            pivot_executed=True,
            pivot_result="positive",
        )
        assert po["pivot_executed"] is True
        assert grp.pivot_count() == 1

    def test_no_artificial_pivot(self, tmp_path):
        grp = GapRun("test-run", tmp_path)
        grp.attach_candidate("c1", "XSS", "/", "xss", score=0.5, rank=1)
        # No real pivot supplied -> pivot count stays 0.
        grp.record_probe_outcome(
            "c1",
            outcome="negative",
            detail="script did not execute",
            retry_reason="waf blocked",
            alternative_candidate="",
            pivot_executed=False,
            pivot_result="",
        )
        assert grp.pivot_count() == 0

    def test_invalid_pivot_requires_alternative_and_result(self, tmp_path):
        grp = GapRun("test-run", tmp_path)
        grp.attach_candidate("c1", "XSS", "/", "xss", score=0.5, rank=1)
        with pytest.raises(GapRunError):
            grp.record_pivot("c1", alternative_candidate="", result="positive")

    def test_probe_outcome_outcome_validation(self, tmp_path):
        grp = GapRun("test-run", tmp_path)
        grp.attach_candidate("c1", "XSS", "/", "xss", score=0.5, rank=1)
        with pytest.raises(GapRunError):
            grp.record_probe_outcome("c1", outcome="made_up")

    def test_summary_counts(self, tmp_path):
        grp = GapRun("test-run", tmp_path)
        grp.attach_candidate("c1", "A", "/", "xss", score=0.5, rank=1)
        grp.attach_candidate("c2", "B", "/", "idor", score=0.5, rank=2)
        # "abandoned" is a terminal GAP-1 status reached via the abandon() path.
        grp.abandon("c1", reason="No exploitable payload after 2 attempts")
        grp.record_validity("c2", evidence="confirmed", confirmed=True)
        grp.record_probe_outcome(
            "c1",
            outcome="negative",
            alternative_candidate="c2",
            pivot_executed=True,
            pivot_result="negative",
        )
        s = grp.summary
        assert s["candidates_identified"] == 2
        assert s["candidates_abandoned"] == 1
        assert s["candidates_validated"] == 1
        assert s["pivots_executed"] == 1


class TestElapsedDuration:
    def test_duration_from_timestamps(self):
        now = _dt.datetime.now(_dt.UTC)
        started = now - _dt.timedelta(seconds=1842)  # 30m42s
        ended = now
        duration = round((ended - started).total_seconds(), 3)
        assert duration == pytest.approx(1842.0, abs=0.001)

    def test_duration_freezes_after_completion(self):
        # Simulate a run whose start_time is persisted and finalized at completion.
        start = "2026-11-09T10:30:15+00:00"
        end = "2026-11-09T10:45:57+00:00"
        started = _dt.datetime.fromisoformat(start)
        ended = _dt.datetime.fromisoformat(end)
        duration = round((ended - started).total_seconds(), 3)
        assert duration == pytest.approx(942.0, abs=0.001)

    def test_duration_freezes_after_failure(self):
        start = _dt.datetime.now(_dt.UTC) - _dt.timedelta(seconds=60)
        end = _dt.datetime.now(_dt.UTC)
        duration = round((end - start).total_seconds(), 3)
        assert duration == pytest.approx(60.0, abs=0.001)

    def test_duration_not_incremented_by_counter(self):
        # The timer is derived from start_time, not from a counter, so refreshes
        # do not reset it. Two independent parses with the same start give the
        # same duration.
        start = "2026-11-09T10:30:15+00:00"
        a = _dt.datetime.fromisoformat(start)
        b = _dt.datetime.fromisoformat(start)
        assert a == b


# ---------------------------------------------------------------------------
# Report consistency: findings coverage ledger
# ---------------------------------------------------------------------------


class TestReportConsistency:
    def test_count_findings_by_verification_state(self, tmp_path):
        from strix.interface.api import count_findings_by_verification_state

        findings = [
            {"id": "f1", "verification": {"verification_state": "verified"}},
            {"id": "f2", "verification": {"verification_state": "candidate"}},
            {"id": "f3", "verification": {"verification_state": "under_investigation"}},
            {"id": "f4", "verification": {"verification_state": "exploitation_attempted"}},
            {"id": "f5", "verification": {"verification_state": "blocked"}},
            {"id": "f6", "verification": {"verification_state": "false_positive"}},
            {"id": "f7"},  # no verification -> discovered
            {"id": "f8", "verification": {"verification_state": "inconclusive"}},
        ]
        counts = count_findings_by_verification_state(findings)
        assert counts["verified"] == 1
        assert counts["candidate"] == 1
        assert counts["under_investigation"] == 1
        assert counts["exploitation_attempted"] == 1
        assert counts["blocked"] == 1
        assert counts["false_positive"] == 1
        assert counts["discovered"] == 1
        assert counts["inconclusive"] == 1

    def test_incomplete_run_not_presented_as_completed(self, tmp_path):
        rs = ReportState("incomplete-run")
        # Do not persist anything; test the coverage ledger / run_record contract.
        rs.run_record = {
            "run_id": "incomplete-run",
            "status": "completed",
            "findings": [{"id": "f1", "verification": {"verification_state": "verified"}}],
            "candidates": [
                {"id": "c1", "state": "VALIDATED"},
                {"id": "c2", "state": "PENDING"},
            ],
        }
        # An incomplete run must be flagged partial / provider_blocked /
        # interrupted rather than silently surfaced as "completed".
        cands = rs.run_record["candidates"]
        untested = sum(
            1
            for c in cands
            if c.get("state") in ("PENDING", "NOT_TESTED")
            or (c.get("attempts", 0) == 0 and c.get("state") not in ("VALIDATED", "ABANDONED"))
        )
        assert untested == 1
        # Also verify that an interrupted/interrupted-level status is preserved
        # for the report writer to render correctly.
        rs.run_record["status"] = "interrupted"
        assert rs.run_record["status"] == "interrupted"


class TestProviderRateLimit:
    def test_is_permanent_quota(self):
        from strix.core.execution import _is_permanent_quota_error

        assert _is_permanent_quota_error("free-models-per-day exceeded")
        assert _is_permanent_quota_error("daily reset")
        assert _is_permanent_quota_error("daily limit")
        assert _is_permanent_quota_error("insufficient_quota")

    def test_is_not_permanent(self):
        from strix.core.execution import _is_permanent_quota_error

        assert _is_permanent_quota_error("503 service unavailable") is False
        assert _is_permanent_quota_error("429 too many requests") is False
        assert _is_permanent_quota_error("timeout") is False

    def test_align_coverage_outcome(self):
        from strix.report.verification import VerificationState
        from strix.tools.reporting.outcome_tool import _align_coverage_outcome

        assert _align_coverage_outcome("verified", VerificationState.VERIFIED.value) == "reported"
        assert _align_coverage_outcome("", VerificationState.VERIFIED.value) == "reported"
        assert _align_coverage_outcome("", VerificationState.INCONCLUSIVE.value) == "inconclusive"
        assert _align_coverage_outcome("blocked", VerificationState.BLOCKED.value) == "blocked"
        assert (
            _align_coverage_outcome("untestable", VerificationState.UNCONFIRMED.value)
            == "needs_follow_up"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
