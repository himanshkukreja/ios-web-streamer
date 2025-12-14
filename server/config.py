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
# Use localhost if using iproxy to forward from device, or device IP if direct
WDA_HOST = "localhost"
WDA_PORT = 8100

# Message types (must match iOS)
MSG_TYPE_VIDEO_FRAME = 0x01
MSG_TYPE_CONFIG = 0x02
MSG_TYPE_HEARTBEAT = 0x03
MSG_TYPE_STATS = 0x04
MSG_TYPE_END_STREAM = 0xFF
