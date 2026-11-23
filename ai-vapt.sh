#!/usr/bin/env bash
# ==============================================================================
# AI-VAPT Platform — Unified Application Launcher
# ==============================================================================
# Primary operational control interface for AI-VAPT.
#
# Supported Commands:
#   setup       Run environment verification and install dependencies
#   start       Start the AI-VAPT Web Operations Console & API server
#   stop        Stop the running AI-VAPT services gracefully
#   restart     Restart the AI-VAPT services
#   status      Inspect running server, health endpoints, and Docker runtime
#   logs        View or tail backend server logs
#   help        Display command usage and options
#
# Usage:
#   ./ai-vapt.sh <command> [options]
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

# ------------------------------------------------------------------------------
# Paths & Default Settings
# ------------------------------------------------------------------------------
RUN_DIR="$SCRIPT_DIR/.run"
LOGS_DIR="$SCRIPT_DIR/logs"
mkdir -p "$RUN_DIR" "$LOGS_DIR" "$SCRIPT_DIR/strix_runs"

PID_FILE="$RUN_DIR/ai-vapt.pid"
LEGACY_PID_FILE="$SCRIPT_DIR/.ai_vapt.pid"
LOG_FILE="$LOGS_DIR/ai_vapt_server.log"
LEGACY_LOG_FILE="$SCRIPT_DIR/ai_vapt_server.log"

DEFAULT_HOST="127.0.0.1"
DEFAULT_PORT="8000"
ENV_FILE="$SCRIPT_DIR/.env"

# ------------------------------------------------------------------------------
# Virtualenv Python Resolution
# ------------------------------------------------------------------------------
get_python_bin() {
    local py="$SCRIPT_DIR/.venv/bin/python"
    if [ ! -f "$py" ]; then
        py="$SCRIPT_DIR/.venv/Scripts/python.exe"
    fi
    echo "$py"
}

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
load_env() {
    local target_env="${1:-$ENV_FILE}"
    if [ -f "$target_env" ]; then
        set -a
        # shellcheck disable=SC1090
        source "$target_env" 2>/dev/null || true
        set +a
    fi
}

get_active_pid() {
    local pid=""
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE" 2>/dev/null || true)
    elif [ -f "$LEGACY_PID_FILE" ]; then
        pid=$(cat "$LEGACY_PID_FILE" 2>/dev/null || true)
    fi

    if [ -n "$pid" ]; then
        if kill -0 "$pid" 2>/dev/null; then
            local cmdline
            cmdline=$(ps -p "$pid" -o args= 2>/dev/null || true)
            if [[ "$cmdline" == *"uvicorn"* ]] || [[ "$cmdline" == *"strix.interface.api"* ]] || [[ "$cmdline" == *"python"* ]]; then
                echo "$pid"
                return 0
            fi
        fi
    fi
    echo ""
}

cleanup_stale_pid_files() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
        fi
    fi
    if [ -f "$LEGACY_PID_FILE" ]; then
        local lpid
        lpid=$(cat "$LEGACY_PID_FILE" 2>/dev/null || true)
        if [ -z "$lpid" ] || ! kill -0 "$lpid" 2>/dev/null; then
            rm -f "$LEGACY_PID_FILE"
        fi
    fi
}

# ------------------------------------------------------------------------------
# Command: setup
# ------------------------------------------------------------------------------
cmd_setup() {
    log_step "Executing AI-VAPT Setup..."
    if [ -x "$SCRIPT_DIR/setup.sh" ]; then
        exec "$SCRIPT_DIR/setup.sh" "$@"
    else
        bash "$SCRIPT_DIR/setup.sh" "$@"
    fi
}

