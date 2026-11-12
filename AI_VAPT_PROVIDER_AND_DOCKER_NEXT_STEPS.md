# AI-VAPT Provider & Docker Next Steps Report

**Date:** 2026-11-11
**Branch:** `ai-vapt-full-application`
**Working Directory:** `/workspaces/ai_vapt_framework`
**Environment:** GitHub Codespaces (Debian 12 bookworm, 2 vCPU, 7.8 GiB RAM, 21 GiB disk)

---

## 1. OpenRouter Authentication Result

### Status
**CONFIGURATION_REQUIRED** — `OPENROUTER_API_KEY` is **not set** in the Codespace environment.

| Check | Result |
|---|---|
| `OPENROUTER_API_KEY` env var | NOT SET (0 occurrences in environment) |
| `~/.strix/cli-config.json` | Contains masked placeholder `«redacted:sk-…»` |
| Key read from environment | Yes — only from env vars (never printed or logged) |
| Key placed in source/config/reports | NONE (no key material was stored or persisted) |
| Authenticated API request | **NOT ATTEMPTED** (no valid key available to sign the request) |

### Work Required
1. Configure `OPENROUTER_API_KEY` through GitHub Codespaces Secrets:
   - Open the Codespace → Settings → Secrets
   - Add secret `OPENROUTER_API_KEY` with a valid, funded OpenRouter API key
   - Restart the Codespace so the secret is available to the running environment
2. After restart, re-run the verification (Part 3 below) to confirm authentication.

### Verification Plan (once key is set)
1. **Authentication check** — minimal API request to `https://openrouter.ai/api/v1/auth/key` with `Authorization: Bearer <OPENROUTER_API_KEY>`:
   - HTTP 200 → authentication succeeded
   - HTTP 401/403 → invalid or unauthorized credential
   - HTTP 429 → quota exceeded or rate limited
2. **Model generation check** — request a response from the configured model and confirm a real output is received.

---

## 2. Model Generation Test Result

### Target Model
`openrouter/nvidia/nemotron-3.5-super-vl:free`

### Catalog Verification
| Check | Result |
|---|---|
| `openrouter/nvidia/nemotron-3.5-super-vl:free` in OpenRouter public catalog | **NOT FOUND** (0 matches) |
| `nvidia/nemotron-3.5-super-vl:free` in OpenRouter catalog | **FOUND** (listed, 12 free models total) |
| `openrouter/` prefix semantics | Reserved namespace for OpenRouter's own models; not applied to NVIDIA-hosted models |

### Finding
The requested model identifier `openrouter/nvidia/nemotron-3.5-super-vl:free` is **not present** in the OpenRouter model catalog. The catalog lists the model as **`nvidia/nemotron-3.5-super-vl:free`** (without the `openrouter/` prefix).

### Recommendation
Use **`nvidia/nemotron-3.5-super-vl:free`** (without the `openrouter/` prefix) as the model identifier. If the user specifically requires the `openrouter/` prefix format, verify with OpenRouter support — the identifier may have been updated since the catalog scan.

**Do not silently change the model.** Document the discrepancy and require user confirmation before changing the model identifier.

---

## 3. Docker Capability Investigation

### Container Capability State
| Check | Result |
|---|---|
| `CapEff` (effective capabilities) | `0000000000000000` (ALL capabilities dropped) |
| `CapBnd` (bounding set) | `0000000000000000a88425fb` (limited) |
| Docker CLI | Installed (`docker --version` → Docker 20.10.24) |
| Docker daemon | **Cannot start** — iptables/nftables NAT chain creation denied at kernel level |
| `/var/run/docker.sock` | Exists but no daemon bound |
| `docker run hello-world` | **FAILED** — no daemon to execute against |

### Docker Daemon Startup Failure
The `dockerd` log records:

```
failed to start daemon: Error initializing network controller:
error obtaining controller instance: failed to create NAT chain DOCKER:
iptables failed: iptables -t nat -N DOCKER:
iptables v1.8.9 (nf_tables): Could not fetch rule set generation id:
Permission denied (you must be root)
```

