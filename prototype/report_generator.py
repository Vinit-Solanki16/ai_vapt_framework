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
        mode: Execution mode (simulation, lab, real, lab_loopback, lab_docker)

    Returns:
        Evidence tier string for reporting
    """
    mode_map = {
        "simulation": "SIMULATED",
        "lab_loopback": "OBSERVED_LOCAL",
        "lab_docker": "DOCKER_OBSERVED",
        "lab": "DOCKER_OBSERVED",
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
            "LOOPBACK OBSERVED MODE — Outcomes are from loopback (127.0.0.1) target. "
            "No external systems were targeted."
        ) if mode.lower() == "lab_loopback" else (
            "DOCKER OBSERVED MODE — Outcomes are from Docker-isolated emulator responses. "
            "No external systems were targeted."
        ) if mode.lower() in ("lab", "lab_docker") else (
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
        "lab_loopback": "Outcomes observed from loopback (127.0.0.1) target",
        "lab_docker": "Outcomes observed from Docker-isolated vulnerability emulator",
        "lab": "Outcomes observed from Docker-isolated vulnerability emulator",
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


def generate_html_report(
    scenario_name: str,
    state: dict,
    max_attempts: int = 2,
    mode: str = "simulation",
) -> str:
    """Generate an HTML report from the engine's final state.

    Returns:
        HTML string with styled report
    """
    report = _build_report_dict(scenario_name, state, max_attempts, mode)

    evidence_tier = report["evidence_tier"]
    evidence_color = _get_evidence_tier_color(evidence_tier)
    evidence_emoji = _get_evidence_tier_emoji(evidence_tier)

    # Build candidates table rows
    candidates_rows = ""
    for c in report["candidates"]:
        candidates_rows += f"""
        <tr>
            <td>{c.get("id", "?")}</td>
            <td>{c.get("probability", 0.0):.4f}</td>
            <td>{c.get("quality_rank", "PENDING") or "PENDING"}</td>
            <td>{"Yes" if c.get("assessed") else "No"}</td>
            <td>{"Yes" if c.get("attempted") else "No"}</td>
            <td>{c.get("execution_outcome", "-") or "-"}</td>
            <td>{c.get("ground_truth", "-") or "-"}</td>
        </tr>"""

    # Build attempts per candidate rows
    attempts_rows = ""
    for cid, count in sorted(report["attempts_per_candidate"].items()):
        attempts_rows += f"""
        <tr>
            <td>{cid}</td>
            <td>{count}</td>
        </tr>"""
    if not report["attempts_per_candidate"]:
        attempts_rows = '<tr><td colspan="2">(no execution attempts recorded)</td></tr>'

    # Build pivot events rows
    pivot_rows = ""
    for event in report["pivot_events"]:
        pivot_rows += f"""
        <tr>
            <td><span class="badge badge-pivot">{event["type"]}</span></td>
            <td>{event["details"]}</td>
        </tr>"""
    if not report["pivot_events"]:
        pivot_rows = '<tr><td colspan="2">(no pivot events recorded)</td></tr>'

    # Build decision trace
    decision_trace = "\n".join(
        f"        <li><code>{line}</code></li>" for line in report["decision_trace"]
    )

    # Build execution results
    exec_results = ""
    for r in report["execution_results"]:
        exec_results += f"""
        <tr>
            <td>{r.get("candidate_id", "?")}</td>
            <td>{r.get("outcome", "?")}</td>
            <td>{r.get("detail", "")}</td>
        </tr>"""
    if not report["execution_results"]:
        exec_results = '<tr><td colspan="3">(no execution results recorded)</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI VAPT Report — {report["scenario"]}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f7fa;
            padding: 2rem;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
            background: #fff;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
            color: #fff;
            padding: 2rem;
            text-align: center;
        }}
        .header h1 {{
            font-size: 1.8rem;
            margin-bottom: 0.5rem;
        }}
        .header .subtitle {{
            opacity: 0.9;
            font-size: 0.95rem;
        }}
        .content {{
            padding: 2rem;
        }}
        .section {{
            margin-bottom: 2rem;
        }}
        .section h2 {{
            font-size: 1.3rem;
            color: #1a237e;
            border-bottom: 2px solid #e8eaf6;
            padding-bottom: 0.5rem;
            margin-bottom: 1rem;
        }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-size: 0.85rem;
            font-weight: 600;
            color: #fff;
        }}
        .badge-tier {{
            background: {evidence_color};
        }}
        .badge-pivot {{
            background: #ff6f00;
        }}
        .badge-success {{
            background: #2e7d32;
        }}
        .badge-fail {{
            background: #c62828;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 0.5rem;
            font-size: 0.9rem;
        }}
        th, td {{
            text-align: left;
            padding: 0.6rem 0.8rem;
            border-bottom: 1px solid #e0e0e0;
        }}
        th {{
            background: #f5f5f5;
            font-weight: 600;
        }}
        tr:hover {{
            background: #fafafa;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
        }}
        .meta-item {{
            background: #f8f9fa;
            padding: 0.75rem 1rem;
            border-radius: 4px;
            border-left: 3px solid #1a237e;
        }}
        .meta-item .label {{
            font-size: 0.8rem;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .meta-item .value {{
            font-size: 1rem;
            font-weight: 600;
            color: #1a237e;
        }}
        .decision-trace {{
            background: #263238;
            color: #e0e0e0;
            border-radius: 4px;
            padding: 1rem;
            max-height: 400px;
            overflow-y: auto;
        }}
        .decision-trace li {{
            list-style: none;
            padding: 0.2rem 0;
            font-family: "Fira Code", "Courier New", monospace;
            font-size: 0.85rem;
        }}
        .safety-notice {{
            background: #fff3e0;
            border-left: 4px solid #ff9800;
            padding: 1rem 1.5rem;
            border-radius: 0 4px 4px 0;
            margin-top: 2rem;
        }}
        .safety-notice h2 {{
            color: #e65100;
            border-bottom-color: #ffe0b2;
        }}
        .safety-notice p {{
            color: #bf360c;
        }}
        .evidence-description {{
            margin-top: 0.5rem;
            font-size: 0.95rem;
            color: #555;
        }}
        @media (max-width: 768px) {{
            body {{
                padding: 0.5rem;
            }}
            .content {{
                padding: 1rem;
            }}
            .header h1 {{
                font-size: 1.4rem;
            }}
            table {{
                font-size: 0.8rem;
            }}
            th, td {{
                padding: 0.4rem 0.5rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>AI VAPT Decision Engine — Run Report</h1>
            <div class="subtitle">Mentor Prototype — Evidence-Based Vulnerability Assessment</div>
        </div>
        <div class="content">
            <!-- Metadata Section -->
            <div class="section">
                <h2>Run Metadata</h2>
                <div class="meta-grid">
                    <div class="meta-item">
                        <div class="label">Scenario</div>
                        <div class="value">{report["scenario"]}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Execution Mode</div>
                        <div class="value">{report["execution_mode"].upper()}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Evidence Tier</div>
                        <div class="value"><span class="badge badge-tier">{evidence_tier}</span></div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Max Attempts</div>
                        <div class="value">{report["max_attempts"]}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Final Status</div>
                        <div class="value">{report["final_status"]}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Generated</div>
                        <div class="value">{report["generated_timestamp"]}</div>
                    </div>
                </div>
            </div>

            <!-- Evidence Tier Section -->
            <div class="section">
                <h2>Evidence Tier <span class="badge badge-tier">{evidence_emoji} {evidence_tier}</span></h2>
                <p class="evidence-description">{_get_evidence_tier_description(report["execution_mode"])}</p>
            </div>

            <!-- Per-Candidate Attempts Section -->
            <div class="section">
                <h2>Per-Candidate Attempts</h2>
                <table>
                    <thead>
                        <tr><th>Candidate ID</th><th>Attempts</th></tr>
                    </thead>
                    <tbody>
{attempts_rows}
                    </tbody>
                </table>
            </div>

            <!-- Pivot Events Section -->
            <div class="section">
                <h2>Pivot Events</h2>
                <table>
                    <thead>
                        <tr><th>Type</th><th>Details</th></tr>
                    </thead>
                    <tbody>
{pivot_rows}
                    </tbody>
                </table>
            </div>

            <!-- Candidate Ranking Section -->
            <div class="section">
                <h2>Candidate Ranking</h2>
                <table>
                    <thead>
                        <tr><th>ID</th><th>Probability</th><th>Quality Rank</th><th>Assessed</th><th>Attempted</th><th>Outcome</th><th>Ground Truth</th></tr>
                    </thead>
                    <tbody>
{candidates_rows}
                    </tbody>
                </table>
            </div>

            <!-- Engine Execution Section -->
            <div class="section">
                <h2>Engine Execution</h2>
                <table>
                    <thead>
                        <tr><th>Candidate ID</th><th>Outcome</th><th>Detail</th></tr>
                    </thead>
                    <tbody>
{exec_results}
                    </tbody>
                </table>
            </div>

            <!-- Decision Trace Section -->
            <div class="section">
                <h2>Decision Trace</h2>
                <div class="decision-trace">
                    <ul>
{decision_trace}
                    </ul>
                </div>
            </div>

            <!-- Final Result Section -->
            <div class="section">
                <h2>Final Result</h2>
                <div class="meta-grid">
                    <div class="meta-item">
                        <div class="label">Status</div>
                        <div class="value">{report["final_status"]}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Total Attempts</div>
                        <div class="value">{report["total_attempts"]}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Pivot Count</div>
                        <div class="value">{report["pivot_count"]}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Candidates Processed</div>
                        <div class="value">{len(report["candidates_processed"])}</div>
                    </div>
                </div>
                <p style="margin-top: 0.5rem; font-size: 0.9rem; color: #666;">
                    IDs: {", ".join(report["candidates_processed"]) if report["candidates_processed"] else "(none)"}
                </p>
            </div>

            <!-- Safety Notice Section -->
            <div class="safety-notice">
                <h2>Safety Notice</h2>
                <p>{report["safety_notice"]}</p>
            </div>
        </div>
    </div>
</body>
</html>"""

    return html


