"""
Configuration settings for the iOS Simulator Streaming Server
"""

# WebSocket settings (iOS -> Mac)
# Use 0.0.0.0 to listen on all interfaces (required for physical iOS devices)
WEBSOCKET_HOST = "0.0.0.0"
WEBSOCKET_PORT = 8765

# HTTP/WebRTC settings (Mac -> Browser)
HTTP_HOST = "0.0.0.0"
HTTP_PORT = 8999

# WebRTC settings
ICE_SERVERS = [
    {"urls": "stun:stun.l.google.com:19302"},
    {"urls": "stun:stun1.l.google.com:19302"},
]

# Frame queue settings
FRAME_QUEUE_MAX_SIZE = 10  # Max frames to buffer (drop-oldest policy)

# Video settings
DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
DEFAULT_FPS = 30
DEFAULT_BITRATE = 2_000_000  # 2 Mbps

# Connection settings
CONNECTION_TIMEOUT = 10  # seconds
HEARTBEAT_INTERVAL = 5  # seconds

# WebDriverAgent settings (for device control)
# WDA runs on the iOS device and provides REST API for touch/gesture control
#
# For USB connection (requires iproxy):
#   WDA_HOST = "localhost"
#   WDA_PORT = 8100
#
# For WiFi connection (no USB needed):
#   WDA_HOST = "YOUR_DEVICE_IP"  # e.g., "192.168.1.100"
#   WDA_PORT = 8100
#
# You can find your device IP in Settings > Wi-Fi > (i) icon
WDA_HOST = "localhost"  # Change to device IP for wireless
WDA_PORT = 8100

# Message types (must match iOS)
MSG_TYPE_VIDEO_FRAME = 0x01
MSG_TYPE_CONFIG = 0x02
MSG_TYPE_HEARTBEAT = 0x03
MSG_TYPE_STATS = 0x04
MSG_TYPE_DEVICE_INFO = 0x05
MSG_TYPE_END_STREAM = 0xFF
