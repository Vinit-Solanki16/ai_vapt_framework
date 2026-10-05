# Web Target Assessment (Phase 32)

Authorized local-URL assessments wired into the existing AI decision pipeline.
No second decision engine. No second VAPT workflow. Research core untouched.

## Architecture

```
User enters URL (GUI)
        ↓
POST /targets/validate → preflight (authorize + scope + connectivity, NO scan)
        ↓  AUTHORIZED + REACHABLE
POST /runs {assessment_type: web, target_url, ...}
        ↓
VAPTApplication.run()
  _load_web_candidates()
    parse_web_target()          # strict auth, fail closed (web_target.py)
    preflight_web_target()      # safe GET / probe only
    scanner_service.run_nmap_discovery()   # nmap -Pn -sV -p <port> -oX <out> <host>
    scanner_service.run_nuclei_scan()      # controlled profile, or NOT AVAILABLE
        ↓
  CanonicalFinding → deduplicate → enrich_findings (EPSS/KEV/CVSS/CWE)
        ↓
  candidate dicts (probability prior = EPSS, else 0.0 — never fabricated)
        ↓
  DecisionIntelligence scoring → ValidationPipeline (Planner → SafetyGate →
  Executor(simulation) → Verifier → Evidence)
        ↓
  run_decision_scenario() — research engine, GAP-1/GAP-2 unchanged
  (per-candidate reasoning/latency/fallback observed WITHOUT altering ranks)
        ↓
  _build_result(): engine metadata merged back with scanner metadata by id;
  scanner findings labelled VALIDATION NOT AVAILABLE unless controlled
  validation executed. Evidence tier: OBSERVED_LOCAL.
        ↓
  persist (target_url, assessment_type, pipeline_summary.web) → report
```

## URL input

- Field: Target URL, default `http://127.0.0.1:9191`.
- Fragments (`#/...`) and queries are stripped; the scanner target is always
  `scheme://host:port`. Embedded credentials are rejected, not sanitized.

## Authorization (backend enforcement)

`vapt_platform/web_target.py` — fail closed:

1. Scheme must be `http`/`https`.
2. Host must be in `AUTHORIZED_WEB_HOSTS` (`127.0.0.1`, `localhost`).
3. Host is resolved via `getaddrinfo`; resolved IP must be loopback
   (`127.0.0.1` / `::1`) — DNS-rebinding guard.
4. Port must be in `AUTHORIZED_WEB_PORTS` (default `{9191}`,
   override via `AI_VAPT_AUTHORIZED_WEB_PORTS`).
5. Malformed URLs, userinfo (`user@`, `user:pass@`), non-loopback hosts,
   unauthorized ports → `WebTargetAuthorizationError`.

`AuthorizationTracker` + `ScopeEnforcer` + `SafetyGate` remain authoritative
downstream: the web host is authorized on the tracker and every planned
action is scope/safety validated before execution. Frontend validation is UX
only. `POST /runs` re-validates and returns HTTP 400 on rejection.

## Nmap

- Availability: `shutil.which("nmap")` (`GET /scanners/status`).
- Command (fixed, argv list, no shell):
  `nmap -Pn -sV -p <port> -oX <output> <resolved-host-or-host>`
- Output parsed by the EXISTING `NmapXmlAdapter` → `CanonicalFinding`.
- Provenance recorded: scanner, target, command, start/end, output path,
  exit code, finding count.

## Nuclei

- Availability checked; NOT INSTALLED here → status `NOT AVAILABLE`,
  zero findings, run proceeds with Nmap discovery (reported honestly).
- When installed, fixed profile:
  `nuclei -target <url> -jsonl -o <out> -silent -timeout 5 -rate-limit 10 -retries 1`
  parsed by the EXISTING `NucleiAdapter`. No user templates/flags.

## Normalization → AI assessment → ranking → decision

Unchanged canonical path. AI assessment uses the existing pluggable
assessor (`provider=ollama`, `model=llama3.2:3b`); the LLM only returns a
quality rank + reasoning (no commands, no tools). GAP-1 display
(assessment → ranking → decision) uses server-side ranks only — no JS scoring.

## Safety / validation / evidence

- Scanner findings are labelled `SCANNER-DETECTED` / `VALIDATION NOT AVAILABLE`;
  never called exploits. Evidence tier `OBSERVED_LOCAL`.
- Per-candidate engine outcomes in `simulation` executor are reported as
  simulated outcomes, not validations.
- GAP-2 (`failure_pivot`) is NOT fed by Juice Shop findings; the controlled
  scenario remains the clean GAP-2 demonstration.

## Reporting

Reports distinguish Target (`http://127.0.0.1:9191`), Application
(OWASP Juice Shop), Environment (LOCAL CONTROLLED TEST APPLICATION),
Discovery (Nmap + status), Vulnerability scanner (Nuclei + status),
AI (Ollama / llama3.2:3b), and actual evidence tier. Limitations state that
scanner findings are discovery output, not confirmed vulnerabilities.

## Run history

Persisted runs carry `target_url`, `assessment_type`, `finding_count`
(derived), `assessor_provider`, evidence, attempts, pivots, timestamp and
survive restarts (`~/.ai_vapt_framework/runs`).

## API additions

- `POST /targets/validate` — preflight without scanning.
- `GET /scanners/status` — nmap/nuclei availability + authorized scope.
- `POST /runs` — accepts `assessment_type: web`, `target_url`, `use_nmap`,
  `use_nuclei`; `mode: web` added; HTTP 400 on authorization failure.
- `GET /runs` — now includes `target_url`, `assessment_type`,
  `finding_count`, `assessor_provider`, `target`, `port`.

## Remaining limitations

- Nuclei not installed → no template-based vuln findings in this environment.
- Nmap service fingerprint for Juice Shop reports `sun-as-jpda` (banner-based
  misclassification); the HTTP 200 response identifies the real service.
- Per-candidate LLM reasoning captured, but ranking still uses engine ranks
  (by design — GAP-1).
- No real exploitation/validation of Juice Shop findings in this phase
  (executor is simulation-grade for web mode).
