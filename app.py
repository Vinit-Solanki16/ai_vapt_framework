"""Streamlit dashboard: live VAPT operations view (Phase 3, Tasks 3.1-3.3)."""
from __future__ import annotations

import json
import os
import tempfile

import streamlit as st

from core.scanner import process_scan
from core.agent_graph import run_agent
from core.schemas import Finding, UsabilityRank, findings_from_state
from core.report import build_report, save_json, save_pdf

st.set_page_config(page_title="AI VAPT Framework", page_icon="🛡️", layout="wide")
st.title("🛡️ Autonomous AI VAPT Framework")
st.caption("State-aware VA/PT with Exploit Quality Scoring & Dynamic Decision-Pivoting")

# ---------------- Sidebar ----------------
st.sidebar.header("⚙️ Configuration")
provider = st.sidebar.radio("LLM Provider", ["Ollama", "OpenAI"])
api_key = ""
if provider == "OpenAI":
    api_key = st.sidebar.text_input("OpenAI API Key", type="password",
                                    value=os.getenv("OPENAI_API_KEY", ""))
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
else:
    st.sidebar.info("Local Ollama (llama3.2:3b). Ensure `ollama serve` is running.")

st.sidebar.markdown("---")
max_attempts = st.sidebar.slider("Pivot Failure Threshold (N)", 1, 5, 2)
mode = st.sidebar.radio("Execution Mode", ["simulation", "real"],
                        help="simulation = ground-truth labels; real = live safe probe")
st.sidebar.markdown("---")
st.sidebar.write("**Literature basis**")
st.sidebar.caption("Paul et al. 2024 (EPSS enrichment) · Lu et al. 2024 "
                   "(PoC quality) · Deng et al. 2025 (Type-B pivot)")

# ---------------- Tabs ----------------
tab1, tab2 = st.tabs(["📊 Scan Data", "🤖 Autonomous Agent Pipeline"])

with tab1:
    st.subheader("1. Ingest Vulnerability Scan Results")
    uploaded = st.file_uploader("Upload Scanner Output (Nmap XML / JSON)", type=["xml", "json"])
    findings: list[Finding] = []
    if uploaded is not None:
        suffix = ".xml" if uploaded.name.endswith(".xml") else ".json"
        with tempfile.NamedTemporaryFile("wb", suffix=suffix, delete=False) as tf:
            tf.write(uploaded.read())
            tmp_path = tf.name
        findings = process_scan(tmp_path)
        os.unlink(tmp_path)
        st.session_state["findings"] = [f.model_dump() for f in findings]
    else:
        st.info("Using default data/sample_scan.json")
        if os.path.exists("data/sample_scan.json"):
            findings = process_scan("data/sample_scan.json")
            st.session_state["findings"] = [f.model_dump() for f in findings]

    if findings:
        rows = [{"CVE": f.cve, "Port": f.port, "Service": f.service,
                 "EPSS": f"{f.epss_score:.4f}"} for f in findings]
        st.dataframe(rows, use_container_width=True)

with tab2:
    st.subheader("2. Execute VAPT Workflow")
    if st.button("🚀 Start Autonomous Assessment", type="primary"):
        if "findings" not in st.session_state or not st.session_state["findings"]:
            st.warning("Load scan data in Tab 1 first.")
        else:
            with st.spinner("Running agent graph (assess → execute → pivot)..."):
                final = run_agent(
                    "127.0.0.1", st.session_state["findings"],
                    provider=provider.lower(), max_attempts=max_attempts, mode=mode,
                )
            fs = findings_from_state(final["findings"])

            st.subheader("Live Agent Execution Feed")
            st.markdown("<br>".join([f"<code>{l}</code>" for l in final["logs"]]),
                        unsafe_allow_html=True)

            st.subheader("Execution Outcomes")
            orows = [{"CVE": f.cve, "Usability": f.usability_rank.value if f.usability_rank else "-",
                      "Outcome": f.execution_outcome.value if f.execution_outcome else "-",
                      "EPSS": f"{f.epss_score:.4f}"} for f in fs]
            st.dataframe(orows, use_container_width=True)

            report = build_report("127.0.0.1", fs, final["logs"], final["results"],
                                  provider.lower(), mode, max_attempts)
            st.subheader("Run Summary")
            st.json(report["summary"])

            json_path = save_json(report)
            pdf_path = save_pdf(report)
            c1, c2 = st.columns(2)
            with open(json_path, "rb") as f:
                c1.download_button("⬇️ Download JSON Report", f, file_name="vapt_report.json")
            with open(pdf_path, "rb") as f:
                c2.download_button("⬇️ Download PDF Report", f, file_name="vapt_report.pdf")
