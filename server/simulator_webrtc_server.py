#!/usr/bin/env python3
"""
Simulator WebRTC Server - Complete standalone server for iOS Simulator streaming
Streams iOS Simulator screen to web browsers via WebRTC using idb
"""

import asyncio
import json
import logging
import signal
import sys
import subprocess
import re
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaRelay

# Import our simulator receiver
from simulator_receiver import SimulatorVideoTrack, check_ffmpeg_available, find_ffmpeg

# Import H.264 encoder patch for WebRTC keyframe injection
from h264_encoder_patch import patch_aiortc_h264_encoder

# Import simulator control server
from simulator_control_server import SimulatorControlServer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress aiohttp access logs
logging.getLogger('aiohttp.access').setLevel(logging.WARNING)


class SimulatorWebRTCServer:
    """
    Standalone WebRTC server for iOS Simulator streaming.
    """

    def __init__(self, simulator_udid: str, http_port: int = 8999, enable_control: bool = True):
        self.simulator_udid = simulator_udid
        self.http_port = http_port
        self.enable_control = enable_control

        # Video track
        self.video_track: SimulatorVideoTrack = None

        # WebRTC
        self.peer_connections = set()
        self.relay = MediaRelay()

        # Control server for simulator control via simctl
        self.control_server = None

        # HTTP app
        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self):
        """Set up HTTP routes."""
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_get('/viewer.js', self.handle_viewer_js)
        self.app.router.add_get('/style.css', self.handle_style_css)
        self.app.router.add_post('/offer', self.handle_offer)
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_get('/device-info', self.handle_device_info)
        self.app.router.add_get('/control', self.handle_control_websocket)
        self.app.router.add_get('/control/status', self.handle_control_status)

    async def handle_index(self, request):
        """Serve the viewer page."""
        try:
            with open('../web/index.html', 'r') as f:
                content = f.read()
            return web.Response(content_type='text/html', text=content)
        except FileNotFoundError:
            return web.Response(status=404, text='index.html not found')

    async def handle_viewer_js(self, request):
        """Serve the viewer JavaScript."""
        try:
            with open('../web/viewer.js', 'r') as f:
                content = f.read()
            return web.Response(content_type='application/javascript', text=content)
        except FileNotFoundError:
            return web.Response(status=404, text='viewer.js not found')

    async def handle_style_css(self, request):
        """Serve the CSS styles."""
        try:
            with open('../web/style.css', 'r') as f:
                content = f.read()
            return web.Response(content_type='text/css', text=content)
        except FileNotFoundError:
            return web.Response(status=404, text='style.css not found')

    async def handle_offer(self, request):
        """Handle WebRTC offer from browser."""
        try:
            params = await request.json()
            logger.info("=" * 60)
            logger.info("📥 Received WebRTC offer from browser")
            logger.info(f"Offer type: {params.get('type')}")
            logger.info(f"Offer SDP length: {len(params.get('sdp', ''))}")

            offer = RTCSessionDescription(
                sdp=params['sdp'],
                type=params['type']
            )

            # Check video track is available
            if not self.video_track:
                logger.error("❌ Video track not started!")
                return web.Response(status=500, text="Video track not available")

            logger.info(f"✅ Video track available: {self.video_track}")
            logger.info(f"   Track kind: {getattr(self.video_track, 'kind', 'UNKNOWN')}")
            logger.info(f"   Track id: {getattr(self.video_track, 'id', 'UNKNOWN')}")

            # Create peer connection with ICE configuration
            rtc_config = RTCConfiguration(
                iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]
            )
            pc = RTCPeerConnection(configuration=rtc_config)
            self.peer_connections.add(pc)
            logger.info(f"✅ Created RTCPeerConnection")

            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                logger.info(f"🔄 Connection state: {pc.connectionState}")
                if pc.connectionState in ["failed", "closed"]:
                    await pc.close()
                    self.peer_connections.discard(pc)

            # Add video track BEFORE handling offer
            logger.info("🎬 Adding video track to peer connection...")
            relayed_track = self.relay.subscribe(self.video_track)
            logger.info(f"   Relayed track: {relayed_track}")
            logger.info(f"   Relayed track kind: {getattr(relayed_track, 'kind', 'UNKNOWN')}")
            logger.info(f"   Relayed track id: {getattr(relayed_track, 'id', 'UNKNOWN')}")

            pc.addTrack(relayed_track)
            logger.info(f"✅ Track added to peer connection")

            # Log transceivers state
            logger.info(f"📡 Transceivers after addTrack: {len(pc.getTransceivers())}")
            for i, t in enumerate(pc.getTransceivers()):
                logger.info(f"   Transceiver {i}: mid={t.mid}, direction={t.direction}, currentDirection={t.currentDirection}")

            # Handle offer
            logger.info("📨 Setting remote description (offer)...")
            await pc.setRemoteDescription(offer)
            logger.info("✅ Remote description set")

            # Log transceivers after setRemoteDescription
            logger.info(f"📡 Transceivers after setRemoteDescription: {len(pc.getTransceivers())}")
            for i, t in enumerate(pc.getTransceivers()):
                logger.info(f"   Transceiver {i}: mid={t.mid}, direction={t.direction}, currentDirection={t.currentDirection}, _offerDirection={getattr(t, '_offerDirection', 'N/A')}")

            # Create answer
            logger.info("📝 Creating answer...")
            answer = await pc.createAnswer()
            logger.info(f"✅ Answer created: type={answer.type}")
            logger.info(f"   Answer SDP length: {len(answer.sdp)}")

            # Log transceivers after createAnswer
            logger.info(f"📡 Transceivers after createAnswer: {len(pc.getTransceivers())}")
            for i, t in enumerate(pc.getTransceivers()):
                logger.info(f"   Transceiver {i}: mid={t.mid}, direction={t.direction}, currentDirection={t.currentDirection}, _offerDirection={getattr(t, '_offerDirection', 'N/A')}")

            logger.info("📤 Setting local description (answer)...")
            await pc.setLocalDescription(answer)
            logger.info("✅ Local description set")

            logger.info("✅ New viewer connected successfully")
            logger.info("=" * 60)

            return web.json_response({
                'sdp': pc.localDescription.sdp,
                'type': pc.localDescription.type
            })

        except Exception as e:
            logger.error(f"❌ Error handling offer: {e}")
            import traceback
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def handle_health(self, request):
        """Health check endpoint."""
        return web.json_response({'status': 'ok', 'simulator': self.simulator_udid})

    async def _get_simulator_resolution(self) -> tuple:
        """Get the actual simulator screen resolution using simctl screenshot."""
        try:
            from PIL import Image
            import io

            proc = await asyncio.create_subprocess_exec(
                'xcrun', 'simctl', 'io', self.simulator_udid, 'screenshot', '--type=tiff', '-',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)

            if proc.returncode == 0 and stdout:
                img = Image.open(io.BytesIO(stdout))
                logger.info(f"Detected simulator resolution: {img.width}x{img.height}")
                return img.width, img.height
        except Exception as e:
            logger.warning(f"Could not detect simulator resolution: {e}")

        # Default fallback
        return 1170, 2532  # iPhone 14 Pro resolution

    async def handle_device_info(self, request):
        """Device info endpoint for simulator."""
        try:
            # Get simulator info using simctl
            result = subprocess.run(
                ['xcrun', 'simctl', 'list', 'devices', '-j'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                import json
                devices_data = json.loads(result.stdout)
                # Find the simulator by UDID
                for runtime, devices in devices_data.get('devices', {}).items():
                    for device in devices:
                        if device.get('udid') == self.simulator_udid:
                            # Extract iOS version from runtime string
                            ios_version = "Unknown"
                            if 'iOS' in runtime:
                                # Format: com.apple.CoreSimulator.SimRuntime.iOS-17-2
                                parts = runtime.split('iOS-')
                                if len(parts) > 1:
                                    ios_version = parts[1].replace('-', '.')

                            return web.json_response({
                                'deviceType': 'simulator',
                                'deviceName': device.get('name', 'iOS Simulator'),
                                'deviceModel': device.get('deviceTypeIdentifier', '').split('.')[-1].replace('-', ' '),
                                'systemName': 'iOS Simulator',
                                'systemVersion': ios_version,
                                'udid': self.simulator_udid,
                                'state': device.get('state', 'Unknown'),
                                'screenResolution': f"{self.video_track.frame_width}x{self.video_track.frame_height}" if self.video_track and hasattr(self.video_track, 'frame_width') else '--',
                                'batteryLevel': -1,  # N/A for simulator
                                'batteryState': 'unknown'
                            })

            return web.json_response({
                'deviceType': 'simulator',
                'deviceName': 'iOS Simulator',
                'udid': self.simulator_udid,
                'error': 'Could not fetch device details'
            })
        except Exception as e:
            logger.error(f"Error fetching device info: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def handle_control_websocket(self, request):
        """Handle WebSocket connection for simulator control."""
        if self.control_server:
            return await self.control_server.handle_websocket(request)
        else:
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({
                "type": "error",
                "error": "Control server not available"
            })
            await ws.close()
            return ws

    async def handle_control_status(self, request):
        """Return control server status."""
        if self.control_server:
            return web.json_response({
                "enabled": True,
                "wdaConnected": True,  # For simulator, simctl is always available
                "deviceType": "simulator",
                "screenWidth": self.video_track.frame_width if self.video_track and hasattr(self.video_track, 'frame_width') else 0,
                "screenHeight": self.video_track.frame_height if self.video_track and hasattr(self.video_track, 'frame_height') else 0,
            })
        else:
            return web.json_response({
                "enabled": False,
                "wdaConnected": False,
                "deviceType": "simulator"
            })

    async def start(self):
        """Start the server."""
        logger.info("=" * 70)
        logger.info("iOS Simulator WebRTC Streaming Server")
        logger.info("=" * 70)
        logger.info(f"Simulator UDID: {self.simulator_udid}")
        logger.info("")

        # Patch aiortc H.264 encoder to include periodic keyframes
        # This is critical for preventing corruption during scene transitions
        logger.info("🔧 Patching aiortc H.264 encoder for periodic keyframes...")
        patch_aiortc_h264_encoder(keyframe_interval=15)  # Keyframe every 15 frames (0.5 second at 30fps)

        # Check FFmpeg availability
        ffmpeg_path = find_ffmpeg()
        if ffmpeg_path:
            logger.info(f"✅ FFmpeg found at: {ffmpeg_path}")
        else:
            logger.warning("⚠️ FFmpeg NOT found - will use raw idb stream (may have corruption)")

        # ============================================================
        # CAPTURE CONFIGURATION
        # ============================================================
        # Capture method:
        #   "simctl"   - Recommended. Works headless, uses UDID (~300ms latency)
        #   "quartz"   - Fast (~80ms) but needs visible window
        #   "idb_h264" - 30 FPS but may have corruption
        #
        # Scale factor for network streaming:
        #   1.0 = Full resolution (1206x2622) - best for localhost
        #   0.5 = Half resolution (602x1310) - better for network/tunnel
        #   0.75 = 3/4 resolution (904x1966) - balanced
        # ============================================================
        CAPTURE_METHOD = "simctl"
        SCALE_FACTOR = 0.5  # Use 0.5 for network, 1.0 for localhost

        logger.info(f"🚀 Starting video stream (method: {CAPTURE_METHOD}, scale: {SCALE_FACTOR})...")

        self.video_track = SimulatorVideoTrack(
            simulator_udid=self.simulator_udid,
            fps=30,
            port=10882,
            capture_method=CAPTURE_METHOD,
            scale_factor=SCALE_FACTOR
        )

        await self.video_track.start()

        # Log the pipeline being used
        if CAPTURE_METHOD == "quartz":
            logger.info("   Pipeline: Quartz window capture → frame queue → aiortc H.264")
        elif CAPTURE_METHOD == "simctl":
            scale_info = f" (scaled to {SCALE_FACTOR}x)" if SCALE_FACTOR < 1.0 else ""
            logger.info(f"   Pipeline: simctl screenshot{scale_info} → frame queue → aiortc H.264")
        else:
            logger.info("   Pipeline: idb H.264 → decode → frame queue → aiortc H.264")

        # Initialize control server if enabled
        if self.enable_control:
            self.control_server = SimulatorControlServer(self.simulator_udid)
            # Set the actual screen size (before scaling) for proper coordinate mapping
            # idb uses the native simulator resolution, not the scaled video size
            actual_width, actual_height = await self._get_simulator_resolution()
            self.control_server.set_screen_size(actual_width, actual_height)
            await self.control_server.start()
            logger.info(f"🎮 Control server initialized (using idb, screen: {actual_width}x{actual_height})")

        # Start HTTP server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.http_port)
        await site.start()

        logger.info("")
        logger.info("=" * 70)
        logger.info(f"✅ Server running at: http://localhost:{self.http_port}")
        logger.info("=" * 70)
        logger.info("")
        logger.info("Open the URL above in your browser to view the simulator stream")
        logger.info("Press Ctrl+C to stop")
        logger.info("")

        # Keep running
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass

    async def shutdown(self):
        """Shutdown the server."""
        logger.info("Shutting down...")

        # Stop control server if running
        if self.control_server:
            await self.control_server.stop()

        # Close all peer connections
        for pc in list(self.peer_connections):
            await pc.close()

        # Stop video track
        if self.video_track:
            await self.video_track.stop()

        logger.info("Shutdown complete")


async def main():
    """Main entry point."""
    # Get booted simulator
    result = subprocess.run(
        ['xcrun', 'simctl', 'list', 'devices', 'booted'],
        capture_output=True,
        text=True
    )

    match = re.search(r'\(([A-F0-9-]+)\)', result.stdout)
    if not match:
        logger.error("❌ No booted simulator found")
        logger.error("")
        logger.error("Please boot a simulator first:")
        logger.error("  xcrun simctl list devices available")
        logger.error("  xcrun simctl boot <UDID>")
        sys.exit(1)

    udid = match.group(1)

    # Create and start server
    server = SimulatorWebRTCServer(simulator_udid=udid, http_port=8999)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(server.shutdown()))

    try:
        await server.start()
    except KeyboardInterrupt:
        await server.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nShutdown requested")
        sys.exit(0)
