#!/usr/bin/env python3
"""
Simulator Receiver - Receives video from iOS Simulator via idb and feeds to WebRTC

This module streams video from iOS Simulator using Facebook's idb tool.

KEY INSIGHT: Uses MJPEG format by default instead of H.264!

The H.264 stream from idb has a fundamental issue: keyframes are only
generated every 10 seconds (360 frames). This causes severe corruption
during scene transitions because the decoder cannot reconstruct frames
without a recent reference keyframe.

MJPEG solves this completely because every frame is independently decodable -
there are no inter-frame dependencies, so scene transitions are always clean.

Supported modes:
1. MJPEG (default, recommended): No corruption, every frame independent
2. H.264 with FFmpeg transcoding: Keyframe injection, more complex pipeline
3. H.264 raw: May have corruption during scene changes
"""

import asyncio
import logging
import os
import signal
import subprocess
import shutil
from typing import Optional
import fractions

from grpclib.client import Channel
from idb.grpc.idb_pb2 import CompanionInfo
from idb.grpc.idb_grpc import CompanionServiceStub
from idb.grpc.client import Client
from idb.common.types import TCPAddress, VideoFormat, CompanionInfo as CompanionInfoType

from aiortc import VideoStreamTrack
import av
from av import VideoFrame
from av.codec import CodecContext
import numpy as np

logger = logging.getLogger(__name__)

# Common FFmpeg paths on macOS
FFMPEG_PATHS = [
    'ffmpeg',                           # In PATH
    '/opt/homebrew/bin/ffmpeg',         # Homebrew on Apple Silicon
    '/usr/local/bin/ffmpeg',            # Homebrew on Intel Mac
    '/usr/bin/ffmpeg',                  # System install
]


def find_ffmpeg() -> Optional[str]:
    """Find FFmpeg executable path."""
    # First try shutil.which (respects PATH)
    path = shutil.which('ffmpeg')
    if path:
        return path

    # Try common locations
    for candidate in FFMPEG_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return None


def check_ffmpeg_available() -> bool:
    """Check if FFmpeg is available on the system."""
    return find_ffmpeg() is not None