# ------------------------------------------------------------------------------
# Command: start
# ------------------------------------------------------------------------------
cmd_start() {
    local host=""
    local port=""
    local run_mode="background"
    local wait_timeout=15
    local custom_env=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--host)
                host="$2"
                shift 2
                ;;
            -p|--port)
                port="$2"
                shift 2
                ;;
            -d|--daemon|--background)
                run_mode="background"
                shift
                ;;
            -f|--foreground)
                run_mode="foreground"
                shift
                ;;
            -e|--env-file)
                custom_env="$2"
                shift 2
                ;;
            -w|--wait)
                wait_timeout="$2"
                shift 2
                ;;
            *)
                log_warn "Unknown start argument '$1', ignoring."
                shift
                ;;
        esac
    done

    # Load environment
    if [ -n "$custom_env" ]; then
        if [ ! -f "$custom_env" ]; then
            log_error "Custom environment file not found: $custom_env"
            exit 1
        fi
        load_env "$custom_env"
    else
        load_env "$ENV_FILE"
    fi

    local target_host="${host:-${STRIX_WEB_HOST:-$DEFAULT_HOST}}"
    local target_port="${port:-${STRIX_WEB_PORT:-$DEFAULT_PORT}}"

    local python_bin
    python_bin=$(get_python_bin)
    if [ ! -f "$python_bin" ]; then
        log_warn "Virtual environment (.venv) not found. Triggering setup..."
        cmd_setup
        python_bin=$(get_python_bin)
        if [ ! -f "$python_bin" ]; then
            log_error "Failed to locate Python binary after setup."
            exit 1
        fi
    fi

    # Check if already running
    cleanup_stale_pid_files
    local active_pid
    active_pid=$(get_active_pid)
    if [ -n "$active_pid" ]; then
        log_warn "AI-VAPT is already running (PID: ${active_pid})."
        echo -e "  Web Interface: ${CYAN}http://${target_host}:${target_port}/${RESET}"
        echo -e "  To stop:       ${BOLD}./ai-vapt.sh stop${RESET}"
        return 0
    fi

    # Check port conflicts
    if command -v lsof >/dev/null 2>&1; then
        local port_conflict
        port_conflict=$(lsof -ti :"$target_port" 2>/dev/null || true)
        if [ -n "$port_conflict" ]; then
            log_error "Port ${target_port} is already in use by process PID ${port_conflict}."
            log_info "Specify a different port via --port or stop the occupying process."
            exit 1
        fi
    fi

    log_step "Starting AI-VAPT Operations Console on ${target_host}:${target_port}..."

    if [ "$run_mode" = "foreground" ]; then
        echo "$$" > "$PID_FILE"
        echo "$$" > "$LEGACY_PID_FILE"
        trap 'rm -f "$PID_FILE" "$LEGACY_PID_FILE"; exit 0' INT TERM EXIT
        log_info "Running in foreground. Press Ctrl+C to stop."
        exec "$python_bin" -m uvicorn strix.interface.api:app \
            --host "$target_host" \
            --port "$target_port" \
            --log-level info
    else
        # Background daemon
        setsid "$python_bin" -m uvicorn strix.interface.api:app \
            --host "$target_host" \
            --port "$target_port" \
            --log-level info \
            < /dev/null > "$LOG_FILE" 2>&1 &

        local server_pid=$!
        disown "$server_pid" 2>/dev/null || true
        echo "$server_pid" > "$PID_FILE"
        echo "$server_pid" > "$LEGACY_PID_FILE"
        cp -f "$LOG_FILE" "$LEGACY_LOG_FILE" 2>/dev/null || true

        log_info "Waiting for service initialization (PID: ${server_pid}, timeout: ${wait_timeout}s)..."
        local ready=false
        local checks=$((wait_timeout * 2))

        for ((i=1; i<=checks; i++)); do
            if ! kill -0 "$server_pid" 2>/dev/null; then
                break
            fi
            if curl -s -m 2 "http://127.0.0.1:${target_port}/health" >/dev/null 2>&1 || \
               curl -s -m 2 "http://localhost:${target_port}/health" >/dev/null 2>&1; then
                ready=true
                break
            fi
            sleep 0.5
        done

        if [ "$ready" = true ]; then
            log_success "AI-VAPT Operations Console started successfully!"
            echo -e "\n${BOLD}==============================================================================${RESET}"
            echo -e "  ${GREEN}● AI-VAPT Operations Console is running${RESET}"
            echo -e "  • Web Interface:    ${CYAN}http://${target_host}:${target_port}/${RESET}"
            echo -e "  • Health Endpoint:  ${CYAN}http://${target_host}:${target_port}/health${RESET}"
            echo -e "  • Process PID:      ${BOLD}${server_pid}${RESET}"
            echo -e "  • Server Log:       ${DIM}${LOG_FILE}${RESET}"
            echo -e ""
            echo -e "  Manage commands:    ${BOLD}./ai-vapt.sh status${RESET} | ${BOLD}./ai-vapt.sh logs${RESET} | ${BOLD}./ai-vapt.sh stop${RESET}"
            echo -e "  Start Lab Target:   ${BOLD}./juice-shop.sh start${RESET}"
            echo -e "${BOLD}==============================================================================${RESET}\n"
        else
            log_error "Server failed to respond to health check within ${wait_timeout}s."
            if ! kill -0 "$server_pid" 2>/dev/null; then
                log_error "Process terminated unexpectedly. Last log entries:"
                echo -e "${RED}--- Tail of ${LOG_FILE} ---${RESET}"
                tail -n 25 "$LOG_FILE" 2>/dev/null || true
                rm -f "$PID_FILE" "$LEGACY_PID_FILE"
                exit 1
            else
                log_warn "Process is alive (PID: ${server_pid}) but health check timed out."
                log_info "Check logs with: ./ai-vapt.sh logs -f"
            fi
        fi
    fi
}

