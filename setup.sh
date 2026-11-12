#!/usr/bin/env bash
# ==============================================================================
# AI-VAPT Platform — First-Time Portable Setup Script
# ==============================================================================
# Supports: Linux, GitHub Codespaces, macOS, Windows WSL2, Cloud VMs.
#
# Usage:
#   ./setup.sh
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ------------------------------------------------------------------------------
# Colors and Formatting
# ------------------------------------------------------------------------------
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
DIM="\033[2m"
RESET="\033[0m"

log_info()    { echo -e "${CYAN}[INFO]${RESET} $*"; }
log_success() { echo -e "${GREEN}[OK]${RESET} $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
log_error()   { echo -e "${RED}[ERROR]${RESET} $*"; }
log_step()    { echo -e "\n${BOLD}${CYAN}==>${RESET} ${BOLD}$*${RESET}"; }

echo -e "${BOLD}==============================================================================${RESET}"
echo -e "${BOLD}   AI-VAPT Platform — Portable Setup & Environment Initializer${RESET}"
echo -e "${BOLD}==============================================================================${RESET}"

# ------------------------------------------------------------------------------
# 1. Detect Operating System and Environment
# ------------------------------------------------------------------------------
log_step "1. Detecting Operating System and Environment..."

OS_TYPE="$(uname -s)"
ARCH_TYPE="$(uname -m)"
ENV_KIND="Standard Local"

if [ -n "${CODESPACES:-}" ] || [ -d "/workspaces" ]; then
    ENV_KIND="GitHub Codespaces"
elif [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/version 2>/dev/null; then
    ENV_KIND="Windows Subsystem for Linux (WSL2)"
elif [ "$OS_TYPE" = "Darwin" ]; then
    ENV_KIND="Apple macOS"
elif [ "$OS_TYPE" = "Linux" ]; then
    ENV_KIND="Generic Linux"
fi

log_info "Detected OS:           ${BOLD}${OS_TYPE} (${ARCH_TYPE})${RESET}"
log_info "Execution Environment: ${BOLD}${ENV_KIND}${RESET}"

# ------------------------------------------------------------------------------
# 2. Check System Requirements
# ------------------------------------------------------------------------------
log_step "2. Checking System Hardware Resources..."

CPU_CORES=$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1)
log_info "Available CPU Cores: ${CPU_CORES}"

# Memory check
MEM_AVAIL_MB=0
if [ -f /proc/meminfo ]; then
    MEM_AVAIL_MB=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)
    MEM_TOTAL_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)
    log_info "System Memory:       ${MEM_TOTAL_MB} MB total (${MEM_AVAIL_MB} MB available)"
fi

# Disk space check
DISK_AVAIL_MB=$(df -m . 2>/dev/null | awk 'NR==2 {print $4}' || echo 0)
log_info "Free Disk Space:     ${DISK_AVAIL_MB} MB"

if [ "$DISK_AVAIL_MB" -lt 2000 ] && [ "$DISK_AVAIL_MB" -gt 0 ]; then
    log_warn "Low disk space (<2 GB). Ensure sufficient space for Docker containers and run artifacts."
fi

# ------------------------------------------------------------------------------
# 3. Validate Python
# ------------------------------------------------------------------------------
log_step "3. Validating Python Runtime..."

PYTHON_BIN=""
for cmd in python3.12 python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        VER_STR=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
        MAJOR=$(echo "$VER_STR" | cut -d. -f1)
        MINOR=$(echo "$VER_STR" | cut -d. -f2)
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 12 ]; then
            PYTHON_BIN="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    log_error "Python 3.12+ is required but was not found."
    log_error "Please install Python 3.12 or newer (e.g. 'sudo apt install python3.12 python3.12-venv')."
    exit 1
fi

PY_FULL_VER=$("$PYTHON_BIN" --version 2>&1)
log_success "Found compatible Python: ${PY_FULL_VER} (${PYTHON_BIN})"

