#!/usr/bin/env python3
"""
Simulator Receiver - Receives video from iOS Simulator via idb and feeds to WebRTC
"""

import asyncio
import logging
import os
import signal
import subprocess
from typing import Optional
import fractions

from grpclib.client import Channel
from idb.grpc.idb_pb2 import CompanionInfo
from idb.grpc.idb_grpc import CompanionServiceStub
from idb.grpc.client import Client
from idb.common.types import TCPAddress, VideoFormat, CompanionInfo as CompanionInfoType

from aiortc import VideoStreamTrack
from av import VideoFrame
from av.codec import CodecContext
import numpy as np

logger = logging.getLogger(__name__)


class SimulatorVideoTrack(VideoStreamTrack):
    """
    VideoStreamTrack that receives H.264 from iOS Simulator via idb.
    Integrates with existing WebRTC infrastructure.
    """

    kind = "video"

    def __init__(self, simulator_udid: str, fps: int = 30, port: int = 10882):
        super().__init__()
        self.simulator_udid = simulator_udid
        self.fps = fps
        self.port = port

        # IDB components
        self._companion_process: Optional[subprocess.Popen] = None
        self._client: Optional[Client] = None
        self._channel: Optional[Channel] = None

        # Video decoder
        self._codec: Optional[CodecContext] = None
        self._timestamp = 0
        self._running = False

        # Frame queue (small size for low latency)
        self._frame_queue = asyncio.Queue(maxsize=2)
        self._decoder_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start idb_companion and begin streaming."""
        logger.info(f"🚀 Starting IDB stream for simulator {self.simulator_udid}")

        # Start idb_companion
        await self._start_companion()

        # Wait for companion to initialize
        await asyncio.sleep(2)

        # Connect client
        await self._connect_client()

        # Initialize H.264 decoder with optimized settings
        self._codec = CodecContext.create('h264', 'r')
        # Configure decoder for low latency and quality
        self._codec.thread_count = 1
        self._codec.thread_type = 0
        self._codec.options = {
            'flags': '+low_delay',
            'flags2': '+fast',
        }

        self._running = True

        # Start decoder task
        self._decoder_task = asyncio.create_task(self._stream_and_decode())

        logger.info("✅ IDB stream started successfully")

    async def _start_companion(self):
        """Start idb_companion process."""
        logger.info(f"Starting idb_companion on port {self.port}")

        cmd = [
            'idb_companion',
            '--udid', self.simulator_udid,
            '--grpc-port', str(self.port)
        ]

        self._companion_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )

        logger.info(f"idb_companion started (PID: {self._companion_process.pid})")

    async def _connect_client(self):
        """Connect to idb_companion via gRPC."""
        logger.info(f"Connecting to idb_companion at localhost:{self.port}")

        # Create gRPC channel
        self._channel = Channel('localhost', self.port)
        stub = CompanionServiceStub(self._channel)

        # Create companion info
        address = TCPAddress(host='localhost', port=self.port)
        companion = CompanionInfoType(
            udid=self.simulator_udid,
            address=address,
            is_local=True,
            pid=self._companion_process.pid
        )

        # Create idb client
        self._client = Client(
            stub=stub,
            companion=companion,
            logger=logger
        )

        logger.info("✅ Connected to idb_companion")

    async def _stream_and_decode(self):
        """Stream H.264 from idb and decode to frames."""
        frame_count = 0

        try:
            logger.info("Starting H.264 stream from idb...")

            # Stream video using idb client with highest quality settings
            async for h264_data in self._client.stream_video(
                output_file=None,  # Stream to memory
                fps=self.fps,
                format=VideoFormat.H264,
                compression_quality=1.0,  # Maximum quality (was 0.8)
                scale_factor=1.0
            ):
                if not self._running:
                    break

                # Decode H.264 data
                try:
                    packets = self._codec.parse(h264_data)

                    for packet in packets:
                        frames = self._codec.decode(packet)

                        for frame in frames:
                            frame_count += 1

                            if frame_count % 30 == 0:  # Log every second
                                logger.info(f"📹 Decoded frame {frame_count}: {frame.width}x{frame.height}")

                            # Put frame in queue
                            try:
                                self._frame_queue.put_nowait(frame)
                            except asyncio.QueueFull:
                                # Drop frame if queue is full (backpressure)
                                pass

                except Exception as e:
                    logger.error(f"Error decoding H.264: {e}")
                    continue

        except Exception as e:
            logger.error(f"Stream error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            logger.info(f"Stream stopped after {frame_count} frames")

    async def recv(self) -> VideoFrame:
        """
        Receive next video frame for WebRTC.
        Called by aiortc when it needs a frame.
        """
        if not self._running:
            raise Exception("Stream not started")

        try:
            # Get frame from queue with timeout
            frame = await asyncio.wait_for(
                self._frame_queue.get(),
                timeout=2.0
            )

            # Convert to yuv420p for WebRTC compatibility
            new_frame = frame.reformat(format='yuv420p')

            # Set timestamp
            pts, time_base = await self._next_timestamp()
            new_frame.pts = pts
            new_frame.time_base = time_base

            return new_frame

        except asyncio.TimeoutError:
            # No frame available, return blank frame
            return self._create_blank_frame()

    async def _next_timestamp(self):
        """Generate next timestamp for video frame."""
        VIDEO_CLOCK_RATE = 90000
        VIDEO_PTIME = 1 / self.fps
        self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
        return self._timestamp, fractions.Fraction(1, VIDEO_CLOCK_RATE)

    def _create_blank_frame(self) -> VideoFrame:
        """Create a blank video frame as fallback."""
        width, height = 390, 844  # Default iPhone size
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        frame = VideoFrame.from_ndarray(arr, format='bgr24')
        frame = frame.reformat(format='yuv420p')

        VIDEO_CLOCK_RATE = 90000
        VIDEO_PTIME = 1 / self.fps
        self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
        frame.pts = self._timestamp
        frame.time_base = fractions.Fraction(1, VIDEO_CLOCK_RATE)

        return frame

    async def stop(self):
        """Stop the video stream and cleanup resources."""
        logger.info("Stopping IDB stream")
        self._running = False

        # Cancel decoder task
        if self._decoder_task:
            self._decoder_task.cancel()
            try:
                await self._decoder_task
            except asyncio.CancelledError:
                pass

        # Close gRPC channel
        if self._channel:
            self._channel.close()

        # Stop companion process
        if self._companion_process:
            try:
                os.killpg(os.getpgid(self._companion_process.pid), signal.SIGTERM)
                self._companion_process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"Error stopping companion: {e}")

        logger.info("IDB stream stopped")


class SimulatorReceiver:
    """
    Simulator Receiver - Manages simulator video streaming via idb.
    Provides a similar interface to iOSReceiver for integration with existing server.
    """

    def __init__(self, simulator_udid: str, port: int = 10882):
        self.simulator_udid = simulator_udid
        self.port = port
        self.video_track: Optional[SimulatorVideoTrack] = None
        self.device_info = {
            "deviceName": "iOS Simulator",
            "deviceModel": "Simulator",
            "systemName": "iOS",
            "systemVersion": "Unknown",
            "modelIdentifier": "Simulator",
            "screenResolution": "Unknown",
            "screenScale": "Unknown",
            "batteryLevel": -1,
            "batteryState": "unknown",
            "sourceType": "simulator",
            "udid": simulator_udid
        }

        # Callbacks
        self.on_connect_callback = None
        self.on_disconnect_callback = None

    async def start(self):
        """Start receiving video from simulator."""
        logger.info(f"📱 Starting simulator receiver for UDID: {self.simulator_udid}")

        # Create video track
        self.video_track = SimulatorVideoTrack(
            simulator_udid=self.simulator_udid,
            fps=30,
            port=self.port
        )

        # Start streaming
        await self.video_track.start()

        # Call connect callback
        if self.on_connect_callback:
            await self.on_connect_callback()

        logger.info("✅ Simulator receiver started")

    async def stop(self):
        """Stop receiving video."""
        if self.video_track:
            await self.video_track.stop()

        # Call disconnect callback
        if self.on_disconnect_callback:
            await self.on_disconnect_callback()

        logger.info("Simulator receiver stopped")

    def get_video_track(self) -> Optional[SimulatorVideoTrack]:
        """Get the video track for WebRTC."""
        return self.video_track
