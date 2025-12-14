#!/usr/bin/env python3
"""
iOS Screen Streaming Server

This server receives H264 video frames from an iOS Broadcast Extension
via WebSocket and streams them to web browsers via WebRTC.

Usage:
    python main.py [--test] [--media FILE] [--port PORT] [--no-control]

Options:
    --test          Run in test mode with generated video (no iOS required)
    --media         Stream a media file (mp4, mkv, etc) instead of iOS
    --port          HTTP server port (default: 8999)
    --no-control    Disable device control via WebDriverAgent
"""

import argparse
import asyncio
import logging
import signal
import sys

from config import WEBSOCKET_PORT, HTTP_PORT, FRAME_QUEUE_MAX_SIZE
from frame_queue import FrameQueue
from ios_receiver import iOSReceiver
from webrtc_server import WebRTCServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class StreamingServer:
    """
    Main server class that coordinates iOS receiver and WebRTC server.
    """

    def __init__(self, http_port: int = HTTP_PORT, test_mode: bool = False,
                 media_file: str = None, enable_control: bool = True,
                 wda_host: str = None):
        self.http_port = http_port
        self.test_mode = test_mode
        self.media_file = media_file
        self.enable_control = enable_control
        self.wda_host = wda_host

        # Shared frame queue
        self.frame_queue = FrameQueue(max_size=FRAME_QUEUE_MAX_SIZE)

        # Components
        self.ios_receiver = iOSReceiver(self.frame_queue)
        self.webrtc_server = WebRTCServer(
            self.frame_queue,
            enable_control=enable_control,
            wda_host=wda_host
        )

        if media_file:
            self.webrtc_server.set_media_file(media_file)
        elif test_mode:
            self.webrtc_server.set_test_mode(True)

        # Set up callbacks
        self.ios_receiver.on_connect_callback = self._on_ios_connect
        self.ios_receiver.on_disconnect_callback = self._on_ios_disconnect

        # Running state
        self.running = False

    async def _on_ios_connect(self):
        """Called when iOS app connects."""
        logger.info("iOS broadcast started - video should appear shortly")

    async def _on_ios_disconnect(self):
        """Called when iOS app disconnects."""
        logger.info("iOS broadcast ended")

    async def start(self):
        """Start all server components."""
        self.running = True

        logger.info("=" * 60)
        logger.info("iOS Simulator Screen Streaming Server")
        logger.info("=" * 60)

        if self.media_file:
            logger.info(f"Running in MEDIA FILE MODE - streaming: {self.media_file}")
            logger.info(f"View stream at: http://localhost:{self.http_port}")

            # Only start WebRTC server in media mode
            await self.webrtc_server.start(port=self.http_port)
        elif self.test_mode:
            logger.info("Running in TEST MODE - no iOS connection required")
            logger.info(f"View stream at: http://localhost:{self.http_port}")

            # Only start WebRTC server in test mode
            await self.webrtc_server.start(port=self.http_port)
        else:
            logger.info(f"WebSocket (iOS):  ws://localhost:{WEBSOCKET_PORT}")
            logger.info(f"HTTP (Viewers):   http://0.0.0.0:{self.http_port}")
            if self.enable_control:
                logger.info("Device Control:   Enabled (WebDriverAgent)")
            else:
                logger.info("Device Control:   Disabled")
            logger.info("")
            logger.info("Waiting for iOS Broadcast Extension to connect...")
            logger.info("=" * 60)

            # Start both servers concurrently
            await asyncio.gather(
                self.ios_receiver.start(port=WEBSOCKET_PORT),
                self.webrtc_server.start(port=self.http_port),
            )

    async def shutdown(self):
        """Shutdown all server components."""
        logger.info("Shutting down...")
        self.running = False
        await self.webrtc_server.shutdown()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='iOS Screen Streaming Server')
    parser.add_argument('--test', action='store_true', help='Run in test mode with generated video')
    parser.add_argument('--media', type=str, metavar='FILE', help='Stream a media file (mp4, mkv, etc)')
    parser.add_argument('--port', type=int, default=HTTP_PORT, help=f'HTTP server port (default: {HTTP_PORT})')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--no-control', action='store_true', help='Disable device control via WebDriverAgent')
    parser.add_argument('--wda-host', type=str, metavar='IP', help='WebDriverAgent host IP (default: localhost for USB, or device IP for WiFi)')
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate media file if provided
    if args.media:
        import os
        if not os.path.exists(args.media):
            logger.error(f"Media file not found: {args.media}")
            sys.exit(1)

    # Determine if control should be enabled
    enable_control = not args.no_control

    # Create server
    server = StreamingServer(
        http_port=args.port,
        test_mode=args.test,
        media_file=args.media,
        enable_control=enable_control,
        wda_host=args.wda_host
    )

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(server.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await server.start()
    except asyncio.CancelledError:
        pass
    finally:
        await server.shutdown()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
        sys.exit(0)
