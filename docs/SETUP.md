# Setup Guide

Complete setup instructions for the iOS Screen Streaming system.

> **Important:** ReplayKit broadcast extensions do NOT work in the iOS Simulator. You must use a real iOS device for the broadcast functionality.

## Prerequisites

### Hardware Requirements

- Mac with macOS 12.0 (Monterey) or later
- Real iOS device (iPhone/iPad) with iOS 15.0 or later
- USB cable for initial device setup (wireless debugging available after)

### Software Requirements

- Xcode 15.0 or later
- Python 3.10 or later
- Apple Developer Account (free Apple ID works)

### Network Requirements

- Mac and iOS device on the same Wi-Fi network
- Ports 8765 (WebSocket) and 8999 (HTTP) accessible

### Verify Prerequisites

```bash
# Check macOS version
sw_vers

# Check Xcode
xcodebuild -version

# Check Python
python3 --version

# Check pip
python3 -m pip --version

# Get Mac's IP address (needed for iOS device)
ipconfig getifaddr en0
```

## Installation

### Step 1: Clone/Download the Project

```bash
cd /path/to/your/projects
git clone <repository-url>
cd nativebridge-ios-web-streamer
```

### Step 2: Install Server Dependencies

```bash
./scripts/install-deps.sh
```

This will:
1. Create a Python virtual environment
2. Install required Python packages (aiortc, websockets, aiohttp, av, etc.)
3. Verify Xcode installation

### Step 3: Configure iOS Project in Xcode

#### 3.1 Open the Project

```bash
open ios-app/BroadcastApp/BroadcastApp.xcodeproj
```

#### 3.2 Sign in with Apple ID

1. Open Xcode → Settings (⌘+,)
2. Go to "Accounts" tab
3. Click "+" and select "Apple ID"
4. Sign in with your Apple Developer account

#### 3.3 Configure Main App Target (BroadcastApp)

1. In Xcode, select the project in the navigator (left sidebar)
2. Select "BroadcastApp" target
3. Go to "Signing & Capabilities" tab
4. Check "Automatically manage signing"
5. Select your Team from the dropdown
6. If you see a bundle ID error, change to a unique ID:
   - Example: `com.yourname.broadcast`

#### 3.4 Configure Extension Target (BroadcastExtension)

1. Select "BroadcastExtension" target
2. Go to "Signing & Capabilities" tab
3. Check "Automatically manage signing"
4. Select the **same Team** as the main app
5. Update bundle ID if needed:
   - Must be prefixed with app bundle ID
   - Example: `com.yourname.broadcast.extension`

#### 3.5 Configure App Groups (Critical!)

Both targets must share the same App Group for the extension to communicate with the main app:

**For BroadcastApp target:**
1. Go to "Signing & Capabilities" tab
2. Click "+ Capability" and add "App Groups"
3. Click "+" under App Groups
4. Add identifier: `group.com.yourname.broadcast`

**For BroadcastExtension target:**
1. Same steps as above
2. Add the **exact same** App Group identifier

**Update the code:**
1. Edit `ios-app/BroadcastApp/Shared/Constants.swift`
2. Change `appGroupIdentifier` to match your App Group:
   ```swift
   static let appGroupIdentifier = "group.com.yourname.broadcast"
   ```

#### 3.6 Configure Server Address

Edit `ios-app/BroadcastApp/Shared/Constants.swift`:

```swift
enum Server {
    static let host = "192.168.1.100"  // Your Mac's IP address
    static let port = 8765
}
```

Or configure via the app UI after installation.

### Step 4: Trust Developer Certificate on iOS

When you first install an app from a free Apple ID:

1. Go to **Settings** on your iOS device
2. Navigate to **General → VPN & Device Management**
3. Tap on your developer certificate
4. Tap **"Trust"**

## Running the System

### 1. Start the Server

On your Mac, open a terminal:

```bash
./scripts/start-server.sh
```

Or with debug logging:
```bash
./scripts/start-server.sh --debug
```

You should see:
```
============================================================
iOS Screen Streaming Server
============================================================
WebSocket (iOS):  ws://0.0.0.0:8765
HTTP (Viewers):   http://0.0.0.0:8999

Waiting for iOS Broadcast Extension to connect...
============================================================
```

### 2. Build and Run iOS App

1. Connect your iOS device via USB
2. In Xcode, select your device from the device dropdown (top toolbar)
3. Click Run (⌘+R) or Product → Run
4. Trust the developer certificate if prompted (see Step 4 above)

