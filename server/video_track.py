"""
Custom video track for streaming H264 frames via WebRTC.

Performance optimizations:
- Use direct YUV plane copying instead of RGB conversion
- Minimize memory allocations by reusing buffers where possible
- Single-threaded decoder to prevent segfaults in async context
"""

import asyncio
import logging
import threading
import time
from fractions import Fraction
from typing import Optional

import av
import numpy as np
from aiortc import VideoStreamTrack
from aiortc.mediastreams import VideoFrame as RTCVideoFrame
from av import VideoFrame
from av.codec import CodecContext

from frame_queue import FrameQueue, VideoFrame as QueueVideoFrame
from config import DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FPS

logger = logging.getLogger(__name__)

# Disable threading in FFmpeg to prevent segfaults
av.logging.set_level(av.logging.ERROR)


def copy_frame_fast(src_frame: VideoFrame) -> VideoFrame:
    """
    Create an efficient deep copy of a VideoFrame.

    This avoids the expensive rgb24 conversion by copying YUV planes directly.
    Much faster than to_ndarray(rgb24) -> from_ndarray -> reformat(yuv420p).
    """
    # Get dimensions
    width = src_frame.width
    height = src_frame.height

    # Ensure source is in yuv420p format
    if src_frame.format.name != 'yuv420p':
        src_frame = src_frame.reformat(format='yuv420p')

    # Create a new frame with same dimensions
    dst_frame = VideoFrame(width, height, 'yuv420p')

    # Copy each plane's data (Y, U, V)
    # We need to handle stride (line_size) which may include padding
    for i in range(3):
        src_plane = src_frame.planes[i]
        dst_plane = dst_frame.planes[i]

        # Get plane dimensions accounting for chroma subsampling
        plane_height = height if i == 0 else height // 2
        plane_width = width if i == 0 else width // 2

        # Read source data using the plane's line_size (stride)
        src_stride = src_plane.line_size
        dst_stride = dst_plane.line_size

        # Get the raw buffer data
        src_buffer = bytes(src_plane)

        if src_stride == dst_stride:
            # Strides match - direct copy
            dst_plane.update(src_buffer)
        else:
            # Different strides - need to copy row by row
            dst_buffer = bytearray(len(bytes(dst_plane)))
            for row in range(plane_height):
                src_start = row * src_stride
                src_end = src_start + plane_width
                dst_start = row * dst_stride
                dst_buffer[dst_start:dst_start + plane_width] = src_buffer[src_start:src_end]
            dst_plane.update(bytes(dst_buffer))

    return dst_frame


