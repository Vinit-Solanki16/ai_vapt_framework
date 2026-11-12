# AI-VAPT Production Deployment & Operations Guide

**Target Audience:** DevOps Engineers, Platform Administrators, Security Operations  
**Platform Version:** AI-VAPT Autonomous Security Framework  

---

## 1. Deployment Architecture Options

AI-VAPT can be deployed under two supported architectures:

### Option A: Colocated Single-Host Deployment (Recommended for Dedicated Servers & VMs)
In this pattern, the AI-VAPT Web Operations Console, FastAPI gateway, and the Docker daemon run on the same physical server or cloud VM.

```text
[Operator Browser] ──HTTPS──> [Reverse Proxy (Nginx/Caddy)]
                                      │
                                  HTTP (Port 8000)
                                      ▼
                        [AI-VAPT FastAPI Gateway]
                                      │
                            Local Docker Socket
                          (/var/run/docker.sock)
                                      ▼
                    [Docker Engine & Strix Sandboxes]
```

### Option B: Split-Host Deployment (Recommended for Devcontainers, Codespaces & Cloud Sandboxes)
The AI-VAPT Web Console runs in a restricted devcontainer or cloud workspace, while the containerized sandbox runs on a dedicated, hardened remote Docker VM communicating over mutually authenticated TLS.

```text
[Developer / Codespaces] ──TLS (Port 2376)──> [Remote Docker Host (Ubuntu 24.04)]
 [AI-VAPT Gateway]                                      │
                                                        ▼
                                        [Strix Sandbox Containers]
```

---

## 2. Server Sizing & Resource Sizing

| Sizing Tier | CPU Cores | RAM | Storage (NVMe/SSD) | Concurrency |
|---|---|---|---|---|
| **Development / Lab** | 4 Cores | 8 GB | 30 GB | 1 Active Autonomous Scan |
| **Standard Team** | 8 Cores | 16 GB | 80 GB | 2–3 Concurrent Scans |
| **Enterprise / Heavy** | 16 Cores | 32 GB | 200 GB | 5+ Concurrent Scans |

*Note: Each active autonomous sandbox container allocates up to 2 GB RAM and 1 CPU core.*

---

## 3. Production Service Configuration (systemd)

To run AI-VAPT as a persistent, resilient system service on Linux:

1. Create a dedicated service user:
   ```bash
   sudo useradd -m -s /bin/bash aivapt
   sudo usermod -aG docker aivapt
   ```

2. Clone repository and initialize:
   ```bash
   sudo -u aivapt git clone https://github.com/your-org/ai_vapt_framework.git /opt/ai_vapt
   cd /opt/ai_vapt
   sudo -u aivapt ./setup.sh
   ```

3. Create the systemd service file at `/etc/systemd/system/ai-vapt.service`:
   ```ini
   [Unit]
   Description=AI-VAPT Autonomous Security Operations Platform
   After=network.target docker.service
   Requires=docker.service

   [Service]
   Type=simple
   User=aivapt
   Group=aivapt
   WorkingDirectory=/opt/ai_vapt
   EnvironmentFile=/opt/ai_vapt/.env
   ExecStart=/opt/ai_vapt/.venv/bin/python -m uvicorn strix.interface.api:app --host 127.0.0.1 --port 8000
   Restart=on-failure
   RestartSec=5s
   LimitNOFILE=65536

   [Install]
   WantedBy=multi-user.target
   ```

4. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now ai-vapt
   sudo systemctl status ai-vapt
   ```

---

## 4. Reverse Proxy & TLS Configuration (Nginx)

Place AI-VAPT behind an HTTPS reverse proxy (Nginx or Caddy) to handle TLS encryption, domain routing, and Server-Sent Events (SSE) buffering:

```nginx
server {
    listen 80;
    server_name vapt.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name vapt.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/vapt.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vapt.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Maximum payload size for source uploads
    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Mandatory for real-time Server-Sent Events (SSE) streaming:
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

---

## 5. Persistent Storage & Backup Strategy

All assessment state and reports are stored locally on disk:
- `strix_runs/<run-id>/run.json`: Complete scan execution metadata, metrics, duration, candidate queues, and decision traces.
- `strix_runs/<run-id>/vulnerabilities.json`: Structured finding records with 9-state verification metadata.
- `strix_runs/<run-id>/penetration_test_report.md`: Executive summary and detailed vulnerability reports.
- `strix_runs/<run-id>/findings.sarif`: OASIS SARIF 2.1.0 output for CI/CD ingestion.

### Backup Recommendation:
Schedule daily incremental backups of `/opt/ai_vapt/strix_runs/` to secure, encrypted cloud storage (e.g. AWS S3, Google Cloud Storage, or BorgBackup).

---

## 6. Security & Sandboxing Policy

1. **Docker Isolation**: Strix runs all pentesting tools inside the ephemeral container `ghcr.io/usestrix/strix-sandbox:1.3.0`. The container cannot mount the host root filesystem.
2. **Network Scoping**: Assessment probes must be restricted to explicitly authorized hostnames and CIDR ranges. The decision engine actively blocks candidate URLs outside the designated scope.
3. **Secret Hygiene**: Do not commit API keys to version control. Pass credentials via `.env` or in-memory request headers.
4. **Health Monitoring**: Monitor the service via `GET http://127.0.0.1:8000/health`. A `200 OK` response confirms that the gateway is operational.
