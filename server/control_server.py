"""
Control Server for handling remote control commands from browser.

Receives touch/gesture commands via WebSocket and forwards them to
WebDriverAgent for execution on the iOS device.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, Set
from dataclasses import dataclass

from aiohttp import web, WSMsgType

from wda_client import WDAClient, WDAConnectionManager

logger = logging.getLogger(__name__)


@dataclass
class ControlCommand:
    """Represents a control command from the browser."""
    type: str  # tap, swipe, longpress, home, volumeUp, volumeDown, type, etc.
    x: Optional[int] = None
    y: Optional[int] = None
    end_x: Optional[int] = None
    end_y: Optional[int] = None
    duration: Optional[int] = None
    text: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ControlCommand":
        return cls(
            type=data.get("type", ""),
            x=data.get("x"),
            y=data.get("y"),
            end_x=data.get("endX"),
            end_y=data.get("endY"),
            duration=data.get("duration"),
            text=data.get("text"),
        )


class ControlServer:
    """
    WebSocket server for receiving control commands from browsers
    and executing them via WebDriverAgent.
    """

    def __init__(self, wda_host: str = "localhost", wda_port: int = 8100):
        """
        Initialize the control server.

        Args:
            wda_host: WebDriverAgent host
            wda_port: WebDriverAgent port
        """
        self.wda_manager = WDAConnectionManager(wda_host, wda_port)
        self._control_clients: Set[web.WebSocketResponse] = set()

        # Video dimensions for coordinate translation
        self._video_width: int = 0
        self._video_height: int = 0

    @property
    def wda_client(self) -> WDAClient:
        return self.wda_manager.client

    async def start(self):
        """Start the control server (connect to WDA)."""
        logger.info("Starting control server...")
        connected = await self.wda_manager.start()
        if connected:
            logger.info("Control server connected to WDA")
        else:
            logger.warning("Control server: WDA not available, controls disabled")
        return connected

    async def stop(self):
        """Stop the control server."""
        logger.info("Stopping control server...")

        # Close all WebSocket connections
        for ws in list(self._control_clients):
            await ws.close()
        self._control_clients.clear()

        await self.wda_manager.stop()

    def set_video_dimensions(self, width: int, height: int):
        """
        Set the video dimensions for coordinate translation.

        Args:
            width: Video width in pixels
            height: Video height in pixels
        """
        self._video_width = width
        self._video_height = height
        logger.debug(f"Video dimensions set: {width}x{height}")

    def translate_coordinates(self, x: int, y: int, video_width: int, video_height: int) -> tuple[int, int]:
        """
        Translate coordinates from video space to device screen space.

        Args:
            x, y: Coordinates in video/browser space
            video_width, video_height: Current video display dimensions

        Returns:
            Tuple of (device_x, device_y)
        """
        device_width = self.wda_client.screen_width
        device_height = self.wda_client.screen_height

        if device_width == 0 or device_height == 0:
            # Fallback to video dimensions if WDA dimensions not available
            return (x, y)

        if video_width == 0 or video_height == 0:
            return (x, y)

        # Calculate scale factors
        scale_x = device_width / video_width
        scale_y = device_height / video_height

        device_x = int(x * scale_x)
        device_y = int(y * scale_y)

        logger.debug(f"Coordinate translation: ({x}, {y}) @ {video_width}x{video_height} -> "
                    f"({device_x}, {device_y}) @ {device_width}x{device_height}")

        return (device_x, device_y)

    async def handle_control_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """
        Handle WebSocket connection for control commands.

        Expected message format:
        {
            "type": "tap" | "swipe" | "longpress" | "doubletap" | "home" | "volumeUp" | "volumeDown" | "type" | "scroll",
            "x": number,          // For tap, swipe start, longpress
            "y": number,
            "endX": number,       // For swipe end
            "endY": number,
            "duration": number,   // For longpress, swipe duration
            "text": string,       // For type command
            "videoWidth": number, // Current video display width
            "videoHeight": number // Current video display height
        }
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._control_clients.add(ws)
        logger.info(f"Control client connected (total: {len(self._control_clients)})")

        # Send initial status
        await self._send_status(ws)

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_command(ws, data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON received: {msg.data[:100]}")
                        await ws.send_json({"error": "Invalid JSON"})
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
                    break
        finally:
            self._control_clients.discard(ws)
            logger.info(f"Control client disconnected (remaining: {len(self._control_clients)})")

        return ws

    async def _send_status(self, ws: web.WebSocketResponse):
        """Send current WDA status to client."""
        status = {
            "type": "status",
            "wdaConnected": self.wda_client.is_connected,
            "screenWidth": self.wda_client.screen_width,
            "screenHeight": self.wda_client.screen_height,
        }

        if self.wda_client.is_connected:
            device_info = await self.wda_client.get_device_info()
            if device_info:
                status["deviceInfo"] = device_info

        await ws.send_json(status)

    async def _handle_command(self, ws: web.WebSocketResponse, data: Dict[str, Any]):
        """Handle a control command from the browser."""
        cmd_type = data.get("type", "")

        if not self.wda_client.is_connected:
            await ws.send_json({
                "type": "error",
                "error": "WDA not connected",
                "command": cmd_type
            })
            return

        # Get video dimensions for coordinate translation
        video_width = data.get("videoWidth", self._video_width)
        video_height = data.get("videoHeight", self._video_height)

        success = False
        error_msg = None

        try:
            if cmd_type == "tap":
                x, y = self.translate_coordinates(
                    data.get("x", 0), data.get("y", 0),
                    video_width, video_height
                )
                success = await self.wda_client.tap(x, y)

            elif cmd_type == "doubletap":
                x, y = self.translate_coordinates(
                    data.get("x", 0), data.get("y", 0),
                    video_width, video_height
                )
                success = await self.wda_client.double_tap(x, y)

            elif cmd_type == "longpress":
                x, y = self.translate_coordinates(
                    data.get("x", 0), data.get("y", 0),
                    video_width, video_height
                )
                duration = data.get("duration", 1000)
                success = await self.wda_client.long_press(x, y, duration)

            elif cmd_type == "swipe":
                start_x, start_y = self.translate_coordinates(
                    data.get("x", 0), data.get("y", 0),
                    video_width, video_height
                )
                end_x, end_y = self.translate_coordinates(
                    data.get("endX", 0), data.get("endY", 0),
                    video_width, video_height
                )
                duration = data.get("duration", 300)
                success = await self.wda_client.swipe(start_x, start_y, end_x, end_y, duration)

            elif cmd_type == "scroll":
                x, y = self.translate_coordinates(
                    data.get("x", 0), data.get("y", 0),
                    video_width, video_height
                )
                delta_x = data.get("deltaX", 0)
                delta_y = data.get("deltaY", 0)
                # Scale deltas as well
                scale = self.wda_client.screen_width / video_width if video_width > 0 else 1
                delta_x = int(delta_x * scale)
                delta_y = int(delta_y * scale)
                success = await self.wda_client.scroll(x, y, delta_x, delta_y)

            elif cmd_type == "home":
                success = await self.wda_client.press_home()

            elif cmd_type == "lock":
                success = await self.wda_client.press_lock()

            elif cmd_type == "unlock":
                success = await self.wda_client.unlock()

            elif cmd_type == "volumeUp":
                success = await self.wda_client.press_volume_up()

            elif cmd_type == "volumeDown":
                success = await self.wda_client.press_volume_down()

            elif cmd_type == "type":
                text = data.get("text", "")
                if text:
                    success = await self.wda_client.type_text(text)
                else:
                    error_msg = "No text provided"

            elif cmd_type == "launchApp":
                bundle_id = data.get("bundleId", "")
                if bundle_id:
                    success = await self.wda_client.launch_app(bundle_id)
                else:
                    error_msg = "No bundleId provided"

            elif cmd_type == "getStatus":
                await self._send_status(ws)
                return

            else:
                error_msg = f"Unknown command type: {cmd_type}"

        except Exception as e:
            logger.exception(f"Error executing command {cmd_type}")
            error_msg = str(e)

        # Send response
        if error_msg:
            await ws.send_json({
                "type": "error",
                "error": error_msg,
                "command": cmd_type
            })
        else:
            await ws.send_json({
                "type": "result",
                "success": success,
                "command": cmd_type
            })

    async def broadcast_status(self):
        """Broadcast WDA status to all connected control clients."""
        if not self._control_clients:
            return

        status = {
            "type": "status",
            "wdaConnected": self.wda_client.is_connected,
            "screenWidth": self.wda_client.screen_width,
            "screenHeight": self.wda_client.screen_height,
        }

        for ws in list(self._control_clients):
            try:
                await ws.send_json(status)
            except Exception:
                pass


# Global instance for easy access
_control_server: Optional[ControlServer] = None


def get_control_server() -> Optional[ControlServer]:
    """Get the global control server instance."""
    return _control_server


def set_control_server(server: ControlServer):
    """Set the global control server instance."""
    global _control_server
    _control_server = server
