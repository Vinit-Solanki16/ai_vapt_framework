#!/usr/bin/env bash
# ==============================================================================
# AI-VAPT Platform — Everyday Application Shutdown Script
# ==============================================================================
# Gracefully stops the FastAPI Web Operations Console.
# Preserves all run logs, findings, configurations, and Docker images.
#
# Usage:
#   ./stop.sh
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
RESET="\033[0m"

log_info()    { echo -e "${CYAN}[INFO]${RESET} $*"; }
log_success() { echo -e "${GREEN}[OK]${RESET} $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
log_error()   { echo -e "${RED}[ERROR]${RESET} $*"; }

PID_FILE="$SCRIPT_DIR/.ai_vapt.pid"

# Load .env if present to know configured port
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env 2>/dev/null || true
    set +a
fi
PORT="${STRIX_WEB_PORT:-8000}"

echo -e "${BOLD}==============================================================================${RESET}"
echo -e "${BOLD}               AI-VAPT Platform — Service Shutdown                           ${RESET}"
echo -e "${BOLD}==============================================================================${RESET}"

STOPPED=false

# 1. Stop via PID file if present
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        log_info "Stopping AI-VAPT service (PID: ${PID})..."
        kill -TERM "$PID" 2>/dev/null || true
        
        # Wait up to 10 seconds for clean exit
        for _ in {1..20}; do
            if ! kill -0 "$PID" 2>/dev/null; then
                break
            fi
            sleep 0.5
        done

        # Force kill if still hanging
        if kill -0 "$PID" 2>/dev/null; then
            log_warn "Process ${PID} did not terminate gracefully; sending SIGKILL..."
            kill -9 "$PID" 2>/dev/null || true
        fi

        log_success "AI-VAPT service (PID: ${PID}) stopped successfully."
        STOPPED=true
    else
        log_info "No active process found for PID ${PID:-empty}."
    fi
    rm -f "$PID_FILE"
fi

# 2. Check for any remaining uvicorn process bound to AI-VAPT port or running strix.interface.api
if command -v lsof >/dev/null 2>&1; then
    PORT_PIDS=$(lsof -ti :"$PORT" 2>/dev/null || true)
    if [ -n "$PORT_PIDS" ]; then
        for p in $PORT_PIDS; do
            # Check if this process belongs to strix / uvicorn
            CMDLINE=$(ps -p "$p" -o args= 2>/dev/null || true)
            if [[ "$CMDLINE" == *"strix.interface.api"* ]] || [[ "$CMDLINE" == *"uvicorn"* ]]; then
                log_info "Terminating residual AI-VAPT listener on port ${PORT} (PID: ${p})..."
                kill -TERM "$p" 2>/dev/null || true
                sleep 1
                if kill -0 "$p" 2>/dev/null; then
                    kill -9 "$p" 2>/dev/null || true
                fi
                STOPPED=true
            fi
        done
    fi
fi

# 3. Clean up pgrep for strix.interface.api if any residual
REMAINING=$(pgrep -f "strix.interface.api:app" 2>/dev/null || true)
if [ -n "$REMAINING" ]; then
    for p in $REMAINING; do
        log_info "Stopping residual AI-VAPT worker (PID: ${p})..."
        kill -TERM "$p" 2>/dev/null || true
        STOPPED=true
    done
fi

if [ "$STOPPED" = true ]; then
    echo -e "\n${GREEN}● AI-VAPT services are stopped.${RESET}"
    echo -e "• User data and scan artifacts in ${BOLD}strix_runs/${RESET} are preserved."
    echo -e "• Configurations in ${BOLD}.env${RESET} are preserved."
    echo -e "• Docker container images are preserved."
else
    log_info "AI-VAPT service was not running."
fi

echo -e "${BOLD}==============================================================================${RESET}\n"
