"""Regression tests for defects found by the independent release audit.

Each test reproduces a defect verified from code or raw run artifacts. The
fixes are intentionally minimal: no new features and no weakening of existing
timeout/verification guarantees.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from strix.core.gap_run import GapRun
from strix.interface import api


def _gap(tmp_path: Path) -> GapRun:
    state_dir = tmp_path / ".state"
    state_dir.mkdir(exist_ok=True)
    run = GapRun("release-audit", state_dir, threshold=2)
    run.attach_candidate(
        "c1", "Candidate 1", "/one", "general", rank=1, target="http://127.0.0.1:3000/"
    )
    run.attach_candidate(
        "c2", "Candidate 2", "/two", "general", rank=2, target="http://127.0.0.1:3000/"
    )
    return run


def test_runtime_env_is_not_persisted_for_engine_subprocess(monkeypatch, tmp_path: Path) -> None:
    """Web Console engine runs must not write per-request keys/base to the profile."""
    from strix.config import loader

    target = tmp_path / "cli-config.json"
    original_override, original_cached = loader._override, loader._cached
    monkeypatch.setattr(loader, "_override", target)
    monkeypatch.setattr(loader, "_cached", None)
    monkeypatch.setenv("STRIX_NO_PERSIST_CONFIG", "1")
    monkeypatch.setenv("LLM_API_KEY", "runtime-only-key")
    monkeypatch.setenv("LLM_API_BASE", "https://runtime-only.invalid/v1")
    try:
        loader.persist_current()
        assert not target.exists(), "runtime-only credentials were written to disk"
    finally:
        loader._override, loader._cached = original_override, original_cached


def test_stall_is_detected_after_three_productive_tools() -> None:
    """A late-stage model-only hang must not be immune to stall detection."""
    assert api.should_stop_for_stall(elapsed_seconds=700, last_progress_seconds=700) is True
    assert api.should_stop_for_stall(elapsed_seconds=700, last_progress_seconds=10) is False
    # The legacy helper is unchanged: existing false-stall regressions still hold.
    assert (
        api.should_stop_for_no_progress(
            elapsed_seconds=700,
            last_progress_seconds=700,
            productively_advanced_turns=3,
            max_turns=200,
        )
        is False
    )


def test_native_pivot_count_excludes_self_pivots_and_preparatory_probes(tmp_path: Path) -> None:
    """Native count must agree with the control-plane dedupe/eligibility rules."""
    run = _gap(tmp_path)
    run.record_pivot("c1", "c2", "inconclusive", detail="decision only")
    # A preparatory probe of the alternative is evidence, not execution.
    run.record_probe_outcome("c2", outcome="inconclusive", detail="prep", preparatory=True)
    assert run.pivot_count() == 0
    # A self-referential pivot-executed claim is never a genuine pivot.
    run.record_probe_outcome(
        "c2",
        outcome="inconclusive",
        detail="self claim",
        alternative_candidate="c2",
        pivot_executed=True,
        pivot_result="inconclusive",
    )
    genuine = [
        e
        for e in run.probe_outcomes
        if e.get("pivot_executed")
        and str(e.get("candidate_id")) != str(e.get("alternative_candidate"))
    ]
    assert genuine == []
    # A real non-preparatory probe of the selected alternative makes it genuine.
    run.record_probe_outcome("c2", outcome="inconclusive", detail="real execution")
    assert run.pivot_count() == 1


def test_same_call_pivot_execution_is_persisted_as_linked(tmp_path: Path) -> None:
    """A fallback pivot decision must carry execution evidence immediately."""
    run = _gap(tmp_path)
    run.record_probe_outcome(
        "c2",
        outcome="inconclusive",
        detail="executed alternative",
        alternative_candidate="c2",
        pivot_executed=True,
        pivot_result="inconclusive",
    )
    decisions = [e for e in run.decision_trace if e.get("type") == "pivot_decision"]
    assert len(decisions) == 1
    assert decisions[0].get("executed") is True
    assert decisions[0].get("execution_candidate") == "c2"
    assert decisions[0].get("executed_at")
    assert run.pivot_count() == 1


def test_coverage_only_record_is_not_pivot_execution(tmp_path: Path) -> None:
    """A coverage row alone must never be promoted to executed alternative."""
    gap_file = tmp_path / "gap_state.json"
    gap_file.write_text(
        json.dumps(
            {
                "candidates": {"c2": {"attempts": 1, "status": "investigated"}},
                "probe_outcomes": [],
                "decision_trace": [],
            }
        ),
        encoding="utf-8",
    )
    assert api.engine_executed_alternatives(gap_file) == set()


def test_preparatory_loop_is_not_cut_after_one_probe() -> None:
    """The prep loop must use its own bounded counter, not agent attempts."""
    import ast
    import inspect

    from strix.core import runner

    source = inspect.getsource(runner._investigate_gap1_candidates)
    assert "prep_attempts = 0" in source
    assert "while prep_attempts < cand.max_attempts:" in source
    assert "if cand.attempts == 0:" not in source
    tree = ast.parse(source)
    assert tree is not None


def test_control_gap_state_is_reconciled_with_engine(tmp_path: Path) -> None:
    """Both stores must agree on authoritative attempts/status after a run."""
    control = tmp_path / "control"
    control.mkdir()
    bridge_state = {
        "attempts": {"c1": 1},
        "exhausted": [],
        "completed": [],
        "probe_outcomes": [{"candidate_id": "c1", "status": "inconclusive"}],
    }
    (control / "gap_state.json").write_text(json.dumps(bridge_state), encoding="utf-8")
    engine = tmp_path / ".state"
    engine.mkdir()
    (engine / "gap_state.json").write_text(
        json.dumps(
            {
                "candidates": {
                    "c1": {"attempts": 2, "status": "abandoned"},
                    "c2": {"attempts": 1, "status": "validated"},
                }
            }
        ),
        encoding="utf-8",
    )
    assert api.reconcile_control_gap_state(control, engine / "gap_state.json") is True
    synced = json.loads((control / "gap_state.json").read_text(encoding="utf-8"))
    assert synced["attempts"] == {"c1": 2, "c2": 1}
    assert synced["exhausted"] == ["c1"]
    assert synced["completed"] == ["c2"]
    assert synced["probe_outcomes"] == bridge_state["probe_outcomes"]


def test_in_memory_stale_running_run_is_not_reported_as_running(
    monkeypatch, tmp_path: Path
) -> None:
    """A dead worker must not leave the dashboard showing an active run."""
    from fastapi.testclient import TestClient

    run_id = "run-in-memory-stale"
    stale = {
        "run_id": run_id,
        "status": "running",
        "start_time": "2026-11-17T11:53:05.170786+00:00",
        "created_at": "2026-11-17T11:53:05.170786+00:00",
        "target_url": "http://127.0.0.1:3000/",
    }
    monkeypatch.setattr(api, "_RUNS", {run_id: stale})
    monkeypatch.setattr(api, "_ACTIVE_PROCESSES", {})
    monkeypatch.setattr(api, "_CURRENT_ACTIVE_RUN_ID", None)
    monkeypatch.setattr(api, "runs_base_dir", lambda: tmp_path)
    with TestClient(api.app) as client:
        response = client.get(f"/runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "interrupted"


def test_sarif_result_preserves_verification_state() -> None:
    """SARIF must not silently drop the finding's verification state."""
    from strix.report.sarif import _result_properties

    props = _result_properties(
        {
            "id": "vuln-0001",
            "title": "SQL Injection",
            "severity": "critical",
            "cvss": 9.8,
            "cwe": "CWE-89",
            "endpoint": "/rest/user/login",
            "verification_state": "verified",
            "verified": True,
        }
    )
    strix_props = props.get("strix") or props
    assert strix_props.get("verification_state") == "verified"
    assert strix_props.get("verified") is True


def test_pdf_does_not_present_unconfirmed_as_confirmed(tmp_path: Path) -> None:
    """The PDF must not count an unconfirmed finding as a confirmed finding."""
    from strix.interface.viewer.report_pdf import generate_report_pdf

    run_dir = tmp_path / "run-unconfirmed"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": "run-unconfirmed", "status": "completed", "turns_consumed": 5}),
        encoding="utf-8",
    )
    (run_dir / "vulnerabilities.json").write_text(
        json.dumps(
            [
                {
                    "id": "vuln-0001",
                    "title": "Unconfirmed SQL Injection",
                    "severity": "high",
                    "cvss": 7.5,
                    "cwe": "CWE-89",
                    "verification_state": "unconfirmed",
                    "verified": False,
                    "description": "Narrative only",
                }
            ]
        ),
        encoding="utf-8",
    )
    pdf = generate_report_pdf(run_dir)
    assert pdf.startswith(b"%PDF")
    assert b"/Filter" in pdf  # a real rendered document, not an empty stub

    from pypdf import PdfReader

    text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "total confirmed findings" not in text.lower().replace("  ", " ")
    assert "unconfirmed" in text.lower()
