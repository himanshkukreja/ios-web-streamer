# Quick Start Guide

This guide provides quick steps to start streaming your iOS device screen with remote control capabilities.

## Prerequisites

- macOS with Xcode 15.0+
- iOS device (iPhone/iPad) with iOS 15.0+
- Node.js 18+ (for server)
- Python 3.8+ with pip

## Installation

```bash
# Clone the repository (if you haven't)
git clone <repository-url>
cd nativebridge-ios-web-streamer

# Install Python dependencies
pip install -r requirements.txt
```

---

## Option A: If WebDriverAgent is Already Installed

If you've already set up WebDriverAgent on your iOS device, follow these steps:

### Step 1: Start Port Forwarding

Open a terminal and run:

```bash
# Get your device UDID first
xcrun xctrace list devices

# Start port forwarding (replace with your UDID)
iproxy 8100 8100 -u YOUR_DEVICE_UDID
```

Keep this terminal open.

### Step 2: Start WDA on Device

You have two options:

**Option A - Via Xcode:**
1. Open the WDA project in Xcode
2. Select `WebDriverAgentRunner` scheme
3. Select your device
4. Press `Cmd+U` to run tests

**Option B - Via Command Line (if previously built):**
```bash
cd WebDriverAgent

xcodebuild test-without-building \
  -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination 'id=YOUR_DEVICE_UDID'
```

### Step 3: Verify WDA is Running

```bash
curl http://localhost:8100/status
```

You should see a JSON response with `"ready": true`.

### Step 4: Start the Streaming Server

```bash
cd server
python main.py
```

### Step 5: Open the Web Viewer

Open your browser and go to: `http://localhost:8999`

---

## Option B: First Time Setup (WDA Not Installed)

### Step 1: Build WebDriverAgent

1. Clone or locate WebDriverAgent:
   ```bash
   git clone https://github.com/appium/WebDriverAgent.git
   cd WebDriverAgent
   ./Scripts/bootstrap.sh
   ```

2. Open in Xcode:
   ```bash
   open WebDriverAgent.xcodeproj
   ```

3. Configure Signing:
   - Select `WebDriverAgentRunner` target
   - Go to "Signing & Capabilities"
   - Enable "Automatically manage signing"
   - Select your Team
   - Change Bundle Identifier to a unique value (e.g., `com.yourname.WebDriverAgentRunner`)

4. Build and Install:
   - Connect your iOS device via USB
   - Select your device in Xcode
   - Select `WebDriverAgentRunner` scheme
   - Press `Cmd+U` to test/install

5. Trust Certificate on Device:
   - Go to Settings > General > VPN & Device Management
   - Find your developer certificate and tap "Trust"

### Step 2: Start Port Forwarding

```bash
# Install libimobiledevice if needed
brew install libimobiledevice

# Start port forwarding
iproxy 8100 8100 -u YOUR_DEVICE_UDID
```

### Step 3: Verify WDA is Running

```bash
curl http://localhost:8100/status
```

### Step 4: Start the Streaming Server

```bash
cd server
python main.py
```

### Step 5: Install iOS App and Start Broadcasting

1. Open the iOS project in Xcode:
   ```bash
   open ios-app/ScreenStreamer.xcodeproj
   ```

2. Build and install on your device
3. Open Control Center on your iOS device
4. Long-press the Screen Recording button
5. Select "ScreenStreamer" and tap "Start Broadcast"

### Step 6: Open the Web Viewer

Open your browser and go to: `http://localhost:8999`

---

## Quick Commands Reference

| Task | Command |
|------|---------|
| List devices | `xcrun xctrace list devices` |
| Start port forward | `iproxy 8100 8100 -u UDID` |
| Check WDA status | `curl http://localhost:8100/status` |
| Start server | `cd server && python main.py` |
| Start server (no control) | `cd server && python main.py --no-control` |
| Start server (debug) | `cd server && python main.py --debug` |

---

## Using Device Controls

Once connected:

1. **Touch Controls**: Click/tap directly on the video to tap on the device
2. **Swipe**: Click and drag on the video to swipe
3. **Volume Up/Down**: Use the buttons on the right side
4. **Home Button**: Press the circular home button
5. **Type Text**: Click the keyboard button and enter text
6. **Lock/Power**: Press the lock button

---

## Troubleshooting

### WDA Connection Failed

```bash
# Check if WDA is running
curl http://localhost:8100/status

# Check if port forwarding is active
lsof -i :8100

# Restart port forwarding
killall iproxy
iproxy 8100 8100 -u YOUR_DEVICE_UDID
```

### Device Not Found

```bash
# List connected devices
xcrun xctrace list devices

# Make sure device is:
# - Connected via USB
# - Unlocked
# - Trusted (tap "Trust" when prompted)
```

### Certificate Not Trusted

On your iOS device:
1. Go to Settings > General > VPN & Device Management
2. Find your developer certificate
3. Tap "Trust"

### Port Already in Use

```bash
# Find and kill process using port 8100
lsof -i :8100
kill -9 <PID>

# Or kill all iproxy processes
killall iproxy
```

---

## Architecture Overview

```
┌─────────────────────┐          ┌─────────────────────┐
│    Web Browser      │          │    iOS Device       │
│                     │          │                     │
│  [Video Display]    │◀─WebRTC──│  [Screen Capture]   │
│  [Touch Controls]   │          │  [Broadcast Ext]    │
│                     │          │                     │
└────────┬────────────┘          └─────────┬───────────┘
         │                                 │
         │ WebSocket                       │ WebSocket
         │ (Controls)                      │ (H264 frames)
         │                                 │
         ▼                                 ▼
┌─────────────────────────────────────────────────────┐
│              Python Streaming Server                 │
│                                                      │
│  [WebRTC Server] ◀── [Frame Queue] ◀── [iOS Recv]   │
│  [Control Server] ──▶ [WDA Client] ──▶ Port 8100    │
│                                                      │
└─────────────────────────────────────────────────────┘
                           │
                           │ HTTP/REST
                           ▼
                ┌─────────────────────┐
                │  WebDriverAgent     │
                │  (on iOS Device)    │
                │  Port 8100          │
                └─────────────────────┘
```

---

## Next Steps

- [Full WDA Setup Guide](wda-setup.md) - Detailed WebDriverAgent setup
- [Troubleshooting Guide](troubleshooting.md) - Common issues and fixes
- [Architecture Overview](architecture.md) - System design details
