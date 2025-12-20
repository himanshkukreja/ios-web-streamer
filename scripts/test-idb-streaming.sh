#!/bin/bash

# Test script for IDB-based simulator streaming
# This script demonstrates the complete end-to-end workflow

set -e  # Exit on error

echo "================================================================="
echo "IDB Simulator Streaming Test"
echo "================================================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check dependencies
echo "🔍 Checking dependencies..."

if ! command -v idb_companion &> /dev/null; then
    echo "❌ idb_companion not found. Please install:"
    echo "   brew tap facebook/fb && brew install idb-companion"
    exit 1
fi

if ! python3 -c "import idb" &> /dev/null; then
    echo "❌ idb Python module not found. Please install:"
    echo "   pip3 install fb-idb"
    exit 1
fi

if ! python3 -c "import aiortc" &> /dev/null; then
    echo "❌ aiortc not found. Please install:"
    echo "   pip3 install aiortc"
    exit 1
fi

echo "✅ All dependencies installed"
echo ""

# Get booted simulator
echo "📱 Finding booted simulator..."
SIM_UDID=$(xcrun simctl list devices booted | grep "iPhone" | awk -F'[()]' '{print $2}' | head -1)

if [ -z "$SIM_UDID" ]; then
    echo "❌ No booted iPhone simulator found"
    echo ""
    echo "Please boot a simulator first:"
    echo "  xcrun simctl list devices available"
    echo "  xcrun simctl boot <UDID>"
    exit 1
fi

SIM_NAME=$(xcrun simctl list devices booted | grep "iPhone" | sed -E 's/^[[:space:]]+([^(]+).*/\1/' | head -1)
echo "✅ Found: $SIM_NAME ($SIM_UDID)"
echo ""

# Kill any existing idb_companion processes
echo "🧹 Cleaning up existing processes..."
pkill -9 idb_companion 2>/dev/null || true
pkill -9 -f "idb_streamer_final" 2>/dev/null || true
sleep 2
echo "✅ Cleanup complete"
echo ""

# Test 1: Basic IDB video streaming
echo "================================================================="
echo "Test 1: Basic IDB Video Streaming"
echo "================================================================="
echo ""

cd "$(dirname "$0")/.."

python3 server/idb_streamer_final.py

echo ""
echo "================================================================="
echo "✅ Test Complete!"
echo "================================================================="
echo ""
echo "Next steps:"
echo "  1. Integrate with WebRTC server"
echo "  2. Test browser viewing"
echo "  3. Test multiple simulators"
echo ""