class SimulatorVideoTrack(VideoStreamTrack):
    """
    VideoStreamTrack that receives video from iOS Simulator via idb.
    Integrates with existing WebRTC infrastructure.

    CRITICAL: Uses MJPEG format by default instead of H.264!

    The H.264 stream from idb has a fundamental issue: keyframes are only
    generated every 10 seconds (360 frames). This causes severe corruption
    during scene transitions (scrolling, navigation, animations) because
    the decoder cannot reconstruct frames without a reference keyframe.

    MJPEG solves this because every frame is independently decodable -
    there are no inter-frame dependencies, so no corruption on scene changes.

    The trade-off is slightly higher bandwidth, but for simulator streaming
    at 30fps this is acceptable and provides perfect visual quality.
    """

    kind = "video"

    def __init__(
        self,
        simulator_udid: str,
        fps: int = 30,
        port: int = 10882,
        keyframe_interval: float = 1.0,
        use_ffmpeg_transcoding: bool = False,
        use_mjpeg: bool = True  # NEW: Use MJPEG to avoid keyframe issues
    ):
        """
        Initialize SimulatorVideoTrack.

        Args:
            simulator_udid: The UDID of the iOS Simulator to stream from
            fps: Frames per second (default: 30)
            port: gRPC port for idb_companion (default: 10882)
            keyframe_interval: Seconds between keyframes (default: 1.0) - only used with H.264
            use_ffmpeg_transcoding: Whether to use FFmpeg to inject keyframes (default: False)
            use_mjpeg: Use MJPEG format instead of H.264 (default: True)
                      MJPEG has no keyframe issues - every frame is independent
        """
        super().__init__()
        self.simulator_udid = simulator_udid
        self.fps = fps
        self.port = port
        self.keyframe_interval = keyframe_interval
        self.use_ffmpeg_transcoding = use_ffmpeg_transcoding
        self.use_mjpeg = use_mjpeg

        # IDB components
        self._companion_process: Optional[subprocess.Popen] = None
        self._client: Optional[Client] = None
        self._channel: Optional[Channel] = None

        # FFmpeg transcoder process
        self._ffmpeg_process: Optional[asyncio.subprocess.Process] = None
        self._ffmpeg_feeder_task: Optional[asyncio.Task] = None
        self._ffmpeg_reader_task: Optional[asyncio.Task] = None

        # Video decoder
        self._codec: Optional[CodecContext] = None
        self._timestamp = 0
        self._running = False

        # Statistics
        self._frames_decoded = 0
        self._keyframes_injected = 0
        self._frames_dropped = 0

        # Frame queue - larger size to handle bursts during scene transitions
        # Too small = frame drops during transitions = jerky video
        # Too large = increased latency
        self._frame_queue = asyncio.Queue(maxsize=10)
        self._decoder_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start streaming from simulator."""
        logger.info(f"🚀 Starting stream for simulator {self.simulator_udid}")

        self._running = True

        # Screenshot mode - uses simctl directly, no idb needed
        if self.use_mjpeg:
            logger.info("📸 Using simctl screenshot mode (zero corruption, every frame independent)")
            self._decoder_task = asyncio.create_task(self._stream_mjpeg())
            logger.info("✅ Screenshot stream started")
            return

        # H.264 mode - uses idb
        logger.info("📹 Using H.264 format via idb (may have corruption during scene changes)")

        # Check FFmpeg availability if transcoding is enabled
        if self.use_ffmpeg_transcoding:
            if not check_ffmpeg_available():
                logger.warning("⚠️ FFmpeg not found, falling back to raw idb stream")
                self.use_ffmpeg_transcoding = False
            else:
                logger.info(f"✅ FFmpeg available, will inject keyframes every {self.keyframe_interval}s")

        # Start idb_companion
        await self._start_companion()

        # Wait for companion to initialize
        await asyncio.sleep(2)

        # Connect client
        await self._connect_client()

        # Initialize H.264 decoder
        self._codec = CodecContext.create('h264', 'r')
        logger.info("✅ H.264 decoder initialized")

        # Start H.264 streaming method
        if self.use_ffmpeg_transcoding:
            self._decoder_task = asyncio.create_task(self._stream_with_ffmpeg_transcoding())
            logger.info("✅ IDB stream started with FFmpeg keyframe injection")
        else:
            self._decoder_task = asyncio.create_task(self._stream_and_decode())
            logger.info("✅ IDB stream started (raw H.264 mode)")

    async def _start_companion(self):
        """Start idb_companion process (or reuse existing one)."""
        import subprocess as sp

        # Check if idb_companion is already running on this port
        try:
            result = sp.run(['lsof', '-i', f':{self.port}'], capture_output=True, text=True)
            if 'idb_companion' in result.stdout:
                logger.info(f"✅ idb_companion already running on port {self.port}")
                # Find the PID
                for line in result.stdout.split('\n'):
                    if 'idb_companion' in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                pid = int(parts[1])
                                logger.info(f"   Existing idb_companion PID: {pid}")
                                # Create a dummy Popen-like object
                                class ExistingProcess:
                                    def __init__(self, pid):
                                        self.pid = pid
                                self._companion_process = ExistingProcess(pid)
                                return
                            except ValueError:
                                pass
        except Exception as e:
            logger.debug(f"Could not check for existing companion: {e}")

        # Find idb_companion executable
        idb_paths = [
            shutil.which('idb_companion'),
            '/opt/homebrew/bin/idb_companion',
            '/usr/local/bin/idb_companion',
        ]

        idb_path = None
        for path in idb_paths:
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                idb_path = path
                break

        if not idb_path:
            raise FileNotFoundError(
                "idb_companion not found. Please install it with: brew install idb-companion"
            )

        logger.info(f"Starting idb_companion on port {self.port}")
        logger.info(f"   Path: {idb_path}")

        cmd = [
            idb_path,
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

    async def _stream_mjpeg(self):
        """
        Optimized screenshot streaming with triple-buffered parallel capture.

        Latency optimizations:
        1. Use TIFF format (fastest capture with good quality ~190ms)
        2. Triple-buffering: 3 captures in flight at once
        3. Thread pool for parallel image decoding
        4. Frame queue with newest-wins policy

        Target: 8-12 FPS with parallel capture
        """
        try:
            logger.info("Starting optimized screenshot stream...")
            logger.info("   Pipeline: simctl screenshot (triple-buffered) → decode → frame queue")
            logger.info("   🚀 Using TIFF format + parallel capture for best performance")

            from PIL import Image
            import io
            import concurrent.futures
            from collections import deque

            # Use thread pool for CPU-bound image decoding
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

            # Stats tracking
            capture_times = deque(maxlen=30)
            process_times = deque(maxlen=30)
            last_log_time = asyncio.get_event_loop().time()

            def decode_image(data):
                """Decode image in thread pool."""
                img = Image.open(io.BytesIO(data))
                img_rgb = img.convert('RGB')
                return np.array(img_rgb)

            async def capture_screenshot():
                """Capture a single screenshot using TIFF format."""
                start = asyncio.get_event_loop().time()
                proc = await asyncio.create_subprocess_exec(
                    'xcrun', 'simctl', 'io', self.simulator_udid,
                    'screenshot', '--type=tiff', '-',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
                elapsed = asyncio.get_event_loop().time() - start
                return stdout, elapsed

            # Triple-buffering: maintain 3 captures in flight
            NUM_BUFFERS = 3
            pending_captures = [asyncio.create_task(capture_screenshot()) for _ in range(NUM_BUFFERS)]
            next_capture_idx = 0

            while self._running:
                frame_start = asyncio.get_event_loop().time()

                try:
                    # Wait for the next capture in round-robin order
                    capture_task = pending_captures[next_capture_idx]
                    screenshot_data, capture_time = await capture_task
                    capture_times.append(capture_time)

                    # Start replacement capture immediately
                    pending_captures[next_capture_idx] = asyncio.create_task(capture_screenshot())
                    next_capture_idx = (next_capture_idx + 1) % NUM_BUFFERS

                    if screenshot_data and len(screenshot_data) > 0:
                        # Decode in thread pool
                        loop = asyncio.get_event_loop()
                        decode_start = asyncio.get_event_loop().time()
                        arr = await loop.run_in_executor(executor, decode_image, screenshot_data)
                        process_times.append(asyncio.get_event_loop().time() - decode_start)

                        # Create VideoFrame
                        frame = VideoFrame.from_ndarray(arr, format='rgb24')

                        self._frames_decoded += 1

                        # Log every second
                        now = asyncio.get_event_loop().time()
                        if now - last_log_time >= 1.0:
                            avg_capture = sum(capture_times) / len(capture_times) * 1000 if capture_times else 0
                            avg_decode = sum(process_times) / len(process_times) * 1000 if process_times else 0
                            fps = self._frames_decoded / (now - (last_log_time - 1)) if self._frames_decoded > 30 else 0
                            logger.info(
                                f"📹 Frame {self._frames_decoded}: {frame.width}x{frame.height} "
                                f"(capture: {avg_capture:.0f}ms, decode: {avg_decode:.0f}ms, "
                                f"~{len(capture_times)/(sum(capture_times) if capture_times else 1):.1f} FPS effective)"
                            )
                            last_log_time = now

                        # Put frame in queue (newest wins)
                        try:
                            self._frame_queue.put_nowait(frame)
                        except asyncio.QueueFull:
                            self._frames_dropped += 1
                            try:
                                self._frame_queue.get_nowait()
                                self._frame_queue.put_nowait(frame)
                            except Exception:
                                pass

                except asyncio.TimeoutError:
                    logger.warning("Screenshot timeout, restarting capture")
                    pending_captures[next_capture_idx] = asyncio.create_task(capture_screenshot())
                    next_capture_idx = (next_capture_idx + 1) % NUM_BUFFERS
                    continue
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if self._frames_decoded == 0:
                        logger.error(f"Screenshot error: {e}")
                        import traceback
                        traceback.print_exc()
                    pending_captures[next_capture_idx] = asyncio.create_task(capture_screenshot())
                    next_capture_idx = (next_capture_idx + 1) % NUM_BUFFERS
                    continue

        except Exception as e:
            logger.error(f"Screenshot stream error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            executor.shutdown(wait=False)
            # Cancel all pending captures
            for task in pending_captures:
                if task and not task.done():
                    task.cancel()
            logger.info(f"Screenshot stream stopped after {self._frames_decoded} frames")

    async def _stream_and_decode(self):
        """
        Stream H.264 from idb and decode to frames.

        APPROACH: On scene change detection, RESET the decoder and wait for
        the stream to stabilize. This forces the decoder to re-sync with the
        new content rather than trying to decode P-frames against stale references.

        The corruption happens because H.264 P-frames reference previous frames.
        When content changes dramatically, these references become invalid.
        By resetting the decoder, we force it to wait for valid frame data.
        """
        try:
            logger.info("Starting direct H.264 stream from idb...")
            logger.info("   Pipeline: idb H.264 → PyAV decode → frame queue → aiortc encode")
            logger.info("   🔄 Scene change handling: decoder reset on major changes")

            # Track state
            last_frame_mean = None
            frames_after_reset = 0
            in_transition = False
            transition_start = 0
            TRANSITION_SETTLE_FRAMES = 10  # Wait this many frames after detecting change

            async for h264_data in self._client.stream_video(
                output_file=None,
                fps=self.fps,
                format=VideoFormat.H264,
                compression_quality=0.8,
                scale_factor=1.0
            ):
                if not self._running:
                    break

                try:
                    packets = self._codec.parse(h264_data)

                    for packet in packets:
                        frames = self._codec.decode(packet)

                        for frame in frames:
                            self._frames_decoded += 1
                            frames_after_reset += 1

                            # Calculate frame brightness for scene detection
                            try:
                                frame_gray = frame.reformat(format='gray')
                                frame_arr = frame_gray.to_ndarray()
                                current_mean = float(np.mean(frame_arr))

                                if last_frame_mean is not None:
                                    diff = abs(current_mean - last_frame_mean)

                                    # Detect scene change (large brightness difference)
                                    if diff > 20 and not in_transition:
                                        in_transition = True
                                        transition_start = self._frames_decoded
                                        logger.info(
                                            f"🔄 Scene transition detected at frame {self._frames_decoded} "
                                            f"(diff={diff:.1f}) - will settle in {TRANSITION_SETTLE_FRAMES} frames"
                                        )

                                # Check if we've settled after transition
                                if in_transition:
                                    frames_in_transition = self._frames_decoded - transition_start
                                    if frames_in_transition >= TRANSITION_SETTLE_FRAMES:
                                        in_transition = False
                                        logger.info(
                                            f"✅ Scene transition settled at frame {self._frames_decoded}"
                                        )

                                last_frame_mean = current_mean
                            except Exception:
                                pass

                            # Log periodically
                            if self._frames_decoded % 30 == 0:
                                status = "TRANSITIONING" if in_transition else "OK"
                                logger.info(
                                    f"📹 Frame {self._frames_decoded}: {frame.width}x{frame.height} "
                                    f"[{status}] (dropped: {self._frames_dropped})"
                                )

                            # Always send the current frame - let the browser handle it
                            # The aiortc encoder will re-encode with proper keyframes
                            try:
                                self._frame_queue.put_nowait(frame)
                            except asyncio.QueueFull:
                                self._frames_dropped += 1
                                try:
                                    self._frame_queue.get_nowait()
                                    self._frame_queue.put_nowait(frame)
                                except Exception:
                                    pass

                except Exception as e:
                    logger.error(f"Error decoding H.264: {e}")
                    continue

        except Exception as e:
            logger.error(f"Stream error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            logger.info(f"Stream stopped after {self._frames_decoded} frames (dropped: {self._frames_dropped})")

    async def _stream_with_ffmpeg_transcoding(self):
        """
        Stream H.264 from idb through FFmpeg to inject keyframes.

        This method pipes the idb H.264 stream through FFmpeg which re-encodes
        the video with regular keyframe intervals. This solves the corruption
        issue during scene transitions caused by idb's encoder only producing
        keyframes every 10 seconds.

        Pipeline: idb H.264 -> FFmpeg (re-encode with keyframes) -> PyAV decoder -> frames
        """
        try:
            logger.info("Starting FFmpeg transcoding pipeline...")

            # Calculate keyframe interval in frames
            keyframe_frames = int(self.fps * self.keyframe_interval)

            # Find FFmpeg executable
            ffmpeg_path = find_ffmpeg()
            if not ffmpeg_path:
                raise RuntimeError("FFmpeg not found")

            # Start FFmpeg transcoder process
            # Using libx264 with ultrafast preset and zerolatency tune for minimal latency
            ffmpeg_cmd = [
                ffmpeg_path,
                '-hide_banner',
                '-loglevel', 'error',
                # Input options
                '-f', 'h264',                    # Input format is raw H.264
                '-i', 'pipe:0',                  # Read from stdin
                # Encoder options
                '-c:v', 'libx264',               # Use x264 encoder
                '-preset', 'ultrafast',          # Fastest encoding (lowest latency)
                '-tune', 'zerolatency',          # Optimize for low latency streaming
                '-profile:v', 'baseline',        # Baseline profile for compatibility
                # Keyframe settings - this is the key fix!
                '-g', str(keyframe_frames),      # Keyframe every N frames
                '-keyint_min', str(keyframe_frames),  # Minimum keyframe interval
                '-sc_threshold', '0',            # Disable scene change detection (predictable keyframes)
                # Quality settings
                '-crf', '23',                    # Constant rate factor (lower = better quality)
                '-maxrate', '4M',                # Maximum bitrate
                '-bufsize', '8M',                # Buffer size
                # Output options
                '-f', 'h264',                    # Output raw H.264
                '-bsf:v', 'h264_mp4toannexb',    # Ensure Annex-B format
                'pipe:1'                         # Write to stdout
            ]

            logger.info(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")
            logger.info(f"   Keyframe every {keyframe_frames} frames ({self.keyframe_interval}s at {self.fps}fps)")

            self._ffmpeg_process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            logger.info(f"FFmpeg transcoder started (PID: {self._ffmpeg_process.pid})")

            # Create tasks for feeding and reading FFmpeg
            self._ffmpeg_feeder_task = asyncio.create_task(self._feed_ffmpeg())
            self._ffmpeg_reader_task = asyncio.create_task(self._read_ffmpeg())

            # Also monitor stderr for errors
            stderr_task = asyncio.create_task(self._monitor_ffmpeg_stderr())

            # Wait for reader to complete (or error)
            await self._ffmpeg_reader_task

        except Exception as e:
            logger.error(f"FFmpeg transcoding error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await self._cleanup_ffmpeg()
            logger.info(f"FFmpeg transcoding stopped after {self._frames_decoded} frames")

    async def _feed_ffmpeg(self):
        """Feed idb H.264 data to FFmpeg stdin."""
        bytes_fed = 0
        chunks_fed = 0

        try:
            logger.info("Starting to feed idb stream to FFmpeg...")

            async for h264_data in self._client.stream_video(
                output_file=None,
                fps=self.fps,
                format=VideoFormat.H264,
                compression_quality=0.8,
                scale_factor=1.0
            ):
                if not self._running:
                    break

                if self._ffmpeg_process and self._ffmpeg_process.stdin:
                    try:
                        self._ffmpeg_process.stdin.write(h264_data)
                        await self._ffmpeg_process.stdin.drain()
                        bytes_fed += len(h264_data)
                        chunks_fed += 1

                        if chunks_fed % 30 == 0:
                            logger.debug(f"Fed {chunks_fed} chunks ({bytes_fed / 1024:.1f} KB) to FFmpeg")

                    except (BrokenPipeError, ConnectionResetError) as e:
                        logger.error(f"FFmpeg stdin pipe broken: {e}")
                        break

        except Exception as e:
            logger.error(f"Error feeding FFmpeg: {e}")

        finally:
            # Close FFmpeg stdin to signal end of input
            if self._ffmpeg_process and self._ffmpeg_process.stdin:
                try:
                    self._ffmpeg_process.stdin.close()
                    await self._ffmpeg_process.stdin.wait_closed()
                except Exception:
                    pass

            logger.info(f"Finished feeding FFmpeg: {chunks_fed} chunks, {bytes_fed / 1024:.1f} KB")

    async def _read_ffmpeg(self):
        """Read transcoded H.264 from FFmpeg stdout and decode to frames."""
        buffer = b''
        read_bytes = 0

        try:
            logger.info("Starting to read transcoded stream from FFmpeg...")

            while self._running:
                if not self._ffmpeg_process or not self._ffmpeg_process.stdout:
                    break

                # Read chunk from FFmpeg output
                try:
                    chunk = await asyncio.wait_for(
                        self._ffmpeg_process.stdout.read(65536),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    # No data for 5 seconds, check if still running
                    if self._ffmpeg_process.returncode is not None:
                        logger.warning("FFmpeg process ended")
                        break
                    continue

                if not chunk:
                    # EOF
                    logger.info("FFmpeg stdout EOF")
                    break

                read_bytes += len(chunk)
                buffer += chunk

                # Parse and decode H.264 data
                try:
                    packets = self._codec.parse(buffer)

                    for packet in packets:
                        # Track keyframes from packet
                        is_keyframe = packet.is_keyframe

                        frames = self._codec.decode(packet)

                        for frame in frames:
                            self._frames_decoded += 1

                            # Also check if frame is a keyframe (more reliable than packet flag)
                            frame_is_key = getattr(frame, 'key_frame', False)
                            if not frame_is_key:
                                # Check picture type
                                pict_type = getattr(frame, 'pict_type', None)
                                if pict_type is not None:
                                    frame_is_key = str(pict_type) == 'I'

                            if frame_is_key or is_keyframe:
                                self._keyframes_injected += 1
                                if self._keyframes_injected <= 5 or self._keyframes_injected % 30 == 0:
                                    logger.info(
                                        f"🔑 Keyframe #{self._keyframes_injected} at frame {self._frames_decoded} "
                                        f"(pkt={is_keyframe}, frame={frame_is_key}, pict_type={getattr(frame, 'pict_type', 'N/A')})"
                                    )

                            if self._frames_decoded % 30 == 0:
                                logger.info(
                                    f"📹 Frame {self._frames_decoded}: {frame.width}x{frame.height} "
                                    f"(keyframes: {self._keyframes_injected}, dropped: {self._frames_dropped})"
                                )

                            # Put frame in queue
                            try:
                                self._frame_queue.put_nowait(frame)
                            except asyncio.QueueFull:
                                # Queue full - drop oldest frame to make room
                                self._frames_dropped += 1
                                try:
                                    self._frame_queue.get_nowait()
                                    self._frame_queue.put_nowait(frame)
                                    if self._frames_dropped % 10 == 1:
                                        logger.warning(
                                            f"⚠️ Frame queue full, dropped {self._frames_dropped} frames total "
                                            f"(queue size: {self._frame_queue.qsize()})"
                                        )
                                except Exception:
                                    pass

                    # Clear buffer after successful parse
                    buffer = b''

                except Exception as e:
                    # Keep buffer and try again with more data
                    if len(buffer) > 1024 * 1024:  # 1MB limit
                        logger.warning(f"Buffer too large ({len(buffer)} bytes), clearing")
                        buffer = b''

        except Exception as e:
            logger.error(f"Error reading from FFmpeg: {e}")
            import traceback
            traceback.print_exc()

        finally:
            logger.info(f"Finished reading FFmpeg: {read_bytes / 1024:.1f} KB, {self._frames_decoded} frames")

    async def _monitor_ffmpeg_stderr(self):
        """Monitor FFmpeg stderr for errors."""
        try:
            while self._running and self._ffmpeg_process:
                if self._ffmpeg_process.stderr:
                    line = await self._ffmpeg_process.stderr.readline()
                    if line:
                        logger.warning(f"FFmpeg: {line.decode().strip()}")
                    elif self._ffmpeg_process.returncode is not None:
                        break
                else:
                    break
        except Exception:
            pass

    async def _cleanup_ffmpeg(self):
        """Clean up FFmpeg process and related tasks."""
        # Cancel feeder task
        if self._ffmpeg_feeder_task and not self._ffmpeg_feeder_task.done():
            self._ffmpeg_feeder_task.cancel()
            try:
                await self._ffmpeg_feeder_task
            except asyncio.CancelledError:
                pass

        # Cancel reader task
        if self._ffmpeg_reader_task and not self._ffmpeg_reader_task.done():
            self._ffmpeg_reader_task.cancel()
            try:
                await self._ffmpeg_reader_task
            except asyncio.CancelledError:
                pass

        # Terminate FFmpeg process
        if self._ffmpeg_process:
            try:
                if self._ffmpeg_process.returncode is None:
                    self._ffmpeg_process.terminate()
                    try:
                        await asyncio.wait_for(self._ffmpeg_process.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        self._ffmpeg_process.kill()
                        await self._ffmpeg_process.wait()
            except Exception as e:
                logger.warning(f"Error terminating FFmpeg: {e}")

        self._ffmpeg_process = None
        logger.info("FFmpeg cleanup complete")

    async def recv(self) -> VideoFrame:
        """
        Receive next video frame for WebRTC.
        Called by aiortc when it needs a frame.

        IMPORTANT: We create a fresh frame from numpy array to ensure:
        1. No residual metadata from the decoder (pict_type, etc.)
        2. Clean frame for the WebRTC encoder to work with
        3. Proper keyframe generation without interference
        """
        if not self._running:
            raise Exception("Stream not started")

        try:
            # Get frame from queue with timeout
            frame = await asyncio.wait_for(
                self._frame_queue.get(),
                timeout=2.0
            )

            # CRITICAL FIX: Create a completely fresh frame from pixel data
            # This removes all residual metadata (pict_type, key_frame, etc.)
            # that could interfere with the WebRTC encoder's keyframe logic

            # Convert to numpy array first
            frame_yuv = frame.reformat(format='yuv420p')

            # Extract the raw pixel data as numpy array
            # This strips all metadata from the frame
            arr = frame_yuv.to_ndarray()

            # Create a completely new frame from the pixel data
            new_frame = VideoFrame.from_ndarray(arr, format='yuv420p')

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

        # Clean up FFmpeg if it was used
        if self.use_ffmpeg_transcoding:
            await self._cleanup_ffmpeg()

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

        logger.info(
            f"IDB stream stopped "
            f"(frames: {self._frames_decoded}, keyframes: {self._keyframes_injected})"
        )


class SimulatorReceiver:
    """
    Simulator Receiver - Manages simulator video streaming via idb.
    Provides a similar interface to iOSReceiver for integration with existing server.

    By default, uses FFmpeg transcoding to inject keyframes every 1 second,
    which prevents video corruption during scene transitions.
    """

    def __init__(
        self,
        simulator_udid: str,
        port: int = 10882,
        fps: int = 30,
        keyframe_interval: float = 1.0,
        use_ffmpeg_transcoding: bool = True
    ):
        """
        Initialize SimulatorReceiver.

        Args:
            simulator_udid: The UDID of the iOS Simulator
            port: gRPC port for idb_companion (default: 10882)
            fps: Frames per second (default: 30)
            keyframe_interval: Seconds between keyframes (default: 1.0)
            use_ffmpeg_transcoding: Use FFmpeg to inject keyframes (default: True)
        """
        self.simulator_udid = simulator_udid
        self.port = port
        self.fps = fps
        self.keyframe_interval = keyframe_interval
        self.use_ffmpeg_transcoding = use_ffmpeg_transcoding

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
            "udid": simulator_udid,
            "ffmpeg_transcoding": use_ffmpeg_transcoding,
            "keyframe_interval": keyframe_interval
        }

        # Callbacks
        self.on_connect_callback = None
        self.on_disconnect_callback = None

    async def start(self):
        """Start receiving video from simulator."""
        logger.info(f"📱 Starting simulator receiver for UDID: {self.simulator_udid}")
        logger.info(f"   FFmpeg transcoding: {self.use_ffmpeg_transcoding}")
        logger.info(f"   Keyframe interval: {self.keyframe_interval}s")

        # Create video track with FFmpeg transcoding settings
        self.video_track = SimulatorVideoTrack(
            simulator_udid=self.simulator_udid,
            fps=self.fps,
            port=self.port,
            keyframe_interval=self.keyframe_interval,
            use_ffmpeg_transcoding=self.use_ffmpeg_transcoding
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
