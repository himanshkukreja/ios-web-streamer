#!/usr/bin/env python3
"""
Simulator WebRTC Server - Complete standalone server for iOS Simulator streaming
Streams iOS Simulator screen to web browsers via WebRTC using idb
"""

import asyncio
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SimulatorWebRTCServer:
    """
    Standalone WebRTC server for iOS Simulator streaming.
    """

    def __init__(self, simulator_udid: str, http_port: int = 8999):
        self.simulator_udid = simulator_udid
        self.http_port = http_port

        # Video track
        self.video_track: SimulatorVideoTrack = None

        # WebRTC
        self.peer_connections = set()
        self.relay = MediaRelay()

        # HTTP app
        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self):
        """Set up HTTP routes."""
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_post('/offer', self.handle_offer)
        self.app.router.add_get('/health', self.handle_health)

    async def handle_index(self, request):
        """Serve the viewer page."""
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>iOS Simulator Stream</title>
    <style>
        body {
            background: #1a1a1a;
            color: #fff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }
        h1 { margin-bottom: 30px; }
        #video {
            background: #000;
            border-radius: 8px;
            max-width: 90vw;
            max-height: 80vh;
            box-shadow: 0 10px 40px rgba(0,0,0,0.5);
        }
        #status {
            margin-top: 20px;
            padding: 10px 20px;
            border-radius: 4px;
            background: #333;
        }
        .connecting { color: #ffa500; }
        .connected { color: #00ff00; }
        .error { color: #ff0000; }
    </style>
</head>
<body>
    <h1>📱 iOS Simulator Stream</h1>
    <video id="video" autoplay playsinline muted></video>
    <div id="status" class="connecting">Connecting...</div>

    <script>
        const video = document.getElementById('video');
        const status = document.getElementById('status');

        async function start() {
            try {
                const pc = new RTCPeerConnection({
                    iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
                });

                pc.ontrack = (event) => {
                    console.log('Received track:', event.track);
                    video.srcObject = event.streams[0];
                    status.textContent = '✅ Connected';
                    status.className = 'connected';
                };

                pc.oniceconnectionstatechange = () => {
                    console.log('ICE state:', pc.iceConnectionState);
                    if (pc.iceConnectionState === 'disconnected' || pc.iceConnectionState === 'failed') {
                        status.textContent = '❌ Disconnected';
                        status.className = 'error';
                    }
                };

                // Add transceiver to receive video (required for recvonly offer)
                pc.addTransceiver('video', { direction: 'recvonly' });

                // Create offer
                const offer = await pc.createOffer();
                await pc.setLocalDescription(offer);

                console.log('Sending offer, SDP length:', offer.sdp.length);

                // Send offer to server
                const response = await fetch('/offer', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        sdp: pc.localDescription.sdp,
                        type: pc.localDescription.type
                    })
                });

                const answer = await response.json();
                if (answer.error) {
                    throw new Error(answer.error);
                }

                console.log('Received answer, SDP length:', answer.sdp.length);
                await pc.setRemoteDescription(answer);

                status.textContent = 'Waiting for video...';

            } catch (e) {
                console.error('Error:', e);
                status.textContent = '❌ Error: ' + e.message;
                status.className = 'error';
            }
        }

        start();
    </script>
</body>
</html>
        """
        return web.Response(content_type='text/html', text=html)

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
        # CAPTURE METHOD CONFIGURATION
        # ============================================================
        # Available options:
        #   "quartz"   - Fast Quartz window capture (~50-80ms latency, ~45 FPS)
        #   "simctl"   - simctl screenshot (~250-350ms latency, ~12 FPS)
        #   "idb_h264" - idb H.264 stream (30 FPS, may have corruption on transitions)
        #
        # Recommended: "quartz" for best performance
        # ============================================================
        CAPTURE_METHOD = "simctl"

        logger.info(f"🚀 Starting video stream (capture method: {CAPTURE_METHOD})...")

        self.video_track = SimulatorVideoTrack(
            simulator_udid=self.simulator_udid,
            fps=30,
            port=10882,
            capture_method=CAPTURE_METHOD
        )

        await self.video_track.start()

        # Log the pipeline being used
        if CAPTURE_METHOD == "quartz":
            logger.info("   Pipeline: Quartz window capture → frame queue → aiortc H.264")
        elif CAPTURE_METHOD == "simctl":
            logger.info("   Pipeline: simctl screenshot → decode → frame queue → aiortc H.264")
        else:
            logger.info("   Pipeline: idb H.264 → decode → frame queue → aiortc H.264")

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
