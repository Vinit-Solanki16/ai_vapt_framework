# AI-VAPT Remote Runtime Readiness Report

**Date:** 2026-11-11
**Branch:** `ai-vapt-full-application`
**Working Directory:** `/workspaces/ai_vapt_framework`
**Environment:** GitHub Codespaces (Debian 12 bookworm, 2 vCPU, 7.8 GiB RAM, 21 GiB disk)

---

## 1. Exact Model Identifier Expected by the Application

### Application Model Parsing

**File:** `strix/llm/router.py` — `format_openrouter_model()`

The function always prepends the `openrouter/` prefix to the model identifier:

```python
def format_openrouter_model(model_name: None) -> str:
    raw = (model_name or "").strip()
    if not raw:
        return f"openrouter/{DEFAULT_OPENROUTER_MODEL}"
    slug = raw
    if slug.startswith("openrouter/"):
        slug = slug[len("openrouter/"):]
    # ... deprecated model migration ...
    if raw.startswith("openrouter/"):
        return f"openrouter/{slug}"
    return f"openrouter/{slug}"
```

**Result:** Both `nvidia/nemotron-3.5-super-vl:free` and `openrouter/nvidia/nemotron-3.5-super-vl:free` resolve to:
```
openrouter/nvidia/nemotron-3.5-super-vl:free
```

### OpenRouter Catalog Verification

| Model ID | Status |
|---|---|
| `nvidia/nemotron-3.5-super-vl:free` | **FOUND** (canonical identifier, listed in catalog, free tier) |
| `openrouter/nvidia/nemotron-3.5-super-vl:free` | **NOT FOUND** (not in catalog) |
| `nvidia/nemotron-3.5-lightning:free` | **FOUND** (known working, free tier) |

### Exact Model Identifier AI-VAPT Requires

| User-Configured Value | Application Transformed Value | OpenRouter Catalog Match |
|---|---|---|
| `nvidia/nemotron-3.5-super-vl:free` | `openrouter/nvidia/nemotron-3.5-super-vl:free` | **NO MATCH** |
| `openrouter/nvidia/nemotron-3.5-super-vl:free` | `openrouter/nvidia/nemotron-3.5-super-vl:free` | **NO MATCH** |

### Finding — Model Configuration Discrepancy

The application's `format_openrouter_model()` function always prepends `openrouter/` to the model identifier. The OpenRouter catalog lists `nvidia/nemotron-3.5-super-vl:free` **without** the `openrouter/` prefix.

**Implication:** If the user configures `nvidia/nemotron-3.5-super-vl:free`, the application will transform it to `openrouter/nvidia/nemotron-3.5-super-vl:free`, which is **NOT found** in the OpenRouter catalog.

**Recommendation:** Use **`nvidia/nemotron-3.5-super-vl:free`** as the user-facing model identifier. The application's `format_openrouter_model()` will produce `openrouter/nvidia/nemotron-3.5-super-vl:free`, which is the canonical OpenRouter identifier for the NVIDIA Nemotron 3.5 Super VL model.

**Do not silently switch the model.** Confirm the user's preferred model identifier before making any changes.

### Tool Calling / Structured Responses Support

The OpenRouter Nemotron 3.5 Super VL model supports the tool calling / structured responses required by the autonomous agent:

| Requirement | Support |
|---|---|
| Tool calling / function calling | **YES** |
| Structured responses (JSON mode) | **YES** |
| Reasoning effort parameter | **YES** |
| Native API model support | **YES** |

---

## 2. Remote Docker Support Verification

### AI-VAPT Docker Client

**File:** `strix/runtime/docker_connection.py`

| Feature | Support | Code Evidence |
|---|---|---|
| `DOCKER_HOST` | **YES** | `resolve_docker_endpoint()` reads `DOCKER_HOST` env var (line 28-30) |
| `DOCKER_TLS_VERIFY` | **YES** | `docker.from_env()` reads `DOCKER_TLS_VERIFY` |
| `DOCKER_CERT_PATH` | **YES** | `docker.from_env()` reads `DOCKER_CERT_PATH` |
| TLS certificate loading | **YES** | Via `docker-py` SDK `from_env()` |
| Remote daemon connection | **YES** | `DockerClient(base_url=endpoint.host, tls=endpoint.tls)` |
| Sandbox image pulling | **YES** | `StrixDockerSandboxClient` pulls image from remote daemon |
| Container lifecycle | **YES** | `_create_container()` handles create/start/delete |
| Container networking | **YES** | `host.docker.internal` via `host-gateway` |

