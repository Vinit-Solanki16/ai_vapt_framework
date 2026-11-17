#!/usr/bin/env bash
# ==============================================================================
# AI-VAPT Platform — OWASP Juice Shop Lab Management Script
# ==============================================================================
# Manages the local vulnerable target container (OWASP Juice Shop) for
# authentic, authorized penetration testing demonstrations and development.
#
# Network Architecture:
#   - Host loopback:  127.0.0.1:3000  (Host browser / API test access)
#   - Bridge gateway: 172.17.0.1:3000 (Strix Docker Sandbox / host.docker.internal)
#
# Usage:
#   ./juice-shop.sh start     # Start Juice Shop container
#   ./juice-shop.sh stop      # Stop Juice Shop container
#   ./juice-shop.sh restart   # Restart Juice Shop container
#   ./juice-shop.sh status    # Check container status and health
#   ./juice-shop.sh logs      # View container logs (-f to follow)
#   ./juice-shop.sh remove    # Remove container (preserves images)
#   ./juice-shop.sh help      # Show this help
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
# Configuration
# ------------------------------------------------------------------------------
CONTAINER_NAME="${JUICE_SHOP_CONTAINER:-juice-shop}"
IMAGE_NAME="${JUICE_SHOP_IMAGE:-bkimminich/juice-shop}"
DEFAULT_PORT="3000"
PORT="${JUICE_SHOP_PORT:-$DEFAULT_PORT}"
HEALTH_TIMEOUT="${JUICE_SHOP_HEALTH_TIMEOUT:-30}"

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        log_error "Docker CLI ('docker') not found in PATH."
        log_info "Please install Docker to run the Juice Shop lab container."
        exit 1
    fi

    if ! docker info >/dev/null 2>&1; then
        log_error "Docker daemon is not running or socket is inaccessible."
        log_info "Start Docker daemon: sudo systemctl start docker (or start Docker Desktop)."
        exit 1
    fi
}

get_docker_bridge_gateway() {
    # Dynamically detect default docker0 bridge gateway IP (commonly 172.17.0.1)
    local gw
    gw=$(docker network inspect bridge --format='{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null || true)
    if [ -z "$gw" ] || [ "$gw" = "<no value>" ]; then
        echo "172.17.0.1"
    else
        echo "$gw"
    fi
}

is_container_running() {
    local status
    status=$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || echo "false")
    [ "$status" = "true" ]
}

is_container_present() {
    docker inspect "$CONTAINER_NAME" >/dev/null 2>&1
}

