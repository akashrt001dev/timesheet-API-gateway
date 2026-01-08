#!/bin/bash

# FastAPI Gateway Service - Startup Script
# Starts the gateway service on the server

set -e

echo "╔════════════════════════════════════════════════════════╗"
echo "║  FastAPI Gateway Service - Startup                     ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Check Python version
echo "✓ Checking Python version..."
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
echo "  Python version: $python_version"

if (( $(echo "$python_version < 3.11" | bc -l) )); then
    echo "  ✗ Python 3.11+ required!"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "  ✗ .env file not found!"
    echo "  Please create .env with required configuration"
    exit 1
else
    echo "  ✓ .env file found"
fi

# Create necessary directories
echo ""
echo "✓ Creating directories..."
mkdir -p logs
mkdir -p tmp
echo "  Created: logs/, tmp/"

# Check dependencies
echo ""
echo "✓ Checking dependencies..."
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "  Installing dependencies..."
    pip install -q -r requirements.txt
    echo "  Dependencies installed"
else
    echo "  All dependencies available"
fi

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║  Starting Gateway Service...                           ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "Configuration:"
echo "  Profile: QA"
echo "  Server: 0.0.0.0:8000"
echo "  Log Level: INFO"
echo ""
echo "Starting FastAPI server..."
echo ""

# Start the application
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
