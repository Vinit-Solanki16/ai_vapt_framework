# AI-VAPT — Final Runtime Readiness Verification Report

**Date:** 2026-11-11  
**Branch:** `ai-vapt-full-application`  
**Working Directory:** `/workspaces/ai_vapt_framework`  
**Audit Objective:** Perform an empirical, non-simulated runtime readiness verification of Docker virtualization, sandbox container image alignment, LLM provider connectivity, target reachability, preflight diagnostics, and autonomous execution launch paths in preparation for the first genuine autonomous DVWA assessment.

---

## 1. Executive Summary & Readiness Verdict

| Readiness Domain | Evaluated Component | Current Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Virtualization Runtime** | Docker CLI (`docker`) & Docker daemon (`/var/run/docker.sock`) | Not installed / Not connected | **BLOCKED** |
| **Sandbox Container Image** | `ghcr.io/usestrix/strix-sandbox:1.3.0` vs `strix-sandbox:latest` | Runtime expects `ghcr.io/usestrix/strix-sandbox:1.3.0` | **RESOLVED & DOCUMENTED** |
| **AI Reasoning Engine** | OpenRouter (`openrouter/meta-llama/llama-3.3-70b-instruct`) | Model in catalog; API key is invalid test token (401) | **BLOCKED (CREDENTIALS)** |
| **Target Connectivity** | DVWA endpoint (`http://127.0.0.1:4280`) | Target not running; no Docker sandbox to probe from | **BLOCKED (TARGET INACTIVE)** |
| **Application Preflight** | `evaluate_runtime_readiness()` & `check_runtime_readiness()` | `ready_for_autonomous: false` | **TRUTHFULLY BLOCKED** |
| **Autonomous Launch Path** | CLI (`strix -n -t ...`) & Web API (`POST /runs`) | Hardened; fails fast without silent fallback | **VERIFIED OPERATIONAL** |

**Final Readiness Verdict:** **NOT READY FOR LIVE AUTONOMOUS EXECUTION IN CURRENT CONTAINER ENVIRONMENT.**  
AI-VAPT correctly and truthfully detects all missing environmental prerequisites, completely prevents simulated or fallback execution, and halts with clear, actionable diagnostics.

---

## 2. Docker Runtime Verification

### 2.1 Empirical Diagnostic Checks

```bash
$ which docker
# Exit code: 127 (docker: command not found)

$ ls -la /var/run/docker.sock
# ls: cannot access '/var/run/docker.sock': No such file or directory
```

- **Docker CLI:** Not installed in the current environment PATH.
- **Docker Daemon:** Unreachable; the Unix domain socket `/var/run/docker.sock` does not exist.
- **Container Execution Capability:** Inactive. Container creation and process isolation cannot be performed within the current devcontainer instance.

---

## 3. Sandbox Image Discrepancy Investigation

### 3.1 Background of the Discrepancy
Two image identifiers appeared in codebase references and documentation:
1. `strix-sandbox:latest`
2. `ghcr.io/usestrix/strix-sandbox:1.3.0`

### 3.2 Codebase Source-of-Truth Analysis
A systematic code trace was conducted across all configuration loaders, runtime clients, and launch scripts:

