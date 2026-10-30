# Phase 0 — Repository Review and Baseline

**Date:** 2026-10-28
**Status:** COMPLETE — Gate 0 passed

## 1. Repository facts

| Fact | Value |
|---|---|
| AI_VAPT root | `/home/vinit/AI_VAPT` |
| AI_VAPT version | `0.1.0` (`pyproject.toml`) |
| AI_VAPT commit | `a4af8fd` |
| AI_VAPT Python (venv) | 3.12.14 |
| Strix root | `/home/vinit/STRIX/strix` |
| Strix version | `1.7.0` |
| Strix commit | `ef5d8100` |
| Strix Python (uv venv) | 3.14 |
| Docker | 29.9.2; sandbox image `ghcr.io/usestrix/strix-sandbox:1.3.0` present |
| Ollama | running; only `qwen2.5:1.5b` installed |
| Go compiler | absent |
| `strix-tui` binary | absent (`build/sidecar/strix-tui`) |

Pre-existing working-tree changes are present in both repositories (AI_VAPT:
91 modified files; Strix: 2 untracked docs). They predate this integration and
are not caused by it. `decision_engine/core/` has **zero** modified files.

## 2. AI_VAPT baseline tests

The venv initially had no pytest. Installed with:

```bash
cd /home/vinit/AI_VAPT
uv pip install --python .venv/bin/python pytest==9.1.1
```

Baseline command and result:

```bash
PYTHONPATH=.venv/lib/python3.12/site-packages .venv/bin/pytest -q
# 1057 passed
```

After Phase 1 adapter tests were added the same command reports **1083 passed**
(1057 baseline + 26 adapter tests at the time of writing).

## 3. Strix baseline run

### Target reachability (important)

Strix runs the scan inside a Docker sandbox and rewrites `127.0.0.1` to
`host.docker.internal:<port>`. A host process bound only to host loopback is
therefore **not reachable** from the sandbox.

A development reverse proxy was used so the authorized local scope
`127.0.0.1:9191` serves DVWA from `https://pentest-ground.com:4280`.
It must bind `0.0.0.0` (not `127.0.0.1`) for the sandbox to reach it:

```bash
python3 /tmp/opencode/target_proxy.py   # 0.0.0.0:9191 -> pentest-ground.com:4280
```

Verified from both the host and a container:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9191/          # 200
docker run --rm --add-host host.docker.internal:host-gateway \
  curlimages/curl:latest -s -o /dev/null -w '%{http_code}\n' \
  http://host.docker.internal:9191/                                      # 200
```

### Model availability

The local `qwen2.5:1.5b` model cannot reliably drive Strix's lifecycle tools
(max-turn exhaustion / no `finish_scan`). The OpenRouter key on this machine has
`total_credits: 0` for paid models, so a free tool-capable model was used:

```bash
cd /home/vinit/STRIX/strix
export STRIX_LLM="openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
export LLM_API_BASE="https://openrouter.ai/api/v1"
export LLM_API_KEY="<runtime key from environment — never logged>"
export STRIX_REASONING_EFFORT=low
uv run strix -n -t http://127.0.0.1:9191 --scan-mode quick \
  --max-budget 1 --max-turns 30
```

### Successful baseline result

| Field | Value |
|---|---|
| Run name | `host-docker-internal-9191_6463` |
| Status | `completed` |
| Start / end | 2026-10-27T18:49:34Z / 2026-10-27T18:54:24Z |
| Duration | ~4m 50s |
| LLM requests | 30 |
| Tokens | 1,860,154 in / 3,942 out / 1,864,096 total |
| Findings filed | 0 (`vulnerabilities.json` absent) |
| Executive summary | Correctly identified DVWA, default creds, Low security level, and the DVWA vulnerability modules |
| Cost | $0 (free model) |

An earlier completed run (`..._3aea`) targeted port 9090 because the proxy was
bound to host loopback only; it is not the authoritative baseline.

### Strix output structure (verified)

```text
strix_runs/<run>/
  run.json                    # lifecycle, targets, llm_usage, scan_results
  coverage.json               # coverage/gap record
  findings.sarif              # SARIF 2.1.0 (0 results is valid)
  strix.log                   # structured runtime log
  penetration_test_report.md  # executive report (terminal runs)
  .state/                     # resumable agent state
  vulnerabilities.json        # only when at least one finding is filed
  vulnerabilities.csv         # only with findings
  vulnerabilities/<id>.md     # only with findings
```

A missing `vulnerabilities.json` on a completed run means **zero findings**, not
a malformed result. The adapter treats it as an empty list.

### Failed/interrupted baseline variants (recorded, not authoritative)

* `..._f79e` — `interrupted`: killed by the command timeout.
* `..._11e2` — `failed`: `MaxTurnsExceeded` with `qwen2.5:1.5b`.
* `..._031e` — failed: OpenRouter `402 in_flight_budget_exhausted` for a paid model.
* `..._3aea` — completed against the wrong port (loopback-only proxy).

## 4. Confirmed integration points

| Purpose | Location |
|---|---|
| Root-task construction (GAP-1 queue injection) | `strix/core/inputs.py` → `build_root_task()`, called from `strix/core/runner.py` (~line 424) |
| Agent turn lifecycle (GAP-2 observation point) | `strix/core/execution.py` → `run_agent_loop()` / `_run_until_lifecycle()` |
| Finding creation (GAP-2 outcome hook) | `strix/tools/reporting/tool.py` → `create_vulnerability_report()` → `_do_create()` → `report_state.add_vulnerability_report()` |
| Findings index writer | `strix/report/writer.py` → `write_vulnerabilities()` |
| Model/runtime env | `strix/config/settings.py` (`STRIX_LLM`, `LLM_API_KEY`, `LLM_API_BASE`, `STRIX_REASONING_EFFORT`) |
| CLI entry / flags | `strix/interface/main.py`, `strix/interface/cli_args.py` (`-n`, `-t`, `-i`, `--scan-mode`, `--max-budget`, `--max-turns`) |
| Run directory | `strix/core/paths.py` → `strix_runs/<run_name>` |

Strix has no explicit candidate-dispatch function: execution is agentic. The
smallest suitable GAP-1 hook is therefore root-task instruction injection plus a
ranked queue artifact; GAP-2 is anchored at report creation outcomes and the
agent loop's attempt accounting.

## 5. Viewer token auth

`strix/interface/viewer/auth.py` stores `{email, token, verified_at}` in
`~/.strix/viewer-auth.json` with mode `0600`; `is_verified` unlocks the local
history list, while the relay still enforces token validity. The viewer CLI
prints a tokened URL (`strix/interface/viewer/cli.py` → `authorized_url`). The
viewer is optional for this integration; AI_VAPT's own UI is the primary
control surface.

## 6. TUI

`make tui-build` requires Go (`strix/interface/tui`). Go and the prebuilt
`strix-tui` binary are both absent. TUI verification is therefore skipped and
documented as an environment limitation; the Python CLI and viewer remain
usable.

## 7. Gate 0

* AI_VAPT baseline suite passes (1057; 1083 after adapter tests).
* Strix runs independently to completion against a controlled authorized target.
* Output structure and integration points recorded.
* Viewer auth mechanism confirmed; TUI unavailability documented.

**Gate 0: PASS.**
