"""Report renderers for VAPT platform.

Provides renderers for JSON, HTML, Markdown, and TXT formats.
All renderers consume the same ReportModel.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from .models import ReportModel, EvidenceTier


class ReportRenderer(ABC):
    """Abstract base class for report renderers."""

    @abstractmethod
    def render(self, report: ReportModel) -> str:
        """Render a report to string format.
        
        Args:
            report: The ReportModel to render.
            
        Returns:
            Rendered report as string.
        """
        ...


class JSONRenderer(ReportRenderer):
    """Renders reports as JSON."""

    def render(self, report: ReportModel) -> str:
        """Render report as JSON string."""
        return json.dumps(report.to_dict(), indent=2, default=str)


class HTMLRenderer(ReportRenderer):
    """Renders reports as HTML."""

    def render(self, report: ReportModel) -> str:
        """Render report as HTML string."""
        evidence_tier = report.evidence_tier
        evidence_color = self._get_evidence_color(evidence_tier)
        evidence_emoji = self._get_evidence_emoji(evidence_tier)
        
        # Build candidates table rows
        candidates_rows = ""
        for c in report.candidates:
            candidates_rows += f"""
            <tr>
                <td>{c.candidate_id}</td>
                <td>{c.probability:.4f}</td>
                <td>{c.quality_rank}</td>
                <td>{"Yes" if c.assessed else "No"}</td>
                <td>{"Yes" if c.attempted else "No"}</td>
                <td>{c.execution_outcome or "-"}</td>
                <td>{c.ground_truth or "-"}</td>
            </tr>"""
        
        if not report.candidates:
            candidates_rows = '<tr><td colspan="7">No candidates</td></tr>'
        
        # Build execution results rows
        exec_rows = ""
        for e in report.execution_results:
            exec_rows += f"""
            <tr>
                <td>{e.candidate_id}</td>
                <td>{e.outcome}</td>
                <td>{e.detail}</td>
                <td>{e.attempt_number}</td>
            </tr>"""
        
        if not report.execution_results:
            exec_rows = '<tr><td colspan="4">No execution results recorded</td></tr>'
        
        # Build pivot events rows
        pivot_rows = ""
        for p in report.pivot_events:
            pivot_rows += f"""
            <tr>
                <td><span class="badge badge-pivot">{p.event_type}</span></td>
                <td>{p.details}</td>
            </tr>"""
        
        if not report.pivot_events:
            pivot_rows = '<tr><td colspan="2">No pivot events recorded</td></tr>'
        
        # Build attempts per candidate rows
        attempts_rows = ""
        for cid, count in sorted(report.attempts_per_candidate.items()):
            attempts_rows += f"""
            <tr>
                <td>{cid}</td>
                <td>{count}</td>
            </tr>"""
        
        if not report.attempts_per_candidate:
            attempts_rows = '<tr><td colspan="2">No execution attempts recorded</td></tr>'
        
        # Build decision trace
        decision_trace = "\n".join(
            f"        <li><code>{line}</code></li>" for line in report.decision_trace
        )
        
        # Build limitations
        limitations = "\n".join(
            f"        <li>{limitation}</li>" for limitation in report.limitations
        )
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI VAPT Report — {report.metadata.scenario}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
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
        .header h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; }}
        .header .subtitle {{ opacity: 0.9; font-size: 0.95rem; }}
        .content {{ padding: 2rem; }}
        .section {{ margin-bottom: 2rem; }}
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
        .badge-tier {{ background: {evidence_color}; }}
        .badge-pivot {{ background: #ff6f00; }}
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
        th {{ background: #f5f5f5; font-weight: 600; }}
        tr:hover {{ background: #fafafa; }}
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
        .safety-notice h2 {{ color: #e65100; border-bottom-color: #ffe0b2; }}
        .safety-notice p {{ color: #bf360c; }}
        .evidence-description {{
            margin-top: 0.5rem;
            font-size: 0.95rem;
            color: #555;
        }}
        .limitations {{
            background: #f5f5f5;
            border-left: 4px solid #9e9e9e;
            padding: 1rem 1.5rem;
            border-radius: 0 4px 4px 0;
        }}
        .limitations li {{ margin-left: 1.5rem; }}
        @media (max-width: 768px) {{
            body {{ padding: 0.5rem; }}
            .content {{ padding: 1rem; }}
            .header h1 {{ font-size: 1.4rem; }}
            table {{ font-size: 0.8rem; }}
            th, td {{ padding: 0.4rem 0.5rem; }}
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
                        <div class="value">{report.metadata.scenario}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Execution Mode</div>
                        <div class="value">{report.metadata.mode.upper()}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Evidence Tier</div>
                        <div class="value"><span class="badge badge-tier">{evidence_tier}</span></div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Max Attempts</div>
                        <div class="value">{report.metadata.max_attempts}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Final Status</div>
                        <div class="value">{report.metadata.final_status}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Generated</div>
                        <div class="value">{report.metadata.generated_at}</div>
                    </div>
                </div>
            </div>

            <!-- Executive Summary -->
            <div class="section">
                <h2>Executive Summary</h2>
                <p>{report.executive_summary}</p>
            </div>

            <!-- Evidence Tier Section -->
            <div class="section">
                <h2>Evidence Tier <span class="badge badge-tier">{evidence_emoji} {evidence_tier}</span></h2>
                <p class="evidence-description">{report.evidence_description}</p>
            </div>

            <!-- Target/Scope Section -->
            <div class="section">
                <h2>Target / Scope</h2>
                <div class="meta-grid">
                    <div class="meta-item">
                        <div class="label">Target</div>
                        <div class="value">{report.target or "N/A"}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Port</div>
                        <div class="value">{report.port}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Path</div>
                        <div class="value">{report.path}</div>
                    </div>
                </div>
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
                        <tr><th>Candidate ID</th><th>Outcome</th><th>Detail</th><th>Attempt</th></tr>
                    </thead>
                    <tbody>
{exec_rows}
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
                        <div class="value">{report.metadata.final_status}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Total Attempts</div>
                        <div class="value">{report.metadata.total_attempts}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Pivot Count</div>
                        <div class="value">{report.metadata.pivot_count}</div>
                    </div>
                    <div class="meta-item">
                        <div class="label">Candidates Processed</div>
                        <div class="value">{len(report.metadata.candidates_processed)}</div>
                    </div>
                </div>
                <p style="margin-top: 0.5rem; font-size: 0.9rem; color: #666;">
                    IDs: {", ".join(report.metadata.candidates_processed) if report.metadata.candidates_processed else "(none)"}
                </p>
            </div>

            <!-- Limitations Section -->
            <div class="section">
                <h2>Limitations</h2>
                <div class="limitations">
                    <ul>
{limitations}
                    </ul>
                </div>
            </div>

            <!-- Safety Notice Section -->
            <div class="safety-notice">
                <h2>Safety Notice</h2>
                <p>{report.safety_notice}</p>
            </div>
        </div>
    </div>
</body>
</html>"""
        
        return html

    def _get_evidence_color(self, tier: str) -> str:
        """Get CSS color for evidence tier."""
        color_map = {
            EvidenceTier.SIMULATED.value: "#ff9800",
            EvidenceTier.OBSERVED_LOCAL.value: "#2196f3",
            EvidenceTier.DOCKER_OBSERVED.value: "#00bcd4",
            EvidenceTier.CONTROLLED_VALIDATION.value: "#4caf50",
            EvidenceTier.UNKNOWN.value: "#9e9e9e",
        }
        return color_map.get(tier, "#9e9e9e")

    def _get_evidence_emoji(self, tier: str) -> str:
        """Get emoji for evidence tier."""
        emoji_map = {
            EvidenceTier.SIMULATED.value: "🧪",
            EvidenceTier.OBSERVED_LOCAL.value: "👁️",
            EvidenceTier.DOCKER_OBSERVED.value: "🐳",
            EvidenceTier.CONTROLLED_VALIDATION.value: "✅",
            EvidenceTier.UNKNOWN.value: "❓",
        }
        return emoji_map.get(tier, "❓")


