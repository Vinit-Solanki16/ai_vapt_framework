# AI-VAPT Remote Docker Connection Checklist & Troubleshooting Guide

**Date:** 2026-11-11  
**Target Environment:** GitHub Codespaces Client <--> Ubuntu 24.04 Remote Docker Host  
**Port:** TCP 2376 (Mutual TLS Authenticated)  

---

## 1. End-to-End Implementation Checklist

### Phase 1: Remote VM Provisioning
- [ ] **Compute Sizing:** Provisioned instance with >= 4 vCPU, >= 16 GB RAM, >= 80 GB SSD (Ubuntu 24.04 LTS or 22.04 LTS).
- [ ] **Docker Engine:** Official Docker CE installed via `download.docker.com/linux/ubuntu`.
- [ ] **Auto-Start Enabled:** `sudo systemctl is-enabled docker` reports `enabled`.
- [ ] **Sandbox Image Pre-Pulled:** `sudo docker pull ghcr.io/usestrix/strix-sandbox:1.3.0` completed.

### Phase 2: TLS Certificate Infrastructure & Hardening
- [ ] **CA Generated:** 4096-bit RSA CA key (`ca-key.pem`) and self-signed certificate (`ca.pem`).
- [ ] **Server SANs Configured:** Server certificate includes `IP:<VM_PUBLIC_IP>`, `IP:<VM_LOCAL_IP>`, `IP:127.0.0.1`, `DNS:localhost`.
- [ ] **Client Certificate Signed:** `cert.pem` and `key.pem` signed by CA with `clientAuth` extended key usage.
- [ ] **Daemon Override Installed:** `/etc/systemd/system/docker.service.d/override.conf` binds `tcp://0.0.0.0:2376` with `--tlsverify`.
- [ ] **Daemon Listening on 2376:** `sudo ss -tlnp | grep 2376` confirms active TLS listener.
- [ ] **Firewall Configured:** UFW permits port 22 and 2376; port 2375 is blocked (`ufw status verbose`).

### Phase 3: Client Distribution & Persistence in GitHub Codespaces
- [ ] **Certificate Directory:** `~/.docker/certs-client/` exists with directory mode `0700`.
- [ ] **File Permissions:**
  - `~/.docker/certs-client/key.pem`: Permissions set to `0600` (`-rw-------`).
  - `~/.docker/certs-client/cert.pem`: Permissions set to `0644` (`-rw-r--r--`).
  - `~/.docker/certs-client/ca.pem`: Permissions set to `0644` (`-rw-r--r--`).
- [ ] **Persistent Secrets (Option A - GitHub Codespaces Secrets):**
  - `DOCKER_HOST` = `tcp://<VM_PUBLIC_IP>:2376`
  - `DOCKER_TLS_VERIFY` = `1`
  - `DOCKER_CERT_PATH` = `/home/vscode/.docker/certs-client`
  - `AI_VAPT_DOCKER_CA_CERT` = `<base64>`
  - `AI_VAPT_DOCKER_CLIENT_CERT` = `<base64>`
  - `AI_VAPT_DOCKER_CLIENT_KEY` = `<base64>`
- [ ] **Local .env (Option B):** `.env` contains matching `DOCKER_HOST`, `DOCKER_TLS_VERIFY`, `DOCKER_CERT_PATH`.

### Phase 4: Non-Destructive Verification
- [ ] **Diagnostic Tool Executed:** `python3 scripts/verify_remote_docker.py` passes all 7 checks.
- [ ] **Docker CLI Connection Verified:** `docker info --format '{{.ServerVersion}}'` successfully queries remote version.
- [ ] **Harmless Container Lifecycle:** Test container creates, starts, and deletes cleanly without leaving orphans.

### Phase 5: AI-VAPT Application Integration
- [ ] **Setup Validation:** `./setup.sh` displays `Docker Runtime: Ready (remote)`.
- [ ] **Startup Verification:** `./start.sh` displays `Remote Docker daemon: Connected (tcp://...)`.
- [ ] **API Readiness Endpoint:** `curl http://127.0.0.1:8000/system/readiness` reports `"docker_runtime": {"status": "ready"}`.
- [ ] **Web Console Verification:** Browser console displays Docker runtime as green and autonomous multi-agent testing unlocked.

---

## 2. Troubleshooting Matrix & Common Failure Modes

### Failure 1: Connection Refused (`Errno 111` / `Connection refused`)

