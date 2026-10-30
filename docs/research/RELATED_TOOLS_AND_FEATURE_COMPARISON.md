# Literature Review & Feature Comparison: AI-VAPT vs. Commercial & Open-Source Tools

**Project Title:** An Autonomous AI Framework for Vulnerability Assessment: Integrating Exploit Quality Scoring and Dynamic Decision-Pivoting  
**Date:** 26 October 2026  

---

## 1. Comparative Analysis Matrix

| Capability / Feature | OWASP ZAP (v2.14) | Burp Suite Pro (v2024.3) | ProjectDiscovery Nuclei (v3.11) | Astra Pentest | AI-VAPT Framework (This Work) |
|---|---|---|---|---|---|
| **Underlying Approach** | Rule-based DAST Proxy | Commercial DAST & Active Scanner | Community Template Engine | SaaS DAST + Manual Pentest | AI-Guided Autonomous State Machine |
| **Exploit Pre-Assessment (GAP-1)** | ❌ None (rules only) | ❌ None | ❌ None | ❌ None | ✅ **Contextual LLM Scoring ($P \times Q$)** |
| **State-Aware Decision Pivoting (GAP-2)** | ❌ Infinite scan queues | ❌ Rigid tree traversal | ❌ Static template batch | ❌ Manual re-routing | ✅ **Bounded Attempt Threshold ($T \le N \cdot |C|$)** |
| **Inventory Separation** | ⚠️ Mixed alert list | ⚠️ Mixed issue tree | ⚠️ Flat JSONL alerts | ⚠️ Severity-ranked list | ✅ **Strict separation (Actionable vs Asset Inventory)** |
| **Local Offline LLM Execution** | ❌ None | ⚠️ Cloud extension only | ❌ None | ❌ Cloud only | ✅ **Local Ollama with CUDA GPU Offload** |
| **Multi-Provider Hosted AI** | ❌ None | ❌ None | ❌ None | ❌ Proprietary | ✅ **OpenRouter, Google Gemini, OpenAI** |
| **Fail-Closed Scope Governance** | ⚠️ URL filter regex | ⚠️ Scope tree | ❌ Target list only | ⚠️ Domain registration | ✅ **Authoritative Backend Allowlist + RoE tracking** |
| **Active Cryptographic Proof** | ❌ None | ⚠️ Response matcher | ⚠️ Grep match | ⚠️ Screenshot/HTML | ✅ **SHA-256 Hashed Evidence & Curl Replay** |
| **Multi-Format Export & Manifest** | HTML / XML | HTML / XML | JSONL / Markdown | PDF / Executive Summary | ✅ **JSON, HTML, Markdown, TXT, Cryptographic Manifest** |

---

## 2. Theoretical Deficiencies in Existing Tools

1. **Static Quality Ranking:** Tools like ZAP and Burp Suite prioritize vulnerabilities based strictly on CVSS base scores. However, CVSS measures theoretical impact, not real-world exploit usability. A CVSS 9.8 flaw with no functional exploit script is practically less urgent than an actively exploited CVSS 7.5 flaw. AI-VAPT bridges this gap with GAP-1.
2. **Brittle Scanner Traversal:** When automated tools hit web application firewalls (WAFs) or defensive rate-limiters, they frequently exhaust rate quotas or stall indefinitely. AI-VAPT's GAP-2 failure-threshold pivoting formally guarantees termination in $O(N \cdot |C|)$ steps.
3. **Data Contamination:** In standard scanners, technology banners (`nginx/1.31.8`) and missing non-critical headers are presented in the same queue as critical RCEs. AI-VAPT rigorously partitions observations into:
   - **Service Discovery & Informational Inventory:** Asset context preserved for reports.
   - **Actionable Candidates:** Evaluated by the AI decision engine.
   - **Confirmed Findings:** Validated with cryptographic and structural proof.

