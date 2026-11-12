# AI-VAPT GitHub Codespaces Runtime & Persistence Guide

**Date:** 2026-11-11  
**Target Environment:** GitHub Codespaces (Debian 12 Bookworm, Python 3.12.11, Docker CLI 20.10)  
**Execution Objective:** Seamless, persistent autonomous execution without repeated Docker configuration.  

---

## 1. Why GitHub Codespaces Requires Remote Docker

When developing in GitHub Codespaces, you are running inside a managed container. An audit of container capabilities confirms:

```text
CapInh: 0000000000000000
CapPrm: 0000000000000000
CapEff: 0000000000000000
CapBnd: 0000000000000000
```

With **zero effective kernel capabilities**, the container cannot:
1. Mount the overlay filesystem required by Docker-in-Docker (`dind`).
2. Run a background daemon daemon process managing Linux namespaces.
3. Access a local `/var/run/docker.sock`.

### The Solution: Persistent Remote Docker via Mutual TLS (mTLS)
AI-VAPT resolves this limitation natively:
- The Codespace acts as a lightweight management client running the Python runtime, FastAPI server, and Web UI.
- All containerized sandbox operations (Strix autonomous multi-agent execution, tool invocations, browser headless testing) execute on a persistent, hardened remote Docker host.
- Mutual TLS (mTLS) encrypts all traffic and prevents unauthorized access to the remote Docker daemon.

---

## 2. Setting Up Persistent Configuration in Codespaces

To ensure that your remote Docker configuration survives Codespaces restarts, rebuilds, and branch switches, configure GitHub Codespaces Secrets.

### Step 1: Obtain Client Certificates and Base64 Strings from the Remote VM
On your provisioned remote Docker VM (or from the output of `setup_remote_docker_host.sh`):

```bash
# Display DOCKER_HOST
echo "tcp://$(curl -s https://ifconfig.me/ip):2376"

# Display Base64 Secret Values
base64 -w 0 /etc/docker/certs/ca.pem; echo
base64 -w 0 /etc/docker/certs/cert.pem; echo
base64 -w 0 /etc/docker/certs/key.pem; echo
```

### Step 2: Add Secrets to GitHub
1. In GitHub, go to your repository: **Settings** -> **Secrets and variables** -> **Codespaces**.
2. Create the following repository or user secrets:

| Secret Name | Example Value | Description |
| :--- | :--- | :--- |
| `DOCKER_HOST` | `tcp://203.0.113.50:2376` | Remote Docker TCP endpoint |
| `DOCKER_TLS_VERIFY` | `1` | Enforces TLS verification |
| `DOCKER_CERT_PATH` | `/home/vscode/.docker/certs-client` | Client certificate directory |
| `AI_VAPT_DOCKER_CA_CERT` | `LS0tLS1CRUdJTi...` | Base64-encoded `ca.pem` |
| `AI_VAPT_DOCKER_CLIENT_CERT` | `LS0tLS1CRUdJTi...` | Base64-encoded `cert.pem` |
| `AI_VAPT_DOCKER_CLIENT_KEY` | `LS0tLS1CRUdJTi...` | Base64-encoded `key.pem` |

### Step 3: Automatic Materialization in Codespaces
When a Codespace session starts, the environment variables are automatically populated from your Codespaces Secrets.

To materialize the certificates and test the connection, run:
```bash
./scripts/install_codespaces_docker_certs.sh
```

This helper script:
1. Decodes `ca.pem`, `cert.pem`, and `key.pem` into `~/.docker/certs-client/`.
2. Sets strict file permissions (`0600` on `key.pem`, `0644` on certificates).
3. Automatically syncs `DOCKER_HOST`, `DOCKER_TLS_VERIFY`, and `DOCKER_CERT_PATH` into your `.env` file.
4. Executes `verify_remote_docker.py` to confirm daemon responsiveness.

---

## 3. Alternative: Local Workspace Persistence (.env)

If you do not have permissions to set repository-level Codespaces Secrets, you can configure persistence locally in your working directory:

1. Copy the certificate files into your Codespaces home directory:
   ```bash
   mkdir -p ~/.docker/certs-client
   scp user@<VM_PUBLIC_IP>:/etc/docker/certs/{ca.pem,cert.pem,key.pem} ~/.docker/certs-client/
   chmod 600 ~/.docker/certs-client/key.pem
   chmod 644 ~/.docker/certs-client/*.pem
   ```

2. Add the remote configuration to your `.env` file:
   ```bash
   cat >> .env <<'EOF'
   DOCKER_HOST="tcp://<VM_PUBLIC_IP>:2376"
   DOCKER_TLS_VERIFY="1"
   DOCKER_CERT_PATH="/home/vscode/.docker/certs-client"
   EOF
   ```

3. Note that `.env` and `~/.docker/` are ignored by Git (`.gitignore`), ensuring private keys and endpoint IPs are never committed.

---

## 4. Everyday Development Workflow

Once remote Docker is configured, your everyday developer workflow requires zero repeated setup:

### 1. Launch the Application
```bash
./start.sh
```
*Output confirms remote connectivity:*
```text
[INFO] Verifying core dependencies and runtime status...
[OK] Remote Docker daemon: Connected (tcp://203.0.113.50:2376). Autonomous multi-agent container mode is active.
[INFO] Starting AI-VAPT Web Operations Console on 0.0.0.0:8000...
[OK] AI-VAPT server started successfully!
```

### 2. Verify Connectivity at Any Time
```bash
# Non-destructive 7-point diagnostic
python3 scripts/verify_remote_docker.py
```

### 3. Open the Web Console
Navigate to `http://localhost:8000/` in your browser.
- **Docker Runtime:** Displays as active/green.
- **Autonomous Mode:** Fully enabled for containerized multi-agent execution.
- **Lightweight Mode:** Remains available as an in-process fallback.

### 4. Stop the Application Cleanly
```bash
./stop.sh
```
Preserves all scan artifacts in `strix_runs/` and leaves remote Docker containers cleanly cleaned up.

---

## 5. Security Architecture & Boundary Isolation

1. **Mutual TLS Encryption:**
   Every API request between Codespaces and the remote VM is authenticated and encrypted using 4096-bit RSA certificates.
2. **Network Scoping:**
   Autonomous agents execute inside isolated Docker bridge networks on the remote VM. Port 2375 is permanently blocked.
3. **Zero Secret Leakage:**
   API keys, client private keys, and host IPs are scrubbed from logs and traces. The API replaces all key strings with `[REDACTED_API_KEY]`.
4. **Target Rewriting:**
   When testing targets on `localhost` or `127.0.0.1`, AI-VAPT rewrites the address to `host.docker.internal` and injects host-gateway routing, ensuring containerized agents resolve the target correctly.
