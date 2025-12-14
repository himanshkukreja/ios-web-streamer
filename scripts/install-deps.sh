#!/bin/bash

# Install dependencies for iOS Simulator Screen Streaming project

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_DIR="$PROJECT_DIR/server"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Installing iOS Simulator Streaming Dependencies${NC}"
echo ""

# Check Python
echo -e "${YELLOW}Checking Python...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed.${NC}"
    echo "Please install Python 3.10 or later."
    echo "  macOS: brew install python@3.11"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo -e "  ${GREEN}✓${NC} $PYTHON_VERSION"

# Check pip
echo -e "${YELLOW}Checking pip...${NC}"
if ! python3 -m pip --version &> /dev/null; then
    echo -e "${RED}pip is not installed.${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} pip available"

# Create virtual environment
echo ""
echo -e "${YELLOW}Setting up Python virtual environment...${NC}"
VENV_DIR="$SERVER_DIR/venv"

if [ -d "$VENV_DIR" ]; then
    echo -e "  Virtual environment already exists"
else
    python3 -m venv "$VENV_DIR"
    echo -e "  ${GREEN}✓${NC} Created virtual environment"
fi

# Activate and install packages
source "$VENV_DIR/bin/activate"

echo ""
echo -e "${YELLOW}Installing Python packages...${NC}"
pip install --upgrade pip -q
pip install -r "$SERVER_DIR/requirements.txt"
echo -e "  ${GREEN}✓${NC} Installed all Python dependencies"

# Check Xcode
echo ""
echo -e "${YELLOW}Checking Xcode...${NC}"
if ! command -v xcodebuild &> /dev/null; then
    echo -e "${RED}Xcode is not installed.${NC}"
    echo "Please install Xcode from the App Store."
    exit 1
fi

XCODE_VERSION=$(xcodebuild -version | head -1)
echo -e "  ${GREEN}✓${NC} $XCODE_VERSION"

# Summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Start the server:"
echo "   ./scripts/start-server.sh"
echo ""
echo "2. Open the iOS project in Xcode:"
echo "   open ios-app/BroadcastApp/BroadcastApp.xcodeproj"
echo ""
echo "3. Build and run the iOS app on the simulator"
echo ""
echo "4. Open your browser to view the stream:"
echo "   http://localhost:8080"
echo ""
