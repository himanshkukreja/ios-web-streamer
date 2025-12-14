# Troubleshooting Guide

Common issues and solutions for the iOS Simulator Screen Streaming system.

## Server Issues

### Server won't start

**Symptoms:**
- `ModuleNotFoundError` or `ImportError`
- Server exits immediately

**Solutions:**

1. Ensure virtual environment is activated:
   ```bash
   source server/venv/bin/activate
   ```

2. Reinstall dependencies:
   ```bash
   pip install -r server/requirements.txt
   ```

3. Check Python version (need 3.10+):
   ```bash
   python3 --version
   ```

### "Address already in use"

**Symptoms:**
- `OSError: [Errno 48] Address already in use`

**Solutions:**

1. Find and kill the process using the port:
   ```bash
   lsof -i :8080
   kill <PID>
   ```

2. Use a different port:
   ```bash
   ./scripts/start-server.sh --port 8081
   ```

### WebSocket connection drops

**Symptoms:**
- Frequent "iOS app disconnected" messages
- Reconnection loops

**Solutions:**

1. Check for network issues
2. Increase timeout in `config.py`:
   ```python
   CONNECTION_TIMEOUT = 30
   ```

## iOS Issues

### Broadcast extension not appearing

**Symptoms:**
- "Screen Streamer" not in broadcast picker
- Only other apps shown

**Solutions:**

1. Clean and rebuild:
   - Product → Clean Build Folder (⇧⌘K)
   - Build again (⌘B)

2. Delete app from simulator:
   - In Simulator: long-press app → Remove App
   - Reinstall

3. Check bundle identifiers:
   - Extension must be prefix of app (e.g., `com.app.extension`)

4. Verify code signing:
   - Both targets need same team
   - Both need valid provisioning

### Broadcast starts but no frames sent

**Symptoms:**
- Server shows "iOS app connected"
- No "Frame received" messages

**Solutions:**

1. Check WebSocket URL in app settings
2. Look for encoder errors in Xcode console
3. Try restarting the simulator

### Extension crashes

**Symptoms:**
- Broadcast stops immediately
- "Broadcast finished" right after start

**Solutions:**

1. Check memory usage (50MB limit for extensions)
2. Look for crash logs:
   - Window → Devices and Simulators → View Device Logs

3. Enable debugging for extension:
   - Debug → Attach to Process → BroadcastExtension

### "Screen Recording" permission denied

**Symptoms:**
- ReplayKit permission dialog not appearing
- Immediate broadcast failure

**Solutions:**

1. Reset simulator:
   - Device → Erase All Content and Settings

2. Check Info.plist has required keys

## Browser Issues

### WebRTC connection fails

**Symptoms:**
- "Connection failed" in browser
- No video displayed

**Solutions:**

1. Check browser supports WebRTC:
   - Try: `new RTCPeerConnection()` in console

2. Disable VPN or proxy

3. Check firewall allows UDP (ports 10000-10100)

4. Try different browser (Chrome recommended)

### Video is black or frozen

**Symptoms:**
- Connection established but no video
- Intermittent freezing

**Solutions:**

1. Check server is receiving frames
2. Verify H264 codec support:
   ```javascript
   RTCRtpReceiver.getCapabilities('video')
   ```

3. Try hardware acceleration settings in browser

### High latency

**Symptoms:**
- Visible delay (>500ms)
- Video feels laggy

**Solutions:**

1. Close bandwidth-heavy applications

2. Reduce video quality in `config.py`:
   ```python
   DEFAULT_BITRATE = 1_000_000  # 1 Mbps
   ```

3. Check network latency:
   ```bash
   ping localhost
   ```

4. Reduce frame queue size (may cause more drops):
   ```python
   FRAME_QUEUE_MAX_SIZE = 2
   ```

## Performance Issues

### High CPU usage

**Symptoms:**
- Mac fans spinning
- Server using >50% CPU

**Solutions:**

1. Check number of connected viewers
2. Reduce video resolution
3. Enable hardware decoding (should be default)

### Frame drops

**Symptoms:**
- Stuttering video
- "Dropped X frames" in logs

**Solutions:**

1. Reduce source frame rate
2. Increase frame queue size:
   ```python
   FRAME_QUEUE_MAX_SIZE = 5
   ```
3. Lower bitrate for faster encoding

### Memory usage growing

**Symptoms:**
- Server memory increasing over time
- Eventually crashes

**Solutions:**

1. Check for memory leaks with profiler
2. Restart server periodically
3. Limit number of concurrent connections

## Diagnostic Commands

### Check server health
```bash
curl http://localhost:8080/health
```

### Get server stats
```bash
curl http://localhost:8080/stats
```

### Check ports in use
```bash
lsof -i :8765
lsof -i :8080
```

### Monitor server logs
```bash
./scripts/start-server.sh --debug 2>&1 | tee server.log
```

### Test WebSocket connection
```bash
# Using websocat (brew install websocat)
websocat ws://localhost:8765
```

## Getting Help

If you're still having issues:

1. Enable debug logging:
   ```bash
   ./scripts/start-server.sh --debug
   ```

2. Capture logs from:
   - Server terminal output
   - Xcode console (iOS app and extension)
   - Browser developer console

3. Note your environment:
   - macOS version
   - Xcode version
   - Python version
   - Browser and version
   - Simulator device type