# ------------------------------------------------------------------------------
# 4. Create or Validate Virtual Environment
# ------------------------------------------------------------------------------
log_step "4. Setting Up Python Virtual Environment..."

USE_UV=false
if command -v uv >/dev/null 2>&1; then
    USE_UV=true
    log_info "Detected fast package manager: uv ($(uv --version))"
fi

if [ ! -d ".venv" ]; then
    log_info "Creating virtual environment in .venv..."
    if [ "$USE_UV" = true ]; then
        uv venv --python "$PYTHON_BIN" .venv
    else
        "$PYTHON_BIN" -m venv .venv
    fi
    log_success "Virtual environment created at .venv"
else
    log_success "Existing virtual environment found at .venv"
fi

VENV_PY="$SCRIPT_DIR/.venv/bin/python"
if [ ! -f "$VENV_PY" ]; then
    # Windows fallback
    VENV_PY="$SCRIPT_DIR/.venv/Scripts/python.exe"
fi

# ------------------------------------------------------------------------------
# 5. Install Python Dependencies
# ------------------------------------------------------------------------------
log_step "5. Installing Project Dependencies..."

if [ "$USE_UV" = true ]; then
    log_info "Installing dependencies via 'uv sync'..."
    uv sync
else
    log_info "Installing dependencies via pip..."
    "$VENV_PY" -m pip install --upgrade pip
    "$VENV_PY" -m pip install -e .
fi
log_success "Core dependencies installed and verified."

# ------------------------------------------------------------------------------
# 6. Validate Frontend Assets
# ------------------------------------------------------------------------------
log_step "6. Validating Web Operations Console Assets..."

INDEX_HTML="strix/interface/web/index.html"
if [ -f "$INDEX_HTML" ]; then
    log_success "Web console frontend single-page application is present: ${INDEX_HTML}"
else
    log_error "Frontend single-page application entry point missing: ${INDEX_HTML}"
    exit 1
fi

# ------------------------------------------------------------------------------
# 7. Environment Configuration (.env)
# ------------------------------------------------------------------------------
log_step "7. Checking Environment Configuration (.env)..."

if [ -f ".env" ]; then
    log_success ".env already exists. Preserving existing user configuration."
else
    if [ -f ".env.example" ]; then
        cp .env.example .env
        log_success "Created .env from .env.example template."
        log_info "You can configure your provider credentials and Docker settings in .env."
    else
        touch .env
        log_warn "No .env.example found; created blank .env file."
    fi
fi

# Load .env variables without polluting parent environment
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env 2>/dev/null || true
    set +a
fi

# ------------------------------------------------------------------------------
# 8. Check Docker Installation and Daemon Connectivity
# ------------------------------------------------------------------------------
log_step "8. Checking Docker Runtime & Connectivity..."

DOCKER_CLI_PRESENT=false
DOCKER_DAEMON_OK=false
DOCKER_MODE="none"

if command -v docker >/dev/null 2>&1; then
    DOCKER_CLI_PRESENT=true
    DOCKER_VER=$(docker --version 2>/dev/null || echo "Unknown")
    log_success "Docker CLI is present: ${DOCKER_VER}"
else
    log_warn "Docker CLI ('docker') not found in PATH."
fi

# Check for Codespaces Secrets to automatically install TLS certificates
if [ -n "${AI_VAPT_DOCKER_CA_CERT:-}" ] && [ -x "scripts/install_codespaces_docker_certs.sh" ]; then
    log_info "Codespaces Docker secrets detected. Installing client TLS certificates..."
    ./scripts/install_codespaces_docker_certs.sh || true
fi

