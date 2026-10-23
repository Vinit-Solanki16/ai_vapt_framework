#!/bin/bash
# AI-VAPT Framework — Docker Lab Startup Script
# Usage: ./scripts/start_lab.sh

set -e

# Ensure script runs from repository root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=========================================="
echo "  AI-VAPT Controlled Lab — Startup"
echo "=========================================="

if ! which docker > /dev/null 2>&1; then
    echo "❌ Docker binary not found. Install Docker to run live lab containers."
    exit 1
fi

if ! docker ps > /dev/null 2>&1; then
    echo "❌ Docker daemon is not running or current user lacks permissions."
    echo "   Ensure the Docker daemon is active and accessible."
    exit 1
fi

echo "Building and starting lab containers (vuln-emulator + vuln-executor)..."
docker compose -f lab/docker-compose.yml up -d --build

echo "Waiting for vuln-executor health check on http://localhost:9090/health..."
MAX_TRIES=20
TRIES=0
READY=0

while [ $TRIES -lt $MAX_TRIES ]; do
    if curl -s http://localhost:9090/health > /dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
    TRIES=$((TRIES + 1))
done

if [ $READY -eq 1 ]; then
    echo "✅ Lab environment is READY!"
    echo "   - Emulator: internal network (172.28.0.2:8080)"
    echo "   - Executor: localhost:9090"
    echo ""
    echo "To run the lab integration tests:"
    echo "   .venv/bin/python -m pytest prototype/tests/test_docker_lab.py -v"
    echo ""
    echo "To stop the lab containers:"
    echo "   ./scripts/stop_lab.sh"
else
    echo "⚠️  Lab containers started but http://localhost:9090/health did not respond in time."
    echo "   Inspect container logs with: docker logs vuln-executor"
    exit 1
fi
