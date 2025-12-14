"""
WebSocket server to receive H264 frames from iOS Broadcast Extension.
"""

import asyncio
import logging
import struct
from typing import Optional, Callable

import websockets
from websockets.server import WebSocketServerProtocol

from config import (
    WEBSOCKET_HOST,
    WEBSOCKET_PORT,
    MSG_TYPE_VIDEO_FRAME,
    MSG_TYPE_CONFIG,
    MSG_TYPE_HEARTBEAT,
    MSG_TYPE_STATS,
    MSG_TYPE_DEVICE_INFO,
    MSG_TYPE_END_STREAM,
)
from frame_queue import FrameQueue, VideoFrame

logger = logging.getLogger(__name__)


class iOSReceiver:
    """
    WebSocket server that receives H264 encoded video frames from iOS.

    Message Protocol:
    - Byte 0: Message type (uint8)
    - Bytes 1-8: Timestamp in microseconds (uint64, big-endian)
    - Bytes 9+: Payload (variable length)
    """

    def __init__(self, frame_queue: FrameQueue):
        self.frame_queue = frame_queue
        self.connected = False
        self.websocket: Optional[WebSocketServerProtocol] = None
        self.on_connect_callback: Optional[Callable] = None
        self.on_disconnect_callback: Optional[Callable] = None

        # Stream state
        self.sps_pps: Optional[bytes] = None
        self.frame_count = 0
        self.start_time: Optional[float] = None

        # Device information
        self.device_info: Optional[dict] = None

    async def start(self, host: str = WEBSOCKET_HOST, port: int = WEBSOCKET_PORT):
        """Start the WebSocket server."""
        logger.info(f"Starting iOS receiver on ws://{host}:{port}")

        async with websockets.serve(
            self.handle_connection,
            host,
            port,
            max_size=1024 * 1024,  # 1MB max message size
            ping_interval=20,
            ping_timeout=10,
        ):
            logger.info(f"iOS receiver listening on ws://{host}:{port}")
            await asyncio.Future()  # Run forever

    async def handle_connection(self, websocket: WebSocketServerProtocol):
        """Handle a new iOS connection."""
        self.websocket = websocket
        self.connected = True
        self.frame_count = 0
        self.start_time = asyncio.get_event_loop().time()

        client_info = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"iOS app connected from {client_info}")

        if self.on_connect_callback:
            await self.on_connect_callback()

        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    await self.process_message(message)
                else:
                    logger.warning(f"Received non-binary message: {message}")
        except websockets.ConnectionClosed as e:
            logger.info(f"iOS connection closed: {e.code} - {e.reason}")
        except Exception as e:
            logger.error(f"Error handling iOS connection: {e}")
        finally:
            self.connected = False
            self.websocket = None

            if self.on_disconnect_callback:
                await self.on_disconnect_callback()

            logger.info("iOS app disconnected")

    async def process_message(self, data: bytes):
        """Process a binary message from iOS."""
        if len(data) < 9:
            logger.warning(f"Message too short: {len(data)} bytes")
            return

        # Parse header
        msg_type = data[0]
        timestamp = struct.unpack('>Q', data[1:9])[0]
        payload = data[9:]

        if msg_type == MSG_TYPE_CONFIG:
            await self._handle_config(timestamp, payload)
        elif msg_type == MSG_TYPE_VIDEO_FRAME:
            await self._handle_video_frame(timestamp, payload)
        elif msg_type == MSG_TYPE_HEARTBEAT:
            await self._handle_heartbeat()
        elif msg_type == MSG_TYPE_STATS:
            await self._handle_stats(payload)
        elif msg_type == MSG_TYPE_DEVICE_INFO:
            await self._handle_device_info(payload)
        elif msg_type == MSG_TYPE_END_STREAM:
            await self._handle_end_stream()
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_config(self, timestamp: int, payload: bytes):
        """Handle decoder configuration (SPS/PPS)."""
        self.sps_pps = payload

        # Log the SPS/PPS data for debugging
        hex_preview = payload[:40].hex() if len(payload) >= 40 else payload.hex()
        logger.info(f"Received decoder config: {len(payload)} bytes")
        logger.info(f"SPS/PPS data: {hex_preview}")

        # Parse and log NAL unit types in the config
        self._log_nal_units(payload, "Config")

        # Note: We don't put config as a frame - it's just parameter sets
        # The actual keyframe will come separately and we'll attach sps_pps to it

    async def _handle_video_frame(self, timestamp: int, payload: bytes):
        """Handle an H264 video frame."""
        self.frame_count += 1

        # Check if this is a keyframe (IDR)
        is_keyframe = self._is_keyframe(payload)

        # Log details for first 5 frames
        if self.frame_count <= 5:
            hex_preview = payload[:30].hex() if len(payload) >= 30 else payload.hex()
            logger.info(f"Frame {self.frame_count}: keyframe={is_keyframe}, "
                       f"size={len(payload)}, ts={timestamp}")
            logger.info(f"  Data preview: {hex_preview}")
            self._log_nal_units(payload, f"  Frame {self.frame_count}")

        frame = VideoFrame(
            timestamp=timestamp,
            data=payload,
            is_keyframe=is_keyframe,
            sps_pps=self.sps_pps if is_keyframe else None,
        )

        await self.frame_queue.put(frame)

        # Log periodic stats (every 30 frames = ~1 second at 30fps)
        if self.frame_count % 30 == 0:
            elapsed = asyncio.get_event_loop().time() - self.start_time
            fps = self.frame_count / elapsed if elapsed > 0 else 0
            queue_stats = self.frame_queue.get_stats()
            logger.info(f"Video: {self.frame_count} frames, {fps:.1f} fps, "
                        f"queue: {queue_stats['queue_size']}/{queue_stats['max_size']}, "
                        f"keyframes: {queue_stats['keyframes']}")

    async def _handle_heartbeat(self):
        """Handle heartbeat message."""
        if self.websocket:
            # Send heartbeat response
            response = struct.pack('>B', MSG_TYPE_HEARTBEAT) + struct.pack('>Q', 0)
            await self.websocket.send(response)

    async def _handle_stats(self, payload: bytes):
        """Handle stats message from iOS."""
        try:
            import json
            stats = json.loads(payload.decode('utf-8'))
            logger.info(f"iOS stats: {stats}")
        except Exception as e:
            logger.warning(f"Failed to parse stats: {e}")

    async def _handle_device_info(self, payload: bytes):
        """Handle device info message from iOS."""
        try:
            import json
            self.device_info = json.loads(payload.decode('utf-8'))
            logger.info(f"📱 Device Info Received:")
            logger.info(f"  Device: {self.device_info.get('deviceName', 'Unknown')}")
            logger.info(f"  Model: {self.device_info.get('deviceModel', 'Unknown')}")
            logger.info(f"  System: {self.device_info.get('systemName', 'Unknown')} {self.device_info.get('systemVersion', 'Unknown')}")
            logger.info(f"  Resolution: {self.device_info.get('screenResolution', 'Unknown')} @ {self.device_info.get('screenScale', 'Unknown')}")
            logger.info(f"  Battery: {self.device_info.get('batteryLevel', -1)}% ({self.device_info.get('batteryState', 'unknown')})")
        except Exception as e:
            logger.warning(f"Failed to parse device info: {e}")

    async def _handle_end_stream(self):
        """Handle end of stream message."""
        logger.info("iOS broadcast ended")
        self.frame_queue.clear()

    def _get_nal_type_name(self, nal_type: int) -> str:
        """Get human-readable NAL type name."""
        nal_types = {
            1: "non-IDR",
            5: "IDR",
            6: "SEI",
            7: "SPS",
            8: "PPS",
            9: "AUD",
        }
        return nal_types.get(nal_type, f"type-{nal_type}")

    def _log_nal_units(self, data: bytes, prefix: str = ""):
        """Log NAL units found in the data."""
        nal_units = []
        i = 0
        while i < len(data) - 4:
            if data[i:i+4] == b'\x00\x00\x00\x01':
                nal_type = data[i+4] & 0x1F
                nal_units.append(self._get_nal_type_name(nal_type))
                i += 4
            elif data[i:i+3] == b'\x00\x00\x01':
                nal_type = data[i+3] & 0x1F
                nal_units.append(self._get_nal_type_name(nal_type))
                i += 3
            else:
                i += 1

        if nal_units:
            logger.info(f"{prefix} NAL units: {', '.join(nal_units)}")

    def _is_keyframe(self, nal_data: bytes) -> bool:
        """
        Check if NAL unit is a keyframe (IDR).

        NAL unit type is in the lower 5 bits of the NAL header byte.
        Type 5 = IDR slice (keyframe)
        Type 7 = SPS
        Type 8 = PPS
        """
        if len(nal_data) < 5:
            return False

        # Find start code and get NAL type
        i = 0
        while i < len(nal_data) - 4:
            # Look for start code (0x00000001 or 0x000001)
            if nal_data[i:i+4] == b'\x00\x00\x00\x01':
                nal_type = nal_data[i+4] & 0x1F
                if nal_type == 5 or nal_type == 7 or nal_type == 8:
                    return True
                i += 4
            elif nal_data[i:i+3] == b'\x00\x00\x01':
                nal_type = nal_data[i+3] & 0x1F
                if nal_type == 5 or nal_type == 7 or nal_type == 8:
                    return True
                i += 3
            else:
                i += 1

        return False

    def is_connected(self) -> bool:
        """Check if iOS is currently connected."""
        return self.connected

    def get_stats(self) -> dict:
        """Get receiver statistics."""
        return {
            'connected': self.connected,
            'frame_count': self.frame_count,
            'has_config': self.sps_pps is not None,
            'queue_stats': self.frame_queue.get_stats(),
        }
