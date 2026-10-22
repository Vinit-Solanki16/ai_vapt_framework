#!/bin/bash
# AI-VAPT Operations Console — Startup Script
# Usage: ./scripts/start_demo.sh

set -e

echo "=========================================="
echo "  AI-VAPT Operations Console — Startup"
echo "=========================================="

# Activate virtualenv
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
elif [ -z "$VIRTUAL_ENV" ]; then
    echo "Creating virtual environment (.venv)..."
    python3 -m venv .venv
    source .venv/bin/activate
fi

# Load .env if present
if [ -f ".env" ]; then
    echo "Loading environment from .env..."
    set -a
    source .env
    set +a
fi

# Install dependencies if needed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Check Nmap
if ! which nmap > /dev/null 2>&1; then
    echo "⚠️  Nmap not found on PATH. Install with: sudo apt install nmap"
else
    echo "✅ Nmap is available ($(nmap --version | head -n 1))"
fi

# Check Nuclei
if ! which nuclei > /dev/null 2>&1; then
    echo "ℹ️  Nuclei not installed on PATH (optional: runs will proceed with Nmap discovery only)."
else
    echo "✅ Nuclei is available ($(nuclei -version 2>&1 | head -n 1))"
fi

# Check if Ollama is running
if ! curl -s http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
    echo "⚠️  Ollama HTTP API not reachable at http://127.0.0.1:11434."
    echo "   Local AI assessment will use deterministic fallback."
    echo "   To start Ollama: ollama serve &"
else
    echo "✅ Ollama is running"
fi

# Check if Docker is running
if ! docker ps > /dev/null 2>&1; then
    echo "⚠️  Docker not available. Docker Lab mode will be unavailable."
    echo "   To start Docker: cd lab && docker-compose up -d && cd .."
else
    echo "✅ Docker is available"
    # Check if lab containers are running
    if docker ps --format '{{.Names}}' | grep -q "vuln-emulator"; then
        echo "✅ Docker lab containers are running"
    else
        echo "⚠️  Docker lab containers not running."
        echo "   To start lab: cd lab && docker-compose up -d && cd .."
    fi
fi

echo ""
echo "Starting application..."
echo "  URL: http://localhost:8000"
echo "  API: http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Start the application
uvicorn services.api:app --reload --port 8000
