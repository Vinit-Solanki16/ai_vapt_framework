# T-DOCKER — READINESS ASSESSMENT (DESIGN PHASE)

_Prepared under the T-DOCKER EXPERIMENT PROTOCOL DESIGN authority decision
(2026-08-24). No Docker started; no source modified; project remains FROZEN._

## 1. CURRENT READINESS STATUS
**NOT READY (NO-GO).** The framework's `danger_mode` executor path exists
(`core/executor.py:212-240`) and parses REAL module output via `_parse_module_output`
(`:126-145`), but the entire controlled-validation path is **unexercised** and the
current 12-CVE corpus is **synthetic stubs** incompatible with any real target.

## 2. EXACT BLOCKERS
- **B1 — Docker daemon down** (confirmed this session; no container runtime available).
- **B2 — Corpus/target mismatch:** every `data/poc_corpus/*.py` is a stub. Concretely
  `CVE-2021-44228.py:11-12` hardcodes `run("127.0.0.1")` (ignores `sys.argv` host the
  Executor passes), and no module emits a `_SUCCESS_TOKENS` string (`executor.py:50`), so
  `_parse_module_output` would return `FAIL_TIMEOUT` even against a live target.
- **B3 — No aligned testbed:** DVWA / Metasploitable2 / crAPI do NOT match the 12 labelled
  CVEs; Vulhub log4j is the only partial match and requires a callback server + module rewrite.
- **B4 — Missing safety guard:** `danger_mode` has no `target_allowlist` (Part G/I), so a
  future run is not yet hard-restricted to an authorized lab IP.

## 3. RECOMMENDED TESTBED
**Purpose-built Docker vulnerability emulator** — a single minimal Flask service with
`/vuln` (returns a detectable success response) and `/fail` (returns non-vuln / timeout),
run on an isolated bridge network with no egress. Paired with 2–3 new **lab-corpus** modules
written to the module-output spec. Highest observability (app logs every request), zero
real-exploit risk, directly tests RQ1/RQ2. See protocol Part C/D.

## 4. BACKUP TESTBED
**Vulhub `log4j` / `log4shell-vulnerable-app`** for ONE real-CVE demonstration
(CVE-2021-44228) — but only after (a) rewriting `CVE-2021-44228.py` to read `sys.argv` and
emit `VULNERABLE`, and (b) deploying an isolated LDAP callback server. Higher setup
complexity and lower mechanism-test value than the emulator; use only to add a "real CVE"
data point.

## 5. MINIMUM INFRASTRUCTURE REQUIREMENTS
- Docker Engine running (resolves B1).
- One container host + bridge network, no public egress.
- Flask emulator image (build from a small Dockerfile) OR Vulhub log4j image.
- Python 3.10 venv (present) with current pinned deps.
- ~2 GB disk for images/logs; ample on host.

## 6. REQUIRED USER ACTIONS
- Start/enable the Docker daemon in an **authorized, isolated** environment.
- Provide written authorization for the lab target IP (allowlist).
- Approve the experiment protocol (Part J gate).
- (Optional) approve Vulhub log4j for the backup real-CVE run.

## 7. REQUIRED CODE CHANGES BEFORE EXPERIMENT, IF ANY
Per protocol Part I — NONE to agent_graph/assessor. Required:
- New/rewritten **lab-corpus** modules reading `sys.argv[1:]` + emitting success tokens (B2).
- `core/executor.py` `danger_mode` **target_allowlist** guard (B4).
- Document the module-output contract (tokens already at `executor.py:50-51`).
- (Recommended) one integration test that runs a mock subprocess emitting tokens, closing
  the UNVERIFIED gap without a live target.

## 8. GO / NO-GO RECOMMENDATION
**NO-GO** at this time. All hard gates in protocol Part J are FAIL/BLOCKED (Docker down,
corpus incompatible, allowlist missing). The protocol itself is complete and approvable;
execution must wait until (a) Docker is available, (b) the lab corpus + allowlist are
implemented, and (c) the readiness gate is re-run and passes. Until then, all efficacy
claims remain SIMULATION / proof-of-mechanism — no real-observed result exists.
