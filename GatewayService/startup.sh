#!/bin/bash

# FastAPI Gateway Service - Management Script
# Manages the gateway service lifecycle

set -e

# Configuration
SERVICE_NAME="gateway-service"
PID_FILE="./tmp/gateway.pid"
LOG_FILE="./logs/gateway.log"
ERROR_LOG_FILE="./logs/gateway-error.log"
HOST="0.0.0.0"
PORT="8000"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print banner
print_banner() {
    echo "=========================================================="
    echo "  FastAPI Gateway Service - Management"
    echo "=========================================================="
    echo ""
}

# Check prerequisites
check_prerequisites() {
    echo "✓ Checking Python version..."
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}✗ Python 3 not found!${NC}"
        exit 1
    fi
    
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    echo "  Python version: $python_version"

    # Check if .env file exists
    if [ ! -f ".env" ]; then
        echo -e "${RED}✗ .env file not found!${NC}"
        echo "  Please create .env with required configuration"
        exit 1
    else
        echo "  ✓ .env file found"
    fi
}

# Create necessary directories
create_directories() {
    mkdir -p logs
    mkdir -p tmp
}

# Build/Install dependencies
build_service() {
    print_banner
    echo -e "${GREEN}Building Gateway Service...${NC}"
    echo ""
    
    check_prerequisites
    create_directories
    
    echo ""
    echo "✓ Cleaning up conflicting system packages..."
    # Remove system-installed packages that conflict with pip packages
    pip uninstall -y pyOpenSSL cryptography urllib3 2>/dev/null || true
    sudo apt-get remove -y python3-openssl python3-cryptography python3-urllib3 2>/dev/null || true
    
    echo ""
    echo "✓ Installing dependencies..."
    # Upgrade pip and install clean versions
    pip install --upgrade pip setuptools wheel
    pip install --no-cache-dir -r requirements.txt
    echo -e "${GREEN}✓ Dependencies installed successfully${NC}"
    echo ""
    echo -e "${GREEN}✓ Build completed successfully!${NC}"
}

# Start the service
start_service() {
    print_banner
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${YELLOW}Service is already running (PID: $PID)${NC}"
            exit 0
        else
            echo "Removing stale PID file..."
            rm -f "$PID_FILE"
        fi
    fi
    
    check_prerequisites
    create_directories
    
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
    echo "=========================================================="
    echo "  Starting Gateway Service..."
    echo "=========================================================="
    echo ""
    echo "Configuration:"
    echo "  Profile: QA"
    echo "  Server: $HOST:$PORT"
    echo "  Log Level: INFO"
    echo "  PID File: $PID_FILE"
    echo "  Log File: $LOG_FILE"
    echo ""
    
    # Start the application in background
    nohup python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT" --log-level info > "$LOG_FILE" 2> "$ERROR_LOG_FILE" &
    
    echo $! > "$PID_FILE"
    sleep 3
    
    if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Service started successfully (PID: $(cat $PID_FILE))${NC}"
        echo ""
        echo "Use './startup.sh logs' to view logs"
        echo "Use './startup.sh status' to check status"
    else
        echo -e "${RED}✗ Failed to start service${NC}"
        echo ""
        echo "Error details:"
        if [ -f "$ERROR_LOG_FILE" ]; then
            cat "$ERROR_LOG_FILE"
        fi
        if [ -f "$LOG_FILE" ]; then
            echo ""
            echo "Recent logs:"
            tail -20 "$LOG_FILE"
        fi
        rm -f "$PID_FILE"
        exit 1
    fi
}

# Stop the service
stop_service() {
    print_banner
    
    if [ ! -f "$PID_FILE" ]; then
        echo -e "${YELLOW}Service is not running${NC}"
        exit 0
    fi
    
    PID=$(cat "$PID_FILE")
    
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping service (PID: $PID)..."
        kill "$PID"
        
        # Wait for process to stop
        for i in {1..10}; do
            if ! ps -p "$PID" > /dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        
        # Force kill if still running
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Force stopping service..."
            kill -9 "$PID"
            sleep 1
        fi
        
        rm -f "$PID_FILE"
        echo -e "${GREEN}✓ Service stopped successfully${NC}"
    else
        echo -e "${YELLOW}Service is not running (removing stale PID file)${NC}"
        rm -f "$PID_FILE"
    fi
}

# Restart the service
restart_service() {
    print_banner
    echo "Restarting service..."
    echo ""
    
    stop_service
    sleep 2
    start_service
}

# Check service status
check_status() {
    print_banner
    
    if [ ! -f "$PID_FILE" ]; then
        echo -e "${RED}✗ Service is not running${NC}"
        exit 1
    fi
    
    PID=$(cat "$PID_FILE")
    
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Service is running${NC}"
        echo ""
        echo "Process Information:"
        echo "  PID: $PID"
        echo "  Port: $PORT"
        ps -p "$PID" -o pid,ppid,%cpu,%mem,etime,cmd
        echo ""
        echo "Log Files:"
        echo "  Output: $LOG_FILE"
        echo "  Errors: $ERROR_LOG_FILE"
    else
        echo -e "${RED}✗ Service is not running (stale PID file found)${NC}"
        rm -f "$PID_FILE"
        exit 1
    fi
}

# Show logs
show_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}No log file found${NC}"
        exit 0
    fi
    
    if [ "$1" == "follow" ]; then
        echo "Following logs (Ctrl+C to exit)..."
        echo ""
        tail -f "$LOG_FILE"
    else
        echo "Last 30 lines of logs:"
        echo ""
        tail -n 30 "$LOG_FILE"
    fi
}

# Health check
health_check() {
    print_banner
    
    echo "Performing health check..."
    echo ""
    
    if [ ! -f "$PID_FILE" ]; then
        echo -e "${RED}✗ Service is not running${NC}"
        exit 1
    fi
    
    PID=$(cat "$PID_FILE")
    
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${RED}✗ Service process not found${NC}"
        rm -f "$PID_FILE"
        exit 1
    fi
    
    # Try to connect to the service
    if command -v curl &> /dev/null; then
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/docs" || echo "000")
        
        if [ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "404" ]; then
            echo -e "${GREEN}✓ Service is healthy${NC}"
            echo "  HTTP Status: $HTTP_CODE"
            echo "  Endpoint: http://localhost:$PORT"
        else
            echo -e "${RED}✗ Service is not responding${NC}"
            echo "  HTTP Status: $HTTP_CODE"
            exit 1
        fi
    else
        echo -e "${YELLOW}⚠ curl not found, skipping HTTP health check${NC}"
        echo -e "${GREEN}✓ Service process is running${NC}"
    fi
}

# Show usage
show_usage() {
    print_banner
    echo "Usage: sudo ./startup.sh [command]"
    echo ""
    echo "Commands:"
    echo "  build          Build and install dependencies"
    echo "  start          Start the gateway service"
    echo "  stop           Stop the gateway service"
    echo "  restart        Restart the gateway service"
    echo "  status         Check service status"
    echo "  logs           Show last 30 lines of logs"
    echo "  logs follow    Follow logs in real-time"
    echo "  health         Perform health check"
    echo ""
    echo "Examples:"
    echo "  sudo ./startup.sh build"
    echo "  sudo ./startup.sh start"
    echo "  sudo ./startup.sh logs follow"
    echo ""
}

# Main script logic
case "$1" in
    build)
        build_service
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        check_status
        ;;
    logs)
        show_logs "$2"
        ;;
    health)
        health_check
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
