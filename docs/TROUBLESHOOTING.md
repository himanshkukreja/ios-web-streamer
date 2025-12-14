# Troubleshooting Guide

Common issues and solutions for the iOS Screen Streaming system.

> **Note:** This system requires a real iOS device. ReplayKit broadcast extensions do NOT work in the iOS Simulator.

## Quick Checklist

Before diving into specific issues, verify these common requirements:

- [ ] Real iOS device (not simulator) with iOS 15.0+
- [ ] Mac and iOS device on same Wi-Fi network
- [ ] Server running and showing "Waiting for iOS..."
- [ ] iOS app configured with correct Mac IP address
- [ ] Both Xcode targets signed with same Team
- [ ] App Groups configured identically on both targets

---

## iOS Device Issues

### Broadcast extension not appearing in picker

**Symptoms:**
- "BroadcastExtension" not shown in broadcast picker
- Only other apps appear (like Screen Recording)

**Solutions:**

1. **Verify code signing:**
   - Both targets (BroadcastApp and BroadcastExtension) must use the **same Team**
   - Check: Xcode → each target → Signing & Capabilities

2. **Check bundle ID relationship:**
   - Extension bundle ID must be prefixed with app bundle ID
   - Correct: `com.yourname.broadcast` and `com.yourname.broadcast.extension`
   - Wrong: `com.yourname.broadcast` and `com.yourname.extension`

3. **Verify App Groups:**
   - Both targets must have App Groups capability
   - Both must use the **same** App Group identifier

4. **Clean and reinstall:**
   ```
   In Xcode:
   1. Product → Clean Build Folder (⇧⌘K)
   2. Delete app from device
   3. Build and run again
   ```

5. **Check extension embedding:**
   - Xcode → BroadcastApp target → General → Frameworks, Libraries, and Embedded Content
   - BroadcastExtension.appex should be listed

### iOS device can't connect to server

**Symptoms:**
- App shows "Connecting..." indefinitely
- Server doesn't show "iOS client connected"

**Solutions:**

1. **Verify network connectivity:**
   ```bash
   # On Mac - get your IP
   ipconfig getifaddr en0

   # Verify iOS device is on same network
   # Check Wi-Fi settings on iOS device
   ```

2. **Test from iOS device:**
   - Open Safari on iOS
   - Navigate to `http://<mac-ip>:8999`
   - If this works, the network is fine

3. **Check server binding:**
   - Server should show: `Starting WebSocket server on 0.0.0.0:8765`
   - If it shows `127.0.0.1`, edit `server/config.py`:
     ```python
     WEBSOCKET_HOST = "0.0.0.0"
     ```

4. **Check Mac firewall:**
   - System Settings → Network → Firewall
   - Allow incoming connections for Python
   - Or disable firewall temporarily to test

5. **Verify iOS app configuration:**
   - Check server host in app matches Mac's IP
   - Check port is 8765

### "Unable to install" or signing errors

**Symptoms:**
- Xcode shows signing errors
- "Unable to install" on device
- "Untrusted Developer" error

**Solutions:**

1. **Trust developer certificate on iOS:**
   - Settings → General → VPN & Device Management
   - Tap your certificate → Trust

2. **"No signing certificate" error:**
   - Xcode → Settings → Accounts
   - Sign in with Apple ID
   - Select your Team in project settings

3. **"Bundle ID unavailable" error:**
   - Change to a unique bundle ID
   - Example: `com.yourname.broadcast` instead of `com.nativebridge.broadcast`

4. **"App Group not available" error:**
   - Create a new App Group with unique identifier
   - Example: `group.com.yourname.broadcast`
   - Update both targets and `Constants.swift`

5. **"Device not registered" (free account):**
   - Xcode should auto-register the device
   - Wait a minute and try again
   - Or: Window → Devices and Simulators → right-click device → Add to Portal

### Broadcast starts but no frames sent

**Symptoms:**
- Broadcast appears to start (countdown finishes)
- Server shows "iOS client connected"
- No "Received frame" messages

**Solutions:**

1. **Check WebSocket URL:**
   - Verify server host and port in iOS app
   - Should be `ws://<mac-ip>:8765`

2. **Look for encoder errors:**
   - In Xcode: View → Debug Area → Activate Console
   - Check for "Encoder error" messages

3. **Restart broadcast:**
   - Stop and start the broadcast again
   - Sometimes the first attempt fails

4. **Check device capabilities:**
   - Ensure device supports H264 hardware encoding
   - All modern iOS devices should support this

### Extension crashes immediately

**Symptoms:**
- Broadcast stops right after starting
- "Broadcast finished" appears immediately

**Solutions:**

1. **Check memory usage:**
   - Extensions have 50MB memory limit
   - Reduce video resolution if needed

2. **View crash logs:**
   - Xcode: Window → Devices and Simulators
   - Select device → View Device Logs
   - Filter by "BroadcastExtension"

3. **Debug the extension:**
   - In Xcode: Debug → Attach to Process → BroadcastExtension
   - Start broadcast and check for crashes

---

## Server Issues

### Server won't start

**Symptoms:**
- `ModuleNotFoundError` or `ImportError`
- Server exits immediately

**Solutions:**

1. **Activate virtual environment:**
   ```bash
   source server/venv/bin/activate
   ```

2. **Reinstall dependencies:**
   ```bash
   ./scripts/install-deps.sh
   # Or manually:
   pip install -r server/requirements.txt
   ```

3. **Check Python version:**
   ```bash
   python3 --version  # Need 3.10+
   ```

### "Address already in use"

**Symptoms:**
- `OSError: [Errno 48] Address already in use`

**Solutions:**