wait_for_health() {
    local target_url="http://127.0.0.1:${PORT}/rest/admin/application-version"
    log_info "Waiting for Juice Shop to report healthy at ${target_url} (timeout: ${HEALTH_TIMEOUT}s)..."
    
    local elapsed=0
    while [ "$elapsed" -lt "$HEALTH_TIMEOUT" ]; do
        local resp
        resp=$(curl -s -m 2 "$target_url" 2>/dev/null || true)
        if [[ "$resp" == *"version"* ]]; then
            local ver
            ver=$(echo "$resp" | grep -o '"version":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
            log_success "Juice Shop is healthy (Application Version: ${BOLD}${ver}${RESET})"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    # Fallback check on root path
    if curl -s -m 2 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
        log_success "Juice Shop root page responded successfully."
        return 0
    fi

    log_warn "Juice Shop container is running, but HTTP health probe timed out after ${HEALTH_TIMEOUT}s."
    log_info "Inspect container logs: ./juice-shop.sh logs"
    return 1
}

# ------------------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------------------
cmd_start() {
    log_step "Starting OWASP Juice Shop Lab Container..."
    check_docker

    if is_container_running; then
        log_info "Container '${CONTAINER_NAME}' is already running."
        cmd_status
        return 0
    fi

    if is_container_present; then
        log_info "Existing container '${CONTAINER_NAME}' found (stopped). Starting it..."
        docker start "$CONTAINER_NAME" >/dev/null
        wait_for_health || true
        cmd_status
        return 0
    fi

    # Container does not exist; pull if needed and create
    log_info "Verifying image '${IMAGE_NAME}' locally..."
    if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
        log_info "Image not found locally. Pulling ${IMAGE_NAME}..."
        docker pull "$IMAGE_NAME"
    fi

    local bridge_gw
    bridge_gw=$(get_docker_bridge_gateway)
    log_info "Detected Docker bridge gateway: ${bridge_gw}"

    log_info "Creating and launching container '${CONTAINER_NAME}'..."
    log_info "Port mappings: 127.0.0.1:${PORT}:3000 and ${bridge_gw}:${PORT}:3000"

    # Attempt dual loopback + bridge gateway binding for secure isolation
    if docker run -d \
        --name "$CONTAINER_NAME" \
        -p "127.0.0.1:${PORT}:3000" \
        -p "${bridge_gw}:${PORT}:3000" \
        "$IMAGE_NAME" >/dev/null 2>&1; then
        log_success "Container created with dual loopback + bridge bindings."
    else
        log_warn "Dual binding failed. Falling back to default host binding -p ${PORT}:3000..."
        docker run -d \
            --name "$CONTAINER_NAME" \
            -p "${PORT}:3000" \
            "$IMAGE_NAME" >/dev/null
        log_success "Container created with fallback host binding."
    fi

    wait_for_health || true
    cmd_status
}

cmd_stop() {
    log_step "Stopping OWASP Juice Shop Lab Container..."
    check_docker

    if ! is_container_present; then
        log_info "Container '${CONTAINER_NAME}' does not exist. Nothing to stop."
        return 0
    fi

    if ! is_container_running; then
        log_info "Container '${CONTAINER_NAME}' is already stopped."
        return 0
    fi

    log_info "Stopping container '${CONTAINER_NAME}' gracefully..."
    docker stop -t 5 "$CONTAINER_NAME" >/dev/null
    log_success "Container '${CONTAINER_NAME}' stopped. (Data and state preserved)"
}

cmd_restart() {
    log_step "Restarting OWASP Juice Shop Lab Container..."
    check_docker
    cmd_stop
    sleep 1
    cmd_start
}

cmd_status() {
    echo -e "\n${BOLD}==============================================================================${RESET}"
    echo -e "${BOLD}               OWASP Juice Shop Lab Target Status                            ${RESET}"
    echo -e "${BOLD}==============================================================================${RESET}"
    check_docker

    if ! is_container_present; then
        echo -e "• Container Status:  ${YELLOW}Not Created${RESET} ('${CONTAINER_NAME}' does not exist)"
        echo -e "• Target Image:      ${DIM}${IMAGE_NAME}${RESET}"
        echo -e "\nTo start the lab:     ${GREEN}./juice-shop.sh start${RESET}\n"
        return 0
    fi

    local c_status c_id c_ports c_uptime
    c_status=$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
    c_id=$(docker inspect -f '{{slice .Id 0 12}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
    c_uptime=$(docker inspect -f '{{.State.StartedAt}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
    
    local bridge_gw
    bridge_gw=$(get_docker_bridge_gateway)

    if [ "$c_status" = "running" ]; then
        echo -e "• Container Status:  ${GREEN}● RUNNING${RESET} (ID: ${BOLD}${c_id}${RESET})"
        echo -e "• Host Access URL:   ${CYAN}http://127.0.0.1:${PORT}/${RESET} (or http://localhost:${PORT}/)"
        echo -e "• Strix Sandbox URL: ${CYAN}http://host.docker.internal:${PORT}/${RESET} (resolves to ${bridge_gw}:${PORT})"
        echo -e "• Image:             ${DIM}${IMAGE_NAME}${RESET}"
        echo -e "• Started At:        ${DIM}${c_uptime}${RESET}"

        # Test live HTTP response
        local ver_json
        ver_json=$(curl -s -m 2 "http://127.0.0.1:${PORT}/rest/admin/application-version" 2>/dev/null || true)
        if [[ "$ver_json" == *"version"* ]]; then
            local ver
            ver=$(echo "$ver_json" | grep -o '"version":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
            echo -e "• App Health:        ${GREEN}Responsive${RESET} (Juice Shop v${ver})"
        else
            echo -e "• App Health:        ${YELLOW}HTTP not responding yet${RESET}"
        fi
    else
        echo -e "• Container Status:  ${YELLOW}○ STOPPED${RESET} (ID: ${BOLD}${c_id}${RESET}, state: ${c_status})"
        echo -e "• Host Access URL:   ${DIM}http://127.0.0.1:${PORT}/ (offline)${RESET}"
    fi

    echo -e "${BOLD}==============================================================================${RESET}\n"
}

cmd_logs() {
    check_docker
    if ! is_container_present; then
        log_error "Container '${CONTAINER_NAME}' does not exist."
        exit 1
    fi

    log_info "Displaying logs for container '${CONTAINER_NAME}'..."
    docker logs "$@" "$CONTAINER_NAME"
}

cmd_remove() {
    log_step "Removing OWASP Juice Shop Lab Container..."
    check_docker

    if ! is_container_present; then
        log_info "Container '${CONTAINER_NAME}' does not exist. Nothing to remove."
        return 0
    fi

    if is_container_running; then
        log_info "Stopping running container '${CONTAINER_NAME}'..."
        docker stop -t 3 "$CONTAINER_NAME" >/dev/null
    fi

    log_info "Removing container '${CONTAINER_NAME}' (Docker image is retained)..."
    docker rm "$CONTAINER_NAME" >/dev/null
    log_success "Container '${CONTAINER_NAME}' removed successfully."
}

cmd_help() {
    cat <<EOF
AI-VAPT OWASP Juice Shop Lab Management Script

Usage:
  ./juice-shop.sh <command> [options]

Commands:
  start               Start the Juice Shop container (creates or resumes)
  stop                Stop the Juice Shop container gracefully
  restart             Restart the Juice Shop container
  status              Check container execution and live HTTP health
  logs [opts]         View container stdout/stderr logs (e.g. -f to follow)
  remove              Remove the Juice Shop container (preserves Docker image)
  help                Show this help message

Environment Variables:
  JUICE_SHOP_PORT     Host port to bind (default: 3000)
  JUICE_SHOP_IMAGE    Container image (default: bkimminich/juice-shop)
  JUICE_SHOP_CONTAINER Container name (default: juice-shop)

Examples:
  ./juice-shop.sh start
  ./juice-shop.sh status
  ./juice-shop.sh logs -f
  ./juice-shop.sh stop
EOF
}

# ------------------------------------------------------------------------------
# Main Dispatcher
# ------------------------------------------------------------------------------
ACTION="${1:-help}"
shift || true

case "$ACTION" in
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
    remove|rm)
        cmd_remove "$@"
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
