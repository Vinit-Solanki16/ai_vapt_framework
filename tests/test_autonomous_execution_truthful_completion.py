"""Regression tests for truthful autonomous-completion enforcement.

A run may only be reported as a successful assessment when the configured
model actually participated and real security tools actually executed.
Candidate transitions, decision-trace events, coverage narration and a
'completed' status are derived state, never proof of security testing.
"""

from __future__ import annotations

import ast
from pathlib import Path

from strix.interface import api


def test_execution_evidence_from_logs_counts_only_real_work() -> None:
    logs = [
        "Starting turn 1, current_agent=Root Agent",
        "Calling LLM model=openai/kaggle-model",
        "Invoking tool record_coverage",
        "Invoking tool update_coverage",
        "Invoking tool finish_scan",
        "Calling LLM model=openai/kaggle-model",
        "Invoking tool http_request",
        "Invoking tool terminal",
    ]
    evidence = api.execution_evidence_from_logs(logs)
    assert evidence == {"llm_calls": 2, "security_tool_calls": 2}


def test_execution_evidence_rejects_bookkeeping_only_run() -> None:
    evidence = api.execution_evidence_from_run(
        {"status": "completed", "candidates": [{"state": "ABANDONED"}] * 8},
        "Calling LLM once\nInvoking tool record_coverage\nInvoking tool finish_scan",
    )
    assert evidence["llm_calls"] == 1
    assert evidence["security_tool_calls"] == 0
    assert (
        api.has_genuine_assessment_execution(
            {"status": "completed"}, "Calling LLM\nInvoking tool record_coverage"
        )
        is False
    )


def test_execution_evidence_accepts_model_and_security_tools() -> None:
    evidence = api.execution_evidence_from_run(
        {"llm_requests": [{"outcome": "success"}]},
        "Calling LLM\nInvoking tool http_request",
    )
    assert evidence["has_model_participation"] is True
    assert evidence["has_security_execution"] is True
    assert api.has_genuine_assessment_execution({}, "Calling LLM\nInvoking tool terminal") is True


def test_worker_completion_gate_requires_execution_evidence() -> None:
    """The subprocess result block must reject a no-genuine-execution run."""
    source = Path(api.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    worker = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_execute_run_worker"
    )
    segment = ast.get_source_segment(source, worker) or ""
    # The decisive gate must sit in the final success branch, before any
    # "completed" assignment, so it can never turn a real failure into a pass.
    assert "if insufficient_execution:" in segment
    gate = segment.rfind("if insufficient_execution:")
    success = segment.find('run_entry["status"] = "completed"')
    assert gate != -1 and success != -1 and gate < success


def test_runner_does_not_shortcut_complete_before_model_loop() -> None:
    """Automated probes must not write a success report or skip the model."""
    source = Path(api.__file__).parent.parent.joinpath("core/runner.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    run_scan = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_strix_scan"
    )
    segment = ast.get_source_segment(source, run_scan) or ""
    assert "result = await run_agent_loop(" in segment
    # The old early completion block (before run_agent_loop) wrote a synthetic
    # "Assessment complete after GAP-1 investigation" report and returned.
    assert "Assessment complete after GAP-1 investigation" not in segment
    assert "return without entering the model-driven" not in segment
