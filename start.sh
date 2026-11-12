#!/usr/bin/env bash
# ==============================================================================
# AI-VAPT Platform — Everyday Application Startup Script
# ==============================================================================
# Starts the FastAPI Web Operations Console and background services.
#
# Usage:
#   ./start.sh              # Start in background (daemon mode, default)
#   ./start.sh --foreground # Start interactively in foreground
#   ./start.sh --port 8080  # Start on custom port
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

PID_FILE="$SCRIPT_DIR/.ai_vapt.pid"
LOG_FILE="$SCRIPT_DIR/ai_vapt_server.log"

# ------------------------------------------------------------------------------
# Parse Arguments
# ------------------------------------------------------------------------------
RUN_MODE="background"
PORT_ARG=""
HOST_ARG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--foreground)
            RUN_MODE="foreground"
            shift
            ;;
        -d|--daemon|--background)
            RUN_MODE="background"
            shift
            ;;
        -p|--port)
            PORT_ARG="$2"
            shift 2
            ;;
        -h|--host)
            HOST_ARG="$2"
            shift 2
            ;;
        --help)
            echo "Usage: ./start.sh [options]"
            echo "Options:"
            echo "  -d, --daemon, --background  Run server in the background (default)"
            echo "  -f, --foreground            Run server in foreground"
            echo "  -p, --port <port>           Listen port (default: 8000 or STRIX_WEB_PORT)"
            echo "  -h, --host <host>           Listen host (default: 0.0.0.0 or STRIX_WEB_HOST)"
            exit 0
            ;;
        *)
            log_warn "Unknown argument '$1', ignoring."
            shift
            ;;
    esac
done

echo -e "${BOLD}==============================================================================${RESET}"
echo -e "${BOLD}               AI-VAPT Platform — Service Startup                            ${RESET}"
echo -e "${BOLD}==============================================================================${RESET}"

# ------------------------------------------------------------------------------
# 1. Validate Initial Setup
# ------------------------------------------------------------------------------
if [ ! -d ".venv" ]; then
    log_warn "Virtual environment (.venv) not found."
    log_info "Running first-time setup via ./setup.sh..."
    ./setup.sh
fi

# Load .env if present
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env 2>/dev/null || true
    set +a
fi

# Determine host and port
HOST="${HOST_ARG:-${STRIX_WEB_HOST:-0.0.0.0}}"
PORT="${PORT_ARG:-${STRIX_WEB_PORT:-8000}}"

# Activate virtualenv python
VENV_PY="$SCRIPT_DIR/.venv/bin/python"
if [ ! -f "$VENV_PY" ]; then
    VENV_PY="$SCRIPT_DIR/.venv/Scripts/python.exe"
fi

if [ ! -f "$VENV_PY" ]; then
    log_error "Python executable missing from .venv. Run ./setup.sh to reinitialize."
    exit 1
fi

# ------------------------------------------------------------------------------
# 2. Check if Server is Already Running
# ------------------------------------------------------------------------------
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        log_warn "AI-VAPT server is already running with PID ${OLD_PID}."
        echo -e "  URL: ${CYAN}http://localhost:${PORT}/${RESET}"
        echo -e "  To stop: ${BOLD}./stop.sh${RESET}"
        exit 0
    else
        # Stale PID file
        rm -f "$PID_FILE"
    fi
fi

# Also check if port is currently in use
if command -v lsof >/dev/null 2>&1; then
    PORT_PID=$(lsof -ti :"$PORT" 2>/dev/null || true)
    if [ -n "$PORT_PID" ]; then
        log_warn "Port ${PORT} is already in use by process PID ${PORT_PID}."
        echo -e "  To stop the running process: ${BOLD}./stop.sh${RESET} or specify a different port: ${BOLD}./start.sh --port 8081${RESET}"
        exit 1
    fi
fi

# ------------------------------------------------------------------------------
# 3. Runtime Preflight Check
# ------------------------------------------------------------------------------
log_info "Verifying core dependencies and runtime status..."

# Docker status check (informational, non-blocking)
DOCKER_STATUS="unavailable"
DOCKER_IS_REMOTE=false
if [ -n "${DOCKER_HOST:-}" ]; then
    DOCKER_IS_REMOTE=true
