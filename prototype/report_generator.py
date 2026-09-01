"""Report generator for the prototype.

Generates:
  1. Human-readable text report
  2. JSON report

Both contain:
  - scenario
  - execution mode
  - max_attempts
  - final status
  - candidates
  - execution results
  - decision trace
  - total attempts
  - pivot count
  - generated timestamp

Both clearly include:
  - SIMULATION MODE
  - "Outcomes are resolved from supplied demo ground truth."

Simulated outcomes are NOT described as real vulnerabilities.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from decision_engine.core.schemas import ActionCandidate, EngineStatus

from .trace_formatter import (
    format_engine_trace,
    format_candidate_ranking,
    format_execution_results,
)


def _candidate_to_dict(c) -> dict:
    """Convert a candidate to a JSON-safe dict."""
    if isinstance(c, dict):
        return c
    return {
        "id": getattr(c, "id", "?"),
        "probability": getattr(c, "probability", 0.0),
        "quality_rank": c.quality_rank.value if getattr(c, "quality_rank", None) else None,
        "assessed": getattr(c, "assessed", False),
        "attempted": getattr(c, "attempted", False),
        "execution_outcome": c.execution_outcome.value if getattr(c, "execution_outcome", None) else None,
        "ground_truth": c.ground_truth.value if getattr(c, "ground_truth", None) else None,
    }


def _build_report_dict(
    scenario_name: str,
    state: dict,
    max_attempts: int,
    mode: str,
) -> dict:
    """Build a JSON-safe report dict from engine state."""
    presentation = state.get("_presentation", {})
    candidates = [_candidate_to_dict(c) for c in state.get("candidates", [])]

    return {
        "scenario": scenario_name,
        "execution_mode": mode,
        "max_attempts": max_attempts,
        "final_status": state.get("status", "UNKNOWN"),
        "candidates": candidates,
        "execution_results": state.get("results", []),
        "decision_trace": state.get("logs", []),
        "total_attempts": presentation.get("total_attempts", 0),
        "pivot_count": presentation.get("pivot_count", 0),
        "candidates_processed": presentation.get("candidates_processed", []),
        "generated_timestamp": datetime.now(timezone.utc).isoformat(),
        "safety_notice": (
            "SIMULATION MODE — Outcomes are resolved from supplied demo ground truth. "
            "No real vulnerabilities were validated."
        ),
    }


def generate_json_report(
    scenario_name: str,
    state: dict,
    max_attempts: int = 2,
    mode: str = "simulation",
) -> str:
    """Generate a JSON report from the engine's final state.

    Returns:
        JSON string with all run metadata
    """
    report = _build_report_dict(scenario_name, state, max_attempts, mode)
    return json.dumps(report, indent=2, default=str)


def generate_text_report(
    scenario_name: str,
    state: dict,
    max_attempts: int = 2,
    mode: str = "simulation",
) -> str:
    """Generate a human-readable text report from the engine's final state.

    Returns:
        Multi-line text report
    """
    report = _build_report_dict(scenario_name, state, max_attempts, mode)

    lines = []
    lines.append("=" * 64)
    lines.append("AI VAPT DECISION ENGINE — MENTOR PROTOTYPE — RUN REPORT")
    lines.append("=" * 64)
    lines.append(f"Scenario:        {report['scenario']}")
    lines.append(f"Execution Mode:  {report['execution_mode'].upper()}")
    lines.append(f"Max Attempts:    {report['max_attempts']}")
    lines.append(f"Final Status:    {report['final_status']}")
    lines.append(f"Generated:       {report['generated_timestamp']}")
    lines.append("")
    lines.append("-" * 64)
    lines.append("CANDIDATE RANKING")
    lines.append("-" * 64)
    lines.append(format_candidate_ranking(state))
    lines.append("")
    lines.append("-" * 64)
    lines.append("ENGINE EXECUTION")
    lines.append("-" * 64)
    lines.append(format_execution_results(state))
    lines.append("")
    lines.append("-" * 64)
    lines.append("DECISION TRACE")
    lines.append("-" * 64)
    lines.append(format_engine_trace(state))
    lines.append("")
    lines.append("-" * 64)
    lines.append("FINAL RESULT")
    lines.append("-" * 64)
    lines.append(f"Status:               {report['final_status']}")
    lines.append(f"Total Attempts:       {report['total_attempts']}")
    lines.append(f"Pivot Count:          {report['pivot_count']}")
    lines.append(f"Candidates Processed: {len(report['candidates_processed'])}")
    lines.append(f"  IDs: {', '.join(report['candidates_processed']) if report['candidates_processed'] else '(none)'}")
    lines.append("")
    lines.append("=" * 64)
    lines.append("SAFETY")
    lines.append("=" * 64)
    lines.append("SIMULATION MODE")
    lines.append("Outcomes are resolved from supplied demo ground truth.")
    lines.append("No external targets contacted. No real vulnerabilities validated.")
    lines.append("=" * 64)

    return "\n".join(lines)


def save_json_report(
    scenario_name: str,
    state: dict,
    output_path: str,
    max_attempts: int = 2,
    mode: str = "simulation",
) -> str:
    """Save a JSON report to a file.

    Returns:
        The path the report was written to.
    """
    json_str = generate_json_report(scenario_name, state, max_attempts, mode)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json_str)
    return output_path


def save_text_report(
    scenario_name: str,
    state: dict,
    output_path: str,
    max_attempts: int = 2,
    mode: str = "simulation",
) -> str:
    """Save a text report to a file.

    Returns:
        The path the report was written to.
    """
    text = generate_text_report(scenario_name, state, max_attempts, mode)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    return output_path