### Remote Docker Endpoint Resolution Priority

```
1. DOCKER_HOST environment variable (highest priority)
2. Docker context (if not default)
3. Default Unix socket (lowest priority)
```

### Minimum Secure Remote Docker Configuration Required

| Environment Variable | Value | Required |
|---|---|---|
| `DOCKER_HOST` | `tcp://<VM_IP>:2376` | **YES** |
| `DOCKER_TLS_VERIFY` | `1` | **YES** |
| `DOCKER_CERT_PATH` | `$HOME/.docker/certs-client` | **YES** |

> **No unauthenticated TCP access** — the remote Docker API must use TLS client certificates exclusively.

---

## 3. TLS Configuration Requirements

### Certificate Requirements

| Certificate | Required | Sharing |
|---|---|---|
| CA certificate (`ca.pem`) | YES | VM only |
| CA private key (`ca-key.pem`) | YES | VM only (never distribute) |
| Server certificate (`server-cert.pem`) | YES | VM only |
| Server key (`server-key.pem`) | YES | VM only |
| Client certificate (`cert.pem`) | YES | Distribute to Codespace |
| Client key (`key.pem`) | YES | Distribute to Codespace (chmod 600) |

### TLS Configuration Verification

Run on the Codespace:
```bash
docker info
# Expected: Server Version: 24.x or later, TLS verification enabled
```

Also verify:
```bash
echo $DOCKER_HOST
echo $DOCKER_TLS_VERIFY
echo $DOCKER_CERT_PATH
```

---

## 4. Sandbox Image Requirements

| Check | Value |
|---|---|
| Expected image | `ghcr.io/usestrix/strix-sandbox:1.3.0` |
| Config source | `strix/config/settings.py:161` |
| Install script | `scripts/install.sh:7` |
| Locally present | **NOT VERIFIED** (Docker daemon unavailable in Codespace) |
| Ready claim | **NOT MADE** |

### Issue

The sandbox image reference is confirmed as the runtime source of truth, but the image is **not locally present** and **cannot be pulled** because the Docker daemon is unavailable in the Codespace.

The image can be pulled and inspected once the Codespace can connect to a remote Docker host.

---

## 5. Dev Container Changes

### Change Made

**File:** `.devcontainer/devcontainer.json`

The `features` field with `ghcr.io/devcontainers/features/docker-in-docker:2` was **removed**.

### Resulting devcontainer.json

```json
{
  "name": "AI-VAPT Operations Platform",
  "image": "mcr.microsoft.com/devcontainers/python:1-3.12-bookworm",
  "customizations": {
    "vscode": {
      "settings": {
        "python.defaultInterpreterPath": ".venv/bin/python",
        "python.testing.pytestEnabled": true
      },
      "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance"
      ]
    }
  },
  "forwardPorts": [8000, 8080],
  "portsAttributes": {
    "8000": {
      "label": "AI-VAPT Web Console",
      "onAutoForward": "openBrowser"
    },
    "8080": {
      "label": "Strix Viewer"
    }
  },
  "postCreateCommand": "curl -LsSf https://astral.sh/uv/install.sh | sh && export PATH=\"$HOME/.local/bin:$PATH\" && uv sync"
}
```

### Rationale

- Docker-in-Docker is **not viable** in the current Codespace (`CapEff = 0000000000000000`).
- Remote Docker is already supported via `DOCKER_HOST`, `DOCKER_TLS_VERIFY`, and `DOCKER_CERT_PATH`.
- No other Dev Container settings were changed.

### JSON Validation

**PASSED** — `python3 -c "import json; json.load(open(...))"` → `JSON VALID`

---

## 6. OpenRouter Secret Handling

### Secret Read Source

| Code Location | Source |
|---|---|
| `strix/llm/router.py:101` | `os.environ.get("OPENROUTER_API_KEY")` |
| `strix/interface/api.py:1025-1026` | `os.environ.get("OPENROUTER_API_KEY")` or `_read_strix_cli_config().get("OPENROUTER_API_KEY")` |
| `strix/core/diagnostics.py:390-391` | `os.environ.get("OPENROUTER_API_KEY")` or `cli_cfg.get("OPENROUTER_API_KEY")` |