fi

if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        DOCKER_STATUS="connected"
    fi
fi

if [ "$DOCKER_STATUS" = "connected" ]; then
    if [ "$DOCKER_IS_REMOTE" = true ]; then
        log_success "Remote Docker daemon: Connected (${DOCKER_HOST}). Autonomous multi-agent container mode is active."
    else
        log_success "Local Docker daemon: Connected. Autonomous multi-agent container mode is active."
    fi
else
    if [ "$DOCKER_IS_REMOTE" = true ]; then
        log_warn "Remote Docker daemon: Not reachable at ${DOCKER_HOST}."
        log_info "  Verify the remote VM is running, port 2376 is accessible, and TLS certs are in ${DOCKER_CERT_PATH:-~/.docker/certs-client}."
        log_info "  Run: python scripts/verify_remote_docker.py for detailed diagnostics."
    else
        log_warn "Docker daemon: Not connected on local host."
        log_info "  In GitHub Codespaces, configure remote Docker via DOCKER_HOST in .env to enable autonomous execution."
    fi
    log_info "  Autonomous container execution will be blocked until Docker is connected."
    log_info "  In-process lightweight security scanning and Web API remain fully available."
fi

# ------------------------------------------------------------------------------
# 4. Start Application Server
# ------------------------------------------------------------------------------
log_info "Starting AI-VAPT Web Operations Console on ${HOST}:${PORT}..."

if [ "$RUN_MODE" = "background" ]; then
    nohup "$VENV_PY" -m uvicorn strix.interface.api:app \
        --host "$HOST" \
        --port "$PORT" \
        --log-level info \
        > "$LOG_FILE" 2>&1 &
    
    SERVER_PID=$!
    disown "$SERVER_PID" 2>/dev/null || true
    echo "$SERVER_PID" > "$PID_FILE"

    # Wait up to 10 seconds for server to bind and respond to /health
    log_info "Waiting for service initialization (PID: ${SERVER_PID})..."
    READY=false
    for _ in {1..20}; do
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then
            break
        fi
        if curl -s -m 2 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 || curl -s -m 2 "http://localhost:${PORT}/health" >/dev/null 2>&1; then
            READY=true
            break
        fi
        sleep 0.5
    done

    if [ "$READY" = true ]; then
        log_success "AI-VAPT server started successfully!"
        echo -e "\n${BOLD}==============================================================================${RESET}"
        echo -e "  ${GREEN}● AI-VAPT Operations Console is running${RESET}"
        echo -e "  • Web Interface:    ${CYAN}http://localhost:${PORT}/${RESET}"
        echo -e "  • Health Endpoint:  ${CYAN}http://localhost:${PORT}/health${RESET}"
        echo -e "  • Process PID:      ${BOLD}${SERVER_PID}${RESET}"
        echo -e "  • Server Log:       ${DIM}${LOG_FILE}${RESET}"
        echo -e ""
        echo -e "  To stop the application: ${BOLD}./stop.sh${RESET}"
        echo -e "${BOLD}==============================================================================${RESET}\n"
    else
        log_error "Server process did not report ready within timeout."
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then
            log_error "Server process terminated unexpectedly. Check log:"
            echo -e "${RED}--- Last 20 lines of ${LOG_FILE} ---${RESET}"
            tail -n 20 "$LOG_FILE" 2>/dev/null || true
            rm -f "$PID_FILE"
            exit 1
        else
            log_warn "Server process is running (PID: ${SERVER_PID}), but health check hasn't responded yet."
            echo -e "  Check log: ${DIM}tail -f ${LOG_FILE}${RESET}"
        fi
    fi
else
    # Foreground execution
    log_info "Starting in interactive foreground mode. Press Ctrl+C to stop."
    echo "$$" > "$PID_FILE"
    trap 'rm -f "$PID_FILE"; exit 0' INT TERM EXIT
    exec "$VENV_PY" -m uvicorn strix.interface.api:app \
        --host "$HOST" \
        --port "$PORT" \
        --log-level info
fi
