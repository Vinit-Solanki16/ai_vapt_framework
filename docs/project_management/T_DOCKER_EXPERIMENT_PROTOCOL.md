# T-DOCKER — CONTROLLED VALIDATION EXPERIMENT PROTOCOL (DESIGN ONLY)

_Status: DESIGN DOCUMENT. Authorized for EXPERIMENT DESIGN ONLY._
_No Docker started. No images pulled. No danger_mode run. No offensive PoC executed.
No application source modified. Project remains FROZEN pending this protocol's
readiness gate (see Part J)._

_All statements are grounded in the repository at HEAD
(`0fd4a3e` after T-README+T-UI): executor.py, exploit_assessor.py, agent_graph.py,
schemas.py, poc_corpus.py, data/poc_corpus/*.py, data/poc_corpus/labels.json,
tests/evaluate.py, requirements.txt. No assumptions from prior summaries._

---

## PART A — RESEARCH QUESTION (narrowest defensible)

**RQ1 — GAP-1 controlled validation:**
In an isolated authorized lab, does pre-execution LLM exploit-quality assessment
influence candidate selection so that an OBSERVED (non-label) success is reached
with fewer wasted attempts than an unguided baseline?

**RQ2 — GAP-2 controlled validation:**
Does the framework's explicit per-CVE attempt counter + pivot threshold respond to
OBSERVED failures by pivoting/terminating without repeated non-productive loops?

**Explicitly OUT OF SCOPE (do NOT claim):**
- universal exploit prediction accuracy;
- real-world autonomous exploitation;
- universal loop prevention;
- general penetration-testing superiority;
- faster execution (runtime is a descriptive metric only).

---

## PART B — CURRENT CODE COMPATIBILITY (from source inspection)

### B.1 How `danger_mode` actually executes (executor.py:212-240)
```
proc = subprocess.run([python, module, host, str(port)], capture_output=True, ...)
outcome = self._parse_module_output(proc.stdout, proc.stderr, proc.returncode)
```
The Executor passes `host` (the lab target) and `port` as `sys.argv[1]`, `sys.argv[2]`.

### B.2 Module-output contract (executor.py:126-145, tokens at :50-51)
A module is parsed SUCCESS only if its combined stdout+stderr contains one of:
`"EXPLOIT_SUCCESS"`, `"VULNERABLE"`, `"exploit success"`, `"[+] vulnerable"`.
Else: non-zero exit / Traceback → `FAIL_SYNTAX` (or `FAIL_DEPENDENCY` on dep tokens);
clean run, no token → `FAIL_TIMEOUT` (unconfirmed). Labels are NOT read in this path.

### B.3 Inspection of the 12 corpus modules (data/poc_corpus/*.py + labels.json)
The corpus modules are **synthetic stubs, not real exploits**. Concrete incompatibilities
with a real `danger_mode` run (illustrated by `CVE-2021-44228.py`):
1. **Hardcoded target** — `if __name__=="__main__": print(run("127.0.0.1"))`
   (`CVE-2021-44228.py:11-12`). The `run(target, port)` signature accepts a target, but
   the `__main__` block ignores `sys.argv` and always connects to `127.0.0.1`. The host
   supplied by the Executor is silently discarded. ⇒ Modules never touch the lab target.
2. **No success-token emission** — the stub `s.sendall(...)` + `return s.recv(1024)` prints
   raw socket bytes, never one of `_SUCCESS_TOKENS`. ⇒ Even against a live target,
   `_parse_module_output` returns `FAIL_TIMEOUT`, never `SUCCESS`.
3. **No real target service** — the modules do not implement an actual exploitation chain
   against any running service; they are placeholders representing the *intended* behaviour
   that labels.json encodes.

### B.4 Consequence
- `danger_mode` is **UNVERIFIED**: no committed test or run ever sets it (benchmark and
  smoke tests use `mode="simulation"`). The parser exists; the end-to-end path is unexercised.
- **NONE of the 12 corpus modules can currently produce an OBSERVED SUCCESS** without changes.
- GAP-1's assessor (`exploit_assessor.assess_exploit_quality`) only RANKS by the usability of
  the module *source text*; it does not determine success. In a real run the assessor would
  score the stub source — a valid mechanism test, but the "success" signal comes from the
  executor parser, which (per B.3.2) cannot fire on current stubs.

### B.5 Minimal changes required (see Part I)
(a) Define a formal module-output spec (success/failure tokens); (b) rewrite/extend corpus
modules to (i) read `sys.argv[1:]` as target/port and (ii) emit a success token on observed
success and a structured failure otherwise; (c) optionally build a dedicated lab corpus of
2-3 modules matched to a controlled container. No change to agent_graph or assessor logic is
required — only to corpus modules + the (already-present) parser contract + a safety guard.

---

## PART C — CANDIDATE TESTBEDS (honest compatibility evaluation)

> The task requires: do NOT invent compatibility. If none match, say so.

**Finding: NO current testbed directly matches the 12-CVE corpus.**

| Candidate | Vuln/CVE alignment | Exact corpus PoC runnable? | Repro | Isolation | Observability | Verdict |
|-----------|-------------------|----------------------------|-------|-----------|---------------|---------|
| DVWA | PHP/SQLi/upload, not the 12 CVEs | NO (no module targets it) | High | Easy (docker) | Medium | Not aligned |
| Metasploitable2 | Mixed legacy (incl. some CVEs but NOT the 12 labelled ones verbatim) | NO | High | Easy | Medium | Not aligned |
| OWASP crAPI | API/business-logic, unrelated to corpus | NO | Medium | Medium | Low | Not aligned |
| Vulhub log4j / log4shell-vulnerable-app | Matches CVE-2021-44228 ONLY | Only after rewriting `CVE-2021-44228.py` to (i) accept argv and (ii) detect/log the callback and print `VULNERABLE`; requires an LDAP callback server | Medium | Medium | High | Partial, high setup |
| **Purpose-built Docker vuln-emulator (RECOMMENDED)** | A tiny Flask app with a `/vuln` endpoint that returns a detectable response, plus a `/fail` endpoint | YES — via 2-3 new lab-corpus modules written to spec | High | High (single bridge net) | High (app logs every request) | Best fit |

**Ranking:** (1) Purpose-built emulator — directly tests RQ1/RQ2 with full observability and
zero real-exploit risk; (2) Vulhub log4j for one real-CVE demonstration IF a rewritten module
+ callback infra are built (high complexity, lower value for the mechanism question).

**Conclusion:** The 12-CVE corpus is NOT compatible as-is with any named testbed. The defensible
path is a controlled purpose-built lab + a small lab-corpus, not repurposing DVWA/Metasploitable.

---

## PART D — EXPERIMENT MATRIX (minimum viable)

Two scenarios only — each directly tests one contribution. Candidates are the *lab corpus*
(two rewritten modules), not the real-CVE stubs.

### Scenario S1 — Controlled SUCCESS / GAP-1 ordering
- **Purpose:** RQ1 — assessor ordering leads to earlier observed foothold.
- **GAP-1 mapping:** two candidates A (HIGH usability, targets `/vuln`) and B (LOW, targets `/fail`).
- **Candidates presented:** [A, B].
- **Expected assessor order:** A first (higher usability), then B.
- **First attempt:** A → executor hits `/vuln` → emulator logs request + module prints `VULNERABLE` → OBSERVED_SUCCESS.
- **Expected path:** foothold at attempt 1.
- **Pivot condition:** n/a (success → advance).
- **Termination:** COMPLETED after A succeeds.
- **Observed signal:** emulator access-log entry for `/vuln`; module stdout contains token.
- **Log artifacts:** framework log "SUCCESS", emulator request log, structured result JSON.

### Scenario S2 — Controlled FAILURE → PIVOT / GAP-2
- **Purpose:** RQ2 — pivot after observed failures, no loop.
- **GAP-2 mapping:** one candidate C targeting `/fail` (always returns non-vuln / times out).
- **Candidates presented:** [C] with `max_attempts=N=2`.
- **First attempt:** C → `/fail` returns no success → `FAIL_TIMEOUT` (OBSERVED_FAILURE).
- **Expected failure path:** attempt 1 → retry (per policy) → attempt 2 → `FAIL_TIMEOUT` again.
- **Pivot condition:** `attempt_count >= max_attempts` (2) → pivot/advance.
- **Termination:** COMPLETED (all candidates exhausted, no loop).
- **Observed signal:** exactly 2 execution results for C; pivot log entry; NO 3rd attempt.
- **Log artifacts:** framework "pivot" log, emulator logs showing exactly 2 requests to `/fail`.

(Optional) **S3 — mixed:** [A, C] to show ranking + pivot combined (A succeeds, C pivots).

---

## PART E — SUCCESS CRITERIA (objective, observable)

| State | Definition |
|-------|------------|
| OBSERVED_SUCCESS | Module stdout/stderr contains a `_SUCCESS_TOKENS` string (`executor.py:50`) AND the lab emulator's access log independently records the corresponding request/response. Both required — module token alone is insufficient (guard against false-positive tokens). |
| OBSERVED_FAILURE | Parser returns FAIL_TIMEOUT/FAIL_SYNTAX/FAIL_DEPENDENCY (`executor.py:126-145`) AND emulator log confirms the attempt occurred but no success condition met. |
| INCONCLUSIVE | Target reachable but response ambiguous; or module produced no output and no token (cannot assert success/failure). |
| INFRASTRUCTURE_ERROR | Docker/network/container failure; no experiment data. Quarantine run. |

`labels.json` is NEVER accepted as observed outcome. Success must be corroborated by
target-side evidence.

---

## PART F — SMART vs BASELINE DESIGN

- **Identical candidate set, identical target state, identical `max_attempts`.**
- **Baseline (DUMB):** no usability ranking; processes in list order; retries each candidate up to a hard cap with NO pivot threshold (mirrors `tests/evaluate.py` DUMB).
- **SMART:** `rank_findings` (EPSS×usability) + pivot at `max_attempts` (mirrors framework).
- **Deterministic/random controls:** fixed seed; single run sufficient for mechanism; 3 repeats for variance if time permits.
- **Metrics (no predefined winner):** candidate attempts, observed success/failure, pivot events, repeated-candidate attempts, termination, runtime (descriptive only).
- Comparison is meaningful ONLY after corpus modules emit real observables (Part B.5).

---

## PART G — SAFETY AND ISOLATION

Mandatory lab constraints (must be in the run SOP):
- Explicitly authorized local environment; written authority before any danger_mode run.
- Docker bridge network, **no host port exposure, no public egress**.
- Target allowlist = container IP only (see Part I required change).
- No external callback infrastructure unless itself containerized and allowlisted.
- Full logging; teardown script stops + removes containers/images after each run.
- No non-lab host targets; `target` arg restricted to allowlisted IPs.

**Code change needed to enforce (Part I MINIMAL):** add a `target_allowlist` guard so
`danger_mode` refuses any target not explicitly authorized.

---

## PART H — EVIDENCE COLLECTION

Per run, store under `data/experiment_runs/<run_id>/` (large artifacts gitignored; metadata committed):
- git commit hash (`0fd4a3e` or later at run time);
- Docker image digests + `docker-compose.yml`;
- network config (bridge, no egress);
- emulator access logs;
- framework logs (`final["logs"]`);
- module stdout/stderr (captured by executor);
- structured result JSON (`final` dict);
- benchmark CSV/JSON (SMART vs DUMB);
- pytest output (regression gate).
Naming: `<run_id>_{scenario}_{smirt|dumb}.json`.

---

## PART I — REQUIRED CODE CHANGES (do NOT implement now)

| Class | File | Change | Safety impact | Acceptance test |
|-------|------|--------|--------------|-----------------|
| NO CHANGE REQUIRED | core/agent_graph.py, core/exploit_assessor.py | — | — | existing 29 tests pass |
| MINIMAL REQUIRED | data/poc_corpus/*.py (lab corpus) | New/rewritten modules: read `sys.argv[1:]` as target/port; emit success token on observed success; structured failure otherwise | Positive (observable, no blind fire) | module prints `VULNERABLE` when emulator `/vuln` hit; parser → SUCCESS |
| MINIMAL REQUIRED | core/executor.py (danger_mode) | Add `target_allowlist` guard; refuse non-allowlisted target | Positive (prevents non-lab targets) | danger_mode on disallowed target → refused |
| MINIMAL REQUIRED | docs (this protocol) | Formalize module-output spec (tokens already exist at :50-51; document + optionally extend) | Neutral | documented contract |
| OPTIONAL | core/executor.py `_parse_module_output` | Richer detection (HTTP response/exit-code nuance) | Positive | parses app log line |
| OPTIONAL | tests/ | Add a danger_mode integration test against a mock subprocess emitting tokens | Positive (closes UNVERIFIED gap) | test green, no real target |

---

## PART J — READINESS GATE (PASS / FAIL / BLOCKED)

| Gate | Status | Note |
|------|--------|------|
| Docker availability | BLOCKED | daemon down (confirmed this session) |
| Storage | PASS | ample disk |
| Compatible target selected | FAIL | no corpus module matches a real target as-is |
| Corpus/target compatibility verified | FAIL | stubs hardcoded 127.0.0.1, no tokens (B.3) |
| Isolation design approved | FAIL | allowlist guard not yet implemented (I) |
| Observable success criterion defined | PASS (by this doc, Part E) | |
| Failure/pivot scenario defined | PASS (S2, Part D) | |
| Executor output parsing verified | PARTIAL | parser exists; unexercised end-to-end |
| No labels used as observed outcome | PASS | danger_mode ignores labels by design |
| Regression tests passing | PASS | 29 passed |
| Experiment protocol approved | PENDING | this doc under review |

**Overall: NO-GO until all FAIL/BLOCKED gates clear.**

---

## PART K — THESIS CLAIM MAPPING (conservative)

SUPPORTED (if gates pass + S1/S2 observed):
- "In a controlled laboratory scenario, the state-driven agent pivoted after an observed
  failure within `max_attempts` and terminated without repeated non-productive loops (RQ2)."
- "Under the defined lab scenario, pre-execution usability assessment ordered candidates so
  that an observed success was reached with fewer attempts than the unguided baseline (RQ1)."

NOT SUPPORTED (must not be claimed):
- "The framework prevents loops in all real-world VAPT environments."
- "The assessor predicts exploit success universally / on unseen CVEs."
- "Observed success on a lab emulator generalizes to real exploitation efficacy."
- Any speed/stealth superiority claim.

The experiment validates the *mechanism* under observation — not production efficacy.
