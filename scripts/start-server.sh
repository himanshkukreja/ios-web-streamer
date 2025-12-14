#!/bin/bash

# iOS Simulator Screen Streaming Server Startup Script
# This script starts the Python server that receives video from iOS
# and streams it to web browsers via WebRTC.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_DIR="$PROJECT_DIR/server"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}iOS Simulator Screen Streaming Server${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
echo -e "Python version: ${GREEN}$PYTHON_VERSION${NC}"

# Check if virtual environment exists
VENV_DIR="$SERVER_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Install/update dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install -q -r "$SERVER_DIR/requirements.txt"

# Parse command line arguments
TEST_MODE=""
MEDIA_FILE=""
PORT=8999
DEBUG=""
NO_CONTROL=""
WDA_HOST=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --test)
            TEST_MODE="--test"
            shift
            ;;
        --media)
            MEDIA_FILE="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --debug)
            DEBUG="--debug"
            shift
            ;;
        --no-control)
            NO_CONTROL="--no-control"
            shift
            ;;
        --wda-host)
            WDA_HOST="--wda-host $2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --test             Run in test mode (generates test video, no iOS needed)"
            echo "  --media FILE       Stream a media file (mp4, mkv, etc) to web browsers"
            echo "  --port N           Set HTTP server port (default: 8999)"
            echo "  --debug            Enable debug logging"
            echo "  --no-control       Disable device control via WebDriverAgent"
            echo "  --wda-host IP      WebDriverAgent host IP (use device IP for WiFi control)"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                               # Normal mode (wait for iOS, USB control)"
            echo "  $0 --test                        # Test with generated pattern"
            echo "  $0 --media video.mp4             # Stream a video file"
            echo "  $0 --no-control                  # Stream only, no device control"
            echo "  $0 --wda-host 192.168.1.100      # Use WiFi for device control (no USB)"
            echo "  $0 --media ~/Movies/demo.mkv     # Stream from absolute path"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo ""
echo -e "${GREEN}Starting server...${NC}"
echo ""

# Build the command
MEDIA_ARG=""
if [ -n "$MEDIA_FILE" ]; then
    # Convert relative path to absolute
    if [[ "$MEDIA_FILE" != /* ]]; then
        MEDIA_FILE="$PROJECT_DIR/$MEDIA_FILE"
    fi

    if [ ! -f "$MEDIA_FILE" ]; then
        echo -e "${RED}Error: Media file not found: $MEDIA_FILE${NC}"
        exit 1
    fi
    MEDIA_ARG="--media $MEDIA_FILE"
fi

# Change to server directory and start
cd "$SERVER_DIR"
python3 main.py $TEST_MODE $MEDIA_ARG --port $PORT $DEBUG $NO_CONTROL $WDA_HOST
