# Role: Full-Stack Security UI Developer
Refactor `app.py` into a live VAPT operations dashboard.

## Technical Requirements
1. Sidebar: Ollama/OpenAI toggle, OpenAI API key input, Pivot Threshold slider (default 2), execution-mode radio (simulation/real).
2. Tab 1 (Scan Data): file uploader for Nmap XML/JSON; render findings as a dataframe with CVE/port/service/EPSS.
3. Tab 2 (Live Agent): "Start Autonomous Assessment" button; stream `AgentState["logs"]` as a live terminal feed; show per-finding outcomes; emit JSON + PDF report with download buttons (core/report.py).

## Done criteria
- `streamlit run app.py` launches; uploading live_scan.xml and running the agent shows live logs + downloadable reports.
