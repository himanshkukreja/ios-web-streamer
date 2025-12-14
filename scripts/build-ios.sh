#!/bin/bash

# Build and install iOS app on simulator using CLI tools

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IOS_PROJECT="$PROJECT_DIR/ios-app/BroadcastApp"
XCODEPROJ="$IOS_PROJECT/BroadcastApp.xcodeproj"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default values
SIMULATOR_NAME=""
SCHEME="BroadcastApp"
CONFIGURATION="Debug"
DERIVED_DATA="$PROJECT_DIR/build/DerivedData"
LIST_SIMULATORS=false
LAUNCH_APP=true

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--simulator)
            SIMULATOR_NAME="$2"
            shift 2
            ;;
        -l|--list)
            LIST_SIMULATORS=true
            shift
            ;;
        --release)
            CONFIGURATION="Release"
            shift
            ;;
        --no-launch)
            LAUNCH_APP=false
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  -s, --simulator NAME   Specify simulator name (default: first booted or iPhone 15 Pro)"
            echo "  -l, --list             List available simulators"
            echo "  --release              Build in Release configuration"
            echo "  --no-launch            Don't launch the app after installing"
            echo "  -h, --help             Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                              # Build and run on default simulator"
            echo "  $0 -s 'iPhone 15'               # Build and run on iPhone 15"
            echo "  $0 -l                           # List available simulators"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# List simulators if requested
