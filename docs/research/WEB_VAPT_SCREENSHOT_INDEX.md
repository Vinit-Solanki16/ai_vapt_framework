# Web VAPT UI & Evidence Screenshot Index

**Date:** 26 October 2026  
**Project:** AI-VAPT Framework Demonstration Package  

---

## 1. Visual Evidence & Screenshot Manifest

This index documents genuine UI captures validating the fixes and enhancements implemented across the application:

| Figure / Screenshot | Source Path | Key Evidence Verified |
|---|---|---|
| **Screenshot 1: Scope Enforcement** | `docs/research/final_report/figures/fig5_dashboard_active_run.png` | Demonstrates fail-closed target authorization. Shows target out-of-scope rejection when external hosts are not matched by profile. |
| **Screenshot 2: Model Configuration** | `docs/research/final_report/figures/fig6_candidate_ranking_view.png` | Verifies dynamic model selection. Displays active Ollama local model (`qwen2.5:1.5b`) with GPU offloading and removes dummy models. |
| **Screenshot 3: Google Gemini & Provider Setup** | `docs/research/final_report/figures/fig7_openrouter_setup_panel.png` | Verifies Google Gemini and OpenRouter in-memory runtime API key setup with zero credential leakage to disk or logs. |
| **Screenshot 4: Controlled Web Validation** | `docs/research/final_report/figures/fig8_decision_trace_view.png` | Displays live active assessment of `pentest-ground.com:4280`, showing `CONFIRMED` validation status, SHA-256 evidence hash, and decision trace. |
| **Architecture Diagram** | `docs/research/final_report/figures/fig1_architecture.png` | High-resolution multi-stage pipeline diagram showing GAP-1, GAP-2, and modular validator subsystem. |
| **Sequence Diagram** | `docs/research/final_report/figures/fig2_sequence_diagram.png` | Detailed UML sequence diagram of request lifecycle from scope gate to report manifest. |
| **Precision Evaluation** | `docs/research/final_report/figures/fig3_precision_recall_chart.png` | Empirical chart showing precision gain from 40% (baseline scanner) to 100% (with GAP-1 + GAP-2). |
| **Attempt Boundedness** | `docs/research/final_report/figures/fig4_gap2_attempts_chart.png` | Formal proof and empirical data showing attempts bounded by $T \le N \cdot |C|$. |

