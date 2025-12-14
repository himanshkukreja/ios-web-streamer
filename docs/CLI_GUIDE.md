# CLI Guide - Building and Installing via Command Line

This guide covers how to build and install the iOS app using command-line tools without opening Xcode, and how to manage WebDriverAgent via CLI.

## Prerequisites

- Xcode Command Line Tools installed
- Device connected via USB
- Developer certificate configured in Xcode (even if you're using CLI)

## Building the iOS App via CLI

### 1. List Available Devices

First, find your device ID:

```bash
xcrun devicectl list devices
```

Look for your device name and copy the device ID (format: `00008101-000A51381190801E`)

### 2. Clean and Build

Navigate to the iOS app directory and build:

```bash
cd ios-app/BroadcastApp

# Clean build
xcodebuild -scheme BroadcastApp \
  -configuration Debug \
  -destination 'platform=iOS,id=YOUR_DEVICE_ID' \
  clean build
```

**Example:**
```bash
xcodebuild -scheme BroadcastApp \
  -configuration Debug \
  -destination 'platform=iOS,id=00008101-000A51381190801E' \
  clean build
```

### 3. Install on Device

After successful build, install the app:

```bash
xcrun devicectl device install app \
  --device YOUR_DEVICE_ID \
  "~/Library/Developer/Xcode/DerivedData/BroadcastApp-*/Build/Products/Debug-iphoneos/BroadcastApp.app"
```

**Example:**
```bash
xcrun devicectl device install app \
  --device 00008101-000A51381190801E \
  "/Users/yourusername/Library/Developer/Xcode/DerivedData/BroadcastApp-ctcovlzjjlwkjacghazddzdqauui/Build/Products/Debug-iphoneos/BroadcastApp.app"
```

**Tip:** The full path to the built app is shown in the build output. Look for:
```
Touch /Users/.../BroadcastApp.app
```

### 4. One-Line Build and Install

Combine both steps:

```bash
cd ios-app/BroadcastApp && \
xcodebuild -scheme BroadcastApp -configuration Debug \
  -destination 'platform=iOS,id=00008101-000A51381190801E' build && \
xcrun devicectl device install app --device 00008101-000A51381190801E \
  "$(find ~/Library/Developer/Xcode/DerivedData/BroadcastApp-*/Build/Products/Debug-iphoneos -name "BroadcastApp.app" -type d | head -1)"
```

## Build Script

For convenience, you can use the provided build script:

```bash
./scripts/build-ios.sh
```

The script will:
1. Detect connected device automatically
2. Build the app
3. Install on device
4. Show installation status

## WebDriverAgent CLI Commands

### Starting WebDriverAgent

#### Option 1: Using Xcode (Recommended for first-time setup)

```bash
# Open WDA project
cd WebDriverAgent
open WebDriverAgent.xcodeproj
```

Then in Xcode:
1. Select WebDriverAgentRunner scheme
2. Select your device
3. Press `Cmd+U` to run tests (this starts WDA)

#### Option 2: Using xcodebuild (CLI only)

```bash
cd WebDriverAgent

# Build and run on device
xcodebuild test \
  -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination 'platform=iOS,id=YOUR_DEVICE_ID' \
  -allowProvisioningUpdates
```

**Example:**
```bash
cd WebDriverAgent
xcodebuild test \
  -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination 'platform=iOS,id=00008101-000A51381190801E' \
  -allowProvisioningUpdates
```

This will:
- Build WebDriverAgent
- Install on device
- Start the WDA server on port 8100

### Stopping WebDriverAgent

WDA runs as long as the Xcode test session is active. To stop it:

**If running via Xcode:**
- Press `Cmd+.` (Stop button) in Xcode

**If running via CLI:**
- Press `Ctrl+C` in the terminal where xcodebuild is running

### Restarting WebDriverAgent

If WDA becomes unresponsive or you need to restart it:

```bash
# Kill any existing WDA process on device
xcrun devicectl device process kill \
  --device YOUR_DEVICE_ID \
  --name WebDriverAgentRunner

# Start again
cd WebDriverAgent
xcodebuild test \
  -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination 'platform=iOS,id=YOUR_DEVICE_ID' \
  -allowProvisioningUpdates
```

### Checking WDA Status

```bash
# Check if WDA is running
curl http://localhost:8100/status

# Expected response if running:
# {"value":{"ready":true,"message":"WebDriverAgent is ready to accept commands",...}}

# If not running, you'll get:
# curl: (7) Failed to connect to localhost port 8100
```

### Setting Up USB Port Forwarding for WDA

If using WDA over USB:

```bash
# Forward device port 8100 to Mac localhost:8100
iproxy 8100 8100

# Keep this terminal open while using WDA
```

**Alternative:** Use `--wda-host` with device IP for wireless:
```bash
./scripts/start-server.sh --wda-host 192.168.1.XXX
```

## Complete Workflow Example

Here's a complete workflow from building the app to starting streaming with control:

```bash
# 1. Get device ID
DEVICE_ID=$(xcrun devicectl list devices | grep "iPhone" | head -1 | awk '{print $NF}')
echo "Device ID: $DEVICE_ID"

# 2. Build and install iOS app
cd ios-app/BroadcastApp
xcodebuild -scheme BroadcastApp -configuration Debug \
  -destination "platform=iOS,id=$DEVICE_ID" build

APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/BroadcastApp-*/Build/Products/Debug-iphoneos -name "BroadcastApp.app" -type d | head -1)
xcrun devicectl device install app --device "$DEVICE_ID" "$APP_PATH"

# 3. Start WebDriverAgent
cd ../../WebDriverAgent
xcodebuild test -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination "platform=iOS,id=$DEVICE_ID" \
  -allowProvisioningUpdates &

# Wait for WDA to start
sleep 5

# 4. Start streaming server (in another terminal)
cd ..
./scripts/start-server.sh

# 5. Open browser to http://localhost:8999
```

## Troubleshooting CLI Builds

### "No signing certificate found"

```bash
# List available signing identities
security find-identity -v -p codesigning

# If empty, you need to:
# 1. Open Xcode
# 2. Go to Settings → Accounts
# 3. Add your Apple ID
# 4. Download Manual Profiles
```

### "Device is locked"

Unlock your iOS device and try again.

### "Failed to install app"

```bash
# Check if device is trusted
xcrun devicectl list devices

# If device shows as "untrusted", unlock device and tap "Trust This Computer"
```

### "Build failed - missing provisioning profile"

The first time, you may need to open the project in Xcode to set up code signing:

```bash
open ios-app/BroadcastApp/BroadcastApp.xcodeproj
```

Then:
1. Select BroadcastApp target
2. Go to Signing & Capabilities
3. Check "Automatically manage signing"
4. Select your Team

After this, CLI builds should work.

### WDA "Could not start WebDriverAgent session"

```bash
# 1. Check device logs
xcrun devicectl device info logs --device YOUR_DEVICE_ID

# 2. Rebuild WDA from scratch
cd WebDriverAgent
xcodebuild clean
xcodebuild test -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination "platform=iOS,id=YOUR_DEVICE_ID" \
  -allowProvisioningUpdates

# 3. If still failing, restart device
```

## Automation Script

Create a file `quick-deploy.sh`:

```bash
#!/bin/bash

# Quick deploy script
set -e

DEVICE_ID="00008101-000A51381190801E"  # Replace with your device ID

echo "🔨 Building iOS app..."
cd ios-app/BroadcastApp
xcodebuild -scheme BroadcastApp -configuration Debug \
  -destination "platform=iOS,id=$DEVICE_ID" build > /dev/null 2>&1

echo "📱 Installing on device..."
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/BroadcastApp-*/Build/Products/Debug-iphoneos -name "BroadcastApp.app" -type d | head -1)
xcrun devicectl device install app --device "$DEVICE_ID" "$APP_PATH"

echo "✅ App installed successfully!"
echo "Start broadcast from device and open http://localhost:8999"
```

Make it executable:
```bash
chmod +x quick-deploy.sh
./quick-deploy.sh
```

## Advanced: Build for Release

```bash
# Build release version
xcodebuild -scheme BroadcastApp \
  -configuration Release \
  -destination 'platform=iOS,id=YOUR_DEVICE_ID' \
  clean build
```

Release builds are optimized but harder to debug. Use Debug builds during development.

## Tips

1. **Keep terminal logs**: Save build output for troubleshooting:
   ```bash
   xcodebuild ... 2>&1 | tee build.log
   ```

2. **Faster incremental builds**: Skip `clean` after first build:
   ```bash
   xcodebuild -scheme BroadcastApp -destination ... build
   ```

3. **Check Xcode version**:
   ```bash
   xcodebuild -version
   ```

4. **View device info**:
   ```bash
   xcrun devicectl device info --device YOUR_DEVICE_ID
   ```
