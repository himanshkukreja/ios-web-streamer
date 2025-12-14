# Using WebDriverAgent Wirelessly (No USB Required)

This guide shows you how to use device controls over WiFi instead of USB.

## Prerequisites

- iOS device and Mac must be on the **same WiFi network**
- WebDriverAgent must be running on your iOS device
- You need to know your iOS device's IP address

## Step 1: Find Your Device IP Address

On your iOS device:
1. Go to **Settings** → **Wi-Fi**
2. Tap the **(i)** icon next to your connected network
3. Note the **IP Address** (e.g., `192.168.1.100`)

## Step 2: Start the Server with WiFi Control

### Option A: Using the start script (Recommended)

```bash
./scripts/start-server.sh --wda-host 192.168.1.100
```

Replace `192.168.1.100` with your device's actual IP address.

### Option B: Direct Python command

```bash
cd server
python3 main.py --wda-host 192.168.1.100
```

### Option C: Edit config.py (Permanent)

Edit `server/config.py`:

```python
# Change from:
WDA_HOST = "localhost"

# To your device IP:
WDA_HOST = "192.168.1.100"
```

Then start normally:
```bash
./scripts/start-server.sh
```

## Step 3: Verify Connection

When the server starts, you should see:

```
Control server initialized (WDA: 192.168.1.100:8100)
```

In the web viewer, the control status should show **"Controls Active"** in green.

## Comparison: USB vs WiFi

| Method | Pros | Cons |
|--------|------|------|
| **USB** (`localhost`) | - More stable<br>- Lower latency<br>- No network issues | - Requires USB cable<br>- Requires `iproxy` setup<br>- Device must stay connected |
| **WiFi** (device IP) | - No USB cable needed<br>- Device can move freely<br>- Easier setup | - Depends on WiFi quality<br>- Slightly higher latency<br>- IP may change |

## Troubleshooting

### Control status shows "WDA Not Connected"

**Solution**: Make sure WebDriverAgent is running on your device and accessible:

```bash
# Test WDA connection (replace with your device IP)
curl http://192.168.1.100:8100/status
```

You should see a JSON response with device information.

### "Connection refused" error

**Possible causes**:
1. **WDA not running** - Start WebDriverAgent in Xcode (Cmd+U)
2. **Wrong IP** - Verify device IP in Settings → Wi-Fi
3. **Different network** - Ensure device and Mac are on the same WiFi
4. **Firewall** - Check if iOS firewall is blocking port 8100

### Device IP keeps changing

**Solution**: Set a static IP for your device in your router settings, or use the command-line option each time.

## Example: Full Wireless Setup

```bash
# 1. Find device IP (Settings → Wi-Fi → IP Address)
# Example: 192.168.1.100

# 2. Start WDA on device (Xcode → WebDriverAgent → Cmd+U)

# 3. Test WDA connection
curl http://192.168.1.100:8100/status

# 4. Start server with WiFi control
./scripts/start-server.sh --wda-host 192.168.1.100

# 5. Start iOS broadcast extension

# 6. Open browser: http://localhost:8999
```

## Advanced: Auto-detect Device IP

You can use mDNS/Bonjour to auto-discover devices on your network:

```bash
# Find iOS devices on network
dns-sd -B _apple-mobdev2._tcp

# Or use this one-liner to get the first iOS device IP:
arp -a | grep -i "iphone\|ipad" | awk '{print $2}' | tr -d '()'
```

Then use the IP with `--wda-host`.