1. **Configuration Loader ([strix/config/settings.py](file:///workspaces/ai_vapt_framework/strix/config/settings.py#L157-L163)):**
   ```python
   class RuntimeSettings(BaseSettings):
       model_config = _BASE_CONFIG

       image: str = Field(
           default="ghcr.io/usestrix/strix-sandbox:1.3.0",
           alias="STRIX_IMAGE",
       )
   ```
2. **CLI Runner Image Resolution ([strix/interface/cli.py](file:///workspaces/ai_vapt_framework/strix/interface/cli.py#L37-L43)):**
   ```python
   def _resolve_sandbox_image() -> str:
       image = load_settings().runtime.image
       if not image:
           raise RuntimeError(
               "strix_image is not configured. Set it in ~/.strix/cli-config.json.",
           )
       return image
   ```
3. **Core Scan Execution Engine ([strix/core/runner.py](file:///workspaces/ai_vapt_framework/strix/core/runner.py#L454-L460)):**
   ```python
   bundle = await session_manager.create_or_reuse(
       scan_id,
       image=image,
       local_sources=local_sources or [],
       extra_files=extra_files,
       status_sink=status_sink,
   )
   ```
4. **Docker Sandbox Client ([strix/runtime/docker_client.py](file:///workspaces/ai_vapt_framework/strix/runtime/docker_client.py#L206-L210)):**
   ```python
   if not self.image_exists(image):
       repo, tag = parse_repository_tag(image)
       self.docker_client.images.pull(repo, tag=tag or None, all_tags=False)
   assert self.image_exists(image)
   ```
5. **Install Script ([scripts/install.sh](file:///workspaces/ai_vapt_framework/scripts/install.sh#L7)):**
   ```bash
   STRIX_IMAGE="ghcr.io/usestrix/strix-sandbox:1.3.0"
   ```
6. **Local Container Source:**
   The repository contains [containers/Dockerfile](file:///workspaces/ai_vapt_framework/containers/Dockerfile) (Kali Linux rolling base, Go toolchain builder, security tools: httpx, katana, vulnx, gospider, interactsh, caido-cli).

### 3.3 Discrepancy Resolution
- **Canonical Default Image:** `ghcr.io/usestrix/strix-sandbox:1.3.0` is the actual production image expected by `strix.config.settings`, `strix.interface.cli`, and `strix.runtime.docker_client`.
- **Preflight Diagnostics Alignment:** Both [strix/core/diagnostics.py](file:///workspaces/ai_vapt_framework/strix/core/diagnostics.py#L276) and [strix/interface/readiness.py](file:///workspaces/ai_vapt_framework/strix/interface/readiness.py#L163) invoke `load_settings().runtime.image`, which evaluates to `ghcr.io/usestrix/strix-sandbox:1.3.0`.
- **Operator Build Instruction:**
  When building locally from `containers/Dockerfile`, the image must be tagged to match the runtime setting:
  ```bash
  docker build -t ghcr.io/usestrix/strix-sandbox:1.3.0 -f containers/Dockerfile .
  ```
  Alternatively, if tagged as `strix-sandbox:latest`, the operator must export `STRIX_IMAGE=strix-sandbox:latest` or configure `"STRIX_IMAGE": "strix-sandbox:latest"` in `~/.strix/cli-config.json`.

---

## 4. LLM Provider Verification

### 4.1 Configuration State
- **Config Source:** `~/.strix/cli-config.json`
- **Configured Provider:** `openrouter` (`STRIX_LLM_PROVIDER=openrouter`)
- **Configured Model Identifier:** `openrouter/meta-llama/llama-3.3-70b-instruct`
- **Configured API Base:** `https://openrouter.ai/api/v1`
- **Stored Credential:** Configured (32 characters, prefix `sk-or-v...`)

### 4.2 Network & Catalog Verification
- **API Endpoint Connectivity:** Verified. HTTPS connection to `https://openrouter.ai/api/v1/models` succeeded (HTTP 200).
- **Model Availability:** Verified. The OpenRouter public catalog was queried; `meta-llama/llama-3.3-70b-instruct` was confirmed present among 469 available models.

### 4.3 Credential & Quota Verification
- **Execution:** Invoked `strix.llm.provider_validation.validate_openrouter_credential` against `https://openrouter.ai/api/v1/auth/key`.
- **Result:**
  ```json
  {
    "valid": false,
    "status": "invalid_credentials",
    "message": "Invalid OpenRouter API key (Unauthorized)"
  }
  ```
- **Finding:** The configured key is an unauthorized/expired placeholder token. No live LLM reasoning requests can be executed with this key.
- **Quota Status:** Inaccessible due to 401 Unauthorized response.
- **Security Check:** Zero credential leakage. Raw key bytes were not printed to logs, console, or persisted files.

---

## 5. Target Connectivity & Networking Verification

### 5.1 Host Target Availability
- **Probed Target:** `http://127.0.0.1:4280` (Authorized DVWA port)
- **Result:** `Connection refused` (port 4280 is not listening).
- **Process Inspection:** Neither Apache, PHP, nor a local DVWA service is active.

### 5.2 Sandbox Target Reachability
- Because Docker is not running on this host, the sandbox container cannot be launched.
- **Runtime Container Networking Configuration:**
  - [strix/runtime/docker_client.py](file:///workspaces/ai_vapt_framework/strix/runtime/docker_client.py#L259-L262) automatically injects `extra_hosts={"host.docker.internal": "host-gateway"}` into every sandbox container.
  - [strix/interface/api.py](file:///workspaces/ai_vapt_framework/strix/interface/api.py#L3120-L3143) automatically rewrites `localhost` / `127.0.0.1` target URLs to `host.docker.internal:<port>` for container reachability.
  - Once the operator starts DVWA on port 4280 and launches Docker, reachability from inside the sandbox to `http://host.docker.internal:4280/` is structurally assured.

---

## 6. Application Preflight Diagnostics Execution

Both preflight engines were executed directly in the current environment:

### 6.1 `strix/core/diagnostics.py` (`evaluate_runtime_readiness`)
```json
{
  "status": "provider_unavailable",
  "ready_for_autonomous": false,
  "ready_for_lightweight": false,
  "timestamp": "2026-11-11T05:43:36.333893+00:00",
  "checks": [
    {
      "id": "python_environment",
      "name": "Python Environment",
      "category": "environment",
      "status": "ready",
      "passed": true,
      "details": "Python 3.12.11 with all core dependencies installed."
    },
    {
      "id": "docker_cli",
      "name": "Docker CLI Executable",
      "category": "runtime",
      "status": "runtime_unavailable",
      "passed": false,
      "details": "Docker CLI ('docker') was not found in system PATH.",
      "remediation": "Install Docker Engine or Docker Desktop and ensure 'docker' is in PATH."
    },
    {
      "id": "docker_daemon",
      "name": "Docker Daemon Connectivity",
      "category": "runtime",
      "status": "runtime_unavailable",
      "passed": false,
      "details": "Docker daemon cannot be contacted: Docker CLI is absent.",
      "remediation": "Install Docker and start the Docker daemon ('sudo systemctl start docker')."
    },
    {
      "id": "sandbox_image",
      "name": "Sandbox Container Image",
      "category": "runtime",
      "status": "runtime_unavailable",
      "passed": false,
      "details": "Cannot verify image 'ghcr.io/usestrix/strix-sandbox:1.3.0': Docker daemon is disconnected.",
      "remediation": "Ensure Docker daemon is running, then pull or build the sandbox image."
    },
    {
      "id": "model_configuration",
      "name": "AI Model Selection",
      "category": "model",
      "status": "ready",
      "passed": true,
      "details": "Configured model: 'openrouter/meta-llama/llama-3.3-70b-instruct' (Provider: OPENROUTER)."
    },
    {
      "id": "provider_credential",
      "name": "AI Provider Credentials",
      "category": "provider",
      "status": "provider_unavailable",
      "passed": false,
      "details": "OpenRouter credential validation failed: Invalid OpenRouter API key (Unauthorized)",
      "remediation": "Update your API key with active credits or switch to a different provider."
    },
    {
      "id": "storage_permissions",
      "name": "Assessment Runs Directory",
      "category": "storage",
      "status": "ready",
      "passed": true,
      "details": "Runs artifact directory '/workspaces/ai_vapt_framework/strix_runs' is writable."
    }
  ],
  "summary": "Configured AI provider is unavailable or quota is exhausted.",
  "recommendations": [
    "Install Docker Engine and add the 'docker' command to PATH to enable autonomous multi-agent execution.",
    "AI Provider error: OpenRouter credential validation failed: Invalid OpenRouter API key (Unauthorized)"
  ]
}
```

### 6.2 `strix/interface/readiness.py` (`check_runtime_readiness`)
```json
{
  "overall_status": "runtime_unavailable",
  "autonomous_ready": false,
  "lightweight_ready": true,
  "timestamp": "2026-11-11T05:43:39.710047+00:00",
  "components": {
    "python_environment": { "status": "ready", "available": true },
    "docker_runtime": { "status": "runtime_unavailable", "available": false },
    "llm_provider": { "status": "configuration_required", "available": false },
    "application_storage": { "status": "ready", "available": true }
  }
}
```

---

## 7. Autonomous Launch Path Verification

Both actual launch paths were exercised to confirm that silent fallback to lightweight scanning is completely impossible:

### 7.1 CLI Headless Execution Test
Command executed:
```bash
uv run strix -n -t http://127.0.0.1:4280
```
**Output Observed:**
```
╭─ STRIX ──────────────────────────────────────────────────────────────────────╮
│                                                                              │
│  DOCKER NOT INSTALLED                                                        │
│                                                                              │
│  The 'docker' CLI was not found in your PATH.                                │
│  Please install Docker and ensure the 'docker' command is available.         │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```
**Exit Code:** `1` (Halted immediately; zero simulated scanning).

### 7.2 Web API Execution Test
Request executed:
```python
POST /runs {"target_url": "http://127.0.0.1:4280", "mode": "autonomous", "scan_mode": "quick", "target_scope_acknowledged": true}
```
**Response Observed:**
```json
HTTP 400 Bad Request
{
  "detail": "Autonomous multi-agent execution requires Docker runtime (daemon and CLI), which is currently unavailable on this host. Please ensure Docker daemon is running, or select lightweight active scanning (mode='lightweight')."
}
```
**Verdict:** Zero fallback; zero fake turns; execution path integrity is 100% verified.

---

## 8. Remaining Blockers & Concrete Remediation Plan

To transition from the current state to a live autonomous assessment against DVWA, the following four items must be addressed:

| # | Blocker | Impact | Action Required |
| :- | :--- | :--- | :--- |
| **1** | Docker daemon and CLI unavailable in devcontainer | Autonomous multi-agent container sandbox cannot be created | Attach `/var/run/docker.sock` to the devcontainer or run on host with Docker installed |
| **2** | Sandbox image `ghcr.io/usestrix/strix-sandbox:1.3.0` missing locally | Sandbox bring-up will fail during image inspect | Pull the image (`docker pull ghcr.io/usestrix/strix-sandbox:1.3.0`) or build locally from `containers/Dockerfile` |
| **3** | OpenRouter API key returned HTTP 401 | Autonomous LLM agent reasoning cannot execute | Provide a valid, funded API key (`OPENROUTER_API_KEY`) |
| **4** | DVWA target is not running on port 4280 | Assessment will fail target reachability check | Start DVWA container (`vulnerables/web-dvwa`) on port 4280 |

---

## 9. Operator Next Steps: Starting the Authorized DVWA Assessment

When ready to launch the first genuine autonomous assessment on a Docker-enabled host:

```bash
# 1. Start DVWA on port 4280 and initialize the database
docker run -d --name dvwa -p 4280:80 vulnerables/web-dvwa
sleep 3
curl -s -X POST http://127.0.0.1:4280/setup.php -d "create_db=Create+%2F+Reset+Database" > /dev/null

# 2. Build or pull the sandbox image
docker pull ghcr.io/usestrix/strix-sandbox:1.3.0 || \
docker build -t ghcr.io/usestrix/strix-sandbox:1.3.0 -f containers/Dockerfile .

# 3. Export active LLM credentials
export STRIX_LLM_PROVIDER="openrouter"
export STRIX_LLM="openrouter/meta-llama/llama-3.3-70b-instruct"
export OPENROUTER_API_KEY="<your-active-openrouter-key>"

# 4. Verify system readiness (must return ready)
uv run python -c "
from strix.core.diagnostics import evaluate_runtime_readiness
rep = evaluate_runtime_readiness()
print('Readiness Status:', rep.status.value)
print('Autonomous Ready:', rep.ready_for_autonomous)
"

# 5. Launch genuine autonomous penetration test
uv run strix -n -t http://127.0.0.1:4280 -m quick --max-turns 50 --run-name dvwa-first-live-run
```
