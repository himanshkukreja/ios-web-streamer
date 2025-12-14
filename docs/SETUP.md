# Setup Guide

Complete setup instructions for the iOS Simulator Screen Streaming system.

## Prerequisites

### macOS Requirements

- macOS 12.0 (Monterey) or later
- Xcode 15.0 or later with iOS Simulator
- Python 3.10 or later
- pip (Python package manager)

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
```

## Installation

### Step 1: Clone/Download the Project

```bash
cd /path/to/your/projects
# If cloned:
# git clone <repository-url>
cd nativebridge-ios-web-streamer
```

### Step 2: Install Dependencies

Run the installation script:

```bash
./scripts/install-deps.sh
```

This will:
1. Create a Python virtual environment
2. Install required Python packages (aiortc, websockets, aiohttp, etc.)
3. Verify Xcode installation

### Step 3: Configure iOS Project

1. Open the Xcode project:
   ```bash
   open ios-app/BroadcastApp/BroadcastApp.xcodeproj
   ```

2. Select your Development Team:
   - Select the "BroadcastApp" target
   - Go to "Signing & Capabilities"
   - Select your team (or sign in with Apple ID)
   - Do the same for "BroadcastExtension" target

3. Update Bundle Identifiers (if needed):
   - BroadcastApp: `com.yourcompany.broadcast`
   - BroadcastExtension: `com.yourcompany.broadcast.extension`

   **Important**: The extension bundle ID must be prefixed with the app bundle ID.

4. Update App Group (if you changed bundle IDs):
   - In both targets, update the App Group identifier
   - Also update in `Shared/Constants.swift`

## Running the System

### 1. Start the Server

In one terminal:

```bash
./scripts/start-server.sh
```

You should see:
```
============================================================
iOS Simulator Screen Streaming Server
============================================================
WebSocket (iOS):  ws://localhost:8765
HTTP (Viewers):   http://0.0.0.0:8080

Waiting for iOS Broadcast Extension to connect...
============================================================
```

### 2. Run the iOS App

1. In Xcode, select an iOS Simulator (e.g., iPhone 15 Pro)
2. Click Run (⌘+R) or Product → Run
3. Wait for the app to install and launch

### 3. Start Broadcasting

1. In the iOS app, tap the broadcast button (red circle)
2. A system dialog will appear - select "Screen Streamer"
3. Tap "Start Broadcast"

The server should show:
```
iOS app connected
iOS broadcast started - video should appear shortly
```

### 4. View the Stream

1. Open http://localhost:8080 in your browser
2. Click "Connect"
3. The video stream should appear

## Testing Without iOS

To test the server independently:

```bash
./scripts/start-server.sh --test
```

This generates a test video pattern and streams it via WebRTC.

## Configuration Options

### Server Options

| Option | Description | Default |
|--------|-------------|---------|
| `--test` | Run with test video (no iOS needed) | Off |
| `--port N` | HTTP server port | 8080 |
| `--debug` | Enable debug logging | Off |

### iOS App Settings

Configure in the app UI:
- **Host**: Server hostname (default: localhost)
- **Port**: WebSocket port (default: 8765)

These settings are saved and shared with the broadcast extension.

## Network Configuration

### Local Development

For local development, everything uses localhost:
- iOS Simulator → localhost:8765 (WebSocket)
- Browser → localhost:8080 (HTTP/WebRTC)

### Remote Access

To allow remote viewers:

1. Start server binding to all interfaces (default):
   ```bash
   ./scripts/start-server.sh
   ```

2. Open firewall ports:
   ```bash
   # macOS
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /path/to/python3

   # Or allow ports 8080 and 10000-10100/UDP
   ```

3. Share your public IP or hostname with viewers:
   ```
   http://YOUR-IP:8080
   ```

4. For NAT traversal, you may need a TURN server. Edit `server/config.py`:
   ```python
   ICE_SERVERS = [
       {"urls": "stun:stun.l.google.com:19302"},
       {"urls": "turn:your-turn-server.com:3478",
        "username": "user",
        "credential": "password"},
   ]
   ```

## Troubleshooting

### "Extension not found in broadcast picker"

1. Ensure both app and extension are signed with same team
2. Clean build: Product → Clean Build Folder
3. Delete app from simulator and reinstall

### "WebSocket connection failed"

1. Check server is running
2. Verify port 8765 is not in use: `lsof -i :8765`
3. Check firewall settings

### "No video in browser"

1. Check browser console for errors
2. Try a different browser
3. Verify WebRTC is not blocked by extensions

### "High latency"

1. Close other applications using the network
2. Check CPU usage on Mac
3. Try reducing video bitrate in `config.py`

## Next Steps

- [Troubleshooting Guide](TROUBLESHOOTING.md)
- [API Reference](API.md)
- [Architecture Overview](ARCHITECTURE.md)
