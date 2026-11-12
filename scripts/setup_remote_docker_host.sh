#!/usr/bin/env bash
# ==============================================================================
# AI-VAPT: Remote Docker Host Automated Provisioning Script
# ==============================================================================
# Target OS: Ubuntu 24.04 LTS (noble) or Ubuntu 22.04 LTS (jammy)
# Sizing: 4 vCPU, 16 GiB RAM, 80 GiB SSD recommended
#
# This script:
# 1. Installs official Docker Engine CE and containerd.
# 2. Configures Docker to start automatically on system boot.
# 3. Generates 4096-bit RSA CA, server, and client TLS certificates with SANs.
# 4. Configures Docker daemon systemd override for TLS on port 2376 (disables 2375).
# 5. Configures UFW firewall for SSH and TLS Docker port 2376 only.
# 6. Pre-pulls the official Strix sandbox image (ghcr.io/usestrix/strix-sandbox:1.3.0).
# 7. Outputs base64 strings and client bundle for GitHub Codespaces integration.
#
# Usage:
#   sudo bash scripts/setup_remote_docker_host.sh [VM_PUBLIC_IP]
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
log_step()    { echo -e "\n${BOLD}${CYAN}==> $*${RESET}"; }

# Check root privileges
if [ "$(id -u)" -ne 0 ]; then
    log_error "This script must be run as root (use sudo)."
    exit 1
fi

echo -e "${BOLD}${CYAN}"
echo "================================================================================"
echo "          AI-VAPT Remote Docker VM Provisioning & Hardening Script             "
echo "================================================================================"
echo -e "${RESET}"

# ------------------------------------------------------------------------------
# 1. OS & Hardware Sizing Check
# ------------------------------------------------------------------------------
log_step "1. Validating OS & Hardware Sizing..."

if [ -f /etc/os-release ]; then
    . /etc/os-release
    log_info "Detected OS: ${PRETTY_NAME:-$ID $VERSION_ID}"
    if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
        log_warn "This script is tailored for Ubuntu/Debian. Proceeding with caution..."
    fi
fi

NPROC=$(nproc 2>/dev/null || echo "1")
MEM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo "0")
MEM_GB=$(awk "BEGIN {printf \"%.1f\", $MEM_KB / 1048576}")
DISK_GB=$(df -BG / 2>/dev/null | awk 'NR==2 {print $2}' | tr -d 'G' || echo "0")

log_info "System resources: ${NPROC} CPU cores, ${MEM_GB} GB RAM, ~${DISK_GB} GB Root Disk"

if [ "$NPROC" -lt 4 ]; then
    log_warn "CPUs (${NPROC}) is below the recommended 4 cores for autonomous multi-agent pentesting."
fi
if (( $(echo "$MEM_GB < 7.5" | bc -l 2>/dev/null || [ "$MEM_KB" -lt 7800000 ]) )); then
    log_warn "RAM (${MEM_GB} GB) is below the recommended 16 GB (min 8 GB) for sandbox execution."
fi

# ------------------------------------------------------------------------------
# 2. Determine IP Addresses & Subject Alternative Names (SANs)
# ------------------------------------------------------------------------------
log_step "2. Resolving Host IP and TLS Subject Alternative Names (SANs)..."

PUBLIC_IP="${1:-}"
if [ -z "$PUBLIC_IP" ]; then
    # Try public IP detection services
    PUBLIC_IP=$(curl -s -m 3 https://ifconfig.me/ip || curl -s -m 3 https://api.ipify.org || echo "")
fi

LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
HOSTNAME_FQDN=$(hostname -f 2>/dev/null || hostname)

echo -e "  Primary Public IP  : ${BOLD}${PUBLIC_IP:-Not detected}${RESET}"
echo -e "  Primary Local IP   : ${BOLD}${LOCAL_IP}${RESET}"
echo -e "  Host Name          : ${BOLD}${HOSTNAME_FQDN}${RESET}"

# Build SAN string
SAN_LIST="IP:127.0.0.1,DNS:localhost,DNS:${HOSTNAME_FQDN}"
if [ -n "$LOCAL_IP" ] && [ "$LOCAL_IP" != "127.0.0.1" ]; then
    SAN_LIST="${SAN_LIST},IP:${LOCAL_IP}"
fi
if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "$LOCAL_IP" ]; then
    SAN_LIST="${SAN_LIST},IP:${PUBLIC_IP}"
