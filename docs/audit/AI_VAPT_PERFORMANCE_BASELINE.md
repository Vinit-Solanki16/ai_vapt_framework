# AI-VAPT Framework — Performance and Resource Baseline

## 1. System & Benchmark Environment
- **Platform:** Linux 6.6.137+ x86_64
- **Runtime:** Python 3.12.14 (`.venv`), `uv 0.12.19`, `pytest 9.1.1`
- **FastAPI / Uvicorn Server:** Async event-driven architecture with Starlette TestClient / HTTPX
- **Test Target:** Local loopback (`127.0.0.1`) and isolated lab fixtures
- **Concurrency Architecture:** Non-blocking async event loop with offloaded worker threads for atomic I/O

---

## 2. Micro-Benchmark Performance Metrics

### 2.1 Evidence Integrity & Envelope Serialization (Findings C07, C08, C13)
*Tested across 200 sequential write-and-verify iterations with fsync disk persistence:*

| Operation | Average Latency | p95 Latency | Throughput | Notes |
|---|---|---|---|---|
| **Atomic Evidence Write + Canonical Hash** | **10.78 ms** | **13.00 ms** | ~93 writes/sec | Uses `NamedTemporaryFile` with explicit directory fsync |
| **Evidence Integrity Verification** | **0.057 ms** | **0.079 ms** | **>17,500 checks/sec** | Fast SHA-256 byte digest verification |

### 2.2 GAP-1 Candidate Ticket Scheduler (Findings B01, B02, B03)
*Tested on 100-candidate priority queue with reverse discovery order:*

| Operation | Average Latency | p95 Latency | Throughput | Notes |
|---|---|---|---|---|
| **Queue Initialization (100 candidates)** | **0.273 ms** | **0.310 ms** | 3,660 queues/sec | Sorts and computes discovery vs ranked divergence |
| **Ticket Priority Dispatch** | **0.0049 ms** | **0.0063 ms** | **~204,000 dispatches/sec** | Zero lock contention, in-memory ticket ledger |
| **Unranked Dispatch Check & Override** | **0.0061 ms** | **0.0078 ms** | ~164,000 checks/sec | Audited authorization check |

### 2.3 GAP-2 Adaptive Pivot Deduplication (Findings B04, B05, B06)
*Tested on 500 interleaved raw pivot events:*

| Operation | Latency | Resulting Events | Notes |
|---|---|---|---|
| **Event Deduplication (500 events)** | **0.330 ms** | 10 canonical pivot pairs | Eliminates redundant bridge/engine events |
| **Genuine Pivot Key Derivation** | **0.0018 ms** | Canonical `(orig, alt)` | Strictly requires `pivot_executed=True` |

### 2.4 Control Gateway & Web Console API Latency (Findings A01, A08, D01)
*Tested across 50 requests per endpoint under authenticated operator session:*

| Route | Method | Average Latency | p95 Latency | Description |
|---|---|---|---|---|
| `/` | `GET` | **2.53 ms** | **2.95 ms** | Root SPA HTML with session cookie bootstrap |
| `/settings/llm` | `GET` | **2.76 ms** | **3.85 ms** | Authenticated LLM provider configuration |
| `/runs` | `GET` | **819.29 ms** | **937.58 ms** | Full disk scan, reconciliation, and finding tally |

---

## 3. Resource Optimization & Concurrency Improvements

### 3.1 Subprocess Environment Isolation (Finding A05)
- **Pre-optimization:** Credentials (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) were mutated directly on global `os.environ`, causing race conditions and credential cross-contamination across concurrent runs.
- **Post-optimization:** `build_isolated_subprocess_env` builds a dedicated per-run dictionary passed explicitly to `subprocess.Popen(env=...)`. Global `os.environ` remains pristine and thread contention is eliminated.

### 3.2 Bounded Scanner HTTP Transport (Findings A04, A07)
- **Pre-optimization:** Scanners performed unbounded `resp.read()` and followed cross-origin redirects blindly with `CERT_NONE`.
- **Post-optimization:** `ScopedRedirectHandler` enforces strict maximum redirect hops (max 5), validates target domain boundaries on every hop, and enforces verified TLS (`CERT_REQUIRED`) by default. Link-local and cloud metadata IP ranges (`169.254.169.254`) are blocked at socket level.

### 3.3 Docker Container Lifecycle Preservation (Finding D03)
- **Pre-optimization:** Server startup reaped any container older than 120 seconds not present in transient in-memory run dictionary, killing legitimately running sandbox containers during API restarts.
- **Post-optimization:** `reap_orphaned_containers` defaults to `preserve_running=True`. Active sandboxes and lab testbeds (e.g. Juice Shop) are never terminated; only dead/exited containers are automatically cleaned.
