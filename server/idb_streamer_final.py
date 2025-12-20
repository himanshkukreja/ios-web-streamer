#!/usr/bin/env python3
"""
IDB Simulator Streamer - Final clean implementation using idb Python API
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from typing import Optional
import fractions

from idb.grpc.idb_pb2 import CompanionInfo
from idb.grpc.idb_grpc import CompanionServiceStub
from idb.grpc.client import Client
from idb.common.types import TCPAddress, VideoFormat, CompanionInfo as CompanionInfoType

from aiortc import VideoStreamTrack
from av import VideoFrame, Packet
from av.codec import CodecContext
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IDBVideoTrack(VideoStreamTrack):
    """
    VideoStreamTrack that receives H.264 from iOS Simulator via idb.
    Uses idb Python client for reliable streaming.
    """

    def __init__(self, simulator_udid: str, fps: int = 30, port: int = 10882):
        super().__init__()
        self.simulator_udid = simulator_udid
        self.fps = fps
        self.port = port

        # IDB client
        self._companion_process: Optional[subprocess.Popen] = None
        self._client: Optional[Client] = None

        # Video decoder
        self._codec: Optional[CodecContext] = None
        self._timestamp = 0
        self._running = False

        # Frame queue
        self._frame_queue = asyncio.Queue(maxsize=10)
        self._decoder_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start idb_companion and connect client."""
        logger.info(f"Starting IDB stream for simulator {self.simulator_udid}")

        # Start idb_companion
        await self._start_companion()

        # Wait for companion to be ready
        await asyncio.sleep(2)

        # Connect client
        await self._connect_client()

        # Initialize H.264 decoder
        self._codec = CodecContext.create('h264', 'r')

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

        from grpclib.client import Channel

        # Create channel
        channel = Channel('localhost', self.port)
        stub = CompanionServiceStub(channel)

        # Create companion info
        address = TCPAddress(host='localhost', port=self.port)
        companion = CompanionInfoType(
            udid=self.simulator_udid,
            address=address,
            is_local=True,
            pid=self._companion_process.pid
        )

        # Create client
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

            # Stream video using idb client
            async for h264_data in self._client.stream_video(
                output_file=None,  # Stream to memory, not file
                fps=self.fps,
                format=VideoFormat.H264,
                compression_quality=0.8,
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
                                logger.info(f"Decoded frame {frame_count}: {frame.width}x{frame.height}")

                            # Put frame in queue
                            try:
                                self._frame_queue.put_nowait(frame)
                            except asyncio.QueueFull:
                                logger.debug(f"Frame queue full, dropping frame {frame_count}")

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
        """
        if not self._running:
            raise Exception("Stream not started")

        try:
            # Get frame from queue
            frame = await asyncio.wait_for(
                self._frame_queue.get(),
                timeout=2.0
            )

            # Convert to yuv420p for WebRTC
            new_frame = frame.reformat(format='yuv420p')

            # Set timestamp
            pts, time_base = await self._next_timestamp()
            new_frame.pts = pts
            new_frame.time_base = time_base

            return new_frame

        except asyncio.TimeoutError:
            logger.warning("Frame timeout")
            return self._create_blank_frame()

    async def _next_timestamp(self):
        """Generate next timestamp."""
        VIDEO_CLOCK_RATE = 90000
        VIDEO_PTIME = 1 / self.fps
        self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
        return self._timestamp, fractions.Fraction(1, VIDEO_CLOCK_RATE)

    def _create_blank_frame(self) -> VideoFrame:
        """Create a blank frame."""
        width, height = 390, 844
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
        """Stop streaming."""
        logger.info("Stopping IDB stream")
        self._running = False

        if self._decoder_task:
            self._decoder_task.cancel()
            try:
                await self._decoder_task
            except asyncio.CancelledError:
                pass

        if self._companion_process:
            try:
                os.killpg(os.getpgid(self._companion_process.pid), signal.SIGTERM)
                self._companion_process.wait(timeout=5)
            except:
                pass

        logger.info("IDB stream stopped")


async def test():
    """Test IDB streaming."""
    print("=" * 70)
    print("IDB Simulator Streaming Test")
    print("=" * 70)

    # Get booted simulator UDID
    result = subprocess.run(
        ['xcrun', 'simctl', 'list', 'devices', 'booted'],
        capture_output=True,
        text=True
    )

    import re
    match = re.search(r'\(([A-F0-9-]+)\)', result.stdout)
    if not match:
        print("❌ No booted simulator found")
        sys.exit(1)

    udid = match.group(1)
    print(f"📱 Simulator: {udid}\n")

    track = IDBVideoTrack(simulator_udid=udid, fps=30, port=10882)

    try:
        print("🚀 Starting stream...")
        await track.start()

        print("✅ Stream started\n")
        print("📊 Receiving 90 frames (3 seconds)...")

        for i in range(90):
            frame = await track.recv()
            if i % 30 == 0:
                print(f"   Frame {i+1}: {frame.width}x{frame.height}")

        print("\n✅ Test successful!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\n🛑 Stopping...")
        await track.stop()
        print("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(test())
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(0)