The container has `CapEff = 0000000000000000` — no effective kernel capabilities. Docker daemon startup requires `CAP_NET_ADMIN` (for iptables/nftables), which this environment does not provide. **This is a fundamental capability limitation, not a configuration issue.**

### Can the Current Codespace Support Docker-in-Docker?
**NO.** The container has zero effective kernel capabilities, so Docker-in-Docker cannot function. Repeated attempts to start `dockerd` or mount the socket will fail the same way.

### Recommendations (Ranked)

| Option | Viability | Details |
|---|---|---|
| **1. Remote Docker host** (Docker-enabled Linux VM or cloud instance) | **RECOMMENDED** | Code supports `DOCKER_HOST` env var + TLS (`DOCKER_TLS_VERIFY`, `DOCKER_CERT_PATH`). No code changes required. |
| **2. Separate Docker-enabled Linux VM** | Supported (remote Docker) | Provision a VM with Docker Engine, run `strix` in the Codespace with `DOCKER_HOST=tcp://<vm-ip>:2376` and TLS certs. |
| **3. Dev Container docker-in-docker** | Not viable in this environment | Container lacks CAP_NET_ADMIN; the feature will fail the same way. |
| **4. Mount host Docker socket** | Not viable / security risk | Requires privileged socket access; not supported in Codespaces without host-level changes. |

### Why Remote Docker Is the Best Option
1. **No code changes required** — `strix/runtime/docker_connection.py` already resolves `DOCKER_HOST` and supports TLS.
2. **No host security weakening** — TLS-secured remote connection, no socket mounting.
3. **Code confirmed working** — `strix/runtime/backends.py` registers only the `docker` backend, and `connect_docker()` reads `DOCKER_HOST` from the environment.

### Docker Connection Architecture in AI-VAPT

```
strix/interface/cli.py    → _resolve_sandbox_image()
strix/runtime/session_manager.py → get_backend("docker")
strix/runtime/backends.py → _docker_backend() → StrixDockerSandboxClient(connect_docker())
strix/runtime/docker_connection.py → resolve_docker_endpoint() → connect_docker()
```

Key functions:
- `resolve_docker_endpoint()` — reads `DOCKER_HOST` env var, then docker context, then default socket
- `connect_docker()` — `docker.from_env()` (reads `DOCKER_TLS_VERIFY` + `DOCKER_CERT_PATH`)
- Backend registry: `{"docker": _docker_backend}` (only local Docker; no separate remote backend)

---

## 4. Recommended Docker Hosting Option

### Option 1 — Remote Docker Host (RECOMMENDED)

**Steps:**
1. Provision a Docker-enabled host (cloud VM or local machine on the same network)
2. Configure Docker to accept remote connections over TLS:
   ```bash
   # On the remote host
   sudo dockerd --tlsverify --tlscacert=ca.pem --tlscert=server-cert.pem --tlscert=server-key.pem -H=tcp://0.0.0.0:2376
   ```
3. Copy TLS certificates to the Codespace
4. Configure in the Codespace:
   ```bash
   export DOCKER_HOST="tcp://<remote-ip>:2376"
   export DOCKER_TLS_VERIFY="1"
   export DOCKER_CERT_PATH="$HOME/.docker/certs-client"
   ```
5. Verify: `docker info` should connect to the remote daemon

### Option 2 — Separate Docker-Enabled Linux VM

Same as Option 1 but on a VM provisioned specifically for Docker. The Codespace connects to the VM via `DOCKER_HOST` with TLS.

### Option 3 — Dev Container with Docker-in-Docker

**NOT VIABLE** for this environment due to `CapEff = 0000000000000000`. The Docker daemon cannot start even with the docker-in-docker Dev Container feature.

### Option 4 — Mount Host Docker Socket

**NOT RECOMMENDED** — requires privileged access and weakens host security. The task explicitly prohibits mounting arbitrary host Docker sockets.

---

## 5. Sandbox Image Status

| Check | Result |
|---|---|
| Expected image | `ghcr.io/usestrix/strix-sandbox:1.3.0` (confirmed in code: settings.py:161, scripts/install.sh:7) |
| Image present locally | **NOT VERIFIED** — Docker daemon unavailable, so image cannot be pulled |
| Architecture / tag | Not confirmed (image not pulled) |
| Ready claim | **NOT MADE** (cannot claim ready without a working Docker daemon) |

