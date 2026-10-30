#!/bin/bash
# AI-VAPT Framework — Docker Lab Teardown Script
# Usage: ./scripts/stop_lab.sh

set -e

# Ensure script runs from repository root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=========================================="
echo "  AI-VAPT Controlled Lab — Shutdown"
echo "=========================================="

if which docker > /dev/null 2>&1 && docker ps > /dev/null 2>&1; then
    echo "Stopping and removing lab containers..."
    docker compose -f lab/docker-compose.yml down
    echo "✅ Lab containers stopped."
else
    echo "Docker not available; nothing to stop."
fi
