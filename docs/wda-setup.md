# WebDriverAgent Setup Guide

This guide explains how to set up WebDriverAgent (WDA) to enable remote control of your iOS device from the web viewer.

## Table of Contents

1. [Overview](#overview)
2. [Option 1: Using Appium (Recommended)](#option-1-using-appium-recommended)
3. [Option 2: Manual WDA Setup](#option-2-manual-wda-setup)
4. [Option 3: Using go-ios](#option-3-using-go-ios)
5. [USB vs Wireless Connection](#usb-vs-wireless-connection)
6. [Connecting WDA to Mac](#connecting-wda-to-mac)
7. [Troubleshooting](#troubleshooting)

---

## Overview

WebDriverAgent (WDA) is a WebDriver server for iOS that runs **on the iOS device itself**. It enables automation and remote control by exposing a REST API that accepts commands like tap, swipe, and text input.

### How It Works

```
┌─────────────────┐                    ┌─────────────────┐
│   Mac (Host)    │                    │   iOS Device    │
│                 │                    │                 │
│  Python Server  │ ───HTTP REST───▶   │  WDA Server     │
│  (port 8100)    │    Commands        │  (port 8100)    │
│                 │                    │                 │
│                 │ ◀───Response────   │  Executes       │
│                 │                    │  Touch/Gestures │
└─────────────────┘                    └─────────────────┘
```

### Prerequisites

- macOS with Xcode 15.0 or later
- Real iOS device (iPhone/iPad) with iOS 15.0 or later
- Apple Developer Account (free or paid)
- Node.js 18+ (for Appium)

---

## Option 1: Using Appium (Recommended)

Appium is the easiest way to get WDA running. It handles building, signing, installing, and starting WDA automatically.

### Step 1: Install Node.js

```bash
# Using Homebrew
brew install node

# Verify installation
node --version  # Should be 18+
npm --version
```

### Step 2: Install Appium

```bash
# Install Appium globally
npm install -g appium

# Verify installation
appium --version
```

### Step 3: Install the XCUITest Driver

The XCUITest driver includes WebDriverAgent:

```bash
# Install the driver
appium driver install xcuitest

# Verify it's installed
appium driver list --installed
```

### Step 4: Connect Your iOS Device

**First time setup requires USB:**

1. Connect your iOS device via USB cable
2. Unlock the device
3. Trust the computer when prompted on the device
4. Open Xcode and go to Window → Devices and Simulators
5. Verify your device appears and is connected

### Step 5: Get Your Device UDID

```bash
# List connected devices
xcrun xctrace list devices

# Or using system_profiler
system_profiler SPUSBDataType | grep -A 11 "iPhone\|iPad"

# Or using idevice_id (from libimobiledevice)
brew install libimobiledevice
idevice_id -l
```

Note the UDID (a 40-character hex string or 25-character string for newer devices).

### Step 6: Start Appium Server

```bash
# Start with relaxed security (needed for some features)
appium --relaxed-security --allow-insecure=adb_shell
```

Keep this terminal open. Appium will listen on port 4723 by default.

### Step 7: Create a Session to Install WDA

When you create an Appium session, it automatically:
1. Builds WebDriverAgent from source
2. Signs it with your developer certificate
3. Installs it on your iOS device
4. Starts the WDA server on the device
5. Forwards port 8100 to your Mac

Create a test script to start a session:

```python
# test_appium.py
from appium import webdriver
from appium.options.ios import XCUITestOptions

options = XCUITestOptions()
options.platform_name = "iOS"
options.device_name = "iPhone"  # Your device name
options.udid = "YOUR_DEVICE_UDID"  # Replace with your UDID
options.automation_name = "XCUITest"
options.no_reset = True

# This will install and start WDA
driver = webdriver.Remote("http://localhost:4723", options=options)

print("WDA is now running!")
print(f"WDA URL: http://localhost:8100")

# Keep session alive
input("Press Enter to quit...")
driver.quit()
```

Run it:

```bash
pip install Appium-Python-Client
python test_appium.py
```

### What Appium Does Behind the Scenes

1. **Builds WDA**: Compiles the WebDriverAgent Xcode project
2. **Signs WDA**: Uses your Xcode signing identity to sign the app
3. **Installs WDA**: Deploys the signed WDA app to your iOS device
4. **Starts WDA**: Launches the WDA app on the device
5. **Port Forward**: Creates a USB tunnel from Mac:8100 to Device:8100

### Step 8: Configure the Streaming Server

Once WDA is running, configure your streaming server:

Edit `server/config.py`:

```python
# WebDriverAgent settings
WDA_HOST = "localhost"  # Appium forwards to localhost
WDA_PORT = 8100
```

### Step 9: Verify WDA is Running

```bash
# Check WDA status
curl http://localhost:8100/status

# Should return JSON like:
# {"value":{"ready":true,"message":"WebDriverAgent is ready",...}}
```

---

## Option 2: Manual WDA Setup

For more control, you can build and run WDA directly without Appium.

### Step 1: Clone WebDriverAgent

```bash
git clone https://github.com/appium/WebDriverAgent.git
cd WebDriverAgent
```

### Step 2: Install Dependencies

```bash
# Run the bootstrap script
./Scripts/bootstrap.sh
```

### Step 3: Open in Xcode

```bash
open WebDriverAgent.xcodeproj
```

### Step 4: Configure Signing

1. Select the project in the navigator
2. Select **WebDriverAgentLib** target:
   - Go to "Signing & Capabilities"
   - Check "Automatically manage signing"
   - Select your Team

3. Select **WebDriverAgentRunner** target:
   - Same steps as above
   - Change Bundle ID if needed: `com.yourname.WebDriverAgentRunner`

4. Select **IntegrationApp** target (optional):
   - Same signing configuration

### Step 5: Build for Device

1. Connect your iOS device via USB
2. Select your device in the Xcode toolbar
3. Select the **WebDriverAgentRunner** scheme
4. Click Product → Test (or Cmd+U)

Xcode will:
- Build the WDA app
- Install it on your device
- Start running WDA

### Step 6: Trust the Developer Certificate

On your iOS device:
1. Go to Settings → General → VPN & Device Management
2. Find your developer certificate
3. Tap "Trust"

### Step 7: Set Up Port Forwarding

WDA runs on port 8100 on the device. Forward it to your Mac:

```bash
# Install libimobiledevice
brew install libimobiledevice

# Forward port 8100
iproxy 8100 8100

# Keep this terminal open!
```

### Step 8: Verify WDA is Running

```bash
curl http://localhost:8100/status
```

---

## Option 3: Using go-ios

go-ios is a lightweight alternative to libimobiledevice.

### Step 1: Install go-ios

```bash
brew install go-ios
```

### Step 2: List Devices

```bash
ios list
```

### Step 3: Install and Run WDA

You need to have WDA already built (from Option 2):

```bash
# Install WDA app
ios install --path=/path/to/WebDriverAgentRunner.app

# Run WDA
ios runwda --bundleid=com.facebook.WebDriverAgentRunner.xctrunner
```

### Step 4: Forward Port

```bash
ios forward 8100 8100
```

---

## USB vs Wireless Connection

### USB Connection (Recommended for Setup)

**Pros:**
- More reliable
- Lower latency
- Required for initial WDA installation
- No network configuration needed

**Cons:**
- Requires physical cable
- Device must stay connected

**Setup:**
1. Connect device via USB
2. Port forwarding happens over USB tunnel
3. Use `localhost:8100` to access WDA

```bash
# USB port forwarding
iproxy 8100 8100
```

### Wireless Connection

**Pros:**
- No cable needed
- Device can move freely
- Multiple devices on same network

**Cons:**
- Higher latency
- Requires network configuration
- Initial setup still needs USB
- May have firewall issues

**Requirements:**
- Device and Mac on same Wi-Fi network
- WDA already installed (requires initial USB connection)
- Device IP address

**Setup:**

1. **Get Device IP Address:**
   - On iOS: Settings → Wi-Fi → Tap (i) next to network
   - Note the IP address (e.g., 192.168.1.50)

2. **Enable Wireless Debugging in Xcode:**
   - Connect device via USB first
   - Window → Devices and Simulators
   - Select your device
   - Check "Connect via network"
   - Disconnect USB

3. **Start WDA on Device:**
   - Use Xcode to run WebDriverAgentRunner test
   - Or use a pre-installed WDA

4. **Connect Directly to Device IP:**

   Edit `server/config.py`:
   ```python
   WDA_HOST = "192.168.1.50"  # Device IP
   WDA_PORT = 8100
   ```

5. **Test Connection:**
   ```bash
   curl http://192.168.1.50:8100/status
   ```

### Hybrid Approach (Best of Both)

1. Use USB for initial setup and WDA installation
2. Switch to wireless for regular use
3. Keep USB as fallback for reliability

---

## Connecting WDA to Mac

### Method 1: USB Port Forwarding (iproxy)

Creates a tunnel over USB:

```bash
# Install libimobiledevice
brew install libimobiledevice

# Start port forwarding (keep running)
iproxy 8100 8100

# WDA is now accessible at localhost:8100
```

### Method 2: Direct IP Connection

Connect directly to device's IP:

```bash
# Get device IP
# On device: Settings → Wi-Fi → (i) → IP Address

# Test connection
curl http://192.168.1.50:8100/status

# Configure server
# In config.py: WDA_HOST = "192.168.1.50"
```

### Method 3: Appium Built-in Forwarding

Appium handles forwarding automatically:

```bash
# Just start Appium
appium --relaxed-security

# Appium sets up forwarding when session starts
# WDA accessible at localhost:8100
```

### Verifying Connection

```bash
# Check if WDA is accessible
curl http://localhost:8100/status

# Get device info
curl http://localhost:8100/session

# Get screen size
curl http://localhost:8100/wda/screen

# Test a tap (x=100, y=200)
curl -X POST http://localhost:8100/session/YOUR_SESSION_ID/wda/touch/perform \
  -H "Content-Type: application/json" \
  -d '{"actions":[{"action":"tap","options":{"x":100,"y":200}}]}'
```

---

## Alternatives to Appium

### 1. Manual Xcode Build (Described Above)

**Pros:** Full control, no extra dependencies
**Cons:** More setup steps, manual port forwarding

### 2. go-ios

**Pros:** Lightweight, fast, single binary
**Cons:** Less documentation, fewer features

```bash
brew install go-ios
ios runwda --bundleid=com.facebook.WebDriverAgentRunner.xctrunner
```

### 3. tidevice (Python)

**Pros:** Python-based, easy scripting
**Cons:** Requires Python, less maintained

```bash
pip install tidevice
tidevice wdaproxy -B com.facebook.WebDriverAgentRunner.xctrunner
```

### 4. WebDriverAgent Standalone

Build WDA once, deploy manually:

```bash
# Build with xcodebuild
xcodebuild -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination 'id=YOUR_DEVICE_UDID' \
  test
```

### 5. ios-deploy

For installing pre-built WDA:

```bash
brew install ios-deploy
ios-deploy --bundle WebDriverAgentRunner.app
```

### Comparison Table

| Method | Ease of Setup | Maintenance | USB Required | Wireless Support |
|--------|---------------|-------------|--------------|------------------|
| Appium | Easy | Auto-managed | Initial only | Yes |
| Manual Xcode | Medium | Manual | Initial only | Yes |
| go-ios | Medium | Manual | Initial only | Yes |
| tidevice | Easy | Manual | Initial only | Yes |

---

## Troubleshooting

### WDA Won't Install

1. **Check signing:**
   ```bash
   security find-identity -v -p codesigning
   ```
   Ensure you have a valid certificate.

2. **Trust certificate on device:**
   Settings → General → VPN & Device Management → Trust

3. **Check device is unlocked** during installation

### WDA Crashes on Launch

1. **Free developer account limitation:**
   - Apps expire after 7 days
   - Reinstall WDA weekly
   - Consider paid account for permanent installation

2. **Check console logs:**
   ```bash
   idevicesyslog | grep -i webdriver
   ```

### Connection Refused

1. **Check WDA is running:**
   - Look for WDA icon on device (may be hidden)
   - Check Xcode console for errors

2. **Check port forwarding:**
   ```bash
   lsof -i :8100
   ```

3. **Check firewall:**
   - System Settings → Network → Firewall
   - Allow Python/incoming connections

### Slow Response

1. **Use USB instead of wireless**
2. **Reduce WDA logging:**
   ```bash
   export WDA_LOG_LEVEL=error
   ```
3. **Check network congestion**

### Session Expired

WDA sessions can timeout. The streaming server handles this by:
- Auto-reconnecting to WDA
- Creating new sessions as needed

---

## Quick Reference

### Commands

```bash
# Start Appium
appium --relaxed-security

# USB port forwarding
iproxy 8100 8100

# Check WDA status
curl http://localhost:8100/status

# List devices
xcrun xctrace list devices

# Get device UDID
idevice_id -l
```

### Configuration

```python
# server/config.py

# For USB (with iproxy)
WDA_HOST = "localhost"
WDA_PORT = 8100

# For wireless (direct IP)
WDA_HOST = "192.168.1.50"  # Device IP
WDA_PORT = 8100
```

### Server Options

```bash
# Start server with control enabled (default)
./scripts/start-server.sh

# Start server without control
./scripts/start-server.sh --no-control
```

---

## Next Steps

- [Setup Guide](setup.md) - Main setup instructions
- [Troubleshooting Guide](troubleshooting.md) - Common issues
- [Architecture Overview](architecture.md) - System design
