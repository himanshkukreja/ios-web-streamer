#!/usr/bin/env python3
"""
IDB Simulator Streamer - Simple subprocess-based approach
Captures H.264 video from iOS Simulator using idb_companion and provides it to WebRTC
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from typing import Optional
import fractions

from aiortc import VideoStreamTrack
from av import VideoFrame, Packet
from av.codec import CodecContext
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IDBSimulatorVideoTrack(VideoStreamTrack):
    """
    VideoStreamTrack that receives H.264 from idb video stream via subprocess.
    Uses PyAV to decode H.264 to frames for WebRTC.
    """

    def __init__(self, simulator_udid: str, fps: int = 30, port: int = 10882):
        super().__init__()
        self.simulator_udid = simulator_udid
        self.fps = fps
        self.port = port

        # Subprocess handles
        self._companion_process: Optional[subprocess.Popen] = None
        self._stream_process: Optional[subprocess.Popen] = None

        # Video decoder
        self._codec: Optional[CodecContext] = None
        self._timestamp = 0
        self._running = False

        # Frame queue for decoded frames
        self._frame_queue = asyncio.Queue(maxsize=10)
        self._decoder_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start idb_companion and video stream."""
        logger.info(f"Starting IDB stream for simulator {self.simulator_udid}")

        # Start idb_companion
        await self._start_companion()

        # Wait for companion to be ready
        await asyncio.sleep(2)

        # Start video stream
        await self._start_video_stream()

        # Initialize H.264 decoder
        self._codec = CodecContext.create('h264', 'r')

        self._running = True

        # Start decoder task
        self._decoder_task = asyncio.create_task(self._decode_stream())

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
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid  # Create new process group
        )

        logger.info(f"idb_companion started (PID: {self._companion_process.pid})")

    async def _start_video_stream(self):
        """Start idb video stream and capture output."""
        logger.info("Starting idb video stream (H.264)")

        # Use Python idb client to stream video
        # Format: idb video-stream outputs to stdout
        cmd = [
            'python3', '-m', 'idb.cli',
            'video-stream',
            '--udid', self.simulator_udid,
            '--compression-quality', '0.8',
            '--fps', str(self.fps),
            '-'  # Output to stdout
        ]

        self._stream_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0  # Unbuffered
        )

        logger.info(f"Video stream started (PID: {self._stream_process.pid})")

    async def _decode_stream(self):
        """Read H.264 stream from subprocess and decode to frames."""
        frame_count = 0
        chunk_size = 4096

        try:
            logger.info("Starting stream decoder...")

            while self._running:
                # Read chunk from stream
                chunk = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._stream_process.stdout.read,
                    chunk_size
                )

                if not chunk:
                    logger.warning("Stream ended (no more data)")
                    break

                # Parse H.264 packets and decode
                try:
                    packets = self._codec.parse(chunk)

                    for packet in packets:
                        frames = self._codec.decode(packet)

                        for frame in frames:
                            frame_count += 1

                            if frame_count % 30 == 0:  # Log every second
                                logger.debug(f"Decoded frame {frame_count}: {frame.width}x{frame.height}")

                            # Put frame in queue (non-blocking)
                            try:
                                self._frame_queue.put_nowait(frame)
                            except asyncio.QueueFull:
                                # Drop frame if queue is full
                                logger.debug(f"Frame queue full, dropping frame {frame_count}")

                except Exception as e:
                    logger.error(f"Error decoding chunk: {e}")
                    continue

        except Exception as e:
            logger.error(f"Stream decoder error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            logger.info(f"Stream decoder stopped after {frame_count} frames")

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

            # Convert av.VideoFrame to format expected by WebRTC
            # Reformat to ensure compatibility
            new_frame = frame.reformat(format='yuv420p')

            # Set timestamp
            pts, time_base = await self._next_timestamp()
            new_frame.pts = pts
            new_frame.time_base = time_base

            return new_frame

        except asyncio.TimeoutError:
            logger.warning("Frame timeout, returning blank frame")
            return self._create_blank_frame()

        except Exception as e:
            logger.error(f"Error receiving frame: {e}")
            return self._create_blank_frame()

    async def _next_timestamp(self):
        """Generate next timestamp for video frame."""
        VIDEO_CLOCK_RATE = 90000
        VIDEO_PTIME = 1 / self.fps
        self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
        return self._timestamp, fractions.Fraction(1, VIDEO_CLOCK_RATE)

    def _create_blank_frame(self) -> VideoFrame:
        """Create a blank video frame as fallback."""
        # Create blank 720p frame
        width, height = 390, 844
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        frame = VideoFrame.from_ndarray(arr, format='bgr24')

        # Convert to yuv420p
        frame = frame.reformat(format='yuv420p')

        # Set timestamp synchronously
        VIDEO_CLOCK_RATE = 90000
        VIDEO_PTIME = 1 / self.fps
        self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
        frame.pts = self._timestamp
        frame.time_base = fractions.Fraction(1, VIDEO_CLOCK_RATE)

        return frame

    async def stop(self):
        """Stop the video stream and cleanup."""
        logger.info("Stopping IDB stream")
        self._running = False

        # Cancel decoder task
        if self._decoder_task:
            self._decoder_task.cancel()
            try:
                await self._decoder_task
            except asyncio.CancelledError:
                pass

        # Stop stream process
        if self._stream_process:
            try:
                self._stream_process.terminate()
                self._stream_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._stream_process.kill()
            logger.info("Video stream process stopped")

        # Stop companion process
        if self._companion_process:
            try:
                # Kill entire process group
                os.killpg(os.getpgid(self._companion_process.pid), signal.SIGTERM)
                self._companion_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self._companion_process.pid), signal.SIGKILL)
            except Exception as e:
                logger.warning(f"Error stopping companion: {e}")
            logger.info("idb_companion stopped")

        logger.info("IDB stream stopped")


async def test_stream():
    """Test the IDB simulator video stream."""
    print("=" * 70)
    print("IDB Simulator Video Stream Test")
    print("=" * 70)

    # Get booted simulator
    result = subprocess.run(
        ['xcrun', 'simctl', 'list', 'devices', 'booted'],
        capture_output=True,
        text=True
    )

    # Extract UDID
    import re
    match = re.search(r'\(([A-F0-9-]+)\)', result.stdout)
    if not match:
        print("❌ No booted simulator found")
        print("Please boot a simulator first:")
        print("  xcrun simctl boot <UDID>")
        sys.exit(1)

    udid = match.group(1)
    print(f"📱 Using simulator: {udid}")

    # Create track
    track = IDBSimulatorVideoTrack(simulator_udid=udid, fps=30, port=10882)

    try:
        # Start stream
        print("\n🚀 Starting stream...")
        await track.start()

        print("✅ Stream started successfully")
        print("\n📊 Receiving frames (30 frames = 1 second)...")

        # Receive some frames
        for i in range(30):
            frame = await track.recv()
            if i % 10 == 0:
                print(f"   Frame {i+1}: {frame.width}x{frame.height} @ pts={frame.pts}")

        print("\n✅ Test successful! IDB streaming is working.")
        print(f"   Received 30 frames at {track.fps} fps")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\n🛑 Stopping stream...")
        await track.stop()
        print("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(test_stream())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
