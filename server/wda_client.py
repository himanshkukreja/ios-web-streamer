"""
WebDriverAgent Client for iOS device control.

This module provides a Python client to communicate with WebDriverAgent
running on an iOS device, enabling remote control capabilities like
tap, swipe, and button presses.
"""

import asyncio
import logging
from typing import Optional, Tuple, Dict, Any
import aiohttp

logger = logging.getLogger(__name__)


class WDAClient:
    """
    Async HTTP client for WebDriverAgent.

    WDA runs on port 8100 on the iOS device and provides
    REST endpoints for device control.
    """

    def __init__(self, host: str = "localhost", port: int = 8100):
        """
        Initialize WDA client.

        Args:
            host: WDA server host (localhost if using iproxy, or device IP)
            port: WDA server port (default 8100)
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session_id: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected = False

        # Device screen dimensions (will be fetched from WDA)
        self.screen_width: int = 0
        self.screen_height: int = 0
        self.scale: float = 1.0

    async def connect(self) -> bool:
        """
        Connect to WDA and create a session.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._session = aiohttp.ClientSession()

            # Check WDA status
            status = await self._get("/status")
            if not status:
                logger.error("Failed to get WDA status")
                return False

            logger.info(f"WDA Status: {status.get('value', {}).get('state', 'unknown')}")

            # Create a new session
            session_data = await self._post("/session", {
                "capabilities": {
                    "alwaysMatch": {},
                    "firstMatch": [{}]
                }
            })

            if session_data and "value" in session_data:
                self.session_id = session_data.get("sessionId") or session_data["value"].get("sessionId")
                logger.info(f"WDA session created: {self.session_id}")

                # Get window size
                await self._update_screen_dimensions()

                self._connected = True
                return True
            else:
                # Try to get existing session
                sessions = await self._get("/sessions")
                if sessions and sessions.get("value"):
                    self.session_id = sessions["value"][0]["id"]
                    logger.info(f"Using existing WDA session: {self.session_id}")
                    await self._update_screen_dimensions()
                    self._connected = True
                    return True

            logger.error("Failed to create WDA session")
            return False

        except Exception as e:
            logger.error(f"Failed to connect to WDA: {e}")
            return False

    async def disconnect(self):
        """Close the WDA session and cleanup."""
        if self._session:
            # Optionally delete session
            if self.session_id:
                try:
                    await self._delete(f"/session/{self.session_id}")
                except Exception:
                    pass
            await self._session.close()
            self._session = None
        self._connected = False
        self.session_id = None

    @property
    def is_connected(self) -> bool:
        """Check if connected to WDA."""
        return self._connected and self.session_id is not None

    async def _update_screen_dimensions(self):
        """Fetch screen dimensions from WDA."""
        try:
            result = await self._get(f"/session/{self.session_id}/window/size")
            if result and "value" in result:
                self.screen_width = result["value"].get("width", 0)
                self.screen_height = result["value"].get("height", 0)
                logger.info(f"Screen dimensions: {self.screen_width}x{self.screen_height}")
        except Exception as e:
            logger.warning(f"Failed to get screen dimensions: {e}")

    async def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """Make HTTP request to WDA."""
        if not self._session:
            return None

        url = f"{self.base_url}{path}"
        try:
            async with self._session.request(method, url, json=data, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    text = await resp.text()
                    logger.warning(f"WDA request failed: {method} {path} -> {resp.status}: {text[:200]}")
                    return None
        except asyncio.TimeoutError:
            logger.warning(f"WDA request timeout: {method} {path}")
            return None
        except Exception as e:
            logger.error(f"WDA request error: {method} {path} -> {e}")
            return None

    async def _get(self, path: str) -> Optional[Dict]:
        return await self._request("GET", path)

    async def _post(self, path: str, data: Optional[Dict] = None) -> Optional[Dict]:
        return await self._request("POST", path, data or {})

    async def _delete(self, path: str) -> Optional[Dict]:
        return await self._request("DELETE", path)

    # =========================================================================
    # Touch Actions
    # =========================================================================

    async def tap(self, x: int, y: int) -> bool:
        """
        Perform a tap at the specified coordinates.

        Args:
            x: X coordinate on device screen
            y: Y coordinate on device screen

        Returns:
            True if successful
        """
        if not self.is_connected:
            logger.warning("WDA not connected, cannot tap")
            return False

        logger.debug(f"Tap at ({x}, {y})")

        # Use W3C actions for tap
        actions = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pause", "duration": 50},
                        {"type": "pointerUp", "button": 0}
                    ]
                }
            ]
        }

        result = await self._post(f"/session/{self.session_id}/actions", actions)
        return result is not None

    async def double_tap(self, x: int, y: int) -> bool:
        """Perform a double tap at the specified coordinates."""
        if not self.is_connected:
            return False

        logger.debug(f"Double tap at ({x}, {y})")

        actions = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pause", "duration": 50},
                        {"type": "pointerUp", "button": 0},
                        {"type": "pause", "duration": 100},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pause", "duration": 50},
                        {"type": "pointerUp", "button": 0}
                    ]
                }
            ]
        }

        result = await self._post(f"/session/{self.session_id}/actions", actions)
        return result is not None

    async def long_press(self, x: int, y: int, duration_ms: int = 1000) -> bool:
        """Perform a long press at the specified coordinates."""
        if not self.is_connected:
            return False

        logger.debug(f"Long press at ({x}, {y}) for {duration_ms}ms")

        actions = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pause", "duration": duration_ms},
                        {"type": "pointerUp", "button": 0}
                    ]
                }
            ]
        }

        result = await self._post(f"/session/{self.session_id}/actions", actions)
        return result is not None

    async def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int,
                    duration_ms: int = 300) -> bool:
        """
        Perform a swipe gesture.

        Args:
            start_x, start_y: Starting coordinates
            end_x, end_y: Ending coordinates
            duration_ms: Duration of swipe in milliseconds

        Returns:
            True if successful
        """
        if not self.is_connected:
            return False

        logger.debug(f"Swipe from ({start_x}, {start_y}) to ({end_x}, {end_y})")

        actions = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {"type": "pointerMove", "duration": 0, "x": start_x, "y": start_y},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pointerMove", "duration": duration_ms, "x": end_x, "y": end_y},
                        {"type": "pointerUp", "button": 0}
                    ]
                }
            ]
        }

        result = await self._post(f"/session/{self.session_id}/actions", actions)
        return result is not None

    async def scroll(self, x: int, y: int, delta_x: int, delta_y: int) -> bool:
        """
        Perform a scroll gesture from a point.

        Args:
            x, y: Starting point
            delta_x, delta_y: Scroll amount
        """
        end_x = x + delta_x
        end_y = y + delta_y
        return await self.swipe(x, y, end_x, end_y, duration_ms=200)

    # =========================================================================
    # Device Buttons
    # =========================================================================

    async def press_home(self) -> bool:
        """Press the home button."""
        if not self.is_connected:
            return False

        logger.debug("Pressing home button")
        # Use pressButton endpoint with name="home"
        result = await self._post(f"/session/{self.session_id}/wda/pressButton", {"name": "home"})
        return result is not None

    async def press_lock(self) -> bool:
        """Press the lock button.

        Note: WDA only supports home, volumeUp, volumeDown buttons.
        Lock button is not supported via WDA pressButton API.
        """
        if not self.is_connected:
            return False

        logger.debug("Pressing lock button (not supported by WDA)")
        # WDA doesn't support lock button via pressButton
        # Only supported buttons are: home, volumeUp, volumeDown
        logger.warning("Lock button not supported by WDA")
        return False

    async def unlock(self) -> bool:
        """Unlock the device."""
        if not self.is_connected:
            return False

        logger.debug("Unlocking device")
        result = await self._post(f"/session/{self.session_id}/wda/unlock")
        return result is not None

    async def press_volume_up(self) -> bool:
        """Press volume up button."""
        if not self.is_connected:
            return False

        result = await self._post(
            f"/session/{self.session_id}/wda/pressButton",
            {"name": "volumeUp"}
        )
        return result is not None

    async def press_volume_down(self) -> bool:
        """Press volume down button."""
        if not self.is_connected:
            return False

        result = await self._post(
            f"/session/{self.session_id}/wda/pressButton",
            {"name": "volumeDown"}
        )
        return result is not None

    # =========================================================================
    # Text Input
    # =========================================================================

    async def type_text(self, text: str) -> bool:
        """
        Type text on the device.

        Args:
            text: Text to type

        Returns:
            True if successful
        """
        if not self.is_connected:
            return False

        logger.debug(f"Typing text: {text[:20]}...")

        result = await self._post(
            f"/session/{self.session_id}/wda/keys",
            {"value": list(text)}
        )
        return result is not None

    # =========================================================================
    # App Management
    # =========================================================================

    async def launch_app(self, bundle_id: str) -> bool:
        """Launch an app by bundle ID."""
        if not self.is_connected:
            return False

        logger.debug(f"Launching app: {bundle_id}")
        result = await self._post(
            f"/session/{self.session_id}/wda/apps/launch",
            {"bundleId": bundle_id}
        )
        return result is not None

    async def terminate_app(self, bundle_id: str) -> bool:
        """Terminate an app by bundle ID."""
        if not self.is_connected:
            return False

        logger.debug(f"Terminating app: {bundle_id}")
        result = await self._post(
            f"/session/{self.session_id}/wda/apps/terminate",
            {"bundleId": bundle_id}
        )
        return result is not None

    async def activate_app(self, bundle_id: str) -> bool:
        """Activate (bring to foreground) an app by bundle ID."""
        if not self.is_connected:
            return False

        result = await self._post(
            f"/session/{self.session_id}/wda/apps/activate",
            {"bundleId": bundle_id}
        )
        return result is not None

    # =========================================================================
    # Device Info
    # =========================================================================

    async def get_device_info(self) -> Optional[Dict[str, Any]]:
        """Get device information."""
        if not self.is_connected:
            return None

        result = await self._get(f"/session/{self.session_id}/wda/device/info")
        if result:
            return result.get("value")
        return None

    async def get_battery_info(self) -> Optional[Dict[str, Any]]:
        """Get battery information."""
        if not self.is_connected:
            return None

        result = await self._get(f"/session/{self.session_id}/wda/batteryInfo")
        if result:
            return result.get("value")
        return None

    async def get_screen_size(self) -> Tuple[int, int]:
        """Get screen size (width, height)."""
        return (self.screen_width, self.screen_height)

    # =========================================================================
    # Screenshots (alternative to our streaming)
    # =========================================================================

    async def get_screenshot(self) -> Optional[bytes]:
        """Get a screenshot as PNG bytes."""
        if not self.is_connected:
            return None

        result = await self._get(f"/session/{self.session_id}/screenshot")
        if result and "value" in result:
            import base64
            return base64.b64decode(result["value"])
        return None


class WDAConnectionManager:
    """
    Manages WDA connection lifecycle and provides easy access to WDA client.
    """

    def __init__(self, host: str = "localhost", port: int = 8100):
        self.client = WDAClient(host, port)
        self._reconnect_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the connection manager and connect to WDA."""
        self._running = True
        connected = await self.client.connect()

        if not connected:
            logger.warning("Initial WDA connection failed, will retry...")
            self._start_reconnect_task()

        return connected

    async def stop(self):
        """Stop the connection manager."""
        self._running = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        await self.client.disconnect()

    def _start_reconnect_task(self):
        """Start background reconnection task."""
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        """Try to reconnect to WDA periodically."""
        while self._running and not self.client.is_connected:
            await asyncio.sleep(5)
            logger.info("Attempting to reconnect to WDA...")
            if await self.client.connect():
                logger.info("Reconnected to WDA successfully")
                break
