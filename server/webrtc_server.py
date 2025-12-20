"""
WebRTC server using aiortc for streaming video to browsers.
"""

import asyncio
import json
import logging
from typing import Set, Optional

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaRelay

from config import ICE_SERVERS, HTTP_HOST, HTTP_PORT, WDA_HOST, WDA_PORT
from frame_queue import FrameQueue
from video_track import iOSVideoTrack, TestVideoTrack, MediaFileTrack
from control_server import ControlServer, set_control_server

logger = logging.getLogger(__name__)


class WebRTCServer:
    """
    WebRTC server that streams video to browser clients.

    Handles:
    - SDP offer/answer negotiation
    - ICE candidate exchange
    - Multiple concurrent viewers via MediaRelay
    """

    def __init__(self, frame_queue: FrameQueue, enable_control: bool = True, wda_host: str = None, ios_receiver=None):
        self.frame_queue = frame_queue
        self.peer_connections: Set[RTCPeerConnection] = set()
        self.relay = MediaRelay()
        self.ios_receiver = ios_receiver  # Reference to iOS receiver for device info

        # Shared video track for all viewers
        self.video_track: Optional[iOSVideoTrack] = None
        self.test_mode = False
        self.media_file: Optional[str] = None

        # Control server for remote control via WDA
        self.control_server: Optional[ControlServer] = None
        self.enable_control = enable_control
        self.wda_host = wda_host or WDA_HOST  # Use provided host or fall back to config

        # HTTP app
        self.app = web.Application()
        self._setup_routes()

        # Connection stats
        self.total_connections = 0

    def _setup_routes(self):
        """Set up HTTP routes."""
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_get('/viewer.js', self.handle_viewer_js)
        self.app.router.add_get('/style.css', self.handle_style_css)
        self.app.router.add_post('/offer', self.handle_offer)
        self.app.router.add_get('/stats', self.handle_stats)
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_get('/control', self.handle_control_websocket)
        self.app.router.add_get('/control/status', self.handle_control_status)
        self.app.router.add_get('/device-info', self.handle_device_info)

    def _get_rtc_configuration(self) -> RTCConfiguration:
        """Get RTC configuration with ICE servers."""
        ice_servers = [
            RTCIceServer(urls=server['urls'])
            for server in ICE_SERVERS
        ]
        return RTCConfiguration(iceServers=ice_servers)

    def _get_or_create_video_track(self):
        """Get or create the video track."""
        if self.video_track is None:
            if self.media_file:
                logger.info(f"Creating media file track: {self.media_file}")
                self.video_track = MediaFileTrack(self.media_file)
            elif self.test_mode:
                logger.info("Creating test video track")
                self.video_track = TestVideoTrack()
            else:
                logger.info("Creating iOS video track")
                self.video_track = iOSVideoTrack(self.frame_queue)
        return self.video_track

    async def handle_index(self, request: web.Request) -> web.Response:
        """Serve the main viewer page."""
        try:
            with open('../web/index.html', 'r') as f:
                content = f.read()
            return web.Response(content_type='text/html', text=content)
        except FileNotFoundError:
            # Return inline HTML if file not found
            return web.Response(content_type='text/html', text=self._get_inline_html())

    async def handle_viewer_js(self, request: web.Request) -> web.Response:
        """Serve the viewer JavaScript."""
        try:
            with open('../web/viewer.js', 'r') as f:
                content = f.read()
            return web.Response(content_type='application/javascript', text=content)
        except FileNotFoundError:
            return web.Response(status=404, text='Not found')

    async def handle_style_css(self, request: web.Request) -> web.Response:
        """Serve the CSS styles."""
        try:
            with open('../web/style.css', 'r') as f:
                content = f.read()
            return web.Response(content_type='text/css', text=content)
        except FileNotFoundError:
            return web.Response(status=404, text='Not found')

    async def handle_offer(self, request: web.Request) -> web.Response:
        """Handle WebRTC offer from browser."""
        try:
            params = await request.json()

            offer = RTCSessionDescription(
                sdp=params['sdp'],
                type=params['type']
            )

            # Create peer connection
            pc = RTCPeerConnection(configuration=self._get_rtc_configuration())
            self.peer_connections.add(pc)
            self.total_connections += 1

            pc_id = f"pc_{self.total_connections}"
            logger.info(f"New peer connection: {pc_id}")

            @pc.on('connectionstatechange')
            async def on_connection_state_change():
                logger.info(f"{pc_id} connection state: {pc.connectionState}")
                if pc.connectionState in ('failed', 'closed', 'disconnected'):
                    await self._cleanup_peer_connection(pc)

            @pc.on('iceconnectionstatechange')
            async def on_ice_connection_state_change():
                logger.debug(f"{pc_id} ICE state: {pc.iceConnectionState}")

            # Add video track
            video_track = self._get_or_create_video_track()
            relayed_track = self.relay.subscribe(video_track)
            pc.addTrack(relayed_track)

            # Handle offer
            await pc.setRemoteDescription(offer)

            # Create answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            logger.info(f"{pc_id} sending answer")

            return web.json_response({
                'sdp': pc.localDescription.sdp,
                'type': pc.localDescription.type
            })

        except Exception as e:
            logger.error(f"Error handling offer: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def handle_stats(self, request: web.Request) -> web.Response:
        """Return server statistics."""
        stats = {
            'active_connections': len(self.peer_connections),
            'total_connections': self.total_connections,
            'queue_stats': self.frame_queue.get_stats(),
        }

        if self.video_track and hasattr(self.video_track, 'get_stats'):
            stats['video_track'] = self.video_track.get_stats()

        return web.json_response(stats)

    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({'status': 'healthy'})

    async def handle_device_info(self, request: web.Request) -> web.Response:
        """Device info endpoint."""
        if self.ios_receiver and self.ios_receiver.device_info:
            # Add deviceType to the response
            device_info = dict(self.ios_receiver.device_info)
            device_info['deviceType'] = 'device'  # Real device (not simulator)
            return web.json_response(device_info)
        else:
            return web.json_response({'error': 'No device info available'}, status=404)

    async def handle_control_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connection for device control."""
        if self.control_server:
            return await self.control_server.handle_control_websocket(request)
        else:
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({
                "type": "error",
                "error": "Control server not available"
            })
            await ws.close()
            return ws

    async def handle_control_status(self, request: web.Request) -> web.Response:
        """Return control server status."""
        if self.control_server:
            return web.json_response({
                "enabled": True,
                "wdaConnected": self.control_server.wda_client.is_connected,
                "screenWidth": self.control_server.wda_client.screen_width,
                "screenHeight": self.control_server.wda_client.screen_height,
            })
        else:
            return web.json_response({
                "enabled": False,
                "wdaConnected": False,
            })

    async def _cleanup_peer_connection(self, pc: RTCPeerConnection):
        """Clean up a peer connection."""
        self.peer_connections.discard(pc)
        await pc.close()
        logger.info(f"Peer connection closed. Active: {len(self.peer_connections)}")

    async def start(self, host: str = HTTP_HOST, port: int = HTTP_PORT):
        """Start the HTTP/WebRTC server."""
        # Initialize control server if enabled
        if self.enable_control:
            self.control_server = ControlServer(self.wda_host, WDA_PORT)
            set_control_server(self.control_server)
            await self.control_server.start()
            logger.info(f"Control server initialized (WDA: {self.wda_host}:{WDA_PORT})")

        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info(f"WebRTC server running on http://{host}:{port}")

        # Keep running
        await asyncio.Future()

    async def shutdown(self):
        """Shutdown the server and close all connections."""
        logger.info("Shutting down WebRTC server...")

        # Stop control server if running
        if self.control_server:
            await self.control_server.stop()

        # Close all peer connections
        coros = [pc.close() for pc in self.peer_connections]
        await asyncio.gather(*coros)
        self.peer_connections.clear()

        logger.info("WebRTC server shutdown complete")

    def set_test_mode(self, enabled: bool):
        """Enable or disable test mode."""
        self.test_mode = enabled
        if enabled:
            logger.info("Test mode enabled - will use test video track")

    def set_media_file(self, file_path: str):
        """Set a media file to stream instead of iOS frames."""
        import os
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Media file not found: {file_path}")
        self.media_file = file_path
        logger.info(f"Media file mode enabled - will stream: {file_path}")

    def _get_inline_html(self) -> str:
        """Return inline HTML for the viewer page."""
        return '''<!DOCTYPE html>
<html>
<head>
    <title>iOS Simulator Stream</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { margin: 0; background: #1a1a2e; font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #fff; }
        #container { display: flex; flex-direction: column; align-items: center; padding: 20px; min-height: 100vh; box-sizing: border-box; }
        h1 { font-size: 24px; margin-bottom: 20px; }
        #status { padding: 8px 16px; border-radius: 20px; margin: 10px 0; font-size: 14px; }
        .connected { background: #10b981; }
        .connecting { background: #f59e0b; }
        .disconnected { background: #ef4444; }
        #video { max-width: 100%; max-height: 70vh; border-radius: 12px; background: #000; }
        #stats { color: #888; margin-top: 10px; font-size: 14px; font-family: monospace; }
        #controls { margin-top: 20px; }
        button { background: #4f46e5; color: #fff; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; }
        button:hover { background: #4338ca; }
        button:disabled { background: #666; cursor: not-allowed; }
    </style>
</head>
<body>
    <div id="container">
        <h1>iOS Simulator Stream</h1>
        <div id="status" class="disconnected">Disconnected</div>
        <video id="video" autoplay playsinline muted></video>
        <div id="stats">Waiting for stream...</div>
        <div id="controls">
            <button id="connectBtn" onclick="viewer.connect()">Connect</button>
        </div>
    </div>
    <script>
        class StreamViewer {
            constructor() {
                this.pc = null;
                this.statsInterval = null;
            }

            async connect() {
                this.updateStatus('connecting');
                document.getElementById('connectBtn').disabled = true;

                try {
                    this.pc = new RTCPeerConnection({
                        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
                    });

                    this.pc.ontrack = (event) => {
                        document.getElementById('video').srcObject = event.streams[0];
                        this.updateStatus('connected');
                    };

                    this.pc.onconnectionstatechange = () => {
                        console.log('Connection state:', this.pc.connectionState);
                        if (this.pc.connectionState === 'failed' || this.pc.connectionState === 'disconnected') {
                            this.handleDisconnect();
                        }
                    };

                    this.pc.addTransceiver('video', { direction: 'recvonly' });

                    const offer = await this.pc.createOffer();
                    await this.pc.setLocalDescription(offer);

                    const response = await fetch('/offer', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ sdp: offer.sdp, type: offer.type })
                    });

                    const answer = await response.json();
                    if (answer.error) throw new Error(answer.error);

                    await this.pc.setRemoteDescription(answer);
                    this.startStatsMonitoring();

                } catch (error) {
                    console.error('Connection error:', error);
                    this.updateStatus('disconnected');
                    document.getElementById('connectBtn').disabled = false;
                }
            }

            handleDisconnect() {
                this.updateStatus('disconnected');
                this.cleanup();
                document.getElementById('connectBtn').disabled = false;
                setTimeout(() => this.connect(), 3000);
            }

            startStatsMonitoring() {
                this.statsInterval = setInterval(async () => {
                    if (!this.pc) return;
                    const stats = await this.pc.getStats();
                    let fps = 0, width = 0, height = 0, bytesReceived = 0;

                    stats.forEach(report => {
                        if (report.type === 'inbound-rtp' && report.kind === 'video') {
                            fps = report.framesPerSecond || 0;
                            width = report.frameWidth || 0;
                            height = report.frameHeight || 0;
                            bytesReceived = report.bytesReceived || 0;
                        }
                    });

                    const kbps = Math.round((bytesReceived * 8) / 1000);
                    document.getElementById('stats').textContent =
                        `FPS: ${fps.toFixed(1)} | Resolution: ${width}x${height} | Bitrate: ${kbps} kbps`;
                }, 1000);
            }

            updateStatus(status) {
                const el = document.getElementById('status');
                el.className = status;
                el.textContent = status.charAt(0).toUpperCase() + status.slice(1);
            }

            cleanup() {
                if (this.statsInterval) clearInterval(this.statsInterval);
                if (this.pc) this.pc.close();
                this.pc = null;
            }
        }

        const viewer = new StreamViewer();
    </script>
</body>
</html>'''
