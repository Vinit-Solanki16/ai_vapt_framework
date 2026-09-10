"""Streamlit frontend for the decision engine.

Provides:
- Scenario selection (success / failure_pivot / multi_candidate / corpus)
- Scan file ingestion (upload .xml or .json, run through engine)
- Mode selection (simulation / lab)
- Lab target dropdown (allowlisted only)
- Candidate ranking table
- Execution timeline
- Attempt counters
- Pivot event markers
- Decision trace
- Final report with evidence tier
- HTML / Markdown report download buttons
"""
from __future__ import annotations

import json
import tempfile

import streamlit as st

from decision_engine.core.engine import run_engine
from decision_engine.core.executor import Executor
from decision_engine.core.schemas import candidate_from_dict
from decision_engine.core.assessor import deterministic_assessor

from prototype.demo_data import SCENARIOS
from prototype.engine_integration import (
    load_vapt_corpus_scenario,
    run_scan_file,
)
from prototype.execution_layer import create_simulation_executor, create_lab_executor
from prototype.report_generator import (
    generate_html_report,
    generate_json_report,
    generate_markdown_report,
    generate_text_report,
)
from prototype.trace_formatter import (
    format_engine_trace,
    format_candidate_ranking,
    format_execution_results,
)

st.set_page_config(page_title="AI VAPT Decision Engine", page_icon="🛡️", layout="wide")
st.title("🛡️ AI VAPT Decision Engine")
st.caption("Domain-independent decision engine with bounded retry & pivot")

# --- Sidebar ---
st.sidebar.header("⚙️ Run Configuration")
tab_mode = st.sidebar.radio(
    "Mode",
    ["Demo Scenario", "Scan Ingestion"],
    help="Demo = built-in scenarios; Scan = upload scan file for enrichment + execution",
)

scan_file_obj = None
scan_run_id = None
scenario_name = None
max_attempts = 2
mode = "simulation"
assessor_name = "deterministic"
target = None
scan_max_attempts = 2

if tab_mode == "Demo Scenario":
    scenario_name = st.sidebar.selectbox(
        "Scenario",
        list(SCENARIOS.keys()) + ["corpus"],
        help="Select a demo scenario or load from the VAPT corpus",
    )
    max_attempts = st.sidebar.slider("Pivot Threshold (N)", 1, 5, 2)
    mode = st.sidebar.radio(
        "Execution Mode",
        ["simulation", "lab"],
        help="simulation = ground-truth labels; lab = DOCKER OBSERVED against emulator",
    )

    target = None
    if mode == "lab":
        target = st.sidebar.selectbox(
            "Lab Target",
            ["127.0.0.1", "172.28.0.2"],
            help="Allowlisted targets only — no free-text input",
        )
        st.sidebar.warning("⚠️ LAB MODE: Outcomes are DOCKER OBSERVED from the emulator, not simulated.")

    assessor_name = st.sidebar.radio(
        "Assessor",
        ["deterministic", "llm"],
        help="deterministic = offline fallback; llm = requires Ollama",
    )
else:
    # --- Scan Ingestion tab ---
    st.sidebar.subheader("📁 Scan Upload")
    scan_file_obj = st.sidebar.file_uploader(
        "Upload Scan File",
        type=["xml", "json"],
        help="Accepts Nmap XML, Nmap JSON, or custom JSON (sample_scan.json schema)",
    )
    scan_max_attempts = st.sidebar.slider("Pivot Threshold (N)", 1, 5, 2)
    scan_mode = st.sidebar.radio(
        "Execution Mode",
        ["simulation"],
        help="Scan ingestion runs in simulation mode (EPSS-enriched candidates)",
    )

    scenario_name = None
    max_attempts = scan_max_attempts
    mode = scan_mode
    assessor_name = "deterministic"
    target = None

# --- Safety indicator ---
if mode == "lab":
    st.sidebar.success("🟡 LAB MODE (DOCKER OBSERVED)")
else:
    st.sidebar.info("🔵 SIMULATION MODE")

st.sidebar.markdown("---")
st.sidebar.write("**Literature basis**")
st.sidebar.caption("Paul et al. 2024 (EPSS) · Lu et al. 2024 (PoC quality) · Deng et al. 2025 (pivot)")

# --- Main area ---
final_state = None
source_label = None

if tab_mode == "Demo Scenario":
    if st.button("🚀 Run Decision Engine", type="primary"):
        # Load candidates
        if scenario_name == "corpus":
            candidates = load_vapt_corpus_scenario()
        else:
            fn, kwargs = SCENARIOS[scenario_name]
            candidates = fn(**kwargs)

        # Build executor
        if mode == "lab" and target:
            executor = create_lab_executor(target, 8080)
        else:
            executor = create_simulation_executor()

        # Run engine
        with st.spinner("Running decision engine (assess → execute → pivot)..."):
            final_state = run_engine(
                candidates,
                assess_fn=deterministic_assessor if assessor_name == "deterministic" else None,
                executor=executor,
                max_attempts=max_attempts,
                mode=mode,
            )
        source_label = scenario_name