class iOSVideoTrack(VideoStreamTrack):
    """
    Custom video track that reads H264 frames from the queue
    and provides them to WebRTC.
    """

    kind = "video"

    def __init__(self, frame_queue: FrameQueue):
        super().__init__()
        self.frame_queue = frame_queue

        # Decoder state
        self.decoder: Optional[CodecContext] = None
        self.decoder_initialized = False
        self._decoder_lock = threading.Lock()  # Protect decoder access

        # Timing
        self.start_time: Optional[float] = None
        self.frame_count = 0
        self.pts = 0
        self.time_base = Fraction(1, 90000)  # Standard RTP time base

        # Frame dimensions (will be updated from actual frames)
        self.width = DEFAULT_WIDTH
        self.height = DEFAULT_HEIGHT

        # Last frame for repeat on underflow
        self.last_frame: Optional[VideoFrame] = None
        self._last_frame_lock = threading.Lock()  # Protect last_frame access

        # Stored SPS/PPS for decoder
        self.stored_sps_pps: Optional[bytes] = None

        # Wait for first keyframe before decoding
        self.received_first_keyframe = False

        # Stats
        self.decode_errors = 0
        self.frames_sent = 0

    def _init_decoder(self, sps_pps: Optional[bytes] = None):
        """Initialize the H264 decoder."""
        with self._decoder_lock:
            try:
                self.decoder = av.CodecContext.create('h264', 'r')
                # Disable all threading in FFmpeg to prevent segfaults
                # This is critical for stability when running in async context
                self.decoder.thread_count = 1
                self.decoder.thread_type = 0  # Disable threading entirely
                self.decoder.skip_frame = 'NONKEY'  # Skip non-key frames on high load
                self.decoder.options = {
                    'flags': '+low_delay',
                    'flags2': '+fast',
                    'threads': '1',  # Also set via options
                }

                # Store SPS/PPS for later use
                if sps_pps:
                    self.stored_sps_pps = sps_pps
                    logger.info(f"Stored SPS/PPS: {len(sps_pps)} bytes")
                    # Log first few bytes to help debug
                    hex_preview = sps_pps[:20].hex() if len(sps_pps) >= 20 else sps_pps.hex()
                    logger.debug(f"SPS/PPS data preview: {hex_preview}")

                self.decoder_initialized = True
                logger.info("H264 decoder initialized (single-threaded mode)")
            except Exception as e:
                logger.error(f"Failed to initialize decoder: {e}")
                self.decoder = None

    def _decode_frame(self, frame_data: QueueVideoFrame) -> Optional[VideoFrame]:
        """Decode H264 NAL units to a video frame."""
        # Skip P-frames until we receive a keyframe
        if not self.received_first_keyframe:
            if not frame_data.is_keyframe:
                if self.frames_sent == 0:
                    logger.info("Waiting for first keyframe before decoding...")
                return None
            else:
                self.received_first_keyframe = True
                logger.info("Received first keyframe - starting decode")

        if not self.decoder_initialized:
            self._init_decoder(frame_data.sps_pps)

        if not self.decoder:
            return None

        with self._decoder_lock:
            try:
                data = frame_data.data

                # Debug logging for first few decoded frames
                if self.frames_sent < 5:
                    hex_preview = data[:30].hex() if len(data) >= 30 else data.hex()
                    logger.info(f"Decoding frame {self.frames_sent}: keyframe={frame_data.is_keyframe}, "
                               f"size={len(data)}, preview={hex_preview}")

                # For keyframes, we need SPS/PPS to precede the IDR NAL
                # The iOS app sends SPS/PPS separately as config, then the keyframe
                # We need to prepend SPS/PPS to the keyframe for the decoder
                if frame_data.is_keyframe:
                    sps_pps = frame_data.sps_pps or self.stored_sps_pps
                    if sps_pps:
                        # Prepend SPS/PPS to the keyframe data
                        data = sps_pps + data
                        logger.info(f"Prepended SPS/PPS ({len(sps_pps)} bytes) to keyframe ({len(frame_data.data)} bytes)")

                # Create packet from NAL data (should be in Annex-B format with start codes)
                packet = av.Packet(data)

                # Decode - wrap in try/except to catch any FFmpeg crashes
                try:
                    decoded_frames = self.decoder.decode(packet)
                except Exception as decode_err:
                    logger.error(f"FFmpeg decode error: {decode_err}")
                    return None

                if decoded_frames:
                    frame = decoded_frames[0]

                    # Update dimensions if changed
                    if frame.width != self.width or frame.height != self.height:
                        self.width = frame.width
                        self.height = frame.height
                        logger.info(f"Video dimensions: {self.width}x{self.height}")

                    return frame

                return None

            except Exception as e:
                self.decode_errors += 1
                if self.decode_errors <= 10:
                    # More detailed error logging
                    hex_preview = frame_data.data[:30].hex() if len(frame_data.data) >= 30 else frame_data.data.hex()
                    logger.warning(f"Decode error ({self.decode_errors}): {e}")
                    logger.warning(f"  Frame data: keyframe={frame_data.is_keyframe}, size={len(frame_data.data)}")
                    logger.warning(f"  Data preview: {hex_preview}")
                elif self.decode_errors == 11:
                    logger.warning("Suppressing further decode errors...")
                return None

    def _create_blank_frame(self) -> VideoFrame:
        """Create a blank frame for when no video is available."""
        try:
            # Use actual video dimensions for proper aspect ratio
            width = self.width
            height = self.height

            # Create YUV420P frame directly (more efficient than RGB conversion)
            # Y=16 is black in YUV, U=V=128 is neutral chroma
            frame = VideoFrame(width, height, 'yuv420p')

            # Fill each plane accounting for stride/line_size
            # Plane 0: Y (full resolution)
            plane = frame.planes[0]
            stride = plane.line_size
            buffer_size = len(bytes(plane))

            if stride == width:
                # No padding - direct fill
                y_data = np.full((height, width), 16, dtype=np.uint8)
                plane.update(y_data.tobytes())
            else:
                # Has padding - fill row by row
                buffer = bytearray(buffer_size)
                for row in range(height):
                    start = row * stride
                    buffer[start:start + width] = bytes([16] * width)
                plane.update(bytes(buffer))

            # Plane 1 & 2: U and V (half resolution)
            for i in [1, 2]:
                plane = frame.planes[i]
                stride = plane.line_size
                buffer_size = len(bytes(plane))
                uv_height = height // 2
                uv_width = width // 2

                if stride == uv_width:
                    # No padding - direct fill
                    uv_data = np.full((uv_height, uv_width), 128, dtype=np.uint8)
                    plane.update(uv_data.tobytes())
                else:
                    # Has padding - fill row by row
                    buffer = bytearray(buffer_size)
                    for row in range(uv_height):
                        start = row * stride
                        buffer[start:start + uv_width] = bytes([128] * uv_width)
                    plane.update(bytes(buffer))

            return frame
        except Exception as e:
            logger.error(f"Failed to create blank frame: {e}")
            raise

    async def recv(self) -> RTCVideoFrame:
        """
        Receive the next video frame for WebRTC.

        This method is called by aiortc when it needs a frame.
        """
        try:
            if self.start_time is None:
                self.start_time = time.time()
                logger.info("Video track recv() started")

            # Calculate timing
            self.pts += int(90000 / DEFAULT_FPS)  # Increment by frame duration

            # Log every 30th call to recv
            if self.frame_count % 30 == 0:
                logger.debug(f"recv() called, frame_count={self.frame_count}, frames_sent={self.frames_sent}")

            # Try to get a frame from the queue
            queue_frame = await self.frame_queue.get(timeout=1.0 / DEFAULT_FPS)

            frame = None
            if queue_frame:
                logger.debug(f"Got frame from queue: keyframe={queue_frame.is_keyframe}, size={len(queue_frame.data)}")
                decoded = self._decode_frame(queue_frame)
                if decoded:
                    # CRITICAL: Create a deep copy of the frame to prevent segfaults
                    # The H.264 decoder reuses internal buffers, and aiortc accesses
                    # frames from a different thread. We must copy the data.
                    try:
                        # Use fast YUV plane copy instead of expensive RGB conversion
                        # This is ~3-5x faster than the previous rgb24 roundtrip
                        frame = copy_frame_fast(decoded)

                        with self._last_frame_lock:
                            self.last_frame = frame

                        self.frames_sent += 1
                        if self.frames_sent <= 5:
                            logger.info(f"Successfully decoded frame {self.frames_sent}")
                    except Exception as copy_err:
                        logger.warning(f"Failed to copy frame: {copy_err}")
                        frame = None

            # If no frame decoded, use last frame or blank
            if frame is None:
                with self._last_frame_lock:
                    if self.last_frame is not None:
                        frame = self.last_frame
                    else:
                        frame = self._create_blank_frame()
                        if self.frame_count <= 5:
                            logger.debug("Using blank frame (no decoded frame available)")

            # Set timing info
            frame.pts = self.pts
            frame.time_base = self.time_base

            self.frame_count += 1

            return frame
        except Exception as e:
            logger.error(f"Exception in recv(): {e}", exc_info=True)
            raise

    def get_stats(self) -> dict:
        """Get track statistics."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        fps = self.frames_sent / elapsed if elapsed > 0 else 0

        return {
            'frames_sent': self.frames_sent,
            'decode_errors': self.decode_errors,
            'fps': round(fps, 1),
            'width': self.width,
            'height': self.height,
        }


class TestVideoTrack(VideoStreamTrack):
    """
    Test video track that generates a color pattern.
    Useful for testing WebRTC without iOS connection.
    """

    kind = "video"

    def __init__(self, width: int = 640, height: int = 480):
        super().__init__()
        self.width = width
        self.height = height
        self.pts = 0
        self.frame_count = 0
        self.time_base = Fraction(1, 90000)

    async def recv(self) -> RTCVideoFrame:
        """Generate a test frame."""
        self.pts += int(90000 / DEFAULT_FPS)

        # Create a moving color pattern
        t = self.frame_count / DEFAULT_FPS

        # Create YUV420P frame
        y = np.zeros((self.height, self.width), dtype=np.uint8)

        # Create a gradient that moves
        for row in range(self.height):
            for col in range(self.width):
                y[row, col] = int((col + row + t * 100) % 256)

        u = np.full((self.height // 2, self.width // 2), 128, dtype=np.uint8)
        v = np.full((self.height // 2, self.width // 2), 128, dtype=np.uint8)

        frame = VideoFrame(self.width, self.height, 'yuv420p')
        frame.planes[0].update(y.tobytes())
        frame.planes[1].update(u.tobytes())
        frame.planes[2].update(v.tobytes())

        frame.pts = self.pts
        frame.time_base = self.time_base

        self.frame_count += 1

        # Throttle to target FPS
        await asyncio.sleep(1.0 / DEFAULT_FPS)

        return frame


class MediaFileTrack(VideoStreamTrack):
    """
    Video track that streams from a media file (mp4, mkv, etc).
    Loops the video when it reaches the end.
    """

    kind = "video"

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self.container = None
        self.stream = None
        self.pts = 0
        self.frame_count = 0
        self.time_base = Fraction(1, 90000)
        self.start_time = None
        self._open_file()

    def _open_file(self):
        """Open or reopen the media file."""
        if self.container:
            self.container.close()

        self.container = av.open(self.file_path)
        self.stream = self.container.streams.video[0]

        # Get video properties
        self.fps = float(self.stream.average_rate) if self.stream.average_rate else DEFAULT_FPS
        self.width = self.stream.width
        self.height = self.stream.height

        logger.info(f"Opened media file: {self.file_path}")
        logger.info(f"Video: {self.width}x{self.height} @ {self.fps:.2f} fps")

        # Create frame iterator
        self._frame_iter = self.container.decode(video=0)

    def _get_next_frame(self) -> Optional[VideoFrame]:
        """Get next frame from file, looping if needed."""
        try:
            frame = next(self._frame_iter)
            return frame
        except StopIteration:
            # End of file, loop back
            logger.debug("End of media file, looping...")
            self._open_file()
            try:
                return next(self._frame_iter)
            except StopIteration:
                return None

    async def recv(self) -> RTCVideoFrame:
        """Get the next video frame from the media file."""
        if self.start_time is None:
            self.start_time = time.time()

        # Get frame from file
        frame = self._get_next_frame()

        if frame is None:
            # Create blank frame as fallback
            frame = VideoFrame(self.width or 640, self.height or 480, 'yuv420p')

        # Convert to correct format if needed
        if frame.format.name != 'yuv420p':
            frame = frame.reformat(format='yuv420p')

        # Set timing
        self.pts += int(90000 / self.fps)
        frame.pts = self.pts
        frame.time_base = self.time_base

        self.frame_count += 1

        # Throttle to match video FPS
        elapsed = time.time() - self.start_time
        expected_time = self.frame_count / self.fps
        sleep_time = expected_time - elapsed

        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

        return frame

    def stop(self):
        """Clean up resources."""
        super().stop()
        if self.container:
            self.container.close()
            self.container = None
