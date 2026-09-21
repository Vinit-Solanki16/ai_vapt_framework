#!/bin/bash
# AI-VAPT Operations Console — Startup Script
# Usage: ./scripts/start_demo.sh

set -e

echo "=========================================="
echo "  AI-VAPT Operations Console — Startup"
echo "=========================================="

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3.10 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies if needed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Check if Ollama is running
if ! pgrep -x "ollama" > /dev/null; then
    echo "⚠️  Ollama not running. AI assessment will use deterministic fallback."
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
