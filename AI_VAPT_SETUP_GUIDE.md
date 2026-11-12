# AI-VAPT Setup & Getting Started Guide

**Target Audience:** Security Engineers, Penetration Testers, AI-VAPT Developers  
**Platform Version:** AI-VAPT Autonomous Security Framework  

---

## 1. Quickstart (One-Command Experience)

Get AI-VAPT up and running in under three minutes:

```bash
# 1. Clone the repository
git clone https://github.com/your-org/ai_vapt_framework.git
cd ai_vapt_framework

# 2. Run first-time setup (validates Python, sets up virtualenv, checks Docker, creates .env)
./setup.sh

# 3. Configure credentials in .env (if testing with LLM API keys)
# Open .env with your editor of choice:
#   OPENROUTER_API_KEY=sk-or-v1-...
#   OPENAI_API_KEY=sk-...

# 4. Start AI-VAPT Operations Console
./start.sh

# 5. Open your browser:
#   http://localhost:8000
```

To stop the application at any time:
```bash
./stop.sh
```

---

## 2. System Requirements

| Resource | Minimum | Recommended | Notes |
|---|---|---|---|
| **Operating System** | Linux (Ubuntu 22.04+ / Debian 12+), macOS 13+, Windows 11 with WSL2 | Ubuntu 24.04 LTS / Debian 12 | Tested across Linux devcontainers, Codespaces, and bare metal. |
| **Python** | Python 3.12.0+ | Python 3.12.11+ | Managed via `uv` or system Python. |
| **CPU** | 2 Cores | 4+ Cores | Required for concurrent agent and probe execution. |
| **Memory (RAM)** | 4 GB | 8 GB+ (16 GB for full local Docker) | Docker sandbox allocates 2 GB per active scan. |
| **Disk Space** | 5 GB | 20 GB+ | Accommodates sandbox container image and scan artifacts. |
| **Docker** | Optional for lightweight scanning; **Mandatory** for autonomous agent execution | Docker Engine 24.0+ or Docker Desktop 4.25+ | Can run locally or via remote TLS daemon (`DOCKER_HOST`). |

---

## 3. Environment Configuration (`.env`)

The `.env` file is generated automatically from `.env.example` during `./setup.sh`. It is excluded from Git version control.

### AI Model Provider Options

You can configure one or more AI providers:

```bash
# --- OpenRouter (Default / Multi-Model Hub) ---
OPENROUTER_API_KEY=sk-or-v1-your-key-here
# Optional model override (defaults to openrouter/nvidia/nemotron-3.5-lightning:free):
STRIX_LLM=openrouter/nvidia/nemotron-3.5-lightning:free

# --- Google Gemini ---
GEMINI_API_KEY=your-gemini-api-key

# --- OpenAI ---
OPENAI_API_KEY=sk-your-openai-key

# --- Local Ollama (Zero External Network Access) ---
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:1.5b

# --- Custom OpenAI-Compatible Endpoints (vLLM, llama.cpp, Kaggle) ---
LLM_API_BASE=https://your-custom-endpoint/v1
LLM_API_KEY=your-key
```

### Docker Runtime Configuration

```bash
# Strix official sandbox image
STRIX_IMAGE=ghcr.io/usestrix/strix-sandbox:1.3.0

# Remote Docker Daemon (Required for GitHub Codespaces or external Docker servers)
# DOCKER_HOST=tcp://your-remote-docker-host:2376
# DOCKER_TLS_VERIFY=1
# DOCKER_CERT_PATH=/workspaces/ai_vapt_framework/.docker/certs
```

### Web Server Options

```bash
STRIX_WEB_PORT=8000
STRIX_WEB_HOST=0.0.0.0
```

---

## 4. Platform-Specific Setup Instructions

### 4.1 GitHub Codespaces
GitHub Codespaces containers run with restricted capabilities that prevent running an in-container Docker daemon (Docker-in-Docker is disabled by security policy).

- **For Lightweight In-Process Scanning**: Runs immediately with `./setup.sh` and `./start.sh`.
- **For Autonomous Containerized Multi-Agent Pentesting**: Connect to an external Docker host over TLS.
  1. Follow [`AI_VAPT_REMOTE_DOCKER_VM_SETUP.md`](file:///workspaces/ai_vapt_framework/AI_VAPT_REMOTE_DOCKER_VM_SETUP.md) to provision a secure Ubuntu Docker VM.
  2. Set `DOCKER_HOST`, `DOCKER_TLS_VERIFY`, and `DOCKER_CERT_PATH` in `.env`.
  3. Re-run `./setup.sh` to confirm connectivity.

### 4.2 Linux (Ubuntu / Debian / Arch / Fedora)
1. Install Docker Engine:
   ```bash
   sudo apt update && sudo apt install -y docker.io python3-venv
   sudo usermod -aG docker $USER
   newgrp docker
   sudo systemctl enable --now docker
   ```
2. Run `./setup.sh` and `./start.sh`.

### 4.3 Windows using WSL2
1. Install Docker Desktop for Windows.
2. Under Docker Desktop Settings → Resources → WSL Integration, enable integration with your installed Linux distribution (e.g. Ubuntu).
3. Open your WSL2 terminal:
   ```bash
   cd /path/to/ai_vapt_framework
   ./setup.sh
   ./start.sh
   ```

### 4.4 Apple macOS
1. Install Docker Desktop for Mac and start it.
2. Ensure Python 3.12 is installed (e.g. `brew install python@3.12 uv`).
3. Run `./setup.sh` and `./start.sh`.

---

## 5. Startup and Shutdown Commands

### Starting AI-VAPT
```bash
# Default: Starts in background daemon mode on port 8000
./start.sh

# Start in interactive foreground mode (displays real-time server output)
./start.sh --foreground

# Start on a custom port
./start.sh --port 8080

# Start on a custom host interface
./start.sh --host 127.0.0.1 --port 9000
```

### Stopping AI-VAPT
```bash
./stop.sh
```
`./stop.sh` cleanly stops background processes, frees ports, removes PID locks, and preserves all assessment records and artifacts in `strix_runs/`.

---

## 6. Troubleshooting

| Issue | Cause | Solution |
|---|---|---|
| **`Python 3.12+ is required but was not found`** | System Python is older than 3.12. | Install Python 3.12 via package manager or run `curl -LsSf https://astral.sh/uv/install.sh \| sh` followed by `uv python install 3.12`. |
| **`Port 8000 is already in use`** | Another service or detached instance is bound to 8000. | Run `./stop.sh` or launch on another port via `./start.sh --port 8088`. |
| **`Docker daemon not running or socket is inaccessible`** | Docker service is stopped or user lacks permission. | Run `sudo systemctl start docker` and ensure user is in the `docker` group (`sudo usermod -aG docker $USER`). |
| **`Autonomous multi-agent execution requires Docker runtime`** | Docker daemon cannot be reached. | Ensure local Docker is running or configure `DOCKER_HOST` for remote Docker. Alternatively, run with `mode='lightweight'` for in-process direct scanning. |
| **`OpenRouter authentication failed (HTTP 401)`** | Missing or invalid API key. | Configure a valid `OPENROUTER_API_KEY` in `.env` or input it in the Web Console UI settings. |
