"""Professional AI-VAPT Dashboard.

A security-focused interface for the canonical VAPT application workflow.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime

import streamlit as st

from vapt_platform.application import VAPTRequest, get_application
from vapt_platform.assessment import create_assessor
from prototype.docker_demo_data import DOCKER_SCENARIOS
from prototype.demo_data import SCENARIOS
from prototype.report_generator import (
    generate_json_report,
    generate_text_report,
    generate_html_report,
    generate_markdown_report,
)

# All scenarios
ALL_SCENARIOS = {**SCENARIOS, **DOCKER_SCENARIOS}

# Page config
st.set_page_config(
    page_title="AI-VAPT Dashboard",
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
</style>
""", unsafe_allow_html=True)


def main():
    """Main dashboard entry point."""
    # Header
    st.markdown('<div class="main-header">🛡️ AI-Assisted Vulnerability Assessment</div>', unsafe_allow_html=True)
    st.caption("State-aware bounded failure-threshold pivoting for controlled VAPT validation")

    # Sidebar
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
        run_dashboard(
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


def run_dashboard(
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
    display_results(result, mode)


def display_results(result, mode: str):
    """Display assessment results."""
    # Access domain result
    domain = result.domain if hasattr(result, 'domain') else result
    
    # Status header
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
    if domain.evidence_tier == "DOCKER_OBSERVED":
        st.markdown(
            '<div class="evidence-docker">'
            "🔬 DOCKER_OBSERVED — Outcomes from controlled Docker lab emulator. "
            "Target is allowlisted. No external systems targeted."
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


def display_findings(result):
    """Display findings panel."""
    domain = result.domain if hasattr(result, 'domain') else result
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
            if c.get('execution_outcome'):
                st.markdown(f"**Outcome:** `{c.get('execution_outcome')}`")


def display_candidates(result):
    """Display candidate/AI assessment panel."""
    domain = result.domain if hasattr(result, 'domain') else result
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
    domain = result.domain if hasattr(result, 'domain') else result
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
                f"<small>{detail}</small>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="pivot-event">'
                f"❌ Attempt {i}: {candidate} → {outcome}<br/>"
                f"<small>{detail}</small>"
                "</div>",
                unsafe_allow_html=True,
            )


def display_pivot_visualization(result):
    """Display pivot visualization."""
    domain = result.domain if hasattr(result, 'domain') else result
    st.markdown('<div class="section-header">🔄 Pivot Analysis</div>', unsafe_allow_html=True)

    st.markdown(f"**Threshold:** {domain.total_attempts} attempts")
    st.markdown(f"**Pivots:** {domain.pivot_count}")

    if domain.decision_trace:
        pivots = [log for log in domain.decision_trace if "[PIVOT]" in log]
        if pivots:
            for p in pivots:
                st.markdown(
                    f'<div class="pivot-event">{p}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No pivot events")
    else:
        st.info("No trace available")


def display_decision_trace(result):
    """Display decision trace."""
    domain = result.domain if hasattr(result, 'domain') else result
    st.markdown('<div class="section-header">🔍 Decision Trace</div>', unsafe_allow_html=True)

    if not domain.decision_trace:
        st.info("No trace available")
        return

    with st.expander("View Full Trace", expanded=False):
        for log in domain.decision_trace:
            st.markdown(
                f'<div class="trace-event">{log}</div>',
                unsafe_allow_html=True,
            )


def display_reports(result):
    """Display report download options."""
    domain = result.domain if hasattr(result, 'domain') else result
    st.markdown('<div class="section-header">📄 Reports</div>', unsafe_allow_html=True)

    # Generate reports
    final_state = {
        "candidates": domain.candidates,
        "results": domain.execution_results,
        "logs": domain.decision_trace,
        "_presentation": {
            "total_attempts": domain.total_attempts,
            "pivot_count": domain.pivot_count,
            "candidates_processed": domain.candidates_processed,
        },
        "_assessment": domain.assessment,
    }

    json_report = generate_json_report(domain.scenario, final_state, 2, domain.mode)
    txt_report = generate_text_report(domain.scenario, final_state, 2, domain.mode)
    html_report = generate_html_report(domain.scenario, final_state, 2, domain.mode)
    md_report = generate_markdown_report(domain.scenario, final_state, 2, domain.mode)

    col1, col2, col3, col4 = st.columns(4)
    col1.download_button("⬇️ JSON", json_report, file_name="report.json")
    col2.download_button("⬇️ Text", txt_report, file_name="report.txt")
    col3.download_button("⬇️ HTML", html_report, file_name="report.html")
    col4.download_button("⬇️ Markdown", md_report, file_name="report.md")


if __name__ == "__main__":
    main()