1. **Find and kill the process:**
   ```bash
   # Check what's using the port
   lsof -i :8765
   lsof -i :8999

   # Kill the process
   kill <PID>
   ```

2. **Use different port:**
   ```bash
   ./scripts/start-server.sh --port 9000
   ```

### WebSocket connection drops frequently

**Symptoms:**
- Frequent "iOS client disconnected" messages
- Reconnection loops

**Solutions:**

1. **Check Wi-Fi stability:**
   - Ensure both devices have strong signal
   - Try moving closer to router

2. **Increase timeout:**
   - Edit `server/config.py`:
     ```python
     CONNECTION_TIMEOUT = 30
     ```

3. **Check for network interference:**
   - Disable VPN on either device
   - Try different Wi-Fi network

---

## Browser/Viewer Issues

### WebRTC connection fails

**Symptoms:**
- "Connection failed" in browser
- Stuck on "Connecting..."

**Solutions:**

1. **Check browser supports WebRTC:**
   - Open browser console (F12)
   - Type: `new RTCPeerConnection()`
   - Should not throw an error

2. **Try different browser:**
   - Chrome is recommended
   - Safari and Firefox also work

3. **Disable VPN/proxy:**
   - WebRTC may not work through VPN

4. **Check firewall (UDP ports):**
   - WebRTC needs UDP ports 10000-10100

### Video is black or frozen

**Symptoms:**
- Connection established
- Video element shows but no picture

**Solutions:**

1. **Check server is receiving frames:**
   ```bash
   # Look for these messages in server output:
   # "Received frame: X bytes"
   # "Decoding frame..."
   ```

2. **Verify H264 codec support:**
   - In browser console:
     ```javascript
     RTCRtpReceiver.getCapabilities('video')
     ```
   - Check for H264 in codecs list

3. **Check for decode errors:**
   - Server logs will show decode errors
   - May indicate corrupt frames

4. **Try hardware acceleration:**
   - Chrome: chrome://flags → Hardware-accelerated video decode

### Video appears distorted or wrong aspect ratio

**Symptoms:**
- Video looks stretched or squished
- Aspect ratio doesn't match device

**Solutions:**

1. **Update to latest code:**
   - The encoder now auto-detects device dimensions
   - Rebuild iOS app after updating

2. **Check server logs:**
   - Should show: "Video dimensions: WxH"
   - Dimensions should match device screen

3. **Clear browser cache:**
   - Old viewer code may have hardcoded dimensions

### High latency (>500ms delay)

**Symptoms:**
- Noticeable delay between action and display
- Video feels laggy

**Solutions:**

1. **Reduce video bitrate:**
   - Edit `server/config.py`:
     ```python
     DEFAULT_BITRATE = 1_000_000  # 1 Mbps
     ```

2. **Reduce frame queue:**
   - Edit `server/config.py`:
     ```python
     FRAME_QUEUE_MAX_SIZE = 3
     ```

3. **Check network latency:**
   ```bash
   ping <mac-ip>  # From another device
   ```

4. **Close bandwidth-heavy apps:**
   - Video calls, streaming, downloads

---

## Performance Issues

### High CPU usage on Mac

**Symptoms:**
- Mac fans spinning
- Server using >50% CPU

**Solutions:**

1. **Check viewer count:**
   - Each viewer requires encoding resources
   - Limit concurrent viewers

2. **Reduce video resolution:**
   - Lower resolution = less CPU for encoding

3. **Check for decode errors:**
   - Errors cause re-processing
   - Fix source issues first

### Frame drops / stuttering

**Symptoms:**
- Video stutters or skips
- "Dropped X frames" in logs

**Solutions:**

1. **Increase frame queue:**
   ```python
   FRAME_QUEUE_MAX_SIZE = 10
   ```

2. **Reduce source quality:**
   - Lower bitrate in iOS app
   - Reduce FPS if possible

3. **Check network bandwidth:**
   - 2 Mbps minimum recommended

### Memory usage growing

**Symptoms:**
- Server memory increasing over time
- Eventually crashes

**Solutions:**

1. **Restart server periodically:**
   - Long-running sessions may accumulate memory

2. **Check for connection leaks:**
   - Ensure WebRTC connections are properly closed

3. **Monitor with:**
   ```bash
   top -pid $(pgrep -f "python.*main.py")
   ```

---

## Diagnostic Commands

### Check server health
```bash
curl http://<mac-ip>:8999/health
```

### Get server stats
```bash
curl http://<mac-ip>:8999/stats
```

### Check ports in use
```bash
lsof -i :8765  # WebSocket
lsof -i :8999  # HTTP
```

### Monitor server logs
```bash
./scripts/start-server.sh --debug 2>&1 | tee server.log
```

### Test WebSocket connection
```bash
# Install websocat: brew install websocat
websocat ws://localhost:8765
```

### Check Mac IP address
```bash
ipconfig getifaddr en0    # Wi-Fi
ipconfig getifaddr en1    # Ethernet (if applicable)
```

### View iOS device logs
```bash
# In Xcode: Window → Devices and Simulators → View Device Logs
# Or use Console.app and filter by device
```

---

## Getting Help

If you're still having issues:

1. **Enable debug logging:**
   ```bash
   ./scripts/start-server.sh --debug
   ```

2. **Capture logs from:**
   - Server terminal output
   - Xcode console (iOS app and extension)
   - Browser developer console (F12)

3. **Note your environment:**
   - macOS version: `sw_vers`
   - Xcode version: `xcodebuild -version`
   - Python version: `python3 --version`
   - iOS device model and version
   - Browser and version

4. **Check for common patterns:**
   - Does it work on localhost but not remote?
   - Does test mode (`--test`) work?
   - Is it consistent or intermittent?
