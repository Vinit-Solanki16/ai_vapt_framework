# 08 — RISK REGISTER

| ID | Risk | Severity | Likelihood | Status | Mitigation / Task |
|----|------|----------|-----------|--------|-------------------|
| R-001 | "real" executor mode shells corpus PoC that performs offensive socket sends (e.g. CVE-2021-44228 JNDI) while ignoring output and trusting labels; mislabeled "safe probe" | HIGH (safety + honesty) | Real (verified) | OPEN | T-SAFE (P0); governance §8 — treat as unsafe until verified; no offensive runs outside isolated lab |
| R-002 | No Docker/sandbox for live PoC execution; no genuine exploit validation possible | MEDIUM (thesis) | Real | OPEN | T-DOCKER (P1) — gated; only in authorized isolated lab |
| R-003 | Benchmark loop-avoidance metric hardcoded (smart_loop=0) → headline thesis metric unmeasured (INVALID experiment per §9) | HIGH (validity) | Real (verified) | OPEN | T-BENCH-LOOP (P0) |
| R-004 | No pytest suite / assertions → regressions undetectable | MEDIUM | Real | OPEN | T-TESTS (P3) |
| R-005 | Corpus n=3 → weak statistical basis for thesis | MEDIUM | Real | OPEN | T-CORPUS (P1), T-BENCH-VAR (P3) |
| R-006 | GAP-1 impact on outcomes not empirically demonstrated | MEDIUM (thesis) | Real | OPEN | T-GAP1-VALID (P1) |
| R-007 | OpenAI provider path unverified; silent 401 with dummy-key | LOW | Possible | OPEN | T-OPENAI (P2) |
| R-008 | No version pin → reproducibility drift | LOW | Possible | OPEN | T-REQPIN (P3) |
| R-009 | Streamlit UI never run interactively; unsafe_allow_html on logs | LOW | Possible | OPEN | T-UI (P4) |
| R-010 | Independent review (Claude) unreliable → risk of acting on phantom findings | MEDIUM (process) | Realized | MITIGATED | D-001: verify against actual repo; only carry genuine overlaps |
| R-011 | Benchmark numbers in README stale (SMART=1 vs actual 5) | LOW (docs) | Real | OPEN | T-README (P4) |

## Severity scale
HIGH = P0 (safety / invalid experiment). MEDIUM = P1/P2. LOW = P3/P4.
