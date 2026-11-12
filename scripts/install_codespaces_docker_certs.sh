#!/usr/bin/env bash
# ==============================================================================
# AI-VAPT: Install & Persist Docker Client Certificates in GitHub Codespaces
# ==============================================================================
# Decodes TLS client certificates from GitHub Codespaces Secrets or validates
# existing files in ~/.docker/certs-client/. Sets secure permissions.
# ==============================================================================

set -euo pipefail

# ANSI styling
BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
CYAN="\033[36m"
GRAY="\033[90m"
RESET="\033[0m"

log_info()    { echo -e "  ${CYAN}ℹ${RESET}  $*"; }
log_success() { echo -e "  ${GREEN}✓${RESET}  $*"; }
log_warn()    { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
log_error()   { echo -e "  ${RED}✗${RESET}  $*"; }
log_header()  { echo -e "\n${BOLD}${CYAN}=== $* ===${RESET}\n"; }

log_header "AI-VAPT Codespaces Docker Client Certificate Installer"

TARGET_DIR="${DOCKER_CERT_PATH:-$HOME/.docker/certs-client}"
mkdir -p "$TARGET_DIR"
chmod 700 "$TARGET_DIR"

CERTS_INSTALLED=false

# Method 1: Environment Variables / GitHub Codespaces Secrets (Base64 Encoded)
if [ -n "${AI_VAPT_DOCKER_CA_CERT:-}" ] && \
   [ -n "${AI_VAPT_DOCKER_CLIENT_CERT:-}" ] && \
   [ -n "${AI_VAPT_DOCKER_CLIENT_KEY:-}" ]; then
    log_info "Detected base64-encoded TLS certificates in environment (Codespaces Secrets)..."

    echo "$AI_VAPT_DOCKER_CA_CERT" | base64 -d > "${TARGET_DIR}/ca.pem"
    echo "$AI_VAPT_DOCKER_CLIENT_CERT" | base64 -d > "${TARGET_DIR}/cert.pem"
    echo "$AI_VAPT_DOCKER_CLIENT_KEY" | base64 -d > "${TARGET_DIR}/key.pem"

    chmod 644 "${TARGET_DIR}/ca.pem" "${TARGET_DIR}/cert.pem"
    chmod 600 "${TARGET_DIR}/key.pem"

    log_success "Certificates successfully decoded and installed to: ${TARGET_DIR}"
    CERTS_INSTALLED=true
fi

# Method 2: Check Existing Files in Target Directory
if [ "$CERTS_INSTALLED" = false ]; then
    if [ -f "${TARGET_DIR}/ca.pem" ] && [ -f "${TARGET_DIR}/cert.pem" ] && [ -f "${TARGET_DIR}/key.pem" ]; then
        log_info "Found existing certificate files in: ${TARGET_DIR}"
        chmod 644 "${TARGET_DIR}/ca.pem" "${TARGET_DIR}/cert.pem"
        chmod 600 "${TARGET_DIR}/key.pem"
        log_success "Verified permissions on existing certificates (0600 on key.pem, 0644 on certs)."
        CERTS_INSTALLED=true
    fi
fi

if [ "$CERTS_INSTALLED" = false ]; then
    log_warn "No client TLS certificates found in ${TARGET_DIR} and no Codespaces secrets detected."
    echo ""
    echo -e "${BOLD}To configure remote Docker certificates in GitHub Codespaces, pick one method:${RESET}"
    echo ""
    echo -e "  ${BOLD}Option A: Set GitHub Codespaces Secrets (Recommended - Persists across all rebuilds)${RESET}"
    echo -e "    1. In GitHub, go to ${CYAN}Settings -> Secrets and variables -> Codespaces${RESET}"
    echo -e "    2. Add the following repository or user secrets:"
    echo -e "       - ${BOLD}DOCKER_HOST${RESET} = tcp://<YOUR_VM_IP>:2376"
    echo -e "       - ${BOLD}DOCKER_TLS_VERIFY${RESET} = 1"
    echo -e "       - ${BOLD}DOCKER_CERT_PATH${RESET} = /home/vscode/.docker/certs-client"
    echo -e "       - ${BOLD}AI_VAPT_DOCKER_CA_CERT${RESET} = (base64 -w 0 ca.pem from VM)"
    echo -e "       - ${BOLD}AI_VAPT_DOCKER_CLIENT_CERT${RESET} = (base64 -w 0 cert.pem from VM)"
    echo -e "       - ${BOLD}AI_VAPT_DOCKER_CLIENT_KEY${RESET} = (base64 -w 0 key.pem from VM)"
    echo ""
    echo -e "  ${BOLD}Option B: Copy files directly into Codespaces${RESET}"
    echo -e "    Run on your local machine or terminal:"
    echo -e "       ${GRAY}scp -r user@<YOUR_VM_IP>:~/docker-certs/{ca,cert,key}.pem ~/.docker/certs-client/${RESET}"
    echo -e "    Then re-run this script: ${BOLD}./scripts/install_codespaces_docker_certs.sh${RESET}"
    echo ""
    exit 1
fi

# Sync with repository .env if present
if [ -f ".env" ]; then
    if [ -n "${DOCKER_HOST:-}" ]; then
        if ! grep -q "^DOCKER_HOST=" .env; then
            echo "" >> .env
            echo "# Remote Docker Configuration (Auto-synced)" >> .env
            echo "DOCKER_HOST=\"${DOCKER_HOST}\"" >> .env
            echo "DOCKER_TLS_VERIFY=\"${DOCKER_TLS_VERIFY:-1}\"" >> .env
            echo "DOCKER_CERT_PATH=\"${TARGET_DIR}\"" >> .env
            log_success "Synced remote Docker environment settings into .env"
        fi
    fi
fi

# Run non-destructive verification
if [ -f "scripts/verify_remote_docker.py" ]; then
    log_info "Running connectivity verification check..."
    python3 scripts/verify_remote_docker.py \
        --host "${DOCKER_HOST:-}" \
        --cert-path "${TARGET_DIR}" \
        --tls-verify || true
fi
