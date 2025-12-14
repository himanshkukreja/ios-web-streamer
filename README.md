# iOS Screen Streaming

Real-time streaming of iOS device/simulator screens to web browsers via WebRTC.

## Features

- **Low Latency**: Target <150ms end-to-end latency
- **Hardware Encoding**: H264 encoding via VideoToolbox
- **WebRTC Distribution**: Stream to any modern browser
- **Multi-Viewer Support**: Multiple concurrent viewers
- **Native Resolution**: Automatic detection of device screen dimensions
- **Simple Setup**: One-tap broadcast from iOS
- **Real Device Support**: Works with physical iOS devices

## Architecture

```
┌─────────────────┐     WebSocket      ┌─────────────────┐     WebRTC      ┌─────────────────┐
│   iOS Device    │ ──────────────────▶│  Python Server  │──────────────▶│     Browser     │
│   (ReplayKit)   │   H264 Frames      │ (aiortc/aiohttp)│               │    (Viewer)     │
└─────────────────┘                    └─────────────────┘               └─────────────────┘
```

## Important Note

**ReplayKit broadcast extensions do NOT work in the iOS Simulator.** You must use a **real iOS device** for the broadcast functionality. The simulator can be used for UI development only.

---

## Quick Start (Real iOS Device)

### Prerequisites

- macOS 12.0+ with Xcode 15.0+
- Python 3.10+
- Real iOS device (iOS 15.0+)
- Apple Developer Account (free Apple ID works)
- Mac and iOS device on the same Wi-Fi network

### Step 1: Install Server Dependencies

```bash
./scripts/install-deps.sh
```

### Step 2: Get Your Mac's IP Address

```bash
ipconfig getifaddr en0
```

Note this IP (e.g., `192.168.1.100`) - you'll need it for the iOS app.

### Step 3: Configure and Build iOS App in Xcode

1. **Open the project:**
   ```bash
   open ios-app/BroadcastApp/BroadcastApp.xcodeproj
   ```

2. **Sign in with Apple ID:**
   - Xcode → Settings (⌘+,) → Accounts → Add Apple ID

3. **Configure code signing for both targets:**

   For **BroadcastApp** target:
   - Select project in navigator → BroadcastApp target → Signing & Capabilities
   - Check "Automatically manage signing"
   - Select your Team
   - If bundle ID conflicts, change to unique ID (e.g., `com.yourname.broadcast`)

   For **BroadcastExtension** target:
   - Same steps, use **same Team**
   - Bundle ID must be prefixed (e.g., `com.yourname.broadcast.extension`)

4. **Configure App Groups (both targets must match):**
   - Add App Group capability to both targets
   - Use same identifier (e.g., `group.com.yourname.broadcast`)
   - Update `ios-app/BroadcastApp/Shared/Constants.swift` with your App Group ID

5. **Set server address:**
   - Edit `ios-app/BroadcastApp/Shared/Constants.swift`
   - Change `Server.host` to your Mac's IP address

6. **Build and run:**
   - Connect iOS device via USB
   - Select your device in Xcode toolbar
   - Click Run (⌘+R)
   - Trust developer certificate on iOS if prompted (Settings → General → VPN & Device Management)

### Step 4: Start the Server

```bash
./scripts/start-server.sh
```

Or with debug logging:
```bash
./scripts/start-server.sh --debug
```

### Step 5: Start Broadcasting

1. Open the app on your iOS device
2. Tap the broadcast button (red circle)
3. Select "BroadcastExtension" from the picker
4. Tap "Start Broadcast"

### Step 6: View the Stream

Open in any browser on the same network:
```
http://<mac-ip>:8999
```

Click "Connect" to view the stream.

---

## Testing Without iOS Device

To test the server and WebRTC streaming without a real device:

```bash
./scripts/start-server.sh --test
```

This generates a test video pattern at http://localhost:8999

---

## Detailed Setup Guide

### Xcode Code Signing

#### Bundle Identifiers

| Target | Default Bundle ID |
|--------|-------------------|
| BroadcastApp | `com.nativebridge.broadcast` |
| BroadcastExtension | `com.nativebridge.broadcast.extension` |

**Important:** The extension bundle ID must be prefixed with the app bundle ID.

#### App Groups

App Groups allow the main app and broadcast extension to share data (server settings).

| Setting | Default Value |
|---------|---------------|
| App Group ID | `group.com.nativebridge.broadcast` |

Both targets must have the **same** App Group identifier.

