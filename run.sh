#!/bin/bash
# Israeli Startup Job Scanner — Startup Script
#
# Runs the data fetcher (with periodic refresh) in the background,
# then starts a local web server.
#
# Usage: ./run.sh
# Then open: http://localhost:8080/web/

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "  Israeli Startup Job Scanner"
echo "=================================================="
echo ""

# Install Python dependencies if needed
if ! python3 -c "import requests" 2>/dev/null; then
    echo "Installing Python dependencies..."
    pip3 install -r fetch/requirements.txt
fi

# Run initial fetch if no data exists
if [ ! -f "data/jobs.json" ]; then
    echo "No data found. Running initial fetch (this may take a few minutes)..."
    python3 -c "
import sys; sys.path.insert(0, 'fetch')
from fetcher import run_fetch
run_fetch()
"
    echo "Initial fetch complete."
fi

echo ""
echo "Starting web server (with refresh API)..."
echo "Open http://localhost:8080/web/ in your browser"
echo "Press Ctrl+C to stop"
echo ""

# Start the custom server (serves static files + /api/refresh endpoint)
python3 serve.py