elif tab_mode == "Scan Ingestion":
    if scan_file_obj is not None:
        if st.button("🔍 Ingest Scan & Run Engine", type="primary"):
            with st.spinner("Parsing scan file, enriching with EPSS, running engine..."):
                # Save uploaded file to temp
                suffix = ".xml" if scan_file_obj.name.endswith(".xml") else ".json"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(scan_file_obj.read())
                    tmp_path = tmp.name

                with st.spinner("Running real engine on scan results..."):
                    final_state = run_scan_file(tmp_path, max_attempts=scan_max_attempts, mode="simulation")
                source_label = f"scan:{scan_file_obj.name}"

                # Show raw findings before engine run
                from decision_engine.adapters.scan_adapter import candidates_from_scan

                findings = candidates_from_scan(tmp_path)

                st.subheader("📋 Parsed & Enriched Findings")
                st.caption("Display only — no direct execution. Data sourced from uploaded scan file.")

                # Build a summary table for display
                rows = []
                for c in findings:
                    # Extract metadata from engine's final_state if available
                    rows.append({
                        "id": c.id,
                        "probability": c.probability,
                        "quality_rank": c.quality_rank.value if c.quality_rank else "PENDING",
                        "assessed": c.assessed,
                        "attempted": c.attempted,
                        "execution_outcome": c.execution_outcome.value if c.execution_outcome else "-",
                        "ground_truth": c.ground_truth.value if c.ground_truth else "-",
                    })

                if rows:
                    import pandas as pd
                    df = pd.DataFrame(rows)

                    # Severity badge styling
                    def _sev_color(val):
                        colors = {
                            "critical": "red",
                            "high": "orange",
                            "medium": "yellow",
                            "low": "green",
                            "informational": "grey",
                            "unknown": "grey",
                            "none": "grey",
                        }
                        return colors.get(str(val).lower(), "grey")

                    # Show as a styled dataframe
                    st.dataframe(
                        df,
                        use_container_width=True,
                        hide_index=True,
                    )

                    # Per-finding detail
                    with st.expander("View Detailed Findings", expanded=False):
                        for r in rows:
                            st.markdown(f"**`{r['id']}`**")
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("EPSS", f"{r['probability']:.4f}")
                            c2.metric("Quality", r["quality_rank"])
                            c3.metric("Outcome", r["execution_outcome"])
                            c4.metric("Attempts", "✅" if r["attempted"] else "—")
                            st.markdown("---")
                else:
                    st.info("No findings extracted from scan file.")

                # Now show engine results
                if final_state:
                    st.markdown("---")
                    st.subheader("🏁 Engine Execution Result")

                    # Evidence tier badge
                    st.info("**EVIDENCE TIER: SIMULATED** — outcomes from ground-truth labels (scan ingestion uses simulation mode)")

                    # Final result metrics
                    status = final_state.get("status", "UNKNOWN")
                    presentation = final_state.get("_presentation", {})
                    total_attempts = presentation.get("total_attempts", 0)
                    pivot_count = presentation.get("pivot_count", 0)
                    candidates_processed = presentation.get("candidates_processed", [])

                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Status", status)
                    col2.metric("Total Attempts", total_attempts)
                    col3.metric("Pivot Count", pivot_count)
                    col4.metric("Candidates Processed", len(candidates_processed))

                    # Candidate ranking table
                    st.subheader("📊 Candidate Ranking")
                    ranking_text = format_candidate_ranking(final_state)
                    st.text(ranking_text)

                    # Execution results
                    st.subheader("⚙️ Engine Execution")
                    results_text = format_execution_results(final_state)
                    st.text(results_text)

                    # Decision trace
                    st.subheader("🔍 Decision Trace")
                    trace_text = format_engine_trace(final_state)
                    st.text(trace_text)

                    # Report download buttons (HTML + Markdown + JSON + Text)
                    st.markdown("---")
                    st.subheader("📄 Reports")
                    json_report = generate_json_report(source_label, final_state, scan_max_attempts, "simulation")
                    txt_report = generate_text_report(source_label, final_state, scan_max_attempts, "simulation")
                    html_report = generate_html_report(source_label, final_state, scan_max_attempts, "simulation")
                    md_report = generate_markdown_report(source_label, final_state, scan_max_attempts, "simulation")

                    c1, c2, c3, c4 = st.columns(4)
                    c1.download_button("⬇️ Download JSON", json_report, file_name="report.json")
                    c2.download_button("⬇️ Download Text", txt_report, file_name="report.txt")
                    c3.download_button("⬇️ Download HTML", html_report, file_name="report.html")
                    c4.download_button("⬇️ Download Markdown", md_report, file_name="report.md")

                    with st.expander("View JSON Report"):
                        st.json(json_report)

    else:
        st.info("👈 Upload a scan file (.xml or .json) in the sidebar to begin.")

# --- Safety notice ---
st.markdown("---")
st.subheader("🛡️ Safety Notice")
if mode == "lab":
    st.warning(
        "LAB MODE (DOCKER OBSERVED): Outcomes are from the Docker-isolated emulator. "
        "Target is allowlisted. No external systems were targeted."
    )
elif tab_mode == "Scan Ingestion":
    st.info(
        "SCAN INGESTION (DISPLAY ONLY): Scan findings are enriched with EPSS scores and "
        "processed through the engine in simulation mode. No real exploits are executed. "
        "No external systems are targeted."
    )
else:
    st.info(
        "SIMULATION MODE: Outcomes are resolved from supplied demo ground truth. "
        "No real vulnerabilities were validated."
    )