#### Signing with Free Apple ID

1. Sign into Xcode with your Apple ID
2. Use "Automatically manage signing"
3. Select your Personal Team
4. Change bundle IDs if they conflict with existing apps

#### Signing with Paid Developer Account

1. Use automatic signing, or
2. Create App IDs and provisioning profiles in the Developer Portal
3. Enable App Groups capability in both App IDs

### Common Signing Errors

| Error | Solution |
|-------|----------|
| "No signing certificate" | Sign into Xcode with Apple ID (Settings → Accounts) |
| "Bundle ID unavailable" | Change to a unique bundle ID |
| "App Group not available" | Create a new App Group with unique identifier |
| "Untrusted Developer" | iOS: Settings → General → VPN & Device Management → Trust |
| "Device not registered" | Xcode auto-registers for free accounts; paid accounts add manually |

### Wireless Debugging

Deploy without USB cable:

1. Connect device via USB first
2. Xcode: Window → Devices and Simulators
3. Select device, check "Connect via network"
4. Disconnect USB - device remains available

### Server Configuration

Edit `server/config.py`:

```python
WEBSOCKET_HOST = "0.0.0.0"  # Listen on all interfaces
WEBSOCKET_PORT = 8765       # iOS connects here
HTTP_PORT = 8999            # Browser connects here
```

### iOS App Configuration

Edit `ios-app/BroadcastApp/Shared/Constants.swift`:

```swift
enum Server {
    static let host = "192.168.1.100"  // Your Mac's IP
    static let port = 8765
}

// Update this to match your App Group
static let appGroupIdentifier = "group.com.yourname.broadcast"
```

---

## CLI Build (Simulator Only - Limited Use)

