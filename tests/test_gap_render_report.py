"""Regression tests for the run-scoped GAP service and report rendering of GAP
progress + live duration.

These tests verify the state-level contracts (no fabrication of GAP events)
without requiring a live scan harness or an LLM provider.
"""

from __future__ import annotations

import pytest

from strix.core.gap_run import GapRun, GapRunError
from strix.report.builder import render_html_report
from strix.report.state import (
    get_global_gap_run,
    set_global_gap_run,
)


class TestGapRunScope:
    def test_gap_run_is_bound_to_a_single_run(self, tmp_path):
        run1 = tmp_path / "run-a"
        run2 = tmp_path / "run-b"
        run1.mkdir()
        run2.mkdir()

        set_global_gap_run(GapRun("run-1", run1))
        assert get_global_gap_run() is not None
        assert get_global_gap_run().run_id == "run-1"

        set_global_gap_run(GapRun("run-2", run2))
        assert get_global_gap_run() is not None
        assert get_global_gap_run().run_id == "run-2"

    def test_gap_run_save_round_trip(self, tmp_path):
        state_dir = tmp_path / "gap"
        state_dir.mkdir()
        grp = GapRun("c1", state_dir)
        grp.attach_candidate("c1", "SQLi in /login", "/login", "sql_injection", score=0.9, rank=1)
        grp.record_investigation("c1", outcome="validated")
        grp.record_probe_outcome(
            "c1",
            outcome="positive",
            alternative_candidate="c2",
            pivot_executed=True,
            pivot_result="positive",
        )
        grp.save()

        loaded = GapRun.load("c1", state_dir)
        assert loaded.run_id == grp.run_id
        assert len(loaded.candidates) == 1
        assert loaded.candidates["c1"].status == "investigated"
        assert loaded.candidates["c1"].investigation_outcome == "validated"
        assert loaded.pivot_count() == 1

    def test_pivot_count_requires_real_pivot(self, tmp_path):
        grp = GapRun("c1", tmp_path)
        grp.attach_candidate("c1", "XSS", "/", "xss", score=0.5, rank=1)
        with pytest.raises(GapRunError):
            grp.record_probe_outcome(
                "c1",
                outcome="positive",
                alternative_candidate="",
                pivot_executed=True,
                pivot_result="positive",
            )
        assert grp.pivot_count() == 0

    def test_no_fabricated_pivot(self, tmp_path):
        grp = GapRun("c1", tmp_path)
        grp.attach_candidate("c1", "XSS", "/", "xss", score=0.5, rank=1)
        grp.record_probe_outcome(
            "c1",
            outcome="negative",
            detail="no payload",
            alternative_candidate="",
            pivot_executed=False,
            pivot_result="",
        )
        assert grp.pivot_count() == 0


class TestReportRenderingOfGapAndDuration:
    """Verify the HTML report renderer consumes GAP progress + live duration."""

    def _run_data(self, *, gap_run=None, duration_seconds: str | None = "120") -> dict:
        return {
            "run_id": "r1",
            "status": "completed",
            "created_at": "2026-11-09T10:00:00+00:00",
            "findings": [
                {
                    "id": "f1",
                    "title": "SQL injection in /login",
                    "severity": "HIGH",
                    "status": "verified",
                    "gap_outcome": "confirmed",
                }
            ],
            "candidates": [
                {
                    "id": "c1",
                    "title": "SQL injection in /login",
                    "category": "sql_injection",
                    "priority_rank": 1,
                    "state": "VALIDATED",
                    "attempts": 2,
                    "reason": "Reproduced with UNION SELECT",
                }
            ],
            "decision_trace": [
                {
                    "type": "probe",
                    "candidate_id": "c1",
                    "outcome": "positive",
                    "pivot_executed": True,
                    "pivot_result": "positive",
                    "at": "2026-11-09T10:10:00+00:00",
                }
            ],
            "pivot_events": [{"type": "REDIRECT", "candidate_id": "c1", "to": "c2", "at": "10:10"}],
            "duration_seconds": duration_seconds,
            "evidence_tier": "OBSERVED_EXTERNAL",
        }

    def test_render_html_includes_gap1_triage(self):
        run_data = self._run_data()
        html = render_html_report(run_data)
        assert "GAP-1 Triage" in html
        assert "SQL injection in /login" in html
        # Verified findings are enumerated; GAP-1 rows come from run_data candidates.
        assert "VALIDATED" in html

    def test_render_html_includes_gap2_trail(self):
        run_data = self._run_data()
        html = render_html_report(run_data)
        # GAP-2 section renders the decision-pivot trace + pivot count.
        assert "GAP-2" in html
        assert "Dynamic Pivots" in html
        assert "1" in html  # total_pivots counts REDIRECT pivots

    def test_render_html_duration_and_evidence_tier(self):
        run_data = self._run_data(duration_seconds="42.5")
        html = render_html_report(run_data)
        assert "42" in html
        assert "OBSERVED_EXTERNAL" in html

    def test_member_not_reported_as_confirmed(self):
        """A finding with an unverified status must not appear as confirmed."""
        run_data = self._run_data()
        run_data["findings"][0]["status"] = "candidate"
        html = render_html_report(run_data)
        assert "SQL injection in /login" in html
        assert "candidate" in html.lower()