# Check Docker connection (local socket or DOCKER_HOST)
if [ "$DOCKER_CLI_PRESENT" = true ]; then
    if [ -n "${DOCKER_HOST:-}" ]; then
        log_info "DOCKER_HOST is configured: ${DOCKER_HOST}"
        if [ "${DOCKER_TLS_VERIFY:-0}" = "1" ]; then
            log_info "Docker TLS authentication is enabled (cert path: ${DOCKER_CERT_PATH:-default})"
        fi
        if docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
            DOCKER_DAEMON_OK=true
            DOCKER_MODE="remote"
            log_success "Successfully connected to Remote Docker Daemon at ${DOCKER_HOST}"
        else
            log_warn "Could not connect to Remote Docker Daemon at ${DOCKER_HOST}"
            log_info "Run \`python scripts/verify_remote_docker.py\` for full connection diagnostics."
        fi
    else
        if docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
            DOCKER_DAEMON_OK=true
            DOCKER_MODE="local"
            log_success "Local Docker daemon is running and reachable via local socket."
        else
            log_warn "Local Docker daemon is not running or socket is inaccessible."
            log_info "In GitHub Codespaces, configure remote Docker via DOCKER_HOST (see AI_VAPT_CODESPACES_RUNTIME_GUIDE.md)."
        fi
    fi
fi

# ------------------------------------------------------------------------------
# 9. Check and Pull Strix Sandbox Image
# ------------------------------------------------------------------------------
log_step "9. Checking Strix Sandbox Container Image..."

CONFIGURED_IMAGE="${STRIX_IMAGE:-ghcr.io/usestrix/strix-sandbox:1.3.0}"
log_info "Target Sandbox Image: ${BOLD}${CONFIGURED_IMAGE}${RESET}"

IMAGE_EXISTS=false
if [ "$DOCKER_DAEMON_OK" = true ]; then
    if docker image inspect "$CONFIGURED_IMAGE" >/dev/null 2>&1; then
        IMAGE_EXISTS=true
        log_success "Sandbox image '${CONFIGURED_IMAGE}' is already present locally."
    else
        log_info "Image '${CONFIGURED_IMAGE}' not found locally. Attempting pull..."
        if docker pull "$CONFIGURED_IMAGE"; then
            IMAGE_EXISTS=true
            log_success "Successfully pulled sandbox image '${CONFIGURED_IMAGE}'."
        else
            log_warn "Failed to automatically pull '${CONFIGURED_IMAGE}'. You can pull it manually later."
        fi
    fi
else
    log_info "Docker daemon is not connected. Skipping image pull check."
fi

# ------------------------------------------------------------------------------
# 10. Check AI Provider Configuration (Safe, No Secret Leakage)
# ------------------------------------------------------------------------------
log_step "10. Inspecting AI Provider Configuration..."