fi
log_info "Generated SAN list: ${SAN_LIST}"

# ------------------------------------------------------------------------------
# 3. Install Docker Engine CE
# ------------------------------------------------------------------------------
log_step "3. Installing Docker Engine (Community Edition)..."

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release ufw

# Add Docker's official GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# Set up repository
ARCH=$(dpkg --print-architecture)
CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${CODENAME} stable" > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin

systemctl enable docker
systemctl start docker
log_success "Docker Engine installed: $(docker --version)"

# ------------------------------------------------------------------------------
# 4. Generate TLS Certificates
# ------------------------------------------------------------------------------
log_step "4. Generating 4096-bit TLS Certificates with SANs..."

CERT_DIR="/etc/docker/certs"
mkdir -p "$CERT_DIR"
chmod 700 "$CERT_DIR"
cd "$CERT_DIR"

# 4.1 Certificate Authority (CA)
if [ ! -f "ca.pem" ] || [ ! -f "ca-key.pem" ]; then
    log_info "Generating Certificate Authority (CA)..."
    openssl genrsa -out ca-key.pem 4096
    openssl req -new -x509 -days 3650 -key ca-key.pem -out ca.pem -subj "/CN=AI-VAPT-Docker-CA"
    chmod 600 ca-key.pem
    chmod 644 ca.pem
    log_success "CA certificate created (valid 10 years)."
else
    log_info "Existing CA certificate found; preserving."
fi

# 4.2 Server Certificate
log_info "Generating Server Certificate..."
openssl genrsa -out server-key.pem 4096
openssl req -new -key server-key.pem -out server.csr -subj "/CN=AI-VAPT-Docker-Server"

cat > extfile-server.cnf <<EOF
subjectAltName=${SAN_LIST}
extendedKeyUsage=serverAuth
EOF

openssl x509 -req -days 3650 -in server.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -out server-cert.pem -extfile extfile-server.cnf
chmod 600 server-key.pem
chmod 644 server-cert.pem
rm -f server.csr extfile-server.cnf
log_success "Server certificate signed with SANs."

# 4.3 Client Certificate for Codespaces
log_info "Generating Client Certificate for AI-VAPT Codespaces..."
openssl genrsa -out key.pem 4096
openssl req -new -key key.pem -out client.csr -subj "/CN=ai-vapt-client"

cat > extfile-client.cnf <<EOF
extendedKeyUsage=clientAuth
EOF

openssl x509 -req -days 3650 -in client.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -out cert.pem -extfile extfile-client.cnf
chmod 600 key.pem
chmod 644 cert.pem
rm -f client.csr extfile-client.cnf
log_success "Client certificate signed."

# ------------------------------------------------------------------------------
# 5. Configure Docker Daemon Systemd Override for TLS on Port 2376
# ------------------------------------------------------------------------------
log_step "5. Configuring Docker Daemon Systemd Service..."

SYSTEMD_DIR="/etc/systemd/system/docker.service.d"
mkdir -p "$SYSTEMD_DIR"

cat > "${SYSTEMD_DIR}/override.conf" <<EOF
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd \\
  --tlsverify \\
  --tlscacert=${CERT_DIR}/ca.pem \\
  --tlscert=${CERT_DIR}/server-cert.pem \\
  --tlskey=${CERT_DIR}/server-key.pem \\
  -H tcp://0.0.0.0:2376 \\
  -H unix:///var/run/docker.sock
EOF

log_info "Reloading systemd and restarting Docker daemon..."
systemctl daemon-reload
systemctl restart docker

# Verify daemon is listening
sleep 2
if ss -tlnp | grep -q ":2376"; then
    log_success "Docker daemon is listening on port 2376 (TLS verified)."
else
    log_error "Docker daemon failed to bind port 2376. Check \`journalctl -u docker.service\`."
    exit 1
fi

# ------------------------------------------------------------------------------
# 6. Pre-pull Official Strix Sandbox Container Image
# ------------------------------------------------------------------------------
log_step "6. Pre-pulling Strix Sandbox Container Image..."

