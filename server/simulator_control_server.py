"""
Simulator Control Server - handles device control for iOS Simulator via idb.

Uses idb (Facebook's iOS Development Bridge) subprocess commands:
- Touch/tap events via idb ui tap
- Swipe gestures via idb ui swipe
- Button presses (home, lock) via idb ui button
- Text input via idb ui text

Works in headless mode - no window interaction needed.
Coordinates are in simulator screen space (not video space).
"""

import asyncio
import logging
import shutil
from typing import Set, Optional, Tuple
from aiohttp import web

logger = logging.getLogger(__name__)

# Find idb and idb_companion paths
IDB_PATH = shutil.which('idb') or '/Library/Frameworks/Python.framework/Versions/3.11/bin/idb'
IDB_COMPANION_PATH = shutil.which('idb_companion') or '/opt/homebrew/bin/idb_companion'


class SimulatorControlServer:
    """
    Control server for iOS Simulator using idb subprocess commands.

    Uses idb CLI for:
    - Touch/tap: idb ui tap x y
    - Swipe: idb ui swipe x1 y1 x2 y2
    - Buttons: idb ui button HOME/LOCK/SIRI
    - Text input: idb ui text "text"

    Coordinates are in simulator's native resolution.
    The server scales video coordinates to screen coordinates.
    """

    def __init__(self, simulator_udid: str):
        self.simulator_udid = simulator_udid
        self.websockets: Set[web.WebSocketResponse] = set()
        self.screen_width = 0  # Pixel width
        self.screen_height = 0  # Pixel height
        self.scale_factor = 3  # Retina scale (3x for Pro devices, 2x for SE)
        self._running = False
        self._idb_available = False

    async def start(self):
        """Start the control server and verify idb availability."""
        self._running = True

        # Check if idb is available
        try:
            proc = await asyncio.create_subprocess_exec(
                IDB_PATH, '--help',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            self._idb_available = proc.returncode == 0
        except FileNotFoundError:
            self._idb_available = False

        if self._idb_available:
            logger.info(f"idb available at: {IDB_PATH}")
            logger.info(f"idb_companion at: {IDB_COMPANION_PATH}")
        else:
            logger.warning("idb not available - controls will not work")
            logger.warning("Install with: pip install fb-idb && brew tap facebook/fb && brew install idb-companion")

        logger.info(f"Simulator control server started for {self.simulator_udid}")

    async def stop(self):
        """Stop the control server."""
        self._running = False

        # Close all websockets
        for ws in list(self.websockets):
            await ws.close()
        self.websockets.clear()
        logger.info("Simulator control server stopped")

    def set_screen_size(self, width: int, height: int, scale_factor: int = 3):
        """Set the screen size for coordinate scaling.

        Args:
            width: Screen width in pixels
            height: Screen height in pixels
            scale_factor: Retina scale factor (3 for Pro devices, 2 for SE)
        """
        self.screen_width = width
        self.screen_height = height
        self.scale_factor = scale_factor
        logger.info(f"Screen size set to {width}x{height} pixels (scale: {scale_factor}x, points: {width//scale_factor}x{height//scale_factor})")

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connection for control commands."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.websockets.add(ws)

        logger.info(f"Control WebSocket connected, total: {len(self.websockets)}")

        # Send initial status
        await ws.send_json({
            "type": "status",
            "wdaConnected": self._idb_available,
            "deviceType": "simulator",
            "deviceInfo": {
                "udid": self.simulator_udid,
                "screenWidth": self.screen_width,
                "screenHeight": self.screen_height,
                "controlMethod": "idb"
            }
        })

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        import json
                        data = json.loads(msg.data)
                        result = await self.handle_command(data)
                        await ws.send_json({
                            "type": "result",
                            "command": data.get("type"),
                            "success": result
                        })
                    except Exception as e:
                        logger.error(f"Error handling control command: {e}")
                        await ws.send_json({
                            "type": "error",
                            "error": str(e),
                            "command": data.get("type") if 'data' in dir() else None
                        })
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
        finally:
            self.websockets.discard(ws)
            logger.info(f"Control WebSocket disconnected, remaining: {len(self.websockets)}")

        return ws

    async def handle_command(self, data: dict) -> bool:
        """Handle a control command."""
        cmd_type = data.get("type")
        logger.info(f"Received control command: {cmd_type}")

        if not self._idb_available:
            logger.warning("idb not available - cannot process command")
            return False

        if cmd_type == "tap":
            return await self.handle_tap(data)
        elif cmd_type == "doubletap":
            return await self.handle_doubletap(data)
        elif cmd_type == "longpress":
            return await self.handle_longpress(data)
        elif cmd_type == "swipe":
            return await self.handle_swipe(data)
        elif cmd_type == "scroll":
            return await self.handle_scroll(data)
        elif cmd_type == "home":
            return await self.press_button("HOME")
        elif cmd_type == "lock":
            return await self.press_button("LOCK")
        elif cmd_type == "volumeUp":
            return await self.press_button("SIDE_BUTTON")  # Closest equivalent
        elif cmd_type == "volumeDown":
            return await self.press_button("SIDE_BUTTON")
        elif cmd_type == "type":
            return await self.type_text(data.get("text", ""))
        else:
            logger.warning(f"Unknown command type: {cmd_type}")
            return False

    def _scale_coordinates(self, video_x: int, video_y: int, video_width: int, video_height: int) -> Tuple[int, int]:
        """
        Scale video coordinates to simulator POINT coordinates.

        IMPORTANT: idb uses POINT coordinates, not PIXEL coordinates.
        iOS devices have a Retina scale factor (2x or 3x).
        - iPhone 16 Pro: 1206x2622 pixels = 402x874 points (3x scale)
        - iPhone SE: 750x1334 pixels = 375x667 points (2x scale)

        We need to:
        1. Scale from video dimensions to pixel dimensions
        2. Convert from pixels to points (divide by scale_factor)
        """
        if video_width <= 0 or video_height <= 0:
            return video_x, video_y

        if self.screen_width <= 0 or self.screen_height <= 0:
            # Use video dimensions as screen size (1:1 mapping)
            return video_x, video_y

        # Step 1: Scale from video coordinates to pixel coordinates
        scale_x = self.screen_width / video_width
        scale_y = self.screen_height / video_height
        pixel_x = video_x * scale_x
        pixel_y = video_y * scale_y

        # Step 2: Convert pixels to points (idb expects points)
        point_x = int(pixel_x / self.scale_factor)
        point_y = int(pixel_y / self.scale_factor)

        logger.debug(f"Coordinate scale: video({video_x},{video_y}) -> pixel({pixel_x:.0f},{pixel_y:.0f}) -> point({point_x},{point_y})")

        return point_x, point_y

    async def _run_idb_command(self, *args) -> bool:
        """Run an idb command and return success status."""
        cmd = [
            IDB_PATH,
            '--companion-path', IDB_COMPANION_PATH,
            *args,
            '--udid', self.simulator_udid
        ]

        logger.debug(f"Running idb command: {' '.join(cmd)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)

            if proc.returncode != 0:
                logger.error(f"idb command failed: {stderr.decode()}")
                return False

            return True

        except asyncio.TimeoutError:
            logger.error("idb command timed out")
            return False
        except Exception as e:
            logger.error(f"idb command error: {e}")
            return False

    async def handle_tap(self, data: dict) -> bool:
        """Handle tap event using idb ui tap."""
        x = data.get("x", 0)
        y = data.get("y", 0)
        video_width = data.get("videoWidth", 0)
        video_height = data.get("videoHeight", 0)

        point_x, point_y = self._scale_coordinates(x, y, video_width, video_height)
        logger.info(f"Tap at video({x}, {y}) -> point({point_x}, {point_y})")

        return await self._run_idb_command('ui', 'tap', str(point_x), str(point_y))

    async def handle_doubletap(self, data: dict) -> bool:
        """Handle double tap event."""
        x = data.get("x", 0)
        y = data.get("y", 0)
        video_width = data.get("videoWidth", 0)
        video_height = data.get("videoHeight", 0)

        point_x, point_y = self._scale_coordinates(x, y, video_width, video_height)
        logger.info(f"Double tap at video({x}, {y}) -> point({point_x}, {point_y})")

        # Two quick taps
        await self._run_idb_command('ui', 'tap', str(point_x), str(point_y))
        await asyncio.sleep(0.1)
        return await self._run_idb_command('ui', 'tap', str(point_x), str(point_y))

    async def handle_longpress(self, data: dict) -> bool:
        """Handle long press event."""
        x = data.get("x", 0)
        y = data.get("y", 0)
        duration = data.get("duration", 1000) / 1000.0  # Convert ms to seconds
        video_width = data.get("videoWidth", 0)
        video_height = data.get("videoHeight", 0)

        point_x, point_y = self._scale_coordinates(x, y, video_width, video_height)
        logger.info(f"Long press at video({x}, {y}) -> point({point_x}, {point_y}), duration={duration}s")

        return await self._run_idb_command('ui', 'tap', str(point_x), str(point_y), '--duration', str(duration))

    async def handle_swipe(self, data: dict) -> bool:
        """Handle swipe gesture."""
        x = data.get("x", 0)
        y = data.get("y", 0)
        end_x = data.get("endX", 0)
        end_y = data.get("endY", 0)
        duration = data.get("duration", 300) / 1000.0  # Convert ms to seconds
        video_width = data.get("videoWidth", 0)
        video_height = data.get("videoHeight", 0)

        start_point_x, start_point_y = self._scale_coordinates(x, y, video_width, video_height)
        end_point_x, end_point_y = self._scale_coordinates(end_x, end_y, video_width, video_height)

        logger.info(f"Swipe from video({x}, {y}) to ({end_x}, {end_y}) -> point({start_point_x}, {start_point_y}) to ({end_point_x}, {end_point_y})")

        return await self._run_idb_command(
            'ui', 'swipe',
            str(start_point_x), str(start_point_y),
            str(end_point_x), str(end_point_y),
            '--duration', str(duration)
        )

    async def handle_scroll(self, data: dict) -> bool:
        """Handle scroll/wheel event."""
        x = data.get("x", 0)
        y = data.get("y", 0)
        delta_x = data.get("deltaX", 0)
        delta_y = data.get("deltaY", 0)
        video_width = data.get("videoWidth", 0)
        video_height = data.get("videoHeight", 0)

        # Convert wheel delta to swipe distance (in video coordinates)
        swipe_distance = 100  # pixels in video space

        if abs(delta_y) > abs(delta_x):
            # Vertical scroll - swipe up/down
            direction = 1 if delta_y > 0 else -1
            end_y = y - (direction * swipe_distance)
            return await self.handle_swipe({
                "x": x, "y": y,
                "endX": x, "endY": end_y,
                "duration": 200,
                "videoWidth": video_width,
                "videoHeight": video_height
            })
        else:
            # Horizontal scroll - swipe left/right
            direction = 1 if delta_x > 0 else -1
            end_x = x - (direction * swipe_distance)
            return await self.handle_swipe({
                "x": x, "y": y,
                "endX": end_x, "endY": y,
                "duration": 200,
                "videoWidth": video_width,
                "videoHeight": video_height
            })

    async def press_button(self, button_type: str) -> bool:
        """Press a button using idb ui button."""
        logger.info(f"Pressing button: {button_type}")
        return await self._run_idb_command('ui', 'button', button_type)

    async def type_text(self, text: str) -> bool:
        """Type text into the simulator using idb ui text."""
        if not text:
            return False

        logger.info(f"Typing text: {text[:20]}{'...' if len(text) > 20 else ''}")
        return await self._run_idb_command('ui', 'text', text)
