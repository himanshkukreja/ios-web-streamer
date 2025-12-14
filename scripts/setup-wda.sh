#!/bin/bash
#
# Manual WDA Setup Script
# This script helps build and install WebDriverAgent manually
#

set -e

# Configuration
DEVICE_UDID="00008101-000A51381190801E"
TEAM_ID="669TY9XL65"
WDA_BUNDLE_ID="com.himanshukukreja.WebDriverAgentRunner"
WDA_PATH="$HOME/.appium/node_modules/appium-xcuitest-driver/node_modules/appium-webdriveragent"

echo "============================================================"
echo "WebDriverAgent Manual Setup"
echo "============================================================"
echo ""
echo "Device UDID: $DEVICE_UDID"
echo "Team ID: $TEAM_ID"
echo "WDA Bundle ID: $WDA_BUNDLE_ID"
echo "WDA Path: $WDA_PATH"
echo ""

# Check if WDA exists
if [ ! -d "$WDA_PATH" ]; then
    echo "ERROR: WDA not found at $WDA_PATH"
    echo "Run: appium driver install xcuitest"
    exit 1
fi

# Check if device is connected
echo "Checking device connection..."
if ! xcrun xctrace list devices 2>/dev/null | grep -q "$DEVICE_UDID"; then
    echo "ERROR: Device not found. Make sure it's connected and unlocked."
    exit 1
fi
echo "Device found!"
echo ""

# Option 1: Open in Xcode for manual signing
echo "============================================================"
echo "OPTION 1: Manual Xcode Setup (Recommended for first time)"
echo "============================================================"
echo ""
echo "1. Open WDA project in Xcode:"
echo "   open '$WDA_PATH/WebDriverAgent.xcodeproj'"
echo ""
echo "2. In Xcode:"
echo "   a. Select 'WebDriverAgentRunner' target"
echo "   b. Go to 'Signing & Capabilities'"
echo "   c. Enable 'Automatically manage signing'"
echo "   d. Select your Team: Sahil Choudhary ($TEAM_ID)"
echo "   e. Change Bundle Identifier to: $WDA_BUNDLE_ID"
echo ""
echo "3. Build and Run:"
echo "   a. Select your device from the device dropdown"
echo "   b. Press Cmd+U to test (this installs WDA)"
echo "   c. On first run, you'll need to trust the certificate on device:"
echo "      Settings > General > VPN & Device Management"
echo ""
echo "4. Once WDA is installed and running, start the port forward:"
echo "   iproxy 8100 8100 -u $DEVICE_UDID"
echo ""

# Option 2: Try command-line build
echo "============================================================"
echo "OPTION 2: Command-line Build (if already set up in Xcode)"
echo "============================================================"
echo ""
echo "If you've already configured signing in Xcode, try:"
echo ""
echo "cd '$WDA_PATH'"
echo "xcodebuild build-for-testing \\"
echo "  -project WebDriverAgent.xcodeproj \\"
echo "  -scheme WebDriverAgentRunner \\"
echo "  -destination 'id=$DEVICE_UDID' \\"
echo "  DEVELOPMENT_TEAM=$TEAM_ID \\"
echo "  CODE_SIGN_IDENTITY='Apple Development' \\"
echo "  PRODUCT_BUNDLE_IDENTIFIER=$WDA_BUNDLE_ID"
echo ""

# Ask user what to do
echo "============================================================"
echo "What would you like to do?"
echo "============================================================"
echo ""
echo "  1) Open WDA in Xcode (recommended for first setup)"
echo "  2) Try command-line build"
echo "  3) Start iproxy only (if WDA already installed)"
echo "  4) Exit"
echo ""
read -p "Choice [1-4]: " choice

case $choice in
    1)
        echo "Opening WDA project in Xcode..."
        open "$WDA_PATH/WebDriverAgent.xcodeproj"
        echo ""
        echo "Follow the instructions above to configure signing and build."
        ;;
    2)
        echo "Attempting command-line build..."
        cd "$WDA_PATH"
        xcodebuild build-for-testing \
            -project WebDriverAgent.xcodeproj \
            -scheme WebDriverAgentRunner \
            -destination "id=$DEVICE_UDID" \
            -allowProvisioningUpdates \
            DEVELOPMENT_TEAM="$TEAM_ID" \
            CODE_SIGN_IDENTITY="Apple Development" \
            PRODUCT_BUNDLE_IDENTIFIER="$WDA_BUNDLE_ID"

        if [ $? -eq 0 ]; then
            echo ""
            echo "Build successful! Now run WDA on device with:"
            echo "xcodebuild test-without-building \\"
            echo "  -project WebDriverAgent.xcodeproj \\"
            echo "  -scheme WebDriverAgentRunner \\"
            echo "  -destination 'id=$DEVICE_UDID'"
        fi
        ;;
    3)
        echo "Starting iproxy for port forwarding..."
        echo "This assumes WDA is already installed and running on device."
        echo ""
        echo "Running: iproxy 8100 8100 -u $DEVICE_UDID"
        iproxy 8100 8100 -u "$DEVICE_UDID"
        ;;
    4)
        echo "Exiting."
        exit 0
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac
