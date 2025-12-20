#!/usr/bin/env python3
"""
IDB Video Streamer - Captures video from iOS Simulator via idb_companion
and provides frames for WebRTC streaming.
"""

import asyncio
import logging
import struct
import time
from typing import AsyncGenerator, Optional
import fractions

from grpclib.client import Channel
from idb.grpc.idb_pb2 import VideoStreamRequest, Payload, TargetDescriptionRequest
from idb.grpc.idb_grpc import CompanionServiceStub
from idb.common.types import VideoFormat

from aiortc import VideoStreamTrack
from av import VideoFrame
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IDBVideoStreamTrack(VideoStreamTrack):
    """
    Custom VideoStreamTrack that receives H.264 frames from idb and
    converts them to VideoFrames for WebRTC.
    """

    def __init__(self, host: str = "localhost", port: int = 10882, fps: int = 30):
        super().__init__()
        self.host = host
        self.port = port
        self.fps = fps
        self._channel: Optional[Channel] = None
        self._stub: Optional[CompanionServiceStub] = None
        self._stream: Optional[AsyncGenerator] = None
        self._timestamp = 0
        self._running = False
        self._frame_queue = asyncio.Queue(maxsize=10)
        self._consumer_task: Optional[asyncio.Task] = None

    async def connect(self):
        """Connect to idb_companion."""
        logger.info(f"Connecting to idb_companion at {self.host}:{self.port}")

        # Create gRPC channel
        self._channel = Channel(self.host, self.port)
        self._stub = CompanionServiceStub(self._channel)

        # Verify connection by getting target description
        try:
            target_request = TargetDescriptionRequest()
            target_response = await self._stub.describe(target_request)
            logger.info(f"Connected to simulator: {target_response.target_description.name}")
            logger.info(f"UDID: {target_response.target_description.udid}")
        except Exception as e:
            logger.error(f"Failed to connect to idb_companion: {e}")
            raise

    async def start_stream(self):
        """Start the video stream from idb_companion."""
        if self._running:
            logger.warning("Stream already running")
            return

        logger.info(f"Starting video stream at {self.fps} fps")
        self._running = True

        # Create video stream request
        request = VideoStreamRequest()
        request.start.format = VideoFormat.H264.value  # H.264 format
        request.start.fps = self.fps
        request.start.compression_quality = 0.8

        try:
            # Start video stream
            self._stream = self._stub.video_stream(request)

            # Start consumer task
            self._consumer_task = asyncio.create_task(self._consume_stream())

            logger.info("✅ Video stream started successfully")

        except Exception as e:
            logger.error(f"Failed to start video stream: {e}")
            self._running = False
            raise

    async def _consume_stream(self):
        """Consume video stream and put frames into queue."""
        frame_count = 0
        try:
            async for payload in self._stream:
                if not self._running:
                    break

                frame_count += 1

                # payload.payload contains the raw frame data
                frame_data = payload.payload

                if frame_count % 30 == 0:  # Log every second
                    logger.debug(f"Received frame {frame_count}: {len(frame_data)} bytes")

                # Put frame in queue (will block if queue is full)
                try:
                    await asyncio.wait_for(
                        self._frame_queue.put(frame_data),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Frame queue full, dropping frame {frame_count}")

        except Exception as e:
            logger.error(f"Stream consumer error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._running = False
            logger.info(f"Stream consumer stopped after {frame_count} frames")

    async def recv(self) -> VideoFrame:
        """
        Receive next video frame for WebRTC.
        Called by aiortc when it needs a frame.
        """
        if not self._running:
            raise Exception("Stream not started")

        # Get frame from queue
        try:
            frame_data = await asyncio.wait_for(
                self._frame_queue.get(),
                timeout=2.0
            )
        except asyncio.TimeoutError:
            # No frame available, return blank frame
            logger.warning("Frame timeout, returning blank frame")
            return self._create_blank_frame()

        # Convert raw BGRA data to VideoFrame
        # Default simulator resolution (can be detected from first frame)
        # iPhone 16 Pro: 1179x2556 (but simulator window may differ)
        # For now, assume a common size
        width, height = 390, 844  # iPhone 14 default portrait

        try:
            # Parse frame data
            # RBGA format: width * height * 4 bytes
            expected_size = width * height * 4

            if len(frame_data) != expected_size:
                # Try to detect dimensions from data size
                total_pixels = len(frame_data) // 4
                # Common simulator sizes
                dimensions = [
                    (390, 844),   # iPhone 14/15
                    (428, 926),   # iPhone 14 Pro Max
                    (393, 852),   # iPhone 16 Pro
                ]
                for w, h in dimensions:
                    if w * h == total_pixels:
                        width, height = w, h
                        break

            # Convert to numpy array
            arr = np.frombuffer(frame_data[:width*height*4], dtype=np.uint8).reshape((height, width, 4))
            bgr = arr[:, :, :3]  # Drop alpha channel

            # Create VideoFrame
            frame = VideoFrame.from_ndarray(bgr, format='bgr24')

            # Set timestamp
            pts, time_base = await self._next_timestamp()
            frame.pts = pts
            frame.time_base = time_base

            return frame

        except Exception as e:
            logger.error(f"Error converting frame: {e}")
            import traceback
            traceback.print_exc()
            return self._create_blank_frame()

    async def _next_timestamp(self):
        """Generate next timestamp for video frame."""
        VIDEO_CLOCK_RATE = 90000
        VIDEO_PTIME = 1 / self.fps
        self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
        return self._timestamp, fractions.Fraction(1, VIDEO_CLOCK_RATE)

    def _create_blank_frame(self) -> VideoFrame:
        """Create a blank video frame."""
        width, height = 390, 844
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        frame = VideoFrame.from_ndarray(arr, format='bgr24')
        pts, time_base = asyncio.run(self._next_timestamp())
        frame.pts = pts
        frame.time_base = time_base
        return frame

    async def stop(self):
        """Stop the video stream."""
        logger.info("Stopping video stream")
        self._running = False

        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        if self._channel:
            self._channel.close()

        logger.info("Video stream stopped")


async def test_stream():
    """Test the IDB video stream."""
    print("=" * 60)
    print("IDB Video Stream Test")
    print("=" * 60)

    track = IDBVideoStreamTrack(host="localhost", port=10882, fps=30)

    try:
        # Connect
        await track.connect()
        print("✅ Connected to idb_companion")

        # Start stream
        await track.start_stream()
        print("✅ Video stream started")

        # Receive some frames
        print("\n📊 Receiving frames...")
        for i in range(30):  # Get 1 second of video
            frame = await track.recv()
            print(f"Frame {i+1}: {frame.width}x{frame.height}, pts={frame.pts}")
            await asyncio.sleep(1/30)  # 30 fps

        print("\n✅ Test successful!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await track.stop()


if __name__ == "__main__":
    asyncio.run(test_stream())