**Symptom:**
```text
[FAIL] Docker Client Initialization
Error: HTTPSConnectionPool(host='203.0.113.50', port=2376): Max retries exceeded
Caused by NewConnectionError: Connection refused
```

**Root Causes & Remediation:**
1. **Docker daemon is not listening on port 2376:**
   - *Fix:* SSH into the remote VM and run `sudo ss -tlnp | grep 2376`.
   - If not listening, check systemd drop-in syntax:
     ```bash
     sudo systemctl status docker.service
     sudo journalctl -u docker.service -n 50 --no-pager
     ```
2. **Cloud Security Group / Firewall blocks port 2376:**
   - *Fix:* Check AWS Security Group, GCP Firewall rule, or DigitalOcean Cloud Firewall. Ensure inbound TCP port 2376 is allowed.
3. **UFW is blocking the connection:**
   - *Fix:* On the VM, run `sudo ufw allow 2376/tcp && sudo ufw reload`.

---

### Failure 2: TLS Handshake / Certificate Verification Failed

**Symptom:**
```text
[FAIL] Docker Client Initialization
Error: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: IP address mismatch, certificate is not valid for '203.0.113.50'
```

**Root Causes & Remediation:**
1. **Subject Alternative Name (SAN) mismatch:**
   - The server certificate was issued without the public IP address in the `subjectAltName` extension.
   - *Fix:* Re-generate the server certificate with the public IP included:
     ```bash
     openssl req -new -key server-key.pem -out server.csr -subj "/CN=AI-VAPT-Docker-Server"
     printf "subjectAltName=IP:203.0.113.50,IP:127.0.0.1,DNS:localhost\nextendedKeyUsage=serverAuth\n" > ext.cnf
     openssl x509 -req -days 3650 -in server.csr -CA ca.pem -CAkey ca-key.pem -out server-cert.pem -extfile ext.cnf
     sudo systemctl restart docker
     ```
2. **CA certificate mismatch:**
   - `ca.pem` in `~/.docker/certs-client/` does not match the CA that signed `server-cert.pem`.
   - *Fix:* Re-copy `ca.pem` from `/etc/docker/certs/ca.pem` on the VM.

---

### Failure 3: Bad Certificate / Client Authentication Rejected

**Symptom:**
```text
[FAIL] Docker Daemon Ping
Error: [SSL: TLSV13_ALERT_BAD_CERTIFICATE] ssl/tls alert bad certificate
```

**Root Causes & Remediation:**
1. **Client certificate not signed by the daemon's configured CA:**
   - The daemon's `--tlscacert` is expecting a certificate signed by its local CA.
   - *Fix:* Re-generate `cert.pem` on the VM using `ca.pem` and `ca-key.pem`, then update Codespaces.
2. **Missing `extendedKeyUsage = clientAuth`:**
   - The client certificate must be designated for client authentication. Ensure `extfile-client.cnf` contained `extendedKeyUsage=clientAuth` when signing.

---

### Failure 4: Private Key Permissions Warning (`0644` instead of `0600`)

**Symptom:**
```text
[WARN] TLS Certificates Validation
Warning: Private key 'key.pem' has permissions 0644 (should be 0600).
```

**Remediation:**
Run in Codespaces:
```bash
chmod 600 ~/.docker/certs-client/key.pem
chmod 644 ~/.docker/certs-client/cert.pem ~/.docker/certs-client/ca.pem
```

---

### Failure 5: Sandbox Image Missing (`ImageNotFound: ghcr.io/usestrix/strix-sandbox:1.3.0`)

**Symptom:**
```text
[FAIL] Strix Sandbox Image Availability
Image 'ghcr.io/usestrix/strix-sandbox:1.3.0' is not found on the remote Docker daemon.
```

**Remediation:**
From your Codespace (using the configured `DOCKER_HOST`):
```bash
docker pull ghcr.io/usestrix/strix-sandbox:1.3.0
```
Or directly on the remote VM:
```bash
sudo docker pull ghcr.io/usestrix/strix-sandbox:1.3.0
```

---

## 3. Quick Verification Commands Reference

```bash
# 1. Run full non-destructive diagnostic
python3 scripts/verify_remote_docker.py

# 2. Check remote Docker info via CLI
docker info

# 3. Check sandbox image on remote host
docker image inspect ghcr.io/usestrix/strix-sandbox:1.3.0 --format '{{.Id}} ({{.Size}} bytes)'

# 4. Verify system readiness endpoint
curl -s http://127.0.0.1:8000/system/readiness | jq .components.docker_runtime
```
