#!/bin/bash
# AI-VAPT Operations Console — Demo Reset Script
# Usage: ./scripts/reset_demo.sh
# 
# Clears persisted runs to return to a clean demonstration state.
# Does NOT modify research core, configuration, or code.

set -e

echo "=========================================="
echo "  AI-VAPT Operations Console — Reset"
echo "=========================================="

# Activate venv
source venv/bin/activate

echo ""
echo "Clearing persisted runs..."

# Clear the runs directory
RUNS_DIR="$HOME/.ai_vapt_framework/runs"
if [ -d "$RUNS_DIR" ]; then
    rm -f "$RUNS_DIR"/*.json 2>/dev/null || true
    rm -f "$RUNS_DIR"/index.json 2>/dev/null || true
    echo "✅ Cleared persisted runs"
else
    echo "✅ No runs directory found (already clean)"
fi

# Remove old report files from project root
rm -f report_*.json report_*.txt report_*.html report_*.md 2>/dev/null || true
echo "✅ Removed old report files"

echo ""
echo "Reset complete. Application is ready for demonstration."
echo ""
echo "To start the application:"
echo "  ./scripts/start_demo.sh"
echo ""
echo "Or manually:"
echo "  source venv/bin/activate"
echo "  uvicorn services.api:app --reload --port 8000"