For UI development only (broadcast won't work):

```bash
./scripts/build-ios.sh
```

Options:
```bash
./scripts/build-ios.sh --list              # List simulators
./scripts/build-ios.sh --simulator "iPhone 15 Pro"
./scripts/build-ios.sh --no-launch
./scripts/build-ios.sh --release
```

---

## Project Structure

```
nativebridge-ios-web-streamer/
├── ios-app/                    # iOS application
│   └── BroadcastApp/
│       ├── BroadcastApp/       # Main app (UI)
│       ├── BroadcastExtension/ # Broadcast extension
│       └── Shared/             # Shared code
├── server/                     # Python streaming server
│   ├── main.py                 # Entry point
│   ├── ios_receiver.py         # WebSocket receiver
│   ├── webrtc_server.py        # WebRTC server
│   ├── video_track.py          # Video track handling
│   ├── frame_queue.py          # Frame buffering
│   └── config.py               # Configuration
├── web/                        # Web viewer
│   ├── index.html
│   ├── viewer.js
│   └── style.css
├── scripts/                    # Utility scripts
│   ├── start-server.sh         # Start Python server
│   ├── build-ios.sh            # Build & install iOS app (CLI)
│   ├── install-deps.sh         # Install dependencies
│   └── test-stream.sh          # Test without iOS
└── docs/                       # Documentation
```

## Scripts Reference

| Script | Description |
|--------|-------------|
| `./scripts/install-deps.sh` | Install Python dependencies and verify Xcode |
| `./scripts/start-server.sh` | Start the streaming server |
| `./scripts/build-ios.sh` | Build and install iOS app on simulator |
| `./scripts/test-stream.sh` | Run server in test mode |

### build-ios.sh Options

| Option | Description |
|--------|-------------|
| `-s, --simulator NAME` | Specify simulator by name |
| `-l, --list` | List available simulators |
| `--release` | Build in Release configuration |
| `--no-launch` | Install without launching |
| `-h, --help` | Show help |

## Configuration

### Server

Edit `server/config.py` to change:
- WebSocket port (default: 8765)
- HTTP port (default: 8999)
- Video settings (resolution, bitrate, FPS)

### iOS App

Configure server address in the app UI, or edit `Shared/Constants.swift`.

## Requirements

### macOS
- macOS 12.0+
- Xcode 15.0+ (with command line tools)
- Python 3.10+

### iOS
- iOS 15.0+ (Real device recommended - broadcast extensions don't work in Simulator)

### Browsers
- Chrome, Safari, Firefox, Edge (modern versions)

### For Real Device Deployment
- Apple Developer Account (free Apple ID works)
- USB cable or same Wi-Fi network for wireless debugging

## Network Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 8765 | WebSocket | iOS → Server (localhost only) |
| 8999 | HTTP | Web UI and signaling |
| 10000-10100 | UDP | WebRTC media |

## Troubleshooting

### Simulator Limitation (Important!)

**ReplayKit broadcast extensions do not work in the iOS Simulator.** The broadcast picker button will not show the system dialog in the simulator. To test the full broadcast flow, you must use a **real iOS device**.

To test the server and WebRTC streaming without an iOS device, use test mode:

```bash
./scripts/start-server.sh --test
```

This generates a test video pattern that streams to the browser at http://localhost:8999.

### Real Device Issues

#### iOS device can't connect to server

1. **Check network connectivity:**
   ```bash
   # On Mac, verify IP address
   ipconfig getifaddr en0

   # Make sure iOS device is on same Wi-Fi network
   ```

2. **Verify server is listening on all interfaces:**
   - Server should show `Starting WebSocket server on 0.0.0.0:8765`
   - If it shows `127.0.0.1`, check `server/config.py`

3. **Check firewall:**
   - System Settings → Network → Firewall
   - Allow incoming connections for Python

4. **Test connectivity from iOS:**
   - In Safari on iOS, try `http://<mac-ip>:8999`
   - If this works but broadcast doesn't, check the server host setting in the app

#### Broadcast extension not appearing in picker

1. **Verify both targets have same Team:**
   - BroadcastApp and BroadcastExtension must use identical Team

2. **Check App Group configuration:**
   - Both targets must have the same App Group enabled
   - App Group ID must match in `Constants.swift`

3. **Clean and reinstall:**
   - In Xcode: Product → Clean Build Folder (⇧⌘K)
   - Delete app from device
   - Rebuild and reinstall

#### "Unable to install" or signing errors

1. **Trust the developer certificate on iOS:**
   - Settings → General → VPN & Device Management
   - Tap your certificate → Trust

2. **For "Device not registered" errors (free account):**
   - Xcode should auto-register, but may take a minute
   - Try: Window → Devices and Simulators → right-click device → Add Device to Portal

3. **Bundle ID conflicts:**
   - Change to unique bundle IDs in both targets
   - Make sure extension bundle ID is prefixed with app bundle ID

### Build Issues

#### Build fails with signing error (Simulator)

The CLI build script disables code signing for simulator builds. If you still have issues:

```bash
# Clean build artifacts
rm -rf build/

# Try building again
./scripts/build-ios.sh
```

#### Build fails for real device

1. Open in Xcode and configure signing (see Real iOS Device Setup section)
2. Ensure you've selected your device, not a simulator

### Server Issues

#### Server won't start

1. Check Python version: `python3 --version` (need 3.10+)
2. Install dependencies: `./scripts/install-deps.sh`
3. Check if port is in use: `lsof -i :8765` or `lsof -i :8999`

#### WebSocket connection drops

1. Check server logs for errors
2. Ensure stable Wi-Fi connection
3. Try restarting the server

### Browser/Viewer Issues

#### Browser can't connect

1. Check browser supports WebRTC
2. Try opening http://localhost:8999/health (or http://<mac-ip>:8999/health)
3. Check browser console for errors

#### No video in browser

1. Check server logs for frame reception:
   ```
   iOS client connected
   Received config: ... bytes
   ```
2. Ensure iOS broadcast is active (red status bar on iOS)
3. Try refreshing browser and clicking Connect again
4. Check for decode errors in server logs

#### Video appears distorted or wrong aspect ratio

1. Ensure you're using the latest code (encoder now detects actual screen dimensions)
2. Rebuild and reinstall the iOS app
3. Check server logs for detected resolution

### Broadcast Extension Issues

#### Extension not appearing (Simulator)

This is expected - use a real device or test mode.

#### Extension not appearing (Real Device)

1. Clean and rebuild in Xcode
2. Delete app from device and reinstall
3. Verify App Groups match between targets
4. Check that extension is embedded in the app (Xcode → BroadcastApp target → General → Frameworks, Libraries, and Embedded Content)

## Development

### Running in Test Mode

To test the server without an iOS device:

```bash
./scripts/start-server.sh --test
```

This generates a test video pattern.

### Debug Logging

Enable debug output:

```bash
./scripts/start-server.sh --debug
```

### Verbose iOS Build

For detailed build output:

```bash
xcodebuild -project ios-app/BroadcastApp/BroadcastApp.xcodeproj \
  -scheme BroadcastApp \
  -destination 'platform=iOS Simulator,name=iPhone 15 Pro' \
  build
```

## License

MIT