def generate_markdown_report(
    scenario_name: str,
    state: dict,
    max_attempts: int = 2,
    mode: str = "simulation",
) -> str:
    """Generate a Markdown report from the engine's final state.

    Returns:
        Markdown string with formatted report
    """
    report = _build_report_dict(scenario_name, state, max_attempts, mode)

    evidence_tier = report["evidence_tier"]
    evidence_emoji = _get_evidence_tier_emoji(evidence_tier)

    lines = []
    lines.append(f"# AI VAPT Decision Engine — Run Report")
    lines.append(f"")
    lines.append(f"## Run Metadata")
    lines.append(f"")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Scenario | {report['scenario']} |")
    lines.append(f"| Execution Mode | {report['execution_mode'].upper()} |")
    lines.append(f"| Evidence Tier | {evidence_emoji} **{evidence_tier}** |")
    lines.append(f"| Max Attempts | {report['max_attempts']} |")
    lines.append(f"| Final Status | {report['final_status']} |")
    lines.append(f"| Generated | {report['generated_timestamp']} |")
    lines.append(f"")
    lines.append(f"## Evidence Tier: {evidence_emoji} {evidence_tier}")
    lines.append(f"")
    lines.append(f"> {_get_evidence_tier_description(report['execution_mode'])}")
    lines.append(f"")
    lines.append(f"## Per-Candidate Attempts")
    lines.append(f"")
    if report["attempts_per_candidate"]:
        lines.append(f"| Candidate ID | Attempts |")
        lines.append(f"|--------------|----------|")
        for cid, count in sorted(report["attempts_per_candidate"].items()):
            lines.append(f"| {cid} | {count} |")
    else:
        lines.append(f"_No execution attempts recorded._")
    lines.append(f"")
    lines.append(f"## Pivot Events")
    lines.append(f"")
    if report["pivot_events"]:
        lines.append(f"| Type | Details |")
        lines.append(f"|------|---------|")
        for event in report["pivot_events"]:
            lines.append(f"| `{event['type']}` | {event['details']} |")
    else:
        lines.append(f"_No pivot events recorded._")
    lines.append(f"")
    lines.append(f"## Candidate Ranking")
    lines.append(f"")
    if report["candidates"]:
        lines.append(f"| ID | Probability | Quality Rank | Assessed | Attempted | Outcome | Ground Truth |")
        lines.append(f"|----|-------------|--------------|----------|-----------|---------|--------------|")
        for c in report["candidates"]:
            cid = c.get("id", "?")
            prob = c.get("probability", 0.0)
            qr = c.get("quality_rank", "PENDING") or "PENDING"
            assessed = "Yes" if c.get("assessed") else "No"
            attempted = "Yes" if c.get("attempted") else "No"
            outcome = c.get("execution_outcome", "-") or "-"
            gt = c.get("ground_truth", "-") or "-"
            lines.append(f"| {cid} | {prob:.4f} | {qr} | {assessed} | {attempted} | {outcome} | {gt} |")
    else:
        lines.append(f"_No candidates._")
    lines.append(f"")
    lines.append(f"## Engine Execution")
    lines.append(f"")
    if report["execution_results"]:
        lines.append(f"| Candidate ID | Outcome | Detail |")
        lines.append(f"|--------------|---------|--------|")
        for r in report["execution_results"]:
            cid = r.get("candidate_id", "?")
            outcome = r.get("outcome", "?")
            detail = r.get("detail", "")
            lines.append(f"| {cid} | {outcome} | {detail} |")
    else:
        lines.append(f"_No execution results recorded._")
    lines.append(f"")
    lines.append(f"## Decision Trace")
    lines.append(f"")
    lines.append(f"```")
    for line in report["decision_trace"]:
        lines.append(line)
    lines.append(f"```")
    lines.append(f"")
    lines.append(f"## Final Result")
    lines.append(f"")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Status | {report['final_status']} |")
    lines.append(f"| Total Attempts | {report['total_attempts']} |")
    lines.append(f"| Pivot Count | {report['pivot_count']} |")
    lines.append(f"| Candidates Processed | {len(report['candidates_processed'])} |")
    lines.append(f"")
    ids_str = ", ".join(report["candidates_processed"]) if report["candidates_processed"] else "(none)"
    lines.append(f"**Candidate IDs:** {ids_str}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## Safety Notice")
    lines.append(f"")
    lines.append(f"> ⚠️ **{evidence_emoji} {report['safety_notice']}**")
    lines.append(f"")

    return "\n".join(lines)