check_key_configured() {
    local var_name="$1"
    local val="${!var_name:-}"
    if [ -n "$val" ]; then
        local len=${#val}
        echo -e "Configured (${len} chars, ${val:0:4}...${val: -3})"
    else
        echo -e "Not set"
    fi
}

log_info "OPENROUTER_API_KEY: $(check_key_configured OPENROUTER_API_KEY)"
log_info "OPENAI_API_KEY:     $(check_key_configured OPENAI_API_KEY)"
log_info "GEMINI_API_KEY:     $(check_key_configured GEMINI_API_KEY)"
log_info "OLLAMA_HOST:        ${OLLAMA_HOST:-http://localhost:11434 (default)}"
log_info "STRIX_LLM:          ${STRIX_LLM:-${OPENROUTER_MODEL:-Default (openrouter/nvidia/nemotron-3.5-lightning:free)}}"

# ------------------------------------------------------------------------------
# 11. Run Application Readiness Check
# ------------------------------------------------------------------------------
log_step "11. Running AI-VAPT Application Readiness Preflight..."

PREFLIGHT_OUTPUT=""
if [ -f "$VENV_PY" ]; then
    PREFLIGHT_OUTPUT=$("$VENV_PY" -c '
import json
try:
    from strix.interface.readiness import check_runtime_readiness
    r = check_runtime_readiness()
    print("STATUS:" + r.status)
    for name, comp in r.components.items():
        print(f"COMP:{name}:{comp.status}:{comp.available}:{comp.actionable_message}")
except Exception as exc:
    print(f"ERROR:{exc}")
' 2>/dev/null || echo "ERROR:Failed to execute readiness script")
fi

log_info "Readiness Diagnostic Results:"
while IFS= read -r line; do
    if [[ "$line" =~ ^COMP: ]]; then
        IFS=':' read -r _ c_name c_status c_avail c_msg <<< "$line"
        if [ "$c_avail" = "True" ] || [ "$c_status" = "ready" ]; then
            echo -e "  ${GREEN}✓${RESET} ${BOLD}${c_name}${RESET}: ${c_status}"
        else
            echo -e "  ${YELLOW}!${RESET} ${BOLD}${c_name}${RESET}: ${c_status} (${c_msg})"
        fi
    fi
done <<< "$PREFLIGHT_OUTPUT"

# ------------------------------------------------------------------------------
# 12. Setup Summary
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}==============================================================================${RESET}"
echo -e "${BOLD}                       AI-VAPT SETUP SUMMARY                                 ${RESET}"
echo -e "${BOLD}==============================================================================${RESET}"

echo -e "• Python Environment:   ${GREEN}Ready${RESET} (${PY_FULL_VER})"
echo -e "• Dependencies:         ${GREEN}Installed${RESET} in .venv"
echo -e "• Web Console Assets:   ${GREEN}Verified${RESET}"
echo -e "• Configuration:        ${GREEN}.env configured${RESET}"

if [ "$DOCKER_DAEMON_OK" = true ] && [ "$IMAGE_EXISTS" = true ]; then
    echo -e "• Docker Runtime:       ${GREEN}Ready (${DOCKER_MODE})${RESET}"
    echo -e "• Sandbox Container:    ${GREEN}Ready (${CONFIGURED_IMAGE})${RESET}"
    echo -e "• Autonomous Execution: ${GREEN}READY${RESET} — Full containerized multi-agent testing enabled."
elif [ "$DOCKER_DAEMON_OK" = true ]; then
    echo -e "• Docker Runtime:       ${GREEN}Connected (${DOCKER_MODE})${RESET}"
    echo -e "• Sandbox Container:    ${YELLOW}Missing image${RESET} (${CONFIGURED_IMAGE})"
    echo -e "  ${YELLOW}→ Action:${RESET} Run: docker pull ${CONFIGURED_IMAGE}"
else
    echo -e "• Docker Runtime:       ${YELLOW}Unavailable on this host${RESET}"
    echo -e "• Autonomous Execution: ${YELLOW}BLOCKED until Docker is connected${RESET}"
    echo -e ""
    echo -e "  ${BOLD}Docker Runtime Options for Codespaces / Restricted Hosts:${RESET}"
    echo -e "  1. ${BOLD}Remote Docker Host over TLS (Recommended for Codespaces):${RESET}"
    echo -e "     Configure in .env or environment:"
    echo -e "       export DOCKER_HOST=tcp://<remote-docker-ip>:2376"
    echo -e "       export DOCKER_TLS_VERIFY=1"
    echo -e "       export DOCKER_CERT_PATH=/path/to/certs"
    echo -e "     See: AI_VAPT_REMOTE_DOCKER_VM_SETUP.md and AI_VAPT_DOCKER_RUNTIME_GUIDE.md"
    echo -e "  2. ${BOLD}Lightweight In-Process Scanning:${RESET}"
    echo -e "     Available without Docker for direct HTTP-based probing and API tests."
fi

echo -e "\n${BOLD}Next Steps:${RESET}"
echo -e "  1. Start the application:   ${GREEN}./start.sh${RESET}"
echo -e "  2. Stop the application:    ${GREEN}./stop.sh${RESET}"
echo -e "  3. Configure credentials:   Edit ${CYAN}.env${RESET} or enter keys in the Web Console UI"
echo -e "${BOLD}==============================================================================${RESET}\n"