CONFIGURED_IMAGE="${STRIX_IMAGE:-ghcr.io/usestrix/strix-sandbox:1.3.0}"
log_info "Pulling '${CONFIGURED_IMAGE}'..."
if docker pull "$CONFIGURED_IMAGE"; then
    log_success "Sandbox image pulled successfully."
else
    log_warn "Failed to pull '${CONFIGURED_IMAGE}'. Check network connectivity."
fi

# ------------------------------------------------------------------------------
# 7. Configure Firewall (UFW)
# ------------------------------------------------------------------------------
log_step "7. Hardening Host Firewall (UFW)..."

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH administration"
ufw allow 2376/tcp comment "AI-VAPT Docker TLS API"
# Explicitly ensure 2375 is denied
ufw deny 2375/tcp comment "Block insecure Docker port"
echo "y" | ufw enable || true
ufw status verbose

# ------------------------------------------------------------------------------
# 8. Package Client Bundle & Print Codespaces Secrets
# ------------------------------------------------------------------------------
log_step "8. Generating Client Credentials Bundle..."

OUTPUT_DIR="/root/ai-vapt-client-bundle"
mkdir -p "$OUTPUT_DIR"
cp "${CERT_DIR}/ca.pem" "${OUTPUT_DIR}/ca.pem"
cp "${CERT_DIR}/cert.pem" "${OUTPUT_DIR}/cert.pem"
cp "${CERT_DIR}/key.pem" "${OUTPUT_DIR}/key.pem"
chmod 600 "${OUTPUT_DIR}/key.pem"

tar -czf "/root/ai-vapt-client-certs.tar.gz" -C "$OUTPUT_DIR" ca.pem cert.pem key.pem
log_success "Client archive saved to: /root/ai-vapt-client-certs.tar.gz"

CA_B64=$(base64 -w 0 < "${OUTPUT_DIR}/ca.pem")
CERT_B64=$(base64 -w 0 < "${OUTPUT_DIR}/cert.pem")
KEY_B64=$(base64 -w 0 < "${OUTPUT_DIR}/key.pem")

TARGET_HOST_IP="${PUBLIC_IP:-$LOCAL_IP}"

echo -e "\n${BOLD}${GREEN}================================================================================${RESET}"
echo -e "${BOLD}${GREEN}                 REMOTE DOCKER HOST SETUP COMPLETE!                             ${RESET}"
echo -e "${BOLD}${GREEN}================================================================================${RESET}\n"

echo -e "${BOLD}Use these values for GitHub Codespaces Secrets or .env configuration:${RESET}\n"
echo -e "  ${BOLD}DOCKER_HOST${RESET}       = tcp://${TARGET_HOST_IP}:2376"
echo -e "  ${BOLD}DOCKER_TLS_VERIFY${RESET} = 1"
echo -e "  ${BOLD}DOCKER_CERT_PATH${RESET}  = /home/vscode/.docker/certs-client\n"

echo -e "${BOLD}GitHub Codespaces Secrets (Settings -> Secrets and variables -> Codespaces):${RESET}\n"
echo -e "  Secret: ${CYAN}DOCKER_HOST${RESET}"
echo -e "  Value : tcp://${TARGET_HOST_IP}:2376\n"
echo -e "  Secret: ${CYAN}DOCKER_TLS_VERIFY${RESET}"
echo -e "  Value : 1\n"
echo -e "  Secret: ${CYAN}DOCKER_CERT_PATH${RESET}"
echo -e "  Value : /home/vscode/.docker/certs-client\n"
echo -e "  Secret: ${CYAN}AI_VAPT_DOCKER_CA_CERT${RESET}"
echo -e "  Value : ${CA_B64}\n"
echo -e "  Secret: ${CYAN}AI_VAPT_DOCKER_CLIENT_CERT${RESET}"
echo -e "  Value : ${CERT_B64}\n"
echo -e "  Secret: ${CYAN}AI_VAPT_DOCKER_CLIENT_KEY${RESET}"
echo -e "  Value : ${KEY_B64}\n"

echo -e "${BOLD}Alternative (Manual File Copy via SCP):${RESET}"
echo -e "  scp root@${TARGET_HOST_IP}:/root/ai-vapt-client-bundle/* ~/.docker/certs-client/\n"