def save_html_report(
    scenario_name: str,
    state: dict,
    output_path: str,
    max_attempts: int = 2,
    mode: str = "simulation",
) -> str:
    """Save an HTML report to a file.

    Returns:
        The path the report was written to.
    """
    html = generate_html_report(scenario_name, state, max_attempts, mode)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def save_markdown_report(
    scenario_name: str,
    state: dict,
    output_path: str,
    max_attempts: int = 2,
    mode: str = "simulation",
) -> str:
    """Save a Markdown report to a file.

    Returns:
        The path the report was written to.
    """
    md = generate_markdown_report(scenario_name, state, max_attempts, mode)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    return output_path


def _get_evidence_tier_color(tier: str) -> str:
    """Get CSS color for evidence tier badge.

    Args:
        tier: Evidence tier string

    Returns:
        CSS color hex string
    """
    color_map = {
        "SIMULATED": "#ff9800",
        "OBSERVED_LOCAL": "#2196f3",
        "DOCKER_OBSERVED": "#00bcd4",
        "CONTROLLED VALIDATION": "#4caf50",
        "UNKNOWN": "#9e9e9e",
    }
    return color_map.get(tier, "#9e9e9e")


def _get_evidence_tier_emoji(tier: str) -> str:
    """Get emoji indicator for evidence tier.

    Args:
        tier: Evidence tier string

    Returns:
        Emoji string
    """
    emoji_map = {
        "SIMULATED": "🧪",
        "OBSERVED_LOCAL": "👁️",
        "DOCKER_OBSERVED": "🐳",
        "CONTROLLED VALIDATION": "✅",
        "UNKNOWN": "❓",
    }
    return emoji_map.get(tier, "❓")