### Status
The image reference is **confirmed as the runtime source of truth**, but the image itself is **not locally present** and **cannot be pulled** because the Docker daemon is unavailable. The image status is **PENDING** until a working Docker daemon is available.

---

## 6. Exact Remaining Manual Actions

### Action 1 — Configure OpenRouter API Key
1. Open the Codespace in GitHub
2. Go to Codespace Settings → Secrets
3. Add secret `OPENROUTER_API_KEY` with a valid, funded key
4. Restart the Codespace
5. Re-run the verification to confirm authentication

### Action 2 — Verify Model Identifier
- The requested model `openrouter/nvidia/nemotron-3.5-super-vl:free` is **NOT FOUND** in the OpenRouter catalog.
- The model exists as **`nvidia/nemotron-3.5-super-vl:free`** (without the `openrouter/` prefix).
- **Confirm with the user:** use `nvidia/nemotron-3.5-super-vl:free` or verify with OpenRouter support.

### Action 3 — Provision a Remote Docker Host
1. Provision a Docker-enabled host (cloud VM or local machine)
2. Configure Docker for remote TLS access
3. Copy TLS certs to the Codespace
4. Set environment variables:
   ```bash
   export DOCKER_HOST="tcp://<remote-ip>:2376"
   export DOCKER_TLS_VERIFY="1"
   export DOCKER_CERT_PATH="$HOME/.docker/certs-client"
   ```
5. Test: `docker info` and `docker run --rm hello-world`

### Action 4 — Codespace Rebuild (for Dev Container changes)
- Rebuild the Codespace to activate the docker-in-docker Dev Container feature (`Rebuild Container`)
- Note: This will NOT fix the capability issue (see Part 3).

---

## 7. Is Autonomous Readiness Achievable in the Current Codespace?

**NO.** The current Codespace cannot achieve autonomous readiness because:

1. **Docker daemon cannot start** — the container has zero effective kernel capabilities (`CapEff=0000000000000000`). This is a fundamental limitation, not a configuration issue.
2. **OpenRouter API key is not configured** — the environment variable is not set in the Codespace.
3. **Sandbox image cannot be pulled** — requires a working Docker daemon.

### What CAN Be Done in the Current Codespace
- ✅ Python environment is functional (Python 3.12.11, all core dependencies installed)
- ✅ Docker CLI is installed
- ✅ Dev Container configuration declares docker-in-docker feature
- ✅ AI-VAPT diagnostics correctly report all blockers
- ✅ Execution paths correctly fast-fail (autonomous mode without Docker returns HTTP 400)
- ✅ All 101 targeted tests pass (0 failures)
- ✅ OpenRouter public API is reachable (HTTP 200, 469 models)

### What Must Be Resolved Before Autonomous Execution
- ❌ Docker daemon must run (remote Docker host recommended)
- ❌ OpenRouter API key must be configured via GitHub Codespaces Secrets
- ❌ Sandbox image must be pulled (requires working Docker daemon)
- ❌ Model identifier must be confirmed (`nvidia/nemotron-3.5-super-vl:free` or `openrouter/` prefix variant)

---

## 8. Summary

| Component | Classification |
|---|---|
| OpenRouter API key | **CONFIGURATION_REQUIRED** |
| Model identifier | **UNRECOGNIZED** — `openrouter/nvidia/nemotron-3.5-super-vl:free` not found (use `nvidia/nemotron-3.5-super-vl:free`) |
| Docker daemon (local) | **BLOCKED** — zero container capabilities |
| Docker runtime in current Codespace | **NOT VIABLE** for Docker-in-Docker |
| Remote Docker support | **SUPPORTED** (via `DOCKER_HOST` + TLS) |
| Docker hosting recommendation | **Remote Docker host** (Docker-enabled VM with TLS) |
| Sandbox image | **PENDING** — confirmed reference, not pulled |
| Autonomous readiness | **NOT ACHIEVABLE** in current Codespace |

---

*Report generated automatically. No secrets were accessed, logged, or persisted by this process. The OpenRouter public catalog was queried via a public endpoint (no authentication required). No credentials or key material were stored or displayed.*
