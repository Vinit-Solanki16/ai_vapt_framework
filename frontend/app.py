"""Streamlit frontend for the decision engine.

Provides:
- Scenario selection (success / failure_pivot / multi_candidate / corpus)
- Mode selection (simulation / lab)
- Lab target dropdown (allowlisted only)
- Candidate ranking table
- Execution timeline
- Attempt counters
- Pivot event markers
- Decision trace
- Final report with evidence tier
"""
from __future__ import annotations

import streamlit as st

from decision_engine.core.engine import run_engine
from decision_engine.core.executor import Executor
from decision_engine.core.schemas import candidate_from_dict
from decision_engine.core.assessor import deterministic_assessor

from prototype.demo_data import SCENARIOS
from prototype.engine_integration import load_vapt_corpus_scenario
from prototype.execution_layer import create_simulation_executor, create_lab_executor
from prototype.report_generator import generate_json_report, generate_text_report
from prototype.trace_formatter import format_engine_trace, format_candidate_ranking, format_execution_results

st.set_page_config(page_title="AI VAPT Decision Engine", page_icon="🛡️", layout="wide")
st.title("🛡️ AI VAPT Decision Engine")
st.caption("Domain-independent decision engine with bounded retry & pivot")

# --- Sidebar ---
st.sidebar.header("⚙️ Run Configuration")
scenario_name = st.sidebar.selectbox(
    "Scenario",
    list(SCENARIOS.keys()) + ["corpus"],
    help="Select a demo scenario or load from the VAPT corpus",
)
max_attempts = st.sidebar.slider("Pivot Threshold (N)", 1, 5, 2)
mode = st.sidebar.radio(
    "Execution Mode",
    ["simulation", "lab"],
    help="simulation = ground-truth labels; lab = OBSERVED against Docker emulator",
)

target = None
if mode == "lab":
    target = st.sidebar.selectbox(
        "Lab Target",
        ["127.0.0.1", "172.28.0.2"],
        help="Allowlisted targets only — no free-text input",
    )
    st.sidebar.warning("⚠️ LAB MODE: Outcomes are OBSERVED from the emulator, not simulated.")

assessor_name = st.sidebar.radio(
    "Assessor",
    ["deterministic", "llm"],
    help="deterministic = offline fallback; llm = requires Ollama",
)

# --- Safety indicator ---
if mode == "lab":
    st.sidebar.success("🟡 LAB MODE (OBSERVED)")
else:
    st.sidebar.info("🔵 SIMULATION MODE")

st.sidebar.markdown("---")
st.sidebar.write("**Literature basis**")
st.sidebar.caption("Paul et al. 2024 (EPSS) · Lu et al. 2024 (PoC quality) · Deng et al. 2025 (pivot)")

# --- Main area ---
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

    # --- Results ---
    st.markdown("---")

    # Evidence tier badge
    if mode == "lab":
        st.success("**EVIDENCE TIER: OBSERVED** — outcomes from Docker emulator (real HTTP)")
    else:
        st.info("**EVIDENCE TIER: SIMULATION** — outcomes from ground-truth labels")

    # Candidate ranking
    st.subheader("📊 Candidate Ranking")
    st.text(format_candidate_ranking(final_state))

    # Execution results
    st.subheader("⚙️ Engine Execution")
    st.text(format_execution_results(final_state))

    # Decision trace
    st.subheader("🔍 Decision Trace")
    st.text(format_engine_trace(final_state))

    # Final result
    st.subheader("🏁 Final Result")
    status = final_state.get("status", "UNKNOWN")
    presentation = final_state.get("_presentation", {})
    col1, col2, col3 = st.columns(3)
    col1.metric("Status", status)
    col2.metric("Total Attempts", presentation.get("total_attempts", 0))
    col3.metric("Pivot Count", presentation.get("pivot_count", 0))

    st.markdown("---")
    st.subheader("📄 Report")
    json_report = generate_json_report(scenario_name, final_state, max_attempts, mode)
    txt_report = generate_text_report(scenario_name, final_state, max_attempts, mode)

    col1, col2 = st.columns(2)
    col1.download_button("⬇️ Download JSON", json_report, file_name="report.json")
    col2.download_button("⬇️ Download Text", txt_report, file_name="report.txt")

    with st.expander("View JSON Report"):
        st.json(json_report)
