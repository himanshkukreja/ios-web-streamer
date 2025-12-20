# iOS Simulator Streaming - Quick Start Guide

Get iOS Simulator streaming to your browser in **5 minutes**!

## Prerequisites

✅ macOS 13+ with Xcode installed
✅ Python 3.11+
✅ Homebrew installed

## Installation (One-time)

```bash
# 1. Install idb
brew tap facebook/fb
brew install idb-companion

# 2. Install Python dependencies
pip3 install fb-idb aiortc av numpy grpclib
```

## Usage

### Step 1: Boot a Simulator

```bash
# See available simulators
xcrun simctl list devices available | grep iPhone

# Boot one (example)
xcrun simctl boot "iPhone 16 Pro"
```

### Step 2: Start Streaming Server

```bash
cd server
python3 simulator_webrtc_server.py
```

You'll see:
```
======================================================================
✅ Server running at: http://localhost:8999
======================================================================

Open the URL above in your browser to view the simulator stream
```

### Step 3: Open Browser

```bash
open http://localhost:8999
```

Or manually visit: **http://localhost:8999**

## What You'll See

- ✅ Simulator screen streaming in real-time
- ✅ ~50-80ms latency
- ✅ 30 fps smooth video
- ✅ Native resolution (e.g., 1206x2622 for iPhone 16 Pro)

## Stopping the Server

Press `Ctrl+C` in the terminal running the server.

## Troubleshooting

### "No booted simulator found"

```bash
# Boot a simulator first
xcrun simctl boot <UDID or Name>
```

### "Port 8999 already in use"

```bash
# Kill existing process
lsof -ti:8999 | xargs kill -9

# Then restart
python3 simulator_webrtc_server.py
```

### "idb_companion not found"

```bash
# Install idb
brew tap facebook/fb
brew install idb-companion
```

## Advanced Usage

### Multiple Viewers

Just open http://localhost:8999 in multiple browser tabs/windows. All viewers see the same stream with minimal overhead.

### Different Simulator

```bash
# Kill current server (Ctrl+C)

# Boot different simulator
xcrun simctl shutdown all
xcrun simctl boot "iPhone 15"

# Restart server (auto-detects new simulator)
python3 simulator_webrtc_server.py
```

### Headless Mode

The simulator doesn't need to be visible! It works even if Simulator.app is closed:

```bash
# Boot simulator (no UI needed)
xcrun simctl boot <UDID>

# Stream works immediately
python3 simulator_webrtc_server.py
```

## Performance Tips

- **Lower latency**: Set `compression_quality=0.6` in code
- **Higher quality**: Set `compression_quality=0.9` in code
- **Different FPS**: Change `fps=30` to `fps=60` for smoother video

## Next Steps

- 📖 Read full documentation: [docs/IDB_SIMULATOR_STREAMING.md](docs/IDB_SIMULATOR_STREAMING.md)
- 🔧 Integrate with existing server
- 🚀 Deploy for CI/CD testing
- 📱 Stream multiple simulators

## Support

For issues or questions:
- Check logs in terminal
- See full docs: [IDB_SIMULATOR_STREAMING.md](docs/IDB_SIMULATOR_STREAMING.md)

---

**Status**: ✅ Working
**Latency**: ~50-80ms
**FPS**: 30
**Quality**: High