# ------------------------------------------------------------------------------
# Command: stop
# ------------------------------------------------------------------------------
cmd_stop() {
    load_env "$ENV_FILE"
    local port="${STRIX_WEB_PORT:-$DEFAULT_PORT}"
    log_step "Stopping AI-VAPT Services..."

    local stopped=false
    local active_pid
    active_pid=$(get_active_pid)

    if [ -n "$active_pid" ]; then
        log_info "Sending SIGTERM to AI-VAPT process (PID: ${active_pid})..."
        kill -TERM "$active_pid" 2>/dev/null || true

        # Wait up to 10 seconds for clean shutdown
        for _ in {1..20}; do
            if ! kill -0 "$active_pid" 2>/dev/null; then
                break
            fi
            sleep 0.5
        done

        if kill -0 "$active_pid" 2>/dev/null; then
            log_warn "Process ${active_pid} did not exit cleanly; sending SIGKILL..."
            kill -9 "$active_pid" 2>/dev/null || true
        fi

        log_success "AI-VAPT process (PID: ${active_pid}) terminated."
        stopped=true
    fi

    # Clean residual listeners on the configured port
    if command -v lsof >/dev/null 2>&1; then
        local residual_pids
        residual_pids=$(lsof -ti :"$port" 2>/dev/null || true)
        if [ -n "$residual_pids" ]; then
            for p in $residual_pids; do
                local args
                args=$(ps -p "$p" -o args= 2>/dev/null || true)
                if [[ "$args" == *"strix.interface.api"* ]] || [[ "$args" == *"uvicorn"* ]]; then
                    log_info "Terminating residual listener (PID: ${p})..."
                    kill -TERM "$p" 2>/dev/null || true
                    sleep 0.5
                    kill -9 "$p" 2>/dev/null || true
                    stopped=true
                fi
            done
        fi
    fi

    cleanup_stale_pid_files

    # Run Docker container cleanup backstop for orphaned sandbox containers
    local python_bin
    python_bin=$(resolve_python 2>/dev/null || true)
    if [ -n "$python_bin" ] && command -v docker >/dev/null 2>&1; then
        "$python_bin" -c '
from strix.runtime.docker_cleanup import reap_orphaned_containers
try:
    res = reap_orphaned_containers(min_age_seconds=0)
    if res.get("reaped", 0) > 0:
        print(f"Cleaned up {res[\"reaped\"]} residual sandbox containers.")
except Exception:
    pass
' 2>/dev/null || true
    fi

    if [ "$stopped" = true ]; then
        echo -e "\n${GREEN}● AI-VAPT service is stopped.${RESET}"
        echo -e "• Historical assessment data in ${BOLD}strix_runs/${RESET} is fully preserved."
        echo -e "• Configuration files and credentials are untouched."
    else
        log_info "AI-VAPT was not running."
    fi
    echo ""
}

# ------------------------------------------------------------------------------
# Command: restart
# ------------------------------------------------------------------------------
cmd_restart() {
    log_step "Restarting AI-VAPT Services..."
    cmd_stop
    sleep 1
    cmd_start "$@"
}

