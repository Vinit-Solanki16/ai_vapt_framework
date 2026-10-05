# Juice Shop Live Demo — Click Sequence (Phase 32)

AUTHORIZED LOCAL TARGET ONLY. Do not scan public/internet targets.

## Prerequisites

```bash
# 1. Juice Shop running locally (expect HTTP 200)
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9191/

# 2. Nmap installed (expect version line)
nmap --version | head -1

# 3. Ollama + model (expect llama3.2:3b)
ollama list | grep llama3.2:3b

# 4. Backend running (this repo's FastAPI; example port 8000)
python3 -m uvicorn services.api:app --host 127.0.0.1 --port 8000
```

Nuclei is intentionally NOT required: the UI reports it as NOT AVAILABLE
and the run proceeds with Nmap discovery.

## Click sequence

1. Open Juice Shop in a browser tab: `http://127.0.0.1:9191`
   (confirms the target is the local training app).
2. Open AI-VAPT: `http://127.0.0.1:8000/` (backend serves the console).
3. Click **New Assessment**.
4. Set **Assessment Type** → **Web Application**.
5. **Target URL** already shows `http://127.0.0.1:9191` — leave it
   (or paste it). Click **Validate**.
6. Authorization becomes: **✅ AUTHORIZED LOCAL TARGET**
   (detail: `HTTP 200 from http://127.0.0.1:9191 — resolved 127.0.0.1:9191`).
   Safety shows **AUTHORIZED**.
7. Scanners: ☑ Nmap (READY). Nuclei shows NOT AVAILABLE (expected here).
8. Assessor: **Ollama**, Model: **llama3.2:3b**, Pivot Threshold: **2**.
9. Click **🛡️ START VAPT ASSESSMENT** (Nmap discovery takes ~10–15 s).
10. Result card shows the live pipeline stages:
    TARGET ✓ → DISCOVERY ✓ (Nmap) → VULN SCAN (Nuclei: NOT AVAILABLE) →
    FINDINGS (1) → NORMALIZATION ✓ → ENRICHMENT ✓ →
    AI ASSESSMENT ✓ (ollama / llama3.2:3b) → RANKING ✓ → DECISION ✓ →
    SAFETY ✓ → VALIDATION (NOT AVAILABLE — scanner-detected) →
    EVIDENCE ✓ (OBSERVED_LOCAL) → REPORT ✓.
11. Findings table: 1 row — `sun-as-jpda` open port 9191, source `nmap-xml`,
    AI quality rank + reasoning, validation status
    `VALIDATION NOT AVAILABLE`. (Note: `sun-as-jpda` is Nmap's banner-based
    fingerprint label; the HTTP 200 body is Juice Shop.)
12. EPSS/KEV/CVSS/CWE columns: `—` for a port-discovery finding with no CVE
    (honest: no intelligence where none exists).
13. Download the report (JSON/MD) — it records target, scanners, AI model,
    evidence tier, and the scanner≠exploit limitation.
14. Open **Run History**: the web run shows target URL, `WEB` badge,
    finding count, AI provider, status, evidence, attempts, pivots.
15. Separately run scenario **failure_pivot** (Research Scenario type) to
    demonstrate GAP-2 (attempt → failure → threshold → pivot).

## Negative demo (safety)

Paste `https://example.com` → **❌ REJECTED — TARGET NOT AUTHORIZED**,
START is blocked client-side and `POST /runs` returns HTTP 400 server-side;
no scanner process is ever spawned (covered by automated tests).

## Exact verification commands (no GUI)

```bash
# Preflight (no scan)
curl -s -X POST http://127.0.0.1:8000/targets/validate \
  -H 'Content-Type: application/json' \
  -d '{"target_url":"http://127.0.0.1:9191"}'

# Scanner availability
curl -s http://127.0.0.1:8000/scanners/status

# Full web assessment (deterministic assessor, fast)
curl -s -X POST http://127.0.0.1:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"web_target","mode":"web","assessment_type":"web",
       "target_url":"http://127.0.0.1:9191","assessor":"deterministic",
       "assessor_provider":"ollama","max_attempts":2}'

# Rejection proof
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"web_target","mode":"web","assessment_type":"web",
       "target_url":"https://example.com","assessor":"deterministic",
       "assessor_provider":"ollama","max_attempts":2}'
```