if [ "$LIST_SIMULATORS" = true ]; then
    echo -e "${BLUE}Available iOS Simulators:${NC}"
    echo ""
    xcrun simctl list devices available | grep -E "iPhone|iPad" | grep -v "unavailable"
    exit 0
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Building iOS Broadcast App${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check Xcode
if ! command -v xcodebuild &> /dev/null; then
    echo -e "${RED}Error: Xcode command line tools not found${NC}"
    echo "Please install Xcode and run: xcode-select --install"
    exit 1
fi

XCODE_VERSION=$(xcodebuild -version | head -1)
echo -e "Xcode: ${GREEN}$XCODE_VERSION${NC}"

# Find or boot simulator
get_simulator_udid() {
    local name="$1"
    xcrun simctl list devices available -j | \
        python3 -c "
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data['devices'].items():
    if 'iOS' in runtime:
        for device in devices:
            if device['name'] == '$name' and device['isAvailable']:
                print(device['udid'])
                sys.exit(0)
" 2>/dev/null
}

get_booted_simulator() {
    xcrun simctl list devices booted -j | \
        python3 -c "
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data['devices'].items():
    if 'iOS' in runtime:
        for device in devices:
            if device['state'] == 'Booted':
                print(device['udid'])
                sys.exit(0)
" 2>/dev/null
}

get_default_simulator() {
    # Try common simulator names in order of preference
    local simulators=("iPhone 15 Pro" "iPhone 15" "iPhone 14 Pro" "iPhone 14" "iPhone SE (3rd generation)")
    for sim in "${simulators[@]}"; do
        local udid=$(get_simulator_udid "$sim")
        if [ -n "$udid" ]; then
            echo "$udid"
            return
        fi
    done
}

# Determine which simulator to use
if [ -n "$SIMULATOR_NAME" ]; then
    SIMULATOR_UDID=$(get_simulator_udid "$SIMULATOR_NAME")
    if [ -z "$SIMULATOR_UDID" ]; then
        echo -e "${RED}Error: Simulator '$SIMULATOR_NAME' not found${NC}"
        echo "Use '$0 -l' to list available simulators"
        exit 1
    fi
else
    # Check for already booted simulator
    SIMULATOR_UDID=$(get_booted_simulator)
    if [ -z "$SIMULATOR_UDID" ]; then
        # Find a default simulator
        SIMULATOR_UDID=$(get_default_simulator)
        if [ -z "$SIMULATOR_UDID" ]; then
            echo -e "${RED}Error: No suitable iOS simulator found${NC}"
            echo "Use '$0 -l' to list available simulators"
            exit 1
        fi
    fi
fi

# Get simulator name from UDID
SIMULATOR_INFO=$(xcrun simctl list devices -j | python3 -c "
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data['devices'].items():
    for device in devices:
        if device['udid'] == '$SIMULATOR_UDID':
            print(device['name'])
            sys.exit(0)
" 2>/dev/null)

echo -e "Simulator: ${GREEN}$SIMULATOR_INFO${NC} ($SIMULATOR_UDID)"
echo -e "Configuration: ${GREEN}$CONFIGURATION${NC}"
echo ""

# Boot simulator if not running
SIMULATOR_STATE=$(xcrun simctl list devices -j | python3 -c "
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data['devices'].items():
    for device in devices:
        if device['udid'] == '$SIMULATOR_UDID':
            print(device['state'])
            sys.exit(0)
" 2>/dev/null)

if [ "$SIMULATOR_STATE" != "Booted" ]; then
    echo -e "${YELLOW}Booting simulator...${NC}"
    xcrun simctl boot "$SIMULATOR_UDID" 2>/dev/null || true

    # Open Simulator app
    open -a Simulator --args -CurrentDeviceUDID "$SIMULATOR_UDID"

    # Wait for boot
    echo -n "Waiting for simulator to boot"
    for i in {1..30}; do
        STATE=$(xcrun simctl list devices -j | python3 -c "
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data['devices'].items():
    for device in devices:
        if device['udid'] == '$SIMULATOR_UDID':
            print(device['state'])
            sys.exit(0)
" 2>/dev/null)
        if [ "$STATE" = "Booted" ]; then
            echo ""
            break
        fi
        echo -n "."
        sleep 1
    done
fi

echo -e "${GREEN}✓${NC} Simulator ready"

# Build the project
echo ""
echo -e "${YELLOW}Building project...${NC}"

# Create derived data directory
mkdir -p "$DERIVED_DATA"

# Build for simulator
xcodebuild \
    -project "$XCODEPROJ" \
    -scheme "$SCHEME" \
    -configuration "$CONFIGURATION" \
    -destination "platform=iOS Simulator,id=$SIMULATOR_UDID" \
    -derivedDataPath "$DERIVED_DATA" \
    -allowProvisioningUpdates \
    DEVELOPMENT_TEAM="" \
    CODE_SIGN_IDENTITY="-" \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGNING_ALLOWED=NO \
    build 2>&1 | while IFS= read -r line; do
        # Show progress
        if [[ "$line" == *"Build Succeeded"* ]]; then
            echo -e "${GREEN}✓ Build succeeded${NC}"
        elif [[ "$line" == *"error:"* ]]; then
            echo -e "${RED}$line${NC}"
        elif [[ "$line" == *"warning:"* ]]; then
            echo -e "${YELLOW}$line${NC}"
        elif [[ "$line" == *"Compiling"* ]] || [[ "$line" == *"Linking"* ]]; then
            echo -e "  ${BLUE}$line${NC}"
        fi
    done

# Check if build succeeded
APP_PATH="$DERIVED_DATA/Build/Products/$CONFIGURATION-iphonesimulator/BroadcastApp.app"
if [ ! -d "$APP_PATH" ]; then
    echo -e "${RED}Error: Build failed - app bundle not found${NC}"
    echo "Run with verbose output:"
    echo "  xcodebuild -project '$XCODEPROJ' -scheme '$SCHEME' -configuration '$CONFIGURATION' -destination 'platform=iOS Simulator,id=$SIMULATOR_UDID'"
    exit 1
fi

echo -e "${GREEN}✓${NC} Build completed"

# Install the app
echo ""
echo -e "${YELLOW}Installing app on simulator...${NC}"
xcrun simctl install "$SIMULATOR_UDID" "$APP_PATH"
echo -e "${GREEN}✓${NC} App installed"

# Launch the app
if [ "$LAUNCH_APP" = true ]; then
    echo ""
    echo -e "${YELLOW}Launching app...${NC}"

    # Get bundle identifier
    BUNDLE_ID=$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$APP_PATH/Info.plist" 2>/dev/null || echo "com.nativebridge.broadcast")

    xcrun simctl launch "$SIMULATOR_UDID" "$BUNDLE_ID"
    echo -e "${GREEN}✓${NC} App launched"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Build and Install Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "1. In the iOS app, tap the broadcast button"
echo "2. Select 'Screen Streamer' from the list"
echo "3. Tap 'Start Broadcast'"
echo ""
echo "Make sure the server is running:"
echo "  ./scripts/start-server.sh"
echo ""
echo "Then open the viewer:"
echo "  http://localhost:8080"