class MarkdownRenderer(ReportRenderer):
    """Renders reports as Markdown."""

    def render(self, report: ReportModel) -> str:
        """Render report as Markdown string."""
        evidence_tier = report.evidence_tier
        evidence_emoji = self._get_evidence_emoji(evidence_tier)
        
        lines = []
        
        # Header
        lines.append(f"# AI VAPT Decision Engine — Run Report")
        lines.append("")
        
        # Metadata
        lines.append("## Run Metadata")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| Scenario | {report.metadata.scenario} |")
        lines.append(f"| Execution Mode | {report.metadata.mode.upper()} |")
        lines.append(f"| Evidence Tier | {evidence_emoji} **{evidence_tier}** |")
        lines.append(f"| Max Attempts | {report.metadata.max_attempts} |")
        lines.append(f"| Final Status | {report.metadata.final_status} |")
        lines.append(f"| Generated | {report.metadata.generated_at} |")
        lines.append("")
        
        # Executive Summary
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(report.executive_summary)
        lines.append("")
        
        # Evidence Tier
        lines.append(f"## Evidence Tier: {evidence_emoji} {evidence_tier}")
        lines.append("")
        lines.append(f"> {report.evidence_description}")
        lines.append("")
        
        # Target/Scope
        lines.append("## Target / Scope")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| Target | {report.target or 'N/A'} |")
        lines.append(f"| Port | {report.port} |")
        lines.append(f"| Path | {report.path} |")
        lines.append("")
        
        # Per-Candidate Attempts
        lines.append("## Per-Candidate Attempts")
        lines.append("")
        if report.attempts_per_candidate:
            lines.append("| Candidate ID | Attempts |")
            lines.append("|--------------|----------|")
            for cid, count in sorted(report.attempts_per_candidate.items()):
                lines.append(f"| {cid} | {count} |")
        else:
            lines.append("_No execution attempts recorded._")
        lines.append("")
        
        # Pivot Events
        lines.append("## Pivot Events")
        lines.append("")
        if report.pivot_events:
            lines.append("| Type | Details |")
            lines.append("|------|---------|")
            for event in report.pivot_events:
                lines.append(f"| `{event.event_type}` | {event.details} |")
        else:
            lines.append("_No pivot events recorded._")
        lines.append("")
        
        # Candidate Ranking
        lines.append("## Candidate Ranking")
        lines.append("")
        if report.candidates:
            lines.append("| ID | Probability | Quality Rank | Assessed | Attempted | Outcome | Ground Truth |")
            lines.append("|----|-------------|--------------|----------|-----------|---------|--------------|")
            for c in report.candidates:
                lines.append(
                    f"| {c.candidate_id} | {c.probability:.4f} | {c.quality_rank} | "
                    f"{'Yes' if c.assessed else 'No'} | {'Yes' if c.attempted else 'No'} | "
                    f"{c.execution_outcome or '-'} | {c.ground_truth or '-'} |"
                )
        else:
            lines.append("_No candidates._")
        lines.append("")
        
        # Engine Execution
        lines.append("## Engine Execution")
        lines.append("")
        if report.execution_results:
            lines.append("| Candidate ID | Outcome | Detail | Attempt |")
            lines.append("|--------------|---------|--------|---------|")
            for e in report.execution_results:
                lines.append(f"| {e.candidate_id} | {e.outcome} | {e.detail} | {e.attempt_number} |")
        else:
            lines.append("_No execution results recorded._")
        lines.append("")
        
        # Decision Trace
        lines.append("## Decision Trace")
        lines.append("")
        lines.append("```")
        for line in report.decision_trace:
            lines.append(line)
        lines.append("```")
        lines.append("")
        
        # Final Result
        lines.append("## Final Result")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| Status | {report.metadata.final_status} |")
        lines.append(f"| Total Attempts | {report.metadata.total_attempts} |")
        lines.append(f"| Pivot Count | {report.metadata.pivot_count} |")
        lines.append(f"| Candidates Processed | {len(report.metadata.candidates_processed)} |")
        lines.append("")
        ids_str = ", ".join(report.metadata.candidates_processed) if report.metadata.candidates_processed else "(none)"
        lines.append(f"**Candidate IDs:** {ids_str}")
        lines.append("")
        
        # Limitations
        lines.append("## Limitations")
        lines.append("")
        for limitation in report.limitations:
            lines.append(f"- {limitation}")
        lines.append("")
        
        # Safety Notice
        lines.append("---")
        lines.append("")
        lines.append("## Safety Notice")
        lines.append("")
        lines.append(f"> ⚠️ **{evidence_emoji} {report.safety_notice}**")
        lines.append("")
        
        return "\n".join(lines)

    def _get_evidence_emoji(self, tier: str) -> str:
        """Get emoji for evidence tier."""
        emoji_map = {
            EvidenceTier.SIMULATED.value: "🧪",
            EvidenceTier.OBSERVED_LOCAL.value: "👁️",
            EvidenceTier.DOCKER_OBSERVED.value: "🐳",
            EvidenceTier.CONTROLLED_VALIDATION.value: "✅",
            EvidenceTier.UNKNOWN.value: "❓",
        }
        return emoji_map.get(tier, "❓")


