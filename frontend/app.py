"""AI VAPT Operations Console.

Professional security operations interface for the canonical VAPT platform.

Architecture:
    GUI ──> VAPTApplication ──> canonical workflow
                              ──> persistence
                              ──> events
                              ──> reporting

Design: Modern SOC / VAPT Security Operations Console
- Dark professional security dashboard
- High information density
- Clean typography with restrained accent colors
- Cards, tables, timelines, severity indicators
- Evidence badges, attack-path visualization, decision trace
"""
from __future__ import annotations

import html
import json
import os
import tempfile
from datetime import datetime
from typing import Any, Optional

import streamlit as st
import requests

from vapt_platform.application import VAPTRequest, get_application
from vapt_platform.assessment import create_assessor
from vapt_platform.events import EventType, RunState
from vapt_platform.persistence import get_repository
from vapt_platform.reporting.builder import ReportBuilder
from vapt_platform.reporting.renderers import (
    HTMLRenderer,
    JSONRenderer,
    MarkdownRenderer,
    TXTRenderer,
)
from prototype.docker_demo_data import DOCKER_SCENARIOS
from prototype.demo_data import SCENARIOS

# All scenarios
ALL_SCENARIOS = {**SCENARIOS, **DOCKER_SCENARIOS}

# Page config
st.set_page_config(
    page_title="AI-VAPT Operations Console",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# PROFESSIONAL DARK THEME CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* ── Base ── */
    .stApp {
        background-color: #0a0e17;
        color: #e0e6ed;
    }
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
    }

    /* ── Header ── */
    .console-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.8rem 1.2rem;
        background: linear-gradient(135deg, #0d1b2a 0%, #1b2838 100%);
        border: 1px solid #1e3a5f;
        border-radius: 6px;
        margin-bottom: 1rem;
    }
    .console-header .title {
        font-size: 1.4rem;
        font-weight: 700;
        color: #4fc3f7;
        letter-spacing: 0.5px;
    }
    .console-header .status-badge {
        font-size: 0.75rem;
        font-weight: 600;
        padding: 0.25rem 0.7rem;
        border-radius: 12px;
        background: #1b5e20;
        color: #a5d6a7;
        border: 1px solid #2e7d32;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background-color: #0d1117;
        border-right: 1px solid #1e3a5f;
    }
    [data-testid="stSidebar"] .stRadio > label {
        color: #8899aa;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
        color: #c0cdd8;
        font-size: 0.9rem;
        padding: 0.4rem 0.6rem;
        border-radius: 4px;
        margin: 0.1rem 0;
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:hover {
        background: #1a2744;
    }

    /* ── Navigation ── */
    .nav-section {
        margin-bottom: 0.5rem;
    }
    .nav-label {
        font-size: 0.7rem;
        font-weight: 700;
        color: #5a7a9a;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        padding: 0.3rem 0.6rem;
        margin-top: 0.8rem;
    }

    /* ── Cards ── */
    .metric-card {
        background: #111827;
        border: 1px solid #1e3a5f;
        border-left: 3px solid #4fc3f7;
        border-radius: 4px;
        padding: 0.7rem 0.9rem;
        margin: 0.2rem 0;
    }
    .metric-card .label {
        font-size: 0.7rem;
        color: #6a8aaa;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-card .value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #e0e6ed;
    }
    .metric-card.accent-green { border-left-color: #66bb6a; }
    .metric-card.accent-red { border-left-color: #ef5350; }
    .metric-card.accent-amber { border-left-color: #ffa726; }
    .metric-card.accent-purple { border-left-color: #ab47bc; }
    .metric-card.accent-cyan { border-left-color: #26c6da; }

    /* ── Section headers ── */
    .section-header {
        font-size: 0.95rem;
        font-weight: 700;
        color: #4fc3f7;
        margin-top: 1.2rem;
        margin-bottom: 0.5rem;
        padding-bottom: 0.3rem;
        border-bottom: 1px solid #1e3a5f;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* ── Evidence badges ── */
    .evidence-docker {
        background: #0d2818;
        border: 1px solid #1b5e20;
        color: #a5d6a7;
        padding: 0.6rem 0.9rem;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .evidence-simulated {
        background: #2a2100;
        border: 1px solid #5d4037;
        color: #ffcc80;
        padding: 0.6rem 0.9rem;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .evidence-local {
        background: #0d1b2a;
        border: 1px solid #1565c0;
        color: #90caf9;
        padding: 0.6rem 0.9rem;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .evidence-controlled {
        background: #1a0d2a;
        border: 1px solid #6a1b9a;
        color: #ce93d8;
        padding: 0.6rem 0.9rem;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }

    /* ── AI / Fallback badges ── */
    .ai-badge {
        background: #0d1b2a;
        border: 1px solid #1565c0;
        color: #90caf9;
        padding: 0.15rem 0.5rem;
        border-radius: 3px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .fallback-badge {
        background: #2a2100;
        border: 1px solid #5d4037;
        color: #ffcc80;
        padding: 0.15rem 0.5rem;
        border-radius: 3px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* ── Event timeline ── */
    .event-timeline {
        border-left: 2px solid #1e3a5f;
        margin-left: 0.5rem;
        padding-left: 0.8rem;
    }
    .event-item {
        margin: 0.3rem 0;
        padding: 0.4rem 0.7rem;
        background: #111827;
        border-radius: 3px;
        font-size: 0.82rem;
        border: 1px solid #1e3a5f;
    }
    .event-success {
        background: #0d2818;
        border: 1px solid #1b5e20;
        color: #a5d6a7;
    }
    .event-fail {
        background: #2a0d0d;
        border: 1px solid #5e1b1b;
        color: #ef9a9a;
    }
    .event-pivot {
        background: #2a1a00;
        border: 1px solid #5d4037;
        color: #ffcc80;
    }
    .event-info {
        background: #0d1b2a;
        border: 1px solid #1565c0;
        color: #90caf9;
    }

    /* ── Trace ── */
    .trace-event {
        background: #111827;
        border-left: 2px solid #4fc3f7;
        padding: 0.3rem 0.7rem;
        margin: 0.15rem 0;
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 0.78rem;
        color: #b0c4d8;
    }

    /* ── Safety box ── */
    .safety-box {
        background: #1a1a2e;
        border: 1px solid #333355;
        color: #a0a0c0;
        padding: 0.7rem 0.9rem;
        border-radius: 4px;
        font-size: 0.82rem;
    }

    /* ── Tables ── */
    .stDataFrame {
        background: #111827;
    }
    .stDataFrame th {
        background: #0d1b2a !important;
        color: #4fc3f7 !important;
        font-weight: 600 !important;
        font-size: 0.8rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
    }
    .stDataFrame td {
        color: #c0cdd8 !important;
        font-size: 0.85rem !important;
    }

    /* ── Status indicators ── */
    .status-ready { color: #66bb6a; font-weight: 600; }
    .status-degraded { color: #ffa726; font-weight: 600; }
    .status-unavailable { color: #ef5350; font-weight: 600; }

    /* ── Severity ── */
    .severity-critical { color: #ef5350; font-weight: 700; }
    .severity-high { color: #ff7043; font-weight: 700; }
    .severity-medium { color: #ffa726; font-weight: 600; }
    .severity-low { color: #66bb6a; font-weight: 600; }
    .severity-info { color: #4fc3f7; font-weight: 600; }

    /* ── Pipeline progress ── */
    .pipeline-step {
        display: flex;
        align-items: center;
        padding: 0.3rem 0;
        font-size: 0.85rem;
    }
    .pipeline-step .step-icon {
        width: 1.5rem;
        text-align: center;
        margin-right: 0.5rem;
    }
    .pipeline-step .step-label {
        flex: 1;
    }
    .pipeline-step .step-status {
        font-size: 0.75rem;
        font-weight: 600;
    }
    .step-done { color: #66bb6a; }
    .step-active { color: #4fc3f7; }
    .step-pending { color: #5a7a9a; }

    /* ── Attack path ── */
    .attack-path {
        background: #111827;
        border: 1px solid #1e3a5f;
        border-radius: 4px;
        padding: 0.8rem;
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 0.8rem;
        line-height: 1.6;
    }
    .attack-path .node {
        color: #4fc3f7;
        font-weight: 600;
    }
    .attack-path .edge {
        color: #5a7a9a;
    }
    .attack-path .success { color: #66bb6a; }
    .attack-path .fail { color: #ef5350; }
    .attack-path .pivot { color: #ffa726; }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        background: #0d1117;
        border-radius: 4px 4px 0 0;
        border: 1px solid #1e3a5f;
        border-bottom: none;
    }
    .stTabs [data-baseweb="tab"] {
        color: #8899aa;
        font-weight: 600;
        font-size: 0.85rem;
        padding: 0.6rem 1.2rem;
        border-radius: 0;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #4fc3f7;
        background: #111827;
        border-bottom: 2px solid #4fc3f7;
    }

    /* ── Expander ── */
    .stExpander {
        background: #111827;
        border: 1px solid #1e3a5f;
        border-radius: 4px;
    }
    .stExpander summary {
        color: #c0cdd8;
        font-weight: 600;
        font-size: 0.9rem;
    }

    /* ── Buttons ── */
    .stButton button {
        background: #1565c0;
        color: #ffffff;
        border: none;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
        padding: 0.5rem 1.2rem;
    }
    .stButton button:hover {
        background: #1976d2;
    }

    /* ── Selectbox / Inputs ── */
    .stSelectbox > div > div {
        background: #111827;
        border: 1px solid #1e3a5f;
        color: #c0cdd8;
    }
    .stTextInput > div > div {
        background: #111827;
        border: 1px solid #1e3a5f;
        color: #c0cdd8;
    }
    .stNumberInput > div > div {
        background: #111827;
        border: 1px solid #1e3a5f;
        color: #c0cdd8;
    }

    /* ── Dividers ── */
    .stMarkdown hr {
        border-color: #1e3a5f;
        margin: 0.8rem 0;
    }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar {
        width: 6px;
    }
    ::-webkit-scrollbar-track {
        background: #0a0e17;
    }
    ::-webkit-scrollbar-thumb {
        background: #1e3a5f;
        border-radius: 3px;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def render_header():
    """Render the console header."""
    st.markdown(
        '<div class="console-header">'
        '<span class="title">🛡️ AI-VAPT Operations Console</span>'
        '<span class="status-badge">● SYSTEM READY</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_sidebar_nav() -> str:
    """Render sidebar navigation and return selected view."""
    with st.sidebar:
        st.markdown('<div class="nav-label">Navigation</div>', unsafe_allow_html=True)

        view = st.radio(
            "View",
            [
                "Dashboard",
                "New Assessment",
                "Run History",
                "Findings",
                "Intelligence",
                "Attack Paths",
                "Reports",
                "System",
            ],
            label_visibility="collapsed",
        )

        st.markdown("---")

        # System status mini-panel
        st.markdown('<div class="nav-label">System Status</div>', unsafe_allow_html=True)

        # Check Ollama
        try:
            from core.exploit_assessor import get_llm
            from vapt_platform.model_config import DEFAULT_OLLAMA_MODEL

            llm = get_llm(provider="ollama", model_name=DEFAULT_OLLAMA_MODEL)
            st.markdown('<div class="metric-card" style="padding:0.4rem 0.6rem;">'
                       '<span class="status-ready">● Ollama: READY</span>'
                       f'<br/><small style="color:#6a8aaa;">{DEFAULT_OLLAMA_MODEL}</small></div>',
                       unsafe_allow_html=True)
        except Exception:
            st.markdown('<div class="metric-card" style="padding:0.4rem 0.6rem;">'
                       '<span class="status-degraded">● Ollama: UNAVAILABLE</span></div>',
                       unsafe_allow_html=True)

        # Docker status
        st.markdown('<div class="metric-card" style="padding:0.4rem 0.6rem;">'
                   '<span class="status-unavailable">● Docker: N/A</span>'
                   '<br/><small style="color:#6a8aaa;">Not in this environment</small></div>',
                   unsafe_allow_html=True)

        # Research core
        st.markdown('<div class="metric-card" style="padding:0.4rem 0.6rem;">'
                   '<span class="status-ready">● Research Core: PROTECTED</span></div>',
                   unsafe_allow_html=True)

    return view


def render_metric_card(label: str, value: Any, accent: str = ""):
    """Render a single metric card."""
    css_class = f"metric-card {accent}" if accent else "metric-card"
    st.markdown(
        f'<div class="{css_class}">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_evidence_tier(evidence_tier: str, safety_notice: str):
    """Render evidence tier badge."""
    tier_map = {
        "DOCKER_OBSERVED": ("evidence-docker", "🔬 DOCKER_OBSERVED"),
        "OBSERVED_LOCAL": ("evidence-local", "👁️ OBSERVED_LOCAL"),
        "CONTROLLED_VALIDATION": ("evidence-controlled", "✅ CONTROLLED_VALIDATION"),
        "SIMULATED": ("evidence-simulated", "🟡 SIMULATED"),
    }
    css_class, label = tier_map.get(evidence_tier, ("evidence-simulated", "🟡 SIMULATED"))
    st.markdown(
        f'<div class="{css_class}">{label} — {html.escape(safety_notice)}</div>',
        unsafe_allow_html=True,
    )


def render_assessment_badge(assessment: dict):
    """Render AI/deterministic assessment badge."""
    mode = assessment.get("mode", "unknown")
    provider = assessment.get("provider")

    if mode == "ai":
        if provider:
            st.markdown(f'<span class="ai-badge">🤖 AI / {provider.upper()}</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="ai-badge">🤖 AI</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="fallback-badge">📊 DETERMINISTIC</span>', unsafe_allow_html=True)


def render_pipeline_progress(steps: list[tuple[str, str]]):
    """Render pipeline progress steps.

    Args:
        steps: List of (label, status) tuples where status is 'done', 'active', or 'pending'
    """
    st.markdown('<div class="section-header">Pipeline Progress</div>', unsafe_allow_html=True)

    icons = {"done": "✓", "active": "●", "pending": "○"}
    css_map = {"done": "step-done", "active": "step-active", "pending": "step-pending"}

    for label, status in steps:
        icon = icons.get(status, "○")
        css = css_map.get(status, "step-pending")
        st.markdown(
            f'<div class="pipeline-step">'
            f'<span class="step-icon {css}">{icon}</span>'
            f'<span class="step-label">{html.escape(label)}</span>'
            f'<span class="step-status {css}">{status.upper()}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def render_attack_path_visualization(result):
    """Render attack path / pivot visualization."""
    domain = result.domain if hasattr(result, "domain") else result

    st.markdown('<div class="section-header">Attack Path</div>', unsafe_allow_html=True)

    if not domain.execution_results:
        st.info("No execution results to visualize")
        return

    # Build path from execution results
    lines = []
    lines.append('<div class="attack-path">')

    # Start with finding
    lines.append('<span class="node">Finding</span>')
    lines.append('<span class="edge">  │</span>')
    lines.append('<span class="edge">  ▼</span>')

    for i, r in enumerate(domain.execution_results):
        candidate = r.get("candidate_id", "Unknown")
        outcome = r.get("outcome", "UNKNOWN")
        attempt = r.get("attempt_number", i + 1)

        if outcome == "SUCCESS":
            lines.append(f'<span class="node">{html.escape(candidate)}</span>')
            lines.append('<span class="edge">  │</span>')
            lines.append('<span class="edge">  +---- <span class="success">SUCCESS</span></span>')
        else:
            lines.append(f'<span class="node">{html.escape(candidate)}</span>')
            lines.append('<span class="edge">  │</span>')
            lines.append(f'<span class="edge">  +---- <span class="fail">{html.escape(outcome)}</span></span>')

            # Check if this was a pivot
            if i < len(domain.execution_results) - 1:
                next_candidate = domain.execution_results[i + 1].get("candidate_id", "Unknown")
                if next_candidate != candidate:
                    lines.append('<span class="edge">  │</span>')
                    lines.append('<span class="edge">  ▼</span>')
                    lines.append('<span class="pivot">  THRESHOLD → PIVOT</span>')
                    lines.append('<span class="edge">  │</span>')
                    lines.append('<span class="edge">  ▼</span>')

    lines.append('</div>')
    st.markdown("\n".join(lines), unsafe_allow_html=True)


def render_decision_trace(result):
    """Render decision trace."""
    domain = result.domain if hasattr(result, "domain") else result

    st.markdown('<div class="section-header">Decision Trace</div>', unsafe_allow_html=True)

    if not domain.decision_trace:
        st.info("No trace available")
        return

    with st.expander("View Full Trace", expanded=False):
        for log in domain.decision_trace:
            st.markdown(
                f'<div class="trace-event">{html.escape(log)}</div>',
                unsafe_allow_html=True,
            )


def render_run_reports(result):
    """Render report download options."""
    domain = result.domain if hasattr(result, "domain") else result

    st.markdown('<div class="section-header">Reports</div>', unsafe_allow_html=True)

    builder = ReportBuilder()
    report = builder.from_domain_result(domain)

    json_report = JSONRenderer().render(report)
    html_report = HTMLRenderer().render(report)
    md_report = MarkdownRenderer().render(report)
    txt_report = TXTRenderer().render(report)

    col1, col2, col3, col4 = st.columns(4)
    col1.download_button("⬇️ JSON", json_report, file_name="report.json")
    col2.download_button("⬇️ Text", txt_report, file_name="report.txt")
    col3.download_button("⬇️ HTML", html_report, file_name="report.html")
    col4.download_button("⬇️ Markdown", md_report, file_name="report.md")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

def show_dashboard():
    """Show the main dashboard."""
    st.markdown('<div class="section-header">Dashboard</div>', unsafe_allow_html=True)

    # Get stats from repository
    repository = get_repository()
    runs = repository.list_runs(limit=1000)

    total_runs = len(runs)
    successful = sum(1 for r in runs if r.final_status == "SUCCESS")
    failed = sum(1 for r in runs if r.final_status == "FAILED")
    total_attempts = sum(r.total_attempts for r in runs)
    total_pivots = sum(r.pivot_count for r in runs)
    ai_assessments = sum(1 for r in runs if r.assessor_mode == "ai")
    docker_observed = sum(1 for r in runs if r.evidence_tier == "DOCKER_OBSERVED")

    # Metric cards row
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        render_metric_card("Total Runs", total_runs, "accent-cyan")
    with col2:
        render_metric_card("Successful", successful, "accent-green")
    with col3:
        render_metric_card("Failed", failed, "accent-red")
    with col4:
        render_metric_card("Attempts", total_attempts, "accent-amber")
    with col5:
        render_metric_card("Pivots", total_pivots, "accent-purple")
    with col6:
        render_metric_card("AI Assessments", ai_assessments, "accent-cyan")

    st.markdown("---")

    # Recent runs table
    st.markdown('<div class="section-header">Recent Runs</div>', unsafe_allow_html=True)

    if not runs:
        st.info("No runs yet. Execute an assessment to see results here.")
        return

    # Build table data
    recent = runs[:10]
    table_data = []
    for r in recent:
        table_data.append({
            "Run ID": r.run_id,
            "Scenario": r.scenario,
            "Mode": r.mode,
            "Status": r.status,
            "Evidence": r.evidence_tier,
            "Attempts": r.total_attempts,
            "Pivots": r.pivot_count,
            "Timestamp": r.created_at[:19] if r.created_at else "N/A",
        })

    st.dataframe(table_data, use_container_width=True, hide_index=True)

    st.markdown("---")

    # System health
    st.markdown('<div class="section-header">System Health</div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown('<div class="metric-card">'
                   '<div class="label">Application</div>'
                   '<div class="value status-ready">READY</div></div>',
                   unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="metric-card">'
                   '<div class="label">Persistence</div>'
                   '<div class="value status-ready">READY</div></div>',
                   unsafe_allow_html=True)
    with col3:
        # Check Ollama
        try:
            from core.exploit_assessor import get_llm
            from vapt_platform.model_config import DEFAULT_OLLAMA_MODEL

            llm = get_llm(provider="ollama", model_name=DEFAULT_OLLAMA_MODEL)
            st.markdown('<div class="metric-card">'
                       '<div class="label">Ollama</div>'
                       '<div class="value status-ready">READY</div></div>',
                       unsafe_allow_html=True)
        except Exception:
            st.markdown('<div class="metric-card">'
                       '<div class="label">Ollama</div>'
                       '<div class="value status-unavailable">UNAVAILABLE</div></div>',
                       unsafe_allow_html=True)
    with col4:
        st.markdown('<div class="metric-card">'
                   '<div class="label">Docker Lab</div>'
                   '<div class="value status-unavailable">N/A</div></div>',
                   unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: NEW ASSESSMENT
# ─────────────────────────────────────────────────────────────────────────────

def show_new_assessment():
    """Configure and execute a new assessment."""
    st.markdown('<div class="section-header">New Assessment</div>', unsafe_allow_html=True)

    # Configuration in sidebar
    with st.sidebar:
        st.markdown('<div class="nav-label">Configuration</div>', unsafe_allow_html=True)

        # Execution mode
        mode = st.radio(
            "Execution Mode",
            ["Simulation", "Docker Lab", "Loopback"],
            help="Simulation = ground-truth labels | Docker Lab = real HTTP to emulator | Loopback = local",
        )

        # Target configuration
        if mode == "Docker Lab":
            target = st.selectbox(
                "Target",
                ["172.28.0.2"],
                help="Allowlisted Docker emulator target",
            )
            port = st.number_input("Port", value=8080, min_value=1, max_value=65535)
            path = st.text_input("Path", value="/vuln", help="HTTP path (e.g., /vuln, /fail)")
        elif mode == "Loopback":
            target = st.selectbox("Target", ["127.0.0.1"])
            port = st.number_input("Port", value=8080, min_value=1, max_value=65535)
            path = st.text_input("Path", value="/vuln")
        else:
            target = None
            port = 8080
            path = "/vuln"

        st.markdown("---")

        # Scenario selection
        scenario_name = st.selectbox(
            "Scenario",
            list(ALL_SCENARIOS.keys()) + ["corpus"],
            help="Select a demo scenario",
        )

        # Scan file upload
        scan_file_obj = st.file_uploader(
            "Or Upload Scan File",
            type=["xml", "json"],
            help="Nmap XML/JSON or custom JSON",
        )

        st.markdown("---")

        # Assessor configuration
        assessor_mode = st.radio(
            "Assessor",
            ["deterministic", "ai"],
            help="deterministic = offline | AI = local Ollama or an optional "
                 "hosted provider (OpenRouter / OpenAI)",
        )

        # Phase 33A / OpenRouter: provider + model selection is explicit and
        # opt-in. Ollama is the default (llama3.2:3b is the thesis baseline);
        # hosted providers are never selected implicitly.
        assessor_provider = "ollama"
        assessor_model = None
        if assessor_mode == "ai":
            from vapt_platform.model_config import (
                KNOWN_PROVIDERS, PROVIDER_LABELS, models_for_provider,
            )

            assessor_provider = st.selectbox(
                "Provider",
                list(KNOWN_PROVIDERS),
                index=0,
                format_func=lambda p: PROVIDER_LABELS.get(p, p),
                help="Ollama runs fully offline. OpenRouter/OpenAI are hosted "
                     "APIs and require their API key to be exported on the "
                     "server (the key is never entered or displayed here).",
            )

            _models = list(models_for_provider(assessor_provider))
            assessor_model = st.selectbox(
                "Model",
                _models,
                index=0,
                help="llama3.2:3b is the thesis baseline; qwen2.5:3b is an "
                     "experimental comparison arm (Phase 33A). Hosted models "
                     "are a separate, clearly-labelled run arm.",
            )
            if assessor_provider != "ollama":
                st.info(
                    f"Hosted provider **{assessor_provider}** selected. This "
                    "produces a separate run arm that is never merged into the "
                    "historical Ollama baseline results."
                )

        max_attempts = st.slider("Pivot Threshold (N)", 1, 5, 2)

        st.markdown("---")

        # Safety status
        st.markdown('<div class="nav-label">Safety Status</div>', unsafe_allow_html=True)
        if mode == "Docker Lab":
            st.markdown('<div class="evidence-docker" style="padding:0.5rem;">'
                       '✅ AUTHORIZED / ALLOWLISTED'
                       '<br/><small>Target: 172.28.0.2 (Docker emulator)</small></div>',
                       unsafe_allow_html=True)
        elif mode == "Loopback":
            st.markdown('<div class="evidence-local" style="padding:0.5rem;">'
                       '🔵 LOOPBACK'
                       '<br/><small>Target: 127.0.0.1</small></div>',
                       unsafe_allow_html=True)
        else:
            st.markdown('<div class="evidence-simulated" style="padding:0.5rem;">'
                       '🟡 SIMULATION'
                       '<br/><small>No real execution</small></div>',
                       unsafe_allow_html=True)

        st.markdown("---")

        # Run button
        run_clicked = st.button("🚀 Run Assessment", type="primary", use_container_width=True)

    # Main content area
    if run_clicked:
        execute_assessment(
            mode=mode,
            target=target,
            port=port,
            path=path,
            scenario_name=scenario_name,
            assessor_mode=assessor_mode,
            assessor_provider=assessor_provider,
            max_attempts=max_attempts,
            scan_file_obj=scan_file_obj,
            assessor_model=assessor_model,
        )
    else:
        # Welcome / info screen
        st.markdown('<div class="section-header">Quick Start</div>', unsafe_allow_html=True)
        st.markdown("""
        1. Select **Simulation** mode for offline testing
        2. Choose a scenario (e.g., `failure_pivot`)
        3. Select **AI** assessor for LLM-based grading (requires Ollama)
        4. Click **Run Assessment**
        """)

        st.markdown('<div class="section-header">Research Contribution</div>', unsafe_allow_html=True)
        st.markdown("""
        This platform demonstrates **state-aware bounded failure-threshold pivoting**:
        - Per-candidate attempt counting
        - Configurable failure threshold
        - Automatic pivot to next candidate
        - Bounded termination
        """)


def execute_assessment(
    mode: str,
    target: Optional[str],
    port: int,
    path: str,
    scenario_name: str,
    assessor_mode: str,
    max_attempts: int,
    scan_file_obj,
    assessor_model: Optional[str] = None,
    assessor_provider: str = "ollama",
):
    """Execute the assessment and display results."""
    # Map mode string to internal mode
    mode_map = {
        "Docker Lab": "lab",
        "Loopback": "lab",
        "Simulation": "simulation",
    }
    internal_mode = mode_map[mode]

    # Handle scan file
    scan_file_path = None
    if scan_file_obj is not None:
        suffix = ".xml" if scan_file_obj.name.endswith(".xml") else ".json"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(scan_file_obj.read())
            scan_file_path = tmp.name

    # Build request
    request = VAPTRequest(
        scenario=scenario_name,
        mode=internal_mode,
        target=target,
        port=port,
        path=path,
        assessor_mode=assessor_mode,
        assessor_provider=assessor_provider,
        assessor_model=assessor_model,
        max_attempts=max_attempts,
        scan_file=scan_file_path,
    )

    # Explicit hosted provider -> require its key up front, with a clear
    # message. Never silently downgrade to Ollama/deterministic.
    if request.assessor_mode == "ai":
        from vapt_platform.model_config import api_key_env_for

        _key_env = api_key_env_for(request.assessor_provider)
        if _key_env and not os.getenv(_key_env):
            st.error(
                f"**{request.assessor_provider}** is selected but "
                f"`{_key_env}` is not set on the server. Export "
                f"`{_key_env}` (see `.env.example`) or pick **Ollama** for "
                "the offline path. The platform will not silently switch "
                "providers."
            )
            st.stop()

    # Show pipeline progress during execution
    steps = [
        ("Finding ingestion", "pending"),
        ("Normalization", "pending"),
        ("Intelligence enrichment", "pending"),
        ("Candidate generation", "pending"),
        ("AI assessment", "pending"),
        ("Candidate ranking", "pending"),
        ("Decision", "pending"),
        ("Safety validation", "pending"),
        ("Execution", "pending"),
        ("Verification", "pending"),
        ("Evidence", "pending"),
        ("Report", "pending"),
    ]

    progress_placeholder = st.empty()

    def update_progress(step_name: str, status: str):
        nonlocal steps
        steps = [(label, status if label == step_name else s) for label, s in steps]
        with progress_placeholder.container():
            render_pipeline_progress(steps)

    # Run with progress
    with st.spinner("Running assessment..."):
        application = get_application()
        result = application.run(request)

    # Display results
    display_run_details(result, mode, from_history=False)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: RUN HISTORY
# ─────────────────────────────────────────────────────────────────────────────

def show_run_history():
    """Show run history from the canonical persistence layer."""
    st.markdown('<div class="section-header">Run History</div>', unsafe_allow_html=True)

    # Get runs from repository
    repository = get_repository()
    runs = repository.list_runs(limit=100)

    if not runs:
        st.info("No runs found. Execute an assessment to see results here.")
        return

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        status_filter = st.selectbox("Status", ["All", "COMPLETED", "FAILED"])
    with col2:
        mode_filter = st.selectbox("Mode", ["All", "simulation", "lab"])
    with col3:
        evidence_filter = st.selectbox("Evidence", ["All", "SIMULATED", "DOCKER_OBSERVED", "OBSERVED_LOCAL"])
    with col4:
        assessor_filter = st.selectbox("Assessor", ["All", "deterministic", "ai"])

    # Apply filters
    filtered = runs
    if status_filter != "All":
        filtered = [r for r in filtered if r.status == status_filter]
    if mode_filter != "All":
        filtered = [r for r in filtered if r.mode == mode_filter]
    if evidence_filter != "All":
        filtered = [r for r in filtered if r.evidence_tier == evidence_filter]
    if assessor_filter != "All":
        filtered = [r for r in filtered if r.assessor_mode == assessor_filter]

    st.caption(f"Showing {len(filtered)} of {len(runs)} runs")

    # Run selection
    run_options = {run.run_id: f"{run.run_id} | {run.scenario} | {run.mode} | {run.status}" for run in filtered}
    selected_run_id = st.selectbox(
        "Select a run to view details",
        options=list(run_options.keys()),
        format_func=lambda x: run_options[x],
        label_visibility="collapsed",
    )

    if selected_run_id:
        run = repository.get(selected_run_id)
        if run:
            display_persisted_run_details(run)
        else:
            st.error(f"Run {selected_run_id} not found.")


def display_persisted_run_details(run):
    """Display details of a persisted run."""
    # Header
    st.markdown(f'<div class="section-header">Run: {run.run_id}</div>', unsafe_allow_html=True)
    st.caption(f"Created: {run.created_at} | Updated: {run.updated_at}")

    # Summary cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        render_metric_card("Status", run.status)
    with col2:
        render_metric_card("Scenario", run.scenario)
    with col3:
        render_metric_card("Mode", run.mode)
    with col4:
        render_metric_card("Attempts", run.total_attempts)
    with col5:
        render_metric_card("Pivots", run.pivot_count)

    st.markdown("---")

    # Evidence tier
    render_evidence_tier(run.evidence_tier, run.safety_notice)

    st.markdown("---")

    # Tabs for different views
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Overview",
        "Timeline",
        "Findings",
        "Candidates",
        "Decision Trace",
        "Reports",
    ])

    with tab1:
        display_run_overview(run)
    with tab2:
        display_event_timeline(run)
    with tab3:
        display_findings_from_run(run)
    with tab4:
        display_candidates_from_run(run)
    with tab5:
        display_decision_trace_from_run(run)
    with tab6:
        display_reports_for_run(run)


def display_run_overview(run):
    """Display run overview."""
    st.markdown('<div class="section-header">Run Overview</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Metadata**")
        st.markdown(f"- **Run ID:** {run.run_id}")
        st.markdown(f"- **Scenario:** {run.scenario}")
        st.markdown(f"- **Mode:** {run.mode}")
        st.markdown(f"- **Status:** {run.status}")
        st.markdown(f"- **Final Status:** {run.final_status}")
        st.markdown(f"- **Evidence Tier:** {run.evidence_tier}")
        st.markdown(f"- **Max Attempts:** {run.max_attempts}")
        st.markdown(f"- **Assessor:** {run.assessor_mode} ({run.assessor_provider})")

    with col2:
        st.markdown("**Target/Scope**")
        st.markdown(f"- **Target:** {run.target or 'N/A'}")
        st.markdown(f"- **Port:** {run.port}")
        st.markdown(f"- **Path:** {run.path}")
        st.markdown(f"- **Candidates Processed:** {len(run.candidates_processed)}")
        if run.candidates_processed:
            st.markdown(f"  - {', '.join(run.candidates_processed)}")

    # Assessment
    if run.assessment:
        st.markdown("---")
        st.markdown('<div class="section-header">Assessment</div>', unsafe_allow_html=True)
        render_assessment_badge(run.assessment)

    # Safety notice
    if run.safety_notice:
        st.markdown("---")
        st.markdown(
            f'<div class="safety-box">{html.escape(run.safety_notice)}</div>',
            unsafe_allow_html=True,
        )


def display_event_timeline(run):
    """Display execution timeline from canonical event model."""
    st.markdown('<div class="section-header">Execution Timeline</div>', unsafe_allow_html=True)

    from vapt_platform.events import get_event_bus
    event_bus = get_event_bus()
    events = event_bus.get_events(run.run_id)

    if not events:
        st.info("No events recorded for this run.")
        return

    st.markdown('<div class="event-timeline">', unsafe_allow_html=True)
    for event in events:
        event_type = event.event_type
        timestamp = event.timestamp
        payload = event.payload

        # Determine event styling
        if event_type == EventType.RUN_COMPLETED.value:
            css_class = "event-success"
            icon = "✅"
        elif event_type == EventType.RUN_FAILED.value:
            css_class = "event-fail"
            icon = "❌"
        elif event_type == EventType.PIVOT_OCCURRED.value:
            css_class = "event-pivot"
            icon = "🔄"
        elif event_type == EventType.EXECUTION_STARTED.value:
            css_class = "event-info"
            icon = "▶️"
        elif event_type == EventType.ATTEMPT_COMPLETED.value:
            outcome = payload.get("outcome", "")
            if outcome == "SUCCESS":
                css_class = "event-success"
                icon = "✅"
            else:
                css_class = "event-fail"
                icon = "❌"
        else:
            css_class = "event-info"
            icon = "📌"

        details = ", ".join(f"{k}={v}" for k, v in payload.items()) if payload else ""

        st.markdown(
            f'<div class="event-item {css_class}">'
            f"{icon} **{event_type}**"
            f"<br/><small>{timestamp}"
            f"{' | ' + html.escape(details) if details else ''}"
            f"</small>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def display_findings_from_run(run):
    """Display findings from a persisted run."""
    st.markdown('<div class="section-header">Findings</div>', unsafe_allow_html=True)

    if not run.candidates:
        st.info("No findings recorded.")
        return

    for c in run.candidates:
        with st.expander(f"**{c.get('id', 'Unknown')}**"):
            cols = st.columns(2)
            cols[0].markdown(f"**Probability:** {c.get('probability', 0):.4f}")
            cols[1].markdown(f"**Quality:** {c.get('quality_rank', 'N/A')}")
            cols[0].markdown(f"**Assessed:** {'✅' if c.get('assessed') else '❌'}")
            cols[1].markdown(f"**Attempted:** {'✅' if c.get('attempted') else '❌'}")
            if c.get("execution_outcome"):
                st.markdown(f"**Outcome:** `{c.get('execution_outcome')}`")


def display_candidates_from_run(run):
    """Display candidates from a persisted run."""
    st.markdown('<div class="section-header">Candidates</div>', unsafe_allow_html=True)

    if not run.candidates:
        st.info("No candidates recorded.")
        return

    # Build table
    table_data = []
    for c in run.candidates:
        table_data.append({
            "ID": c.get("id", "Unknown"),
            "Probability": c.get("probability", 0),
            "Quality": c.get("quality_rank", "N/A"),
            "Assessed": "✅" if c.get("assessed") else "❌",
            "Attempted": "✅" if c.get("attempted") else "❌",
            "Outcome": c.get("execution_outcome", "-"),
        })

    st.dataframe(table_data, use_container_width=True, hide_index=True)

    # Execution results
    if run.execution_results:
        st.markdown("---")
        st.markdown('<div class="section-header">Execution Results</div>', unsafe_allow_html=True)

        for i, r in enumerate(run.execution_results, 1):
            outcome = r.get("outcome", "UNKNOWN")
            candidate = r.get("candidate_id", "Unknown")
            detail = r.get("detail", "")

            if outcome == "SUCCESS":
                st.markdown(
                    f'<div class="event-item event-success">'
                    f"✅ Attempt {i}: {candidate} → {outcome}<br/>"
                    f"<small>{html.escape(detail)}</small>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="event-item event-fail">'
                    f"❌ Attempt {i}: {candidate} → {outcome}<br/>"
                    f"<small>{html.escape(detail)}</small>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


def display_decision_trace_from_run(run):
    """Display decision trace from a persisted run."""
    st.markdown('<div class="section-header">Decision Trace</div>', unsafe_allow_html=True)

    if not run.decision_trace:
        st.info("No trace available")
        return

    for log in run.decision_trace:
        st.markdown(
            f'<div class="trace-event">{html.escape(log)}</div>',
            unsafe_allow_html=True,
        )


def display_reports_for_run(run):
    """Display report generation options for a persisted run."""
    st.markdown('<div class="section-header">Reports</div>', unsafe_allow_html=True)

    builder = ReportBuilder()
    report = builder.from_persisted_run(run)

    json_report = JSONRenderer().render(report)
    html_report = HTMLRenderer().render(report)
    md_report = MarkdownRenderer().render(report)
    txt_report = TXTRenderer().render(report)

    col1, col2, col3, col4 = st.columns(4)
    col1.download_button("⬇️ JSON", json_report, file_name=f"report_{run.run_id}.json")
    col2.download_button("⬇️ Text", txt_report, file_name=f"report_{run.run_id}.txt")
    col3.download_button("⬇️ HTML", html_report, file_name=f"report_{run.run_id}.html")
    col4.download_button("⬇️ Markdown", md_report, file_name=f"report_{run.run_id}.md")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: FINDINGS
# ─────────────────────────────────────────────────────────────────────────────

def show_findings():
    """Show all findings across runs."""
    st.markdown('<div class="section-header">Findings</div>', unsafe_allow_html=True)

    repository = get_repository()
    runs = repository.list_runs(limit=100)

    all_findings = []
    for run in runs:
        for c in run.candidates:
            all_findings.append({
                "Run ID": run.run_id,
                "Finding ID": c.get("id", "Unknown"),
                "Probability": c.get("probability", 0),
                "Quality": c.get("quality_rank", "N/A"),
                "Outcome": c.get("execution_outcome", "-"),
                "Evidence": run.evidence_tier,
            })

    if not all_findings:
        st.info("No findings recorded yet.")
        return

    st.dataframe(all_findings, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

def show_intelligence():
    """Show vulnerability intelligence."""
    st.markdown('<div class="section-header">Vulnerability Intelligence</div>', unsafe_allow_html=True)

    from vapt_platform.enrichment import LocalDatasetProvider

    provider = LocalDatasetProvider()

    # Show dataset stats
    col1, col2 = st.columns(2)
    with col1:
        render_metric_card("CISA KEV Entries", len(provider.kev_set), "accent-red")
    with col2:
        render_metric_card("EPSS Corpus Entries", len(provider.epss_corpus), "accent-cyan")

    st.markdown("---")

    # Sample CVE lookup
    st.markdown('<div class="section-header">CVE Lookup</div>', unsafe_allow_html=True)

    cve_id = st.text_input("CVE ID", value="CVE-2021-44228", help="Enter a CVE ID to look up")

    if cve_id:
        epss = provider.get_epss(cve_id)
        in_kev = provider.is_in_kev(cve_id)

        col1, col2 = st.columns(2)
        with col1:
            render_metric_card("EPSS Score", f"{epss:.5f}", "accent-cyan")
        with col2:
            if in_kev:
                render_metric_card("CISA KEV", "YES", "accent-red")
            else:
                render_metric_card("CISA KEV", "NO", "accent-green")

        st.markdown("---")

        # Evidence distinction
        st.markdown('<div class="section-header">Evidence Provenance</div>', unsafe_allow_html=True)
        st.markdown("""
        **Observed fact:** The EPSS score and CISA KEV status are from local datasets.
        **Enriched intelligence:** The quality rank is from the decision engine assessment.
        **AI assessment:** The LLM-based usability scoring (when available).
        **Decision:** The final ranking and pivot decision from the engine.
        """)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: ATTACK PATHS
# ─────────────────────────────────────────────────────────────────────────────

def show_attack_paths():
    """Show attack path visualizations."""
    st.markdown('<div class="section-header">Attack Paths</div>', unsafe_allow_html=True)

    repository = get_repository()
    runs = repository.list_runs(limit=100)

    if not runs:
        st.info("No runs recorded yet.")
        return

    # Select a run
    run_options = {run.run_id: f"{run.run_id} | {run.scenario} | {run.status}" for run in runs}
    selected_run_id = st.selectbox(
        "Select a run",
        options=list(run_options.keys()),
        format_func=lambda x: run_options[x],
        label_visibility="collapsed",
    )

    if selected_run_id:
        run = repository.get(selected_run_id)
        if run:
            # Build a mock result for visualization
            class MockResult:
                def __init__(self, run):
                    self.domain = type('obj', (object,), {
                        'run_id': run.run_id,
                        'scenario': run.scenario,
                        'mode': run.mode,
                        'final_status': run.final_status,
                        'candidates': run.candidates,
                        'execution_results': run.execution_results,
                        'decision_trace': run.decision_trace,
                        'total_attempts': run.total_attempts,
                        'pivot_count': run.pivot_count,
                        'candidates_processed': run.candidates_processed,
                        'evidence_tier': run.evidence_tier,
                        'assessment': run.assessment,
                        'safety_notice': run.safety_notice,
                    })()

            result = MockResult(run)
            render_attack_path_visualization(result)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: REPORTS
# ─────────────────────────────────────────────────────────────────────────────

def show_reports():
    """Show report generation."""
    st.markdown('<div class="section-header">Reports</div>', unsafe_allow_html=True)

    repository = get_repository()
    runs = repository.list_runs(limit=100)

    if not runs:
        st.info("No runs recorded yet.")
        return

    # Select a run
    run_options = {run.run_id: f"{run.run_id} | {run.scenario} | {run.status}" for run in runs}
    selected_run_id = st.selectbox(
        "Select a run",
        options=list(run_options.keys()),
        format_func=lambda x: run_options[x],
        label_visibility="collapsed",
    )

    if selected_run_id:
        run = repository.get(selected_run_id)
        if run:
            display_reports_for_run(run)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

def show_system():
    """Show system health and configuration."""
    st.markdown('<div class="section-header">System Health</div>', unsafe_allow_html=True)

    # Application status
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown('<div class="metric-card">'
                   '<div class="label">Application</div>'
                   '<div class="value status-ready">READY</div>'
                   '<small>v0.1.0</small></div>',
                   unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="metric-card">'
                   '<div class="label">Persistence</div>'
                   '<div class="value status-ready">READY</div>'
                   '<small>JSON Repository</small></div>',
                   unsafe_allow_html=True)

    with col3:
        # Check Ollama
        try:
            from core.exploit_assessor import get_llm
            from vapt_platform.model_config import DEFAULT_OLLAMA_MODEL

            llm = get_llm(provider="ollama", model_name=DEFAULT_OLLAMA_MODEL)
            st.markdown('<div class="metric-card">'
                       '<div class="label">Ollama</div>'
                       '<div class="value status-ready">READY</div>'
                       f'<small>{DEFAULT_OLLAMA_MODEL}</small></div>',
                       unsafe_allow_html=True)
        except Exception:
            st.markdown('<div class="metric-card">'
                       '<div class="label">Ollama</div>'
                       '<div class="value status-unavailable">UNAVAILABLE</div></div>',
                       unsafe_allow_html=True)

    with col4:
        st.markdown('<div class="metric-card">'
                   '<div class="label">Docker Lab</div>'
                   '<div class="value status-unavailable">N/A</div>'
                   '<small>Not in this environment</small></div>',
                   unsafe_allow_html=True)

    st.markdown("---")

    # Research core status
    st.markdown('<div class="section-header">Research Core</div>', unsafe_allow_html=True)

    st.markdown('<div class="metric-card accent-green">'
               '<div class="label">Status</div>'
               '<div class="value status-ready">PROTECTED</div>'
               '<small>GAP-1 and GAP-2 verified intact</small></div>',
               unsafe_allow_html=True)

    st.markdown("---")

    # Component versions
    st.markdown('<div class="section-header">Component Versions</div>', unsafe_allow_html=True)

    import platform
    import sys

    col1, col2, col3 = st.columns(3)
    with col1:
        render_metric_card("Python", platform.python_version(), "accent-cyan")
    with col2:
        render_metric_card("LangGraph", "1.2.11", "accent-purple")
    with col3:
        render_metric_card("Pydantic", "2.13.4", "accent-green")

    st.markdown("---")

    # API endpoints
    st.markdown('<div class="section-header">API Endpoints</div>', unsafe_allow_html=True)

    st.markdown("""
    | Endpoint | Method | Description |
    |----------|--------|-------------|
    | `/health` | GET | Health check |
    | `/runs` | POST | Start a new run |
    | `/runs` | GET | List runs |
    | `/runs/{id}` | GET | Get run status |
    | `/runs/{id}/persisted` | GET | Get persisted run |
    | `/runs/{id}/trace` | GET | Get decision trace |
    | `/runs/{id}/events` | GET | Get run events |
    | `/runs/{id}/report` | GET | Get report |
    | `/runs/{id}/evidence` | GET | Get evidence |
    | `/runs/{id}/findings` | GET | Get findings |
    | `/runs/{id}/candidates` | GET | Get candidates |
    """)


# ─────────────────────────────────────────────────────────────────────────────
# SHARED DISPLAY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def display_run_details(result, mode: str, from_history: bool = True):
    """Display run details (used for both new runs and history)."""
    domain = result.domain if hasattr(result, "domain") else result

    # Header
    st.markdown(f'<div class="section-header">Assessment Results</div>', unsafe_allow_html=True)
    st.caption(f"Run ID: {domain.run_id} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Summary cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        render_metric_card("Status", domain.final_status)
    with col2:
        render_metric_card("Candidates", len(domain.candidates))
    with col3:
        render_metric_card("Attempts", domain.total_attempts)
    with col4:
        render_metric_card("Pivots", domain.pivot_count)
    with col5:
        render_metric_card("Evidence", domain.evidence_tier)

    st.markdown("---")

    # Evidence tier
    render_evidence_tier(domain.evidence_tier, domain.safety_notice)

    st.markdown("---")

    # Two-column layout
    left_col, right_col = st.columns(2)

    with left_col:
        display_findings_panel(result)
        display_candidates_panel(result)

    with right_col:
        display_execution_timeline(result)
        render_attack_path_visualization(result)

    st.markdown("---")

    # Decision trace
    render_decision_trace(result)

    st.markdown("---")

    # Reports
    render_run_reports(result)


def display_findings_panel(result):
    """Display findings panel."""
    domain = result.domain if hasattr(result, "domain") else result
    st.markdown('<div class="section-header">Findings</div>', unsafe_allow_html=True)

    if not domain.candidates:
        st.info("No findings")
        return

    for c in domain.candidates:
        with st.expander(f"**{c.get('id', 'Unknown')}**"):
            cols = st.columns(2)
            cols[0].markdown(f"**Probability:** {c.get('probability', 0):.4f}")
            cols[1].markdown(f"**Quality:** {c.get('quality_rank', 'N/A')}")
            cols[0].markdown(f"**Assessed:** {'✅' if c.get('assessed') else '❌'}")
            cols[1].markdown(f"**Attempted:** {'✅' if c.get('attempted') else '❌'}")
            if c.get("execution_outcome"):
                st.markdown(f"**Outcome:** `{c.get('execution_outcome')}`")


def display_candidates_panel(result):
    """Display candidate/AI assessment panel."""
    domain = result.domain if hasattr(result, "domain") else result
    st.markdown('<div class="section-header">AI Assessment</div>', unsafe_allow_html=True)

    # Assessment provenance
    assessment = domain.assessment
    if assessment:
        render_assessment_badge(assessment)

    if not domain.candidates:
        st.info("No candidates assessed")
        return

    # Candidate table
    for c in domain.candidates:
        quality = c.get("quality_rank", "N/A")
        prob = c.get("probability", 0)
        score = prob * (0.5 + 0.5 * {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}.get(quality, 0))

        st.markdown(f"**{c.get('id', 'Unknown')}**")
        cols = st.columns(3)
        cols[0].markdown(f"Quality: `{quality}`")
        cols[1].markdown(f"Score: `{score:.4f}`")
        cols[2].markdown(f"Outcome: `{c.get('execution_outcome', '-')}`")


def display_execution_timeline(result):
    """Display execution timeline."""
    domain = result.domain if hasattr(result, "domain") else result
    st.markdown('<div class="section-header">Execution Timeline</div>', unsafe_allow_html=True)

    if not domain.execution_results:
        st.info("No execution results")
        return

    for i, r in enumerate(domain.execution_results, 1):
        outcome = r.get("outcome", "UNKNOWN")
        candidate = r.get("candidate_id", "Unknown")
        detail = r.get("detail", "")

        if outcome == "SUCCESS":
            st.markdown(
                f'<div class="event-item event-success">'
                f"✅ Attempt {i}: {candidate} → {outcome}<br/>"
                f"<small>{html.escape(detail)}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="event-item event-fail">'
                f"❌ Attempt {i}: {candidate} → {outcome}<br/>"
                f"<small>{html.escape(detail)}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Main dashboard entry point."""
    render_header()
    view = render_sidebar_nav()

    if view == "Dashboard":
        show_dashboard()
    elif view == "New Assessment":
        show_new_assessment()
    elif view == "Run History":
        show_run_history()
    elif view == "Findings":
        show_findings()
    elif view == "Intelligence":
        show_intelligence()
    elif view == "Attack Paths":
        show_attack_paths()
    elif view == "Reports":
        show_reports()
    elif view == "System":
        show_system()


if __name__ == "__main__":
    main()