# ------------------------------------------------------------------------------
# Command: status
# ------------------------------------------------------------------------------
cmd_status() {
    load_env "$ENV_FILE"
    local port="${STRIX_WEB_PORT:-$DEFAULT_PORT}"
    local host="${STRIX_WEB_HOST:-$DEFAULT_HOST}"

    echo -e "\n${BOLD}==============================================================================${RESET}"
    echo -e "${BOLD}               AI-VAPT Platform — Service Status                             ${RESET}"
    echo -e "${BOLD}==============================================================================${RESET}"

    cleanup_stale_pid_files
    local active_pid
    active_pid=$(get_active_pid)

    if [ -n "$active_pid" ]; then
        local cpu mem start_time
        cpu=$(ps -p "$active_pid" -o %cpu= 2>/dev/null || echo "0.0")
        mem=$(ps -p "$active_pid" -o %mem= 2>/dev/null || echo "0.0")
        start_time=$(ps -p "$active_pid" -o lstart= 2>/dev/null || echo "Unknown")

        echo -e "• Application Status: ${GREEN}● RUNNING${RESET}"
        echo -e "• Process PID:        ${BOLD}${active_pid}${RESET}"
        echo -e "• Resource Usage:     CPU: ${cpu}% | Memory: ${mem}%"
        echo -e "• Started:            ${DIM}${start_time}${RESET}"
        echo -e "• Web Interface:      ${CYAN}http://${host}:${port}/${RESET}"

        # Test live health endpoint
        local health_resp
        health_resp=$(curl -s -m 2 "http://127.0.0.1:${port}/health" 2>/dev/null || true)
        if [[ "$health_resp" == *"status"* ]]; then
            echo -e "• Health Endpoint:    ${GREEN}Responsive (HTTP 200)${RESET}"
        else
            echo -e "• Health Endpoint:    ${YELLOW}Unresponsive${RESET}"
        fi

        # Check provider profiles status via API
        local profiles_resp
        profiles_resp=$(curl -s -m 2 "http://127.0.0.1:${port}/providers/cloud_hosted/profiles" 2>/dev/null || true)
        if [[ "$profiles_resp" == *"["* ]]; then
            local count
            count=$(echo "$profiles_resp" | python3 -c "import json, sys; print(len(json.loads(sys.stdin.read())))" 2>/dev/null || echo "0")
            echo -e "• Cloud Profiles:     ${count} profile(s) registered"
        fi
    else
        echo -e "• Application Status: ${YELLOW}○ STOPPED${RESET}"
        echo -e "• Target Port:        ${port}"
        echo -e "• To start:           ${GREEN}./ai-vapt.sh start${RESET}"
    fi

    # Docker Runtime Status
    echo -e "\n${BOLD}Docker & Container Runtime:${RESET}"
    if command -v docker >/dev/null 2>&1; then
        if docker info >/dev/null 2>&1; then
            echo -e "• Docker Daemon:      ${GREEN}Connected${RESET}"
            # Check sandbox image
            local sandbox_img="${STRIX_IMAGE:-ghcr.io/usestrix/strix-sandbox:1.3.0}"
            if docker image inspect "$sandbox_img" >/dev/null 2>&1; then
                echo -e "• Strix Sandbox Image:${GREEN}Available${RESET} (${sandbox_img})"
            else
                echo -e "• Strix Sandbox Image:${YELLOW}Missing${RESET} (${sandbox_img})"
            fi
            # Check Juice shop status
            if docker inspect -f '{{.State.Running}}' juice-shop 2>/dev/null | grep -q "true"; then
                echo -e "• Lab Target:         ${GREEN}● juice-shop running${RESET} (http://127.0.0.1:3000/)"
            else
                echo -e "• Lab Target:         ${YELLOW}○ juice-shop stopped${RESET} (Run: ./juice-shop.sh start)"
            fi
        else
            echo -e "• Docker Daemon:      ${YELLOW}Not running or permission denied${RESET}"
        fi
    else
        echo -e "• Docker CLI:         ${YELLOW}Not installed${RESET}"
    fi

    echo -e "${BOLD}==============================================================================${RESET}\n"
}

# ------------------------------------------------------------------------------
# Command: logs
# ------------------------------------------------------------------------------
cmd_logs() {
    local target_log="$LOG_FILE"
    if [ ! -f "$target_log" ] && [ -f "$LEGACY_LOG_FILE" ]; then
        target_log="$LEGACY_LOG_FILE"
    fi

    if [ ! -f "$target_log" ]; then
        log_warn "No log file found at ${target_log}."
        exit 0
    fi

    log_info "Viewing server logs (${target_log}):"
    tail "$@" "$target_log"
}

# ------------------------------------------------------------------------------
# Command: help
# ------------------------------------------------------------------------------
cmd_help() {
    cat <<EOF
AI-VAPT Platform — Unified Application Launcher

Usage:
  ./ai-vapt.sh <command> [options]

Commands:
  setup               Run full environment verification and install dependencies
  start [options]     Start the AI-VAPT backend server
  stop                Stop running AI-VAPT services gracefully
  restart [options]   Restart the AI-VAPT server
  status              Display server runtime health, process PID, and Docker status
  logs [tail-opts]    Inspect application server logs (e.g. -f to follow, -n 100)
  help                Show this help message

Start Options:
  -p, --port <port>   Port to bind (default: 8000 or STRIX_WEB_PORT)
  -h, --host <host>   Host IP to bind (default: 127.0.0.1 or STRIX_WEB_HOST)
  -d, --daemon        Run in background (default)
  -f, --foreground    Run in foreground (interactive output)
  -e, --env-file <f>  Path to custom .env file
  -w, --wait <sec>    Seconds to wait for health check (default: 15)

Companion Tools:
  ./juice-shop.sh     Manage the OWASP Juice Shop vulnerable lab target container

Examples:
  ./ai-vapt.sh setup
  ./ai-vapt.sh start
  ./ai-vapt.sh status
  ./ai-vapt.sh logs -f
  ./ai-vapt.sh stop
EOF
}

# ------------------------------------------------------------------------------
# Main Dispatcher
# ------------------------------------------------------------------------------
ACTION="${1:-help}"
shift || true

case "$ACTION" in
    setup)
        cmd_setup "$@"
        ;;
    start)
        cmd_start "$@"
        ;;
    stop)
        cmd_stop "$@"
        ;;
    restart)
        cmd_restart "$@"
        ;;
    status)
        cmd_status "$@"
        ;;
    logs)
        cmd_logs "$@"
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        log_error "Unknown command '$ACTION'."
        cmd_help
        exit 1
        ;;
esac