class TXTRenderer(ReportRenderer):
    """Renders reports as plain text."""

    def render(self, report: ReportModel) -> str:
        """Render report as plain text string."""
        evidence_tier = report.evidence_tier
        
        lines = []
        
        # Header
        lines.append("=" * 70)
        lines.append("AI VAPT DECISION ENGINE — MENTOR PROTOTYPE — RUN REPORT")
        lines.append("=" * 70)
        lines.append(f"Scenario:        {report.metadata.scenario}")
        lines.append(f"Execution Mode:  {report.metadata.mode.upper()}")
        lines.append(f"Evidence Tier:   {evidence_tier}")
        lines.append(f"Max Attempts:    {report.metadata.max_attempts}")
        lines.append(f"Final Status:    {report.metadata.final_status}")
        lines.append(f"Generated:       {report.metadata.generated_at}")
        lines.append("")
        
        # Executive Summary
        lines.append("-" * 70)
        lines.append("EXECUTIVE SUMMARY")
        lines.append("-" * 70)
        lines.append(report.executive_summary)
        lines.append("")
        
        # Evidence Tier
        lines.append("-" * 70)
        lines.append("EVIDENCE TIER")
        lines.append("-" * 70)
        lines.append(f"Classification:  {evidence_tier}")
        lines.append(f"Description:     {report.evidence_description}")
        lines.append("")
        
        # Target/Scope
        lines.append("-" * 70)
        lines.append("TARGET / SCOPE")
        lines.append("-" * 70)
        lines.append(f"Target:          {report.target or 'N/A'}")
        lines.append(f"Port:            {report.port}")
        lines.append(f"Path:            {report.path}")
        lines.append("")
        
        # Per-Candidate Attempts
        lines.append("-" * 70)
        lines.append("PER-CANDIDATE ATTEMPTS")
        lines.append("-" * 70)
        if report.attempts_per_candidate:
            for cid, count in sorted(report.attempts_per_candidate.items()):
                lines.append(f"  {cid:<25}  Attempts: {count}")
        else:
            lines.append("  (no execution attempts recorded)")
        lines.append("")
        
        # Pivot Events
        lines.append("-" * 70)
        lines.append("PIVOT EVENTS")
        lines.append("-" * 70)
        if report.pivot_events:
            for event in report.pivot_events:
                lines.append(f"  [{event.event_type}] {event.details}")
        else:
            lines.append("  (no pivot events recorded)")
        lines.append("")
        
        # Candidate Ranking
        lines.append("-" * 70)
        lines.append("CANDIDATE RANKING")
        lines.append("-" * 70)
        if report.candidates:
            for c in report.candidates:
                lines.append(f"  {c.candidate_id}")
                lines.append(f"    Probability: {c.probability:.4f}")
                lines.append(f"    Quality:     {c.quality_rank}")
                lines.append(f"    Outcome:     {c.execution_outcome or '-'}")
                lines.append("")
        else:
            lines.append("  (no candidates)")
        lines.append("")
        
        # Engine Execution
        lines.append("-" * 70)
        lines.append("ENGINE EXECUTION")
        lines.append("-" * 70)
        if report.execution_results:
            for e in report.execution_results:
                lines.append(f"  Attempt {e.attempt_number}: {e.candidate_id} -> {e.outcome}")
                if e.detail:
                    lines.append(f"    Detail: {e.detail}")
        else:
            lines.append("  (no execution results recorded)")
        lines.append("")
        
        # Decision Trace
        lines.append("-" * 70)
        lines.append("DECISION TRACE")
        lines.append("-" * 70)
        if report.decision_trace:
            for log in report.decision_trace:
                lines.append(f"  {log}")
        else:
            lines.append("  (no decision trace recorded)")
        lines.append("")
        
        # Final Result
        lines.append("-" * 70)
        lines.append("FINAL RESULT")
        lines.append("-" * 70)
        lines.append(f"Status:               {report.metadata.final_status}")
        lines.append(f"Total Attempts:       {report.metadata.total_attempts}")
        lines.append(f"Pivot Count:          {report.metadata.pivot_count}")
        lines.append(f"Candidates Processed: {len(report.metadata.candidates_processed)}")
        lines.append(f"  IDs: {', '.join(report.metadata.candidates_processed) if report.metadata.candidates_processed else '(none)'}")
        lines.append("")
        
        # Limitations
        lines.append("-" * 70)
        lines.append("LIMITATIONS")
        lines.append("-" * 70)
        for limitation in report.limitations:
            lines.append(f"  - {limitation}")
        lines.append("")
        
        # Safety Notice
        lines.append("=" * 70)
        lines.append("SAFETY NOTICE")
        lines.append("=" * 70)
        lines.append(report.safety_notice)
        lines.append("=" * 70)
        
        return "\n".join(lines)


def get_renderer(format: str) -> ReportRenderer:
    """Get a renderer for the specified format.
    
    Args:
        format: One of 'json', 'html', 'markdown', 'txt'
        
    Returns:
        ReportRenderer instance
        
    Raises:
        ValueError: If format is not supported
    """
    renderers = {
        "json": JSONRenderer,
        "html": HTMLRenderer,
        "markdown": MarkdownRenderer,
        "md": MarkdownRenderer,
        "txt": TXTRenderer,
        "text": TXTRenderer,
    }
    
    renderer_class = renderers.get(format.lower())
    if renderer_class is None:
        raise ValueError(f"Unsupported format: {format}. Supported: {list(renderers.keys())}")
    
    return renderer_class()