### 3. Start Broadcasting

1. Open the app on your iOS device
2. Tap the broadcast button (red circle icon)
3. A system picker will appear - select "BroadcastExtension"
4. Tap "Start Broadcast"
5. After 3-second countdown, broadcasting begins

The server should show:
```
iOS client connected
Received config: X bytes
```

### 4. View the Stream

On any device on the same network, open a browser:

```
http://<mac-ip>:8999
```

For example: `http://192.168.1.100:8999`

Click "Connect" to view the stream.

## Testing Without iOS Device

To test the server and WebRTC streaming without a real device:

```bash
./scripts/start-server.sh --test
```

This generates a test video pattern at http://localhost:8999

## Configuration Options

### Server Options

| Option | Description | Default |
|--------|-------------|---------|
| `--test` | Run with test video (no iOS needed) | Off |
| `--port N` | HTTP server port | 8999 |
| `--debug` | Enable debug logging | Off |

### Server Configuration File

Edit `server/config.py`:

```python
# Network settings
WEBSOCKET_HOST = "0.0.0.0"  # Listen on all interfaces
WEBSOCKET_PORT = 8765       # iOS connects here
HTTP_PORT = 8999            # Browser connects here

# Video settings
DEFAULT_WIDTH = 1080        # Used for test mode only
DEFAULT_HEIGHT = 1920       # Actual device dimensions auto-detected
DEFAULT_FPS = 30
DEFAULT_BITRATE = 2_000_000  # 2 Mbps

# Frame queue
FRAME_QUEUE_MAX_SIZE = 10   # Buffer size (drop-oldest policy)
```

### iOS App Settings

Configure in the app UI or edit `Shared/Constants.swift`:

| Setting | Description | Default |
|---------|-------------|---------|
| Server Host | Mac's IP address | `localhost` |
| Server Port | WebSocket port | `8765` |
| App Group | Shared container ID | `group.com.nativebridge.broadcast` |

## Network Configuration

### Local Network Setup

For devices on the same Wi-Fi network:

1. **Mac IP Address:**
   ```bash
   ipconfig getifaddr en0
   ```

2. **iOS App:** Configure server host to Mac's IP

3. **Browser:** Access `http://<mac-ip>:8999`

### Firewall Configuration

If connections fail, check macOS firewall:

1. System Settings → Network → Firewall
2. Allow incoming connections for Python
3. Or add specific rules:
   ```bash
   # Allow Python (run with sudo)
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add $(which python3)
   ```

### Required Ports

| Port | Protocol | Direction | Purpose |
|------|----------|-----------|---------|
| 8765 | TCP | iOS → Mac | WebSocket (H264 frames) |
| 8999 | TCP | Browser → Mac | HTTP/WebRTC signaling |
| 10000-10100 | UDP | Bidirectional | WebRTC media |

### Remote Access (Advanced)

For viewers outside your local network:

1. Configure port forwarding on your router
2. Consider using a TURN server for NAT traversal
3. Edit `server/config.py`:
   ```python
   ICE_SERVERS = [
       {"urls": "stun:stun.l.google.com:19302"},
       {"urls": "turn:your-turn-server.com:3478",
        "username": "user",
        "credential": "password"},
   ]
   ```

## Wireless Debugging

Deploy without USB cable after initial setup:

1. Connect device via USB first
2. In Xcode: Window → Devices and Simulators
3. Select your device
4. Check "Connect via network"
5. Disconnect USB - device should still appear in Xcode

Requirements:
- Device and Mac on same network
- Device must have been connected via USB at least once

## Quick Reference

### Bundle Identifiers

| Target | Default | Your Value |
|--------|---------|------------|
| BroadcastApp | `com.nativebridge.broadcast` | `com.yourname.broadcast` |
| BroadcastExtension | `com.nativebridge.broadcast.extension` | `com.yourname.broadcast.extension` |

### App Group

| Setting | Default | Your Value |
|---------|---------|------------|
| App Group ID | `group.com.nativebridge.broadcast` | `group.com.yourname.broadcast` |

### Network Addresses

| Service | Address |
|---------|---------|
| WebSocket (iOS) | `ws://<mac-ip>:8765` |
| HTTP (Browser) | `http://<mac-ip>:8999` |
| Health Check | `http://<mac-ip>:8999/health` |

## Next Steps

- [Troubleshooting Guide](troubleshooting.md) - Solutions for common issues
- [Architecture Overview](architecture.md) - How the system works