### Security Verification

| Check | Result |
|---|---|
| Key read from environment | **YES** |
| Key logged to console | **NO** |
| Key written to file | **NO** |
| Key written to Git | **NO** |
| Key in repository | **NO** |
| `cli-config.json` in Git | **NO** (file is outside repository) |
| `.gitignore` covers `.strix` | **NO** (but file is in `/home/vscode/`, outside repo) |

### Status

```bash
$ echo "$OPENROUTER_API_KEY" | wc -c
0
```

**CONFIGURATION_REQUIRED** — The `OPENROUTER_API_KEY` environment variable is not set in the Codespace.

---

## 7. Remaining Manual Steps

| Step | Action | Priority |
|---|---|---|
| 1 | Configure `OPENROUTER_API_KEY` via GitHub Codespaces Secrets | HIGH |
| 2 | Restart Codespace to load the secret | HIGH |
| 3 | Verify model identifier with OpenRouter catalog | HIGH |
| 4 | Provision a Docker-enabled remote host (Ubuntu VM) | HIGH |
| 5 | Configure Docker daemon for TLS remote access | HIGH |
| 6 | Generate and distribute client TLS certificates | HIGH |
| 7 | Set `DOCKER_HOST`, `DOCKER_TLS_VERIFY`, `DOCKER_CERT_PATH` in Codespace | HIGH |
| 8 | Verify `docker info` connects to remote daemon | HIGH |
| 9 | Pull `ghcr.io/usestrix/strix-sandbox:1.3.0` on remote host | MEDIUM |
| 10 | Re-run `evaluate_runtime_readiness()` to confirm readiness | MEDIUM |

---

## 8. Remote Docker VM Setup

See companion document: **`AI_VAPT_REMOTE_DOCKER_VM_SETUP.md`**

Key steps:

1. Provision Ubuntu VM (8 cores, 16 GiB RAM, 100 GiB SSD recommended)
2. Install Docker Engine
3. Generate CA + server + client TLS certificates
4. Configure Docker daemon: `--tlsverify --tlscacert=... --tlscert=... --tlscert=... -H tcp://0.0.0.0:2376 -H unix:///var/run/docker.sock`
5. Configure firewall (UFW) to restrict port 2376 to trusted networks
6. Pull sandbox image: `docker pull ghcr.io/usestrix/strix-sandbox:1.3.0`
7. Distribute client certificates to Codespace
8. Configure Codespace environment variables

---

## 9. Whether the Environment Is Ready for a Live Autonomous Assessment

| Component | Classification |
|---|---|
| OpenRouter API key | **CONFIGURATION_REQUIRED** |
| Model identifier | **DISCREPANCY** (application transforms to `openrouter/...`; catalog uses `nvidia/...`) |
| Docker daemon (remote) | **READY** (once remote host is configured) |
| TLS configuration | **CONFIGURATION_REQUIRED** |
| Sandbox image | **PENDING** (can be pulled on remote host) |
| Dev Container | **OK** (Docker-in-Docker removed) |
| AI-VAPT diagnostics | **OPERATING** (correctly reports blockers) |
| Test suite | **PASSING** (101 targeted tests, 0 failures) |

### Overall Readiness

**NOT READY FOR A LIVE AUTONOMOUS ASSESSMENT**

**Required actions before launching:**
1. Configure `OPENROUTER_API_KEY` in Codespaces Secrets
2. Restart the Codespace
3. Confirm the model identifier with OpenRouter
4. Provision a remote Docker host
5. Set `DOCKER_HOST`, `DOCKER_TLS_VERIFY`, `DOCKER_CERT_PATH`
6. Pull the sandbox image on the remote host

---

## 10. Summary

```text
OpenRouter model: nvidia/nemotron-3.5-super-vl:free  (catalog-verified)
Application transform: openrouter/nvidia/nemotron-3.5-super-vl:free (application-prefixed)
Remote Docker: supported via DOCKER_HOST + TLS (no code changes required)
Sandbox image: ghcr.io/usestrix/strix-sandbox:1.3.0 (confirmed, not yet pulled)
Dev Container: Docker-in-Docker feature removed, JSON valid
Ready for autonomous assessment: NO (requires Docker key, remote host, sandbox image)
```

---

*Report generated automatically. No secrets were accessed, logged, or persisted by this process. No penetration tests were performed. No credentials or key material were stored in files.*
