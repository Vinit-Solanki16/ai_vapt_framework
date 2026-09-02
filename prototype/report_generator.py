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
  - evidence tier (SIMULATED / OBSERVED / CONTROLLED VALIDATION)
  - per-candidate attempt counts
  - pivot events
  - generated timestamp

Both clearly include:
  - SIMULATION MODE
  - "Outcomes are resolved from supplied demo ground truth."
  - No real vulnerabilities validated.

Simulated outcomes are NOT described as real vulnerabilities.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Any

from decision_engine.core.schemas import ActionCandidate, EngineStatus, Outcome

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


def _get_evidence_tier(mode: str) -> str:
    """Map execution mode to evidence tier for reporting.

    Args:
        mode: Execution mode (simulation, lab, real)

    Returns:
        Evidence tier string for reporting
    """
    mode_map = {
        "simulation": "SIMULATED",
        "lab": "OBSERVED",
        "real": "CONTROLLED VALIDATION"
    }
    return mode_map.get(mode.lower(), "UNKNOWN")


def _count_attempts_per_candidate(results: List[dict]) -> Dict[str, int]:
    """Count execution attempts per candidate from results.

    Args:
        results: List of execution result dicts from engine state

    Returns:
        Dict mapping candidate_id to attempt count
    """
    counts = {}
    for result in results:
        cid = result.get("candidate_id", "unknown")
        counts[cid] = counts.get(cid, 0) + 1
    return counts


def _extract_pivot_events(logs: List[str]) -> List[dict]:
    """Extract pivot events from engine logs.

    Args:
        logs: List of engine log strings

    Returns:
        List of pivot event dicts with type and details
    """
    pivot_events = []
    for log in logs:
        if "[Pivot]" in log:
            event_type = "UNKNOWN"
            details = log.strip()

            if "Abandoning" in log:
                event_type = "ABANDON"
            elif "Redirected" in log:
                event_type = "REDIRECT"
            elif "All candidates processed" in log:
                event_type = "COMPLETE"

            pivot_events.append({
                "type": event_type,
                "details": details
            })
    return pivot_events


def _build_report_dict(
    scenario_name: str,
    state: dict,
    max_attempts: int,
    mode: str,
) -> dict:
    """Build a JSON-safe report dict from engine state."""
    presentation = state.get("_presentation", {})
    candidates = [_candidate_to_dict(c) for c in state.get("candidates", [])]

    # Evidence tier
    evidence_tier = _get_evidence_tier(state.get("mode", mode))

    # Per-candidate attempt counts
    results = state.get("results", [])
    attempts_per_candidate = _count_attempts_per_candidate(results)

    # Pivot events
    pivot_events = _extract_pivot_events(state.get("logs", []))

    report = {
        "scenario": scenario_name,
        "execution_mode": mode,
        "max_attempts": max_attempts,
        "final_status": state.get("status", "UNKNOWN"),
        "candidates": candidates,
        "execution_results": results,
        "decision_trace": state.get("logs", []),
        "total_attempts": presentation.get("total_attempts", 0),
        "pivot_count": presentation.get("pivot_count", 0),
        "candidates_processed": presentation.get("candidates_processed", []),
        "evidence_tier": evidence_tier,
        "evidence_tier_label": f"Evidence: {evidence_tier}",
        "attempts_per_candidate": attempts_per_candidate,
        "pivot_events": pivot_events,
        "generated_timestamp": datetime.now(timezone.utc).isoformat(),
        "safety_notice": (
            "SIMULATION MODE — Outcomes are resolved from supplied demo ground truth. "
            "No real vulnerabilities were validated."
        ) if mode.lower() == "simulation" else (
            "OBSERVED MODE — Outcomes are from real emulator responses. "
            "No external systems were targeted."
        ) if mode.lower() == "lab" else (
            "REAL MODE — Outcomes are from live systems. "
            "Ensure proper authorization before execution."
        ),
    }

    return report


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
    lines.append("=" * 70)
    lines.append("AI VAPT DECISION ENGINE — MENTOR PROTOTYPE — RUN REPORT")
    lines.append("=" * 70)
    lines.append(f"Scenario:        {report['scenario']}")
    lines.append(f"Execution Mode:  {report['execution_mode'].upper()}")
    lines.append(f"Evidence Tier:   {report['evidence_tier']}")
    lines.append(f"Max Attempts:    {report['max_attempts']}")
    lines.append(f"Final Status:    {report['final_status']}")
    lines.append(f"Generated:       {report['generated_timestamp']}")
    lines.append("")
    lines.append("-" * 70)
    lines.append("EVIDENCE TIER")
    lines.append("-" * 70)
    lines.append(f"Classification:  {report['evidence_tier']}")
    lines.append(f"Description:     {_get_evidence_tier_description(report['execution_mode'])}")
    lines.append("")
    lines.append("-" * 70)
    lines.append("PER-CANDIDATE ATTEMPTS")
    lines.append("-" * 70)
    if report["attempts_per_candidate"]:
        for cid, count in sorted(report["attempts_per_candidate"].items()):
            lines.append(f"  {cid:<25}  Attempts: {count}")
    else:
        lines.append("  (no execution attempts recorded)")
    lines.append("")
    lines.append("-" * 70)
    lines.append("PIVOT EVENTS")
    lines.append("-" * 70)
    if report["pivot_events"]:
        for event in report["pivot_events"]:
            lines.append(f"  [{event['type']}] {event['details']}")
    else:
        lines.append("  (no pivot events recorded)")
    lines.append("")
    lines.append("-" * 70)
    lines.append("CANDIDATE RANKING")
    lines.append("-" * 70)
    lines.append(format_candidate_ranking(state))
    lines.append("")
    lines.append("-" * 70)
    lines.append("ENGINE EXECUTION")
    lines.append("-" * 70)
    lines.append(format_execution_results(state))
    lines.append("")
    lines.append("-" * 70)
    lines.append("DECISION TRACE")
    lines.append("-" * 70)
    lines.append(format_engine_trace(state))
    lines.append("")
    lines.append("-" * 70)
    lines.append("FINAL RESULT")
    lines.append("-" * 70)
    lines.append(f"Status:               {report['final_status']}")
    lines.append(f"Total Attempts:       {report['total_attempts']}")
    lines.append(f"Pivot Count:          {report['pivot_count']}")
    lines.append(f"Candidates Processed: {len(report['candidates_processed'])}")
    lines.append(f"  IDs: {', '.join(report['candidates_processed']) if report['candidates_processed'] else '(none)'}")
    lines.append("")
    lines.append("=" * 70)
    lines.append("SAFETY NOTICE")
    lines.append("=" * 70)
    lines.append(report["safety_notice"])
    lines.append("=" * 70)

    return "\n".join(lines)


def _get_evidence_tier_description(mode: str) -> str:
    """Get human-readable description of evidence tier.

    Args:
        mode: Execution mode

    Returns:
        Description string
    """
    descriptions = {
        "simulation": "Outcomes resolved from supplied demo ground truth (labels)",
        "lab": "Outcomes observed from real Docker vulnerability emulator responses",
        "real": "Outcomes from live target systems (requires authorization)"
    }
    return descriptions.get(mode.lower(), "Unknown evidence tier")


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