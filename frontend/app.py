"""AI VAPT Operations Dashboard.

A professional security operations interface for the canonical VAPT platform.

Architecture:
    GUI ──> API ──> VAPTApplication ──> canonical workflow
                                        ──> persistence
                                        ──> events
                                        ──> reporting

Views:
    - Run History: list of persisted runs
    - Run Details: selected run with timeline, findings, evidence, reports
    - New Assessment: configure and execute new runs
"""
from __future__ import annotations

import html
import json
import tempfile
from datetime import datetime

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
    page_title="AI VAPT Operations Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for professional look
st.markdown("""
<style>
    .main-header {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 0.5rem;
    }
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #16213e;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
        border-bottom: 2px solid #0f3460;
        padding-bottom: 0.3rem;
    }
    .metric-card {
        background: #f8f9fa;
        border-left: 4px solid #0f3460;
        padding: 0.8rem;
        margin: 0.3rem 0;
        border-radius: 0 4px 4px 0;
    }
    .evidence-docker {
        background: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 0.8rem;
        border-radius: 4px;
        font-weight: 600;
    }
    .evidence-simulated {
        background: #fff3cd;
        border: 1px solid #ffeeba;
        color: #856404;
        padding: 0.8rem;
        border-radius: 4px;
        font-weight: 600;
    }
    .evidence-local {
        background: #cce5ff;
        border: 1px solid #b8daff;
        color: #004085;
        padding: 0.8rem;
        border-radius: 4px;
        font-weight: 600;
    }
    .evidence-controlled {
        background: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
        padding: 0.8rem;
        border-radius: 4px;
        font-weight: 600;
    }
    .ai-badge {
        background: #e7f3ff;
        border: 1px solid #b8daff;
        color: #004085;
        padding: 0.2rem 0.5rem;
        border-radius: 3px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .fallback-badge {
        background: #fff3cd;
        border: 1px solid #ffeeba;
        color: #856404;
        padding: 0.2rem 0.5rem;
        border-radius: 3px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .pivot-event {
        background: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 0.5rem;
        border-radius: 4px;
        margin: 0.3rem 0;
        font-weight: 500;
    }
    .success-event {
        background: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 0.5rem;
        border-radius: 4px;
        margin: 0.3rem 0;
        font-weight: 500;
    }
    .trace-event {
        background: #f8f9fa;
        border-left: 3px solid #6c757d;
        padding: 0.4rem 0.8rem;
        margin: 0.2rem 0;
        font-family: monospace;
        font-size: 0.85rem;
    }
    .safety-box {
        background: #e2e3e5;
        border: 1px solid #d6d8db;
        color: #383d41;
        padding: 0.8rem;
        border-radius: 4px;
        font-size: 0.9rem;
    }
    .event-timeline {
        border-left: 3px solid #0f3460;
        margin-left: 1rem;
        padding-left: 1rem;
    }
    .event-item {
        margin: 0.5rem 0;
        padding: 0.5rem;
        background: #f8f9fa;
        border-radius: 4px;
    }
    .run-history-table {
        width: 100%;
        border-collapse: collapse;
    }
    .run-history-row {
        border-bottom: 1px solid #dee2e6;
        padding: 0.5rem 0;
    }
    .status-completed {
        color: #28a745;
        font-weight: 600;
    }
    .status-failed {
        color: #dc3545;
        font-weight: 600;
    }
    .status-running {
        color: #007bff;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


def main():
    """Main dashboard entry point."""
    # Header
    st.markdown(
        '<div class="main-header">🛡️ AI VAPT Operations Dashboard</div>',
        unsafe_allow_html=True,
    )
    st.caption("State-aware bounded failure-threshold pivoting for controlled VAPT validation")

    # Sidebar navigation
    with st.sidebar:
        st.markdown("### 📊 Navigation")
        view = st.radio(
            "View",
            ["New Assessment", "Run History"],
            label_visibility="collapsed",
        )

    if view == "New Assessment":
        show_new_assessment()
    elif view == "Run History":
        show_run_history()


def show_new_assessment():
    """Configure and execute a new assessment."""
    # Sidebar configuration
    with st.sidebar:
        st.markdown("### ⚙️ Configuration")

        # Execution mode
        mode = st.radio(
            "Execution Mode",
            ["Docker Lab", "Loopback", "Simulation"],
            help="Docker Lab = real HTTP to emulator | Loopback = local | Simulation = ground-truth labels",
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
            help="deterministic = offline | AI = requires Ollama",
        )

        max_attempts = st.slider("Pivot Threshold (N)", 1, 5, 2)

        st.markdown("---")

        # Safety status
        st.markdown("### 🔒 Safety Status")
        if mode == "Docker Lab":
            st.success("✅ ALLOWLISTED")
            st.caption("Target: 172.28.0.2 (Docker emulator)")
        elif mode == "Loopback":
            st.info("🔵 LOOPBACK")
            st.caption("Target: 127.0.0.1")
        else:
            st.warning("🟡 SIMULATION")
            st.caption("No real execution")

        st.markdown("---")

        # Run button
        run_clicked = st.button("🚀 Run Assessment", type="primary", use_container_width=True)

    # Main dashboard area
    if run_clicked:
        execute_assessment(
            mode=mode,
            target=target,
            port=port,
            path=path,
            scenario_name=scenario_name,
            assessor_mode=assessor_mode,
            max_attempts=max_attempts,
            scan_file_obj=scan_file_obj,
        )
    else:
        show_welcome()


def show_welcome():
    """Show welcome/info screen before run."""
    st.info("👈 Configure your assessment in the sidebar and click **Run Assessment** to begin.")

    st.markdown("### 📋 Quick Start")
    st.markdown("""
    1. Select **Docker Lab** mode for real HTTP execution
    2. Choose a scenario (e.g., `docker_pivot`)
    3. Select **AI** assessor for LLM-based grading
    4. Click **Run Assessment**
    """)

    st.markdown("### 🔬 Research Contribution")
    st.markdown("""
    This platform demonstrates **state-aware bounded failure-threshold pivoting**:
    - Per-candidate attempt counting
    - Configurable failure threshold
    - Automatic pivot to next candidate
    - Bounded termination
    """)


def execute_assessment(
    mode: str,
    target: str | None,
    port: int,
    path: str,
    scenario_name: str,
    assessor_mode: str,
    max_attempts: int,
    scan_file_obj,
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
        max_attempts=max_attempts,
        scan_file=scan_file_path,
    )

    # Run with spinner
    with st.spinner("Running assessment..."):
        application = get_application()
        result = application.run(request)

    # Display results
    display_run_details(result, mode, from_history=False)


def show_run_history():
    """Show run history from the canonical persistence layer."""
    st.markdown('<div class="section-header">📜 Run History</div>', unsafe_allow_html=True)

    # Get runs from repository
    repository = get_repository()
    runs = repository.list_runs(limit=100)

    if not runs:
        st.info("No runs found. Execute an assessment to see results here.")
        return

    # Display run count
    st.caption(f"Total runs: {len(runs)}")

    # Run selection
    run_options = {run.run_id: f"{run.run_id} | {run.scenario} | {run.mode} | {run.status}" for run in runs}
    selected_run_id = st.selectbox(
        "Select a run to view details",
        options=list(run_options.keys()),
        format_func=lambda x: run_options[x],
        label_visibility="collapsed",
    )

    if selected_run_id:
        # Load the selected run
        run = repository.get(selected_run_id)
        if run:
            display_persisted_run_details(run)
        else:
            st.error(f"Run {selected_run_id} not found.")


def display_persisted_run_details(run):
    """Display details of a persisted run."""
    # Header
    st.markdown(f"### 📊 Run: {run.run_id}")
    st.caption(f"Created: {run.created_at} | Updated: {run.updated_at}")

    # Summary cards
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Status", run.status)
    col2.metric("Scenario", run.scenario)
    col3.metric("Mode", run.mode)
    col4.metric("Attempts", run.total_attempts)
    col5.metric("Pivots", run.pivot_count)

    st.markdown("---")

    # Evidence tier
    display_evidence_tier(run.evidence_tier, run.safety_notice)

    st.markdown("---")

    # Tabs for different views
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Overview",
        "⏱️ Timeline",
        "🔍 Findings",
        "🔄 Pivots",
        "📄 Reports",
    ])

    with tab1:
        display_run_overview(run)

    with tab2:
        display_event_timeline(run)

    with tab3:
        display_findings_from_run(run)

    with tab4:
        display_pivots_from_run(run)

    with tab5:
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
        mode_label = run.assessment.get("mode", "unknown")
        provider = run.assessment.get("provider")

        if mode_label == "ai":
            if provider:
                st.markdown(
                    f'<span class="ai-badge">🤖 AI / {provider.upper()}</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<span class="ai-badge">🤖 AI</span>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<span class="fallback-badge">📊 Deterministic</span>',
                unsafe_allow_html=True,
            )

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

    # Get events from event bus
    from vapt_platform.events import get_event_bus
    event_bus = get_event_bus()
    events = event_bus.get_events(run.run_id)

    if not events:
        st.info("No events recorded for this run.")
        return

    # Display events in chronological order
    st.markdown('<div class="event-timeline">', unsafe_allow_html=True)
    for event in events:
        event_type = event.event_type
        timestamp = event.timestamp
        payload = event.payload

        # Determine event styling
        if event_type == EventType.RUN_COMPLETED.value:
            css_class = "success-event"
            icon = "✅"
        elif event_type == EventType.RUN_FAILED.value:
            css_class = "pivot-event"
            icon = "❌"
        elif event_type == EventType.PIVOT_OCCURRED.value:
            css_class = "pivot-event"
            icon = "🔄"
        elif event_type == EventType.EXECUTION_STARTED.value:
            css_class = "event-item"
            icon = "▶️"
        elif event_type == EventType.ATTEMPT_COMPLETED.value:
            outcome = payload.get("outcome", "")
            if outcome == "SUCCESS":
                css_class = "success-event"
                icon = "✅"
            else:
                css_class = "pivot-event"
                icon = "❌"
        else:
            css_class = "event-item"
            icon = "📌"

        # Format event details
        details = ", ".join(f"{k}={v}" for k, v in payload.items()) if payload else ""

        st.markdown(
            f'<div class="{css_class}">'
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
                    f'<div class="success-event">'
                    f"✅ Attempt {i}: {candidate} → {outcome}<br/>"
                    f"<small>{html.escape(detail)}</small>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="pivot-event">'
                    f"❌ Attempt {i}: {candidate} → {outcome}<br/>"
                    f"<small>{html.escape(detail)}</small>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


def display_pivots_from_run(run):
    """Display pivot events from a persisted run."""
    st.markdown('<div class="section-header">Pivot Analysis</div>', unsafe_allow_html=True)

    st.markdown(f"**Threshold:** {run.max_attempts} attempts")
    st.markdown(f"**Pivots:** {run.pivot_count}")

    if run.decision_trace:
        pivots = [log for log in run.decision_trace if "[Pivot]" in log]
        if pivots:
            for p in pivots:
                st.markdown(
                    f'<div class="pivot-event">{html.escape(p)}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No pivot events")
    else:
        st.info("No trace available")


def display_reports_for_run(run):
    """Display report generation options for a persisted run."""
    st.markdown('<div class="section-header">Reports</div>', unsafe_allow_html=True)

    # Generate reports using canonical reporting layer
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


def display_run_details(result, mode: str, from_history: bool = True):
    """Display run details (used for both new runs and history)."""
    domain = result.domain if hasattr(result, "domain") else result

    # Header
    st.markdown(f"### 📊 Assessment Results")
    st.caption(f"Run ID: {domain.run_id} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Summary cards
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Status", domain.final_status)
    col2.metric("Candidates", len(domain.candidates))
    col3.metric("Attempts", domain.total_attempts)
    col4.metric("Pivots", domain.pivot_count)
    col5.metric("Evidence", domain.evidence_tier)

    st.markdown("---")

    # Evidence tier
    display_evidence_tier(domain.evidence_tier, domain.safety_notice)

    st.markdown("---")

    # Two-column layout
    left_col, right_col = st.columns(2)

    with left_col:
        display_findings(result)
        display_candidates(result)

    with right_col:
        display_execution_timeline(result)
        display_pivot_visualization(result)

    st.markdown("---")

    # Decision trace
    display_decision_trace(result)

    st.markdown("---")

    # Reports
    display_reports(result)


def display_evidence_tier(evidence_tier: str, safety_notice: str):
    """Display evidence tier with appropriate styling."""
    if evidence_tier == "DOCKER_OBSERVED":
        st.markdown(
            '<div class="evidence-docker">'
            "🔬 DOCKER_OBSERVED — Outcomes from controlled Docker lab emulator. "
            "Target is allowlisted. No external systems targeted."
            "</div>",
            unsafe_allow_html=True,
        )
    elif evidence_tier == "OBSERVED_LOCAL":
        st.markdown(
            '<div class="evidence-local">'
            "👁️ OBSERVED_LOCAL — Outcomes from loopback (127.0.0.1) target. "
            "No external systems targeted."
            "</div>",
            unsafe_allow_html=True,
        )
    elif evidence_tier == "CONTROLLED_VALIDATION":
        st.markdown(
            '<div class="evidence-controlled">'
            "✅ CONTROLLED_VALIDATION — Outcomes from live target systems. "
            "Ensure proper authorization."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="evidence-simulated">'
            "🟡 SIMULATED — Outcomes from ground-truth labels. No real execution."
            "</div>",
            unsafe_allow_html=True,
        )

    if safety_notice:
        st.markdown(
            f'<div class="safety-box">{html.escape(safety_notice)}</div>',
            unsafe_allow_html=True,
        )


def display_results(result, mode: str):
    """Legacy display function - delegates to display_run_details."""
    display_run_details(result, mode, from_history=False)


def display_findings(result):
    """Display findings panel."""
    domain = result.domain if hasattr(result, "domain") else result
    st.markdown('<div class="section-header">📋 Findings</div>', unsafe_allow_html=True)

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


def display_candidates(result):
    """Display candidate/AI assessment panel."""
    domain = result.domain if hasattr(result, "domain") else result
    st.markdown('<div class="section-header">🤖 AI Assessment</div>', unsafe_allow_html=True)

    # Assessment provenance
    assessment = domain.assessment
    if assessment:
        mode_label = assessment.get("mode", "unknown")
        provider = assessment.get("provider")

        if mode_label == "ai":
            if provider:
                st.markdown(
                    f'<span class="ai-badge">🤖 AI / {provider.upper()}</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<span class="ai-badge">🤖 AI</span>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<span class="fallback-badge">📊 Deterministic</span>',
                unsafe_allow_html=True,
            )

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
    st.markdown('<div class="section-header">⏱️ Execution Timeline</div>', unsafe_allow_html=True)

    if not domain.execution_results:
        st.info("No execution results")
        return

    for i, r in enumerate(domain.execution_results, 1):
        outcome = r.get("outcome", "UNKNOWN")
        candidate = r.get("candidate_id", "Unknown")
        detail = r.get("detail", "")

        if outcome == "SUCCESS":
            st.markdown(
                f'<div class="success-event">'
                f"✅ Attempt {i}: {candidate} → {outcome}<br/>"
                f"<small>{html.escape(detail)}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="pivot-event">'
                f"❌ Attempt {i}: {candidate} → {outcome}<br/>"
                f"<small>{html.escape(detail)}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )


def display_pivot_visualization(result):
    """Display pivot visualization."""
    domain = result.domain if hasattr(result, "domain") else result
    st.markdown('<div class="section-header">🔄 Pivot Analysis</div>', unsafe_allow_html=True)

    st.markdown(f"**Threshold:** {domain.total_attempts} attempts")
    st.markdown(f"**Pivots:** {domain.pivot_count}")

    if domain.decision_trace:
        pivots = [log for log in domain.decision_trace if "[PIVOT]" in log]
        if pivots:
            for p in pivots:
                st.markdown(
                    f'<div class="pivot-event">{html.escape(p)}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No pivot events")
    else:
        st.info("No trace available")


def display_decision_trace(result):
    """Display decision trace."""
    domain = result.domain if hasattr(result, "domain") else result
    st.markdown('<div class="section-header">🔍 Decision Trace</div>', unsafe_allow_html=True)

    if not domain.decision_trace:
        st.info("No trace available")
        return

    with st.expander("View Full Trace", expanded=False):
        for log in domain.decision_trace:
            st.markdown(
                f'<div class="trace-event">{html.escape(log)}</div>',
                unsafe_allow_html=True,
            )


def display_reports(result):
    """Display report download options."""
    domain = result.domain if hasattr(result, "domain") else result
    st.markdown('<div class="section-header">📄 Reports</div>', unsafe_allow_html=True)

    # Generate reports using canonical reporting layer
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


if __name__ == "__main__":
    main()
