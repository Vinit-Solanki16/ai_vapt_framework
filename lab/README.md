# Vulnerability Emulator Lab

This directory contains a purpose-built Docker vulnerability emulator for controlled validation testing. The emulator runs a Flask application with two endpoints inside an isolated Docker network with **no external egress** and **no host port exposure**.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Host Machine                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │            Docker Bridge Network (internal)         │    │
│  │  Subnet: 172.28.0.0/16  Gateway: 172.28.0.1        │    │
│  │                                                     │    │
│  │  ┌─────────────────┐                                │    │
│  │  │  vuln-emulator  │  ← Only reachable from        │    │
│  │  │  IP: 172.28.0.2 │     framework container       │    │
│  │  │  Port: 8080     │     (NO host port mapping)    │    │
│  │  └─────────────────┘                                │    │
│  │                                                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ❌ NO published ports to host                              │
│  ❌ NO external egress (internal: true)                     │
│  ✅ Only framework container can reach emulator             │
└─────────────────────────────────────────────────────────────┘
```

## Known Emulator IP

The emulator container will be assigned **`172.28.0.2`** (first available IP in the subnet after gateway `172.28.0.1`).

**Internal URL**: `http://172.28.0.2:8080`

## Endpoints

| Endpoint | Method | Response Body | Purpose |
|----------|--------|---------------|---------|
| `/vuln`  | GET    | `VULNERABLE`  | **Observable success signal** - validates exploit path |
| `/fail`  | GET    | `NOT_VULNERABLE: This endpoint simulates a non-exploitable path` | Simulates non-exploit (no success tokens) |
| `/health`| GET    | `{"status": "healthy"}` | Health check for orchestration |

## Request Logging

Every request to `/vuln` and `/fail` is logged to stdout with:
- **Timestamp** (ISO format: `YYYY-MM-DD HH:MM:SS`)
- **Path** requested
- **Client IP** (source IP of the request)

Example log output:
```
2026-08-25 14:30:45 - path=/vuln client_ip=172.28.0.3
2026-08-25 14:30:46 - path=/fail client_ip=172.28.0.3
```

## Build and Run

### Prerequisites
- Docker Engine 20.10+
- Docker Compose v2 (or `docker-compose` v1.29+)

### Build the emulator image
```bash
cd /home/vinit/ai_vapt_framework/lab
docker compose build
```

### Start the emulator (detached)
```bash
docker compose up -d
```

### Verify it's running
```bash
# Check container status
docker compose ps

# View logs (should show request logs when accessed)
docker compose logs -f emulator
```

### Test from within the lab network (simulated framework container)
```bash
# Run a test container in the same network
docker run --rm --network vuln-lab-network curlimages/curl:latest curl -s http://172.28.0.2:8080/vuln
# Expected output: VULNERABLE

docker run --rm --network vuln-lab-network curlimages/curl:latest curl -s http://172.28.0.2:8080/fail
# Expected output: NOT_VULNERABLE: This endpoint simulates a non-exploitable path
```

### Stop and cleanup
```bash
# Stop containers
docker compose down

# Stop and remove network
docker compose down --volumes --remove-orphans
```

## Isolation Verification (HERMES Review)

### 1. No host port mapping
```bash
docker ps --format "table {{.Names}}\t{{.Ports}}"
# Should show NO port mappings for vuln-emulator (empty PORTS column)
```

### 2. Host cannot reach emulator directly
```bash
# This should FAIL (timeout or connection refused)
curl -s --max-time 5 http://172.28.0.2:8080/vuln
# Expected: curl: (7) Failed to connect to 172.28.0.2 port 8080: Connection refused
```

### 3. Only containers in the network can reach it
```bash
# This should SUCCEED
docker run --rm --network vuln-lab-network curlimages/curl:latest curl -s http://172.28.0.2:8080/vuln
# Expected: VULNERABLE
```

### 4. No external egress from lab network
```bash
# This should FAIL (no internet access from internal network)
docker run --rm --network vuln-lab-network curlimages/curl:latest curl -s --max-time 5 http://example.com
# Expected: curl: (6) Could not resolve host: example.com (or timeout)
```

## Security Notes

- Container runs as non-root user (UID 1000)
- Read-only root filesystem with tmpfs for writable directories
- No new privileges capability
- Resource limits (CPU/Memory) enforced
- Network is fully isolated (`internal: true`)

## Integration with Framework

The framework container should be added to the same `vuln-lab-network` to communicate with the emulator:

```yaml
# In framework's docker-compose.yml
services:
  framework:
    # ... other config
    networks:
      - vuln-lab-network

networks:
  vuln-lab-network:
    external: true
```

Then the framework can access the emulator at `http://172.28.0.2:8080/vuln`.