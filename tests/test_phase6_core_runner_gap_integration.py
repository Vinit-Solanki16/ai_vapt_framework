"""Phase 6: Unified Autonomous Core Integration Tests.

Validates that:
1. The autonomous core runner maintains a genuine run-scoped candidate queue (GAP-1).
2. Probe outcome recording truthfully updates attempts and candidate states.
3. GAP-2 dynamic pivoting executes genuine pivots on threshold exhaustion.
4. Scope validation prevents out-of-scope pivots.
5. Invariant holds: dispatched = investigated + not_tested + blocked.
6. Evidence-based verification contract prevents unverified findings from becoming Verified.
7. Concurrent autonomous runs maintain complete state isolation without global leakage.
8. Resume preserves completed candidate states without re-probing.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strix.core.decision_engine.schemas import (
    CandidateState,
    Outcome,
    PivotActionType,
)
from strix.core.gap_run import GapRun
from strix.report.state import (
    ReportState,
    get_gap_run_for_run,
    get_report_state_for_run,
    set_global_gap_run,
    set_global_report_state,
)
from strix.tools.reporting.outcome_tool import (
    record_probe_outcome,
    record_vulnerability_outcome,
)


# ---------------------------------------------------------------------------
# 1. GAP-1 Candidate Queue and Invariant Lifecycle
# ---------------------------------------------------------------------------


def test_gap1_candidate_queue_lifecycle(tmp_path: Path):
    """Test candidate initialization, prioritization, and invariant preservation."""
    scan_id = "test-phase6-queue"
    gap_run = GapRun(scan_id, tmp_path, threshold=2)

    # Attach candidates in priority order
    c1 = gap_run.attach_candidate(
        "sqli-1",
        "SQL Injection in /vulnerabilities/sqli/",
        "/vulnerabilities/sqli/",
        "sql_injection",
        score=0.95,
        rank=1,
    )
    c2 = gap_run.attach_candidate(
        "xss-1",
        "Reflected XSS in /vulnerabilities/xss_r/",
        "/vulnerabilities/xss_r/",
        "xss",
        score=0.80,
        rank=2,
    )
    c3 = gap_run.attach_candidate(
        "csrf-1",
        "CSRF in /vulnerabilities/csrf/",
        "/vulnerabilities/csrf/",
        "csrf",
        score=0.60,
        rank=3,
    )

    assert c1.status == "discovered"
    assert c2.status == "discovered"
    assert c3.status == "discovered"

    # Initially: all 3 dispatched, 0 investigated, 0 blocked, 3 not_tested
    s0 = gap_run.summary
    assert s0["candidates_dispatched"] == 3
    assert s0["candidates_investigated"] == 0
    assert s0["candidates_blocked"] == 0
    assert s0["candidates_not_tested"] == 3
    assert s0["invariant_holds"] is True
    assert s0["candidates_dispatched"] == (
        s0["candidates_investigated"] + s0["candidates_not_tested"] + s0["candidates_blocked"]
    )

    # Investigate c1 (positive)
    gap_run.record_probe_outcome("sqli-1", outcome="positive", detail="error boolean differential")
    gap_run.record_validity("sqli-1", evidence="UNION SELECT admin", confirmed=True)

    # Investigate c2 (negative, attempt 1)
    gap_run.record_probe_outcome(
        "xss-1", outcome="negative", detail="script tags filtered by htmlspecialchars"
    )

    # Investigate c3 (blocked)
    gap_run.record_blocked(
        "csrf-1", reason="Anti-CSRF token strictly validated and rotation enforced"
    )

    # Invariant check: 3 dispatched = 2 investigated (c1 validated, c2 attempted) + 0 not_tested + 1 blocked (c3)
    s1 = gap_run.summary
    assert s1["candidates_dispatched"] == 3
    assert s1["candidates_investigated"] == 2
    assert s1["candidates_blocked"] == 1
    assert s1["candidates_not_tested"] == 0
    assert s1["invariant_holds"] is True
    assert s1["candidates_dispatched"] == (
        s1["candidates_investigated"] + s1["candidates_not_tested"] + s1["candidates_blocked"]
    )


# ---------------------------------------------------------------------------
# 2. GAP-2 Genuine Pivoting and Scope Enforcement
# ---------------------------------------------------------------------------


def test_gap2_genuine_pivoting_and_scope_validation(tmp_path: Path):
    """Test retry threshold enforcement, scope validation, and genuine pivot increments."""
    scan_id = "test-phase6-gap2"
    gap_run = GapRun(scan_id, tmp_path, threshold=2)

    # Target in scope is http://localhost/dvwa
    authorized_targets = ["http://localhost/dvwa"]

    gap_run.attach_candidate("c1", "Probe A", "/vulnerabilities/fi/", "lfi", score=0.9, rank=1)
    gap_run.attach_candidate(
        "c-out-of-scope",
        "Malicious Out-Of-Scope",
        "http://external-evil.com/leak",
        "ssrf",
        score=0.85,
        rank=2,
    )
    gap_run.attach_candidate("c2", "Probe B", "/vulnerabilities/sqli/", "sqli", score=0.7, rank=3)

    engine = gap_run.sync_decision_engine(authorized_targets=authorized_targets)

    # Attempt 1 on c1 fails -> Retry, no pivot
    act1 = engine.record_outcome("c1", Outcome.FAIL_TIMEOUT, detail="timeout on payload 1")
    assert act1.action == PivotActionType.RETRY
    assert act1.attempt == 1
    assert gap_run.pivot_count() == 0

    # Attempt 2 on c1 fails -> Threshold reached! Candidate c1 abandoned
    act2 = engine.record_outcome("c1", Outcome.FAIL_TIMEOUT, detail="timeout on payload 2")
    # Engine skips c-out-of-scope (blocked as out of scope) and redirects to in-scope c2!
    assert act2.action == PivotActionType.REDIRECT
    assert act2.to_candidate == "c2"

    # Confirm c-out-of-scope was blocked for scope violation
    assert engine.candidates["c-out-of-scope"].state == CandidateState.BLOCKED

    # Now execute actual alternative probe against c2
    po = gap_run.record_probe_outcome(
        "c1",
        outcome="negative",
        detail="Threshold k=2 reached",
        retry_reason="LFI route unreachable",
        alternative_candidate="c2",
        pivot_executed=True,
        pivot_result="positive",
    )
    assert po["pivot_executed"] is True
    assert gap_run.pivot_count() == 1


# ---------------------------------------------------------------------------
# 3. Outcome Tool Integration in Autonomous Execution Loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outcome_tools_enforce_verification_contract_and_gap(tmp_path: Path):
    """Test record_probe_outcome and record_vulnerability_outcome inside agent context."""
    scan_id = "test-phase6-tools"
    report_state = ReportState(scan_id)
    report_state._run_dir = tmp_path
    set_global_report_state(report_state)

    gap_run = GapRun(scan_id, tmp_path, threshold=2)
    report_state.gap_run = gap_run
    set_global_gap_run(gap_run)

    gap_run.attach_candidate("sqli-login", "SQLi in /login", "/login", "sqli", rank=1)
    gap_run.attach_candidate("xss-search", "XSS in /search", "/search", "xss", rank=2)

    # Mock ToolContext
    ctx = MagicMock()
    ctx.tool_name = "record_probe_outcome"
    ctx.run_config = None
    ctx.context = {
        "agent_id": "root-agent-1",
        "scan_id": scan_id,
        "gap_run": gap_run,
        "decision_engine": gap_run.decision_engine,
        "scan_targets": ["http://localhost:8080"],
    }

    # Probe outcome 1: c1 fails
    res_probe1 = await record_probe_outcome.on_invoke_tool(
        ctx,
        json.dumps(
            {
                "candidate_id": "sqli-login",
                "probe_outcome": "negative",
                "detail": "WAF 403 Forbidden",
                "retry_reason": "WAF block",
            }
        ),
    )
    data1 = json.loads(res_probe1)
    assert data1["success"] is True
    assert data1["attempts"] == 1
    assert data1["pivot_executed"] is False
    assert gap_run.pivot_count() == 0

    # Probe outcome 2: c1 fails again -> genuine pivot to xss-search
    res_probe2 = await record_probe_outcome.on_invoke_tool(
        ctx,
        json.dumps(
            {
                "candidate_id": "sqli-login",
                "probe_outcome": "negative",
                "detail": "WAF 403 Forbidden on retry",
                "retry_reason": "Threshold k=2 reached",
                "alternative_candidate": "xss-search",
                "pivot_executed": True,
                "pivot_result": "positive",
            }
        ),
    )
    data2 = json.loads(res_probe2)
    assert data2["success"] is True
    assert data2["pivot_executed"] is True
    assert data2["pivots_total"] == 1
    assert data2["invariant_holds"] is True

    # 4. Create finding: initial creation WITHOUT verification evidence must be CANDIDATE
    rep_id = report_state.add_vulnerability_report(
        title="Reflected XSS in /search query parameter",
        severity="high",
        description="Search input reflected without sanitization.",
        impact="Session cookie theft",
        target="http://localhost:8080/search",
    )
    finding = next(r for r in report_state.vulnerability_reports if r["id"] == rep_id)
    assert finding["verification_state"] == "candidate"

    # Attempt to mark verified WITHOUT reproducible request/response -> must downgrade to UNCONFIRMED
    res_unverified = await record_vulnerability_outcome.on_invoke_tool(
        ctx,
        json.dumps(
            {
                "report_id": rep_id,
                "verification_state": "verified",
                "reproducible_request": "",  # Missing!
                "verification_response": "",  # Missing!
                "verification_procedure": "Looked at code",
                "demonstrated_impact": "Hypothetical impact",
            }
        ),
    )
    data_unv = json.loads(res_unverified)
    assert data_unv["verification"]["verification_state"] == "unconfirmed"
    assert finding["verification_state"] == "unconfirmed"

    # Provide genuine reproducible proof -> becomes VERIFIED
    res_verified = await record_vulnerability_outcome.on_invoke_tool(
        ctx,
        json.dumps(
            {
                "report_id": rep_id,
                "verification_state": "verified",
                "reproducible_request": "GET /search?q=<script>alert(1)</script> HTTP/1.1\nHost: localhost:8080",
                "verification_response": "HTTP/1.1 200 OK\n\nSearch results: <script>alert(1)</script>",
                "verification_procedure": "Injected script tag into search query parameter and observed raw HTML reflection",
                "demonstrated_impact": "Arbitrary JavaScript execution in victim browser session",
                "evidence_timestamp": "2026-11-10T15:00:00Z",
                "confidence": "high",
                "severity": "high",
                "remediation": "Apply HTML entity encoding to user-supplied query parameters.",
            }
        ),
    )
    data_v = json.loads(res_verified)
    assert data_v["verification"]["verification_state"] == "verified"
    assert finding["verification_state"] == "verified"


# ---------------------------------------------------------------------------
# 4. State Isolation Between Concurrent Runs
# ---------------------------------------------------------------------------


def test_concurrent_autonomous_runs_state_isolation(tmp_path: Path):
    """Test that two scans in the same process maintain distinct state without leakage."""
    run_a = "scan-alpha"
    run_b = "scan-beta"
    dir_a = tmp_path / "alpha"
    dir_b = tmp_path / "beta"
    dir_a.mkdir()
    dir_b.mkdir()

    state_a = ReportState(run_a)
    state_a._run_dir = dir_a
    gap_a = GapRun(run_a, dir_a, threshold=2)
    state_a.gap_run = gap_a

    state_b = ReportState(run_b)
    state_b._run_dir = dir_b
    gap_b = GapRun(run_b, dir_b, threshold=3)
    state_b.gap_run = gap_b

    set_global_report_state(state_a)
    set_global_gap_run(gap_a)

    # Attach candidates to Alpha
    gap_a.attach_candidate("c-alpha-1", "Alpha Candidate", "/alpha", "general")

    set_global_report_state(state_b)
    set_global_gap_run(gap_b)

    # Attach candidates to Beta
    gap_b.attach_candidate("c-beta-1", "Beta Candidate", "/beta", "general")
    gap_b.attach_candidate("c-beta-2", "Beta Candidate 2", "/beta/2", "general")

    # Verify per-run lookup
    assert get_report_state_for_run(run_a).run_id == run_a
    assert get_report_state_for_run(run_b).run_id == run_b
    assert get_gap_run_for_run(run_a).run_id == run_a
    assert get_gap_run_for_run(run_b).run_id == run_b

    # Verify candidates are not leaked between runs
    assert "c-alpha-1" in gap_a.candidates
    assert "c-alpha-1" not in gap_b.candidates
    assert "c-beta-1" in gap_b.candidates
    assert "c-beta-1" not in gap_a.candidates

    assert gap_a.summary["candidates_dispatched"] == 1
    assert gap_b.summary["candidates_dispatched"] == 2


# ---------------------------------------------------------------------------
# 5. Resume Preserves Completed Candidate States
# ---------------------------------------------------------------------------


def test_resume_preserves_completed_candidate_states(tmp_path: Path):
    """Test that reloading GapRun preserves completed candidate states without resetting to PENDING."""
    scan_id = "test-resume-preservation"
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    # Initial session
    gap1 = GapRun(scan_id, state_dir, threshold=2)
    gap1.attach_candidate("c1", "Candidate 1", "/p1", "xss")
    gap1.attach_candidate("c2", "Candidate 2", "/p2", "sqli")

    gap1.record_probe_outcome("c1", outcome="positive", detail="Verified XSS")
    gap1.record_validity("c1", evidence="alert(1)", confirmed=True)
    gap1.save()

    # Resume session (loads from state_dir / gap_state.json)
    gap2 = GapRun.load(scan_id, state_dir)
    assert gap2.candidates["c1"].status == "validated"
    assert gap2.candidates["c1"].investigation_outcome == "validated"
    assert gap2.candidates["c2"].status == "discovered"

    # Initializing DecisionEngine must not reset c1 back to ATTEMPTING
    engine = gap2.sync_decision_engine()
    assert engine.candidates["c1"].state == CandidateState.VALIDATED
    assert engine.candidates["c2"].state == CandidateState.PENDING

    # Next candidate selected is c2, NOT c1!
    next_c = engine.get_next_available_candidate()
    assert next_c is not None
    assert next_c.id == "c2"


# ---------------------------------------------------------------------------
# 6. Core Runner Candidate Queue & State Binding End-to-End
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_strix_scan_initializes_gap_queue_and_context(tmp_path: Path):
    """Test that run_strix_scan binds run-scoped GapRun, DecisionEngine, and candidate queue."""
    from strix.core.runner import run_strix_scan

    scan_id = f"test-runner-gap-bind-{uuid.uuid4().hex[:8]}"
    scan_cfg = {
        "targets": [
            {
                "type": "web_application",
                "details": {"target_url": "http://localhost:8080"},
                "original": "http://localhost:8080",
            }
        ],
        "candidates": [
            {
                "id": "c1-login-sqli",
                "name": "SQL Injection in /login",
                "endpoint": "/login",
                "category": "sqli",
                "score": 0.95,
                "rank": 1,
            },
            {
                "id": "c2-profile-xss",
                "name": "Stored XSS in /profile",
                "endpoint": "/profile",
                "category": "xss",
                "score": 0.85,
                "rank": 2,
            },
        ],
        "scan_mode": "quick",
    }

    # Mock sandbox session and LLM agent loop
    mock_bundle = {
        "session": MagicMock(),
        "client": MagicMock(),
        "caido_client": MagicMock(),
    }

    with (
        patch("strix.core.runner.run_dir_for", side_effect=lambda s: tmp_path / s),
        patch("strix.runtime.session_manager.create_or_reuse", AsyncMock(return_value=mock_bundle)),
        patch("strix.runtime.session_manager.cleanup", AsyncMock()),
        patch(
            "strix.core.runner.run_agent_loop",
            AsyncMock(return_value=MagicMock(final_output="Done")),
        ),
        patch("strix.core.runner.open_agent_session", MagicMock()),
        patch("strix.core.runner.setup_scan_logging", MagicMock(return_value=lambda: None)),
        patch("strix.core.runner.load_settings") as mock_settings,
    ):
        settings_obj = MagicMock()
        settings_obj.llm.model = "openrouter/auto"
        settings_obj.llm.api_key = "sk-test-key"
        settings_obj.llm.api_base = None
        settings_obj.llm.force_required_tool_choice = False
        settings_obj.llm.parallel_tool_calls = False
        settings_obj.llm.timeout = 60
        settings_obj.llm.prompt_cache = True
        settings_obj.llm.extra_headers = {}
        settings_obj.llm.extra_body = {}
        settings_obj.llm.reasoning_effort = None
        settings_obj.runtime.max_context_images = 5
        mock_settings.return_value = settings_obj

        # Execute run_strix_scan
        result = await run_strix_scan(
            scan_config=scan_cfg,
            scan_id=scan_id,
            image="strix-sandbox:latest",
            cleanup_on_exit=False,
        )

        # Verify that GapRun was initialized and bound to ReportState
        rep_state = get_report_state_for_run(scan_id)
        assert rep_state is not None
        assert rep_state.gap_run is not None
        assert len(rep_state.gap_run.candidates) == 2
        assert "c1-login-sqli" in rep_state.gap_run.candidates
        assert "c2-profile-xss" in rep_state.gap_run.candidates

        # Candidate invariant holds
        acct = rep_state.run_record.get("candidate_accounting")
        assert acct is not None
        assert acct["dispatched"] == 2
        assert acct["dispatched"] == (acct["investigated"] + acct["not_tested"] + acct["blocked"])
