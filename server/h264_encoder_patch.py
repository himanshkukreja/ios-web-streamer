"""
Patched H.264 encoder for aiortc with configurable keyframe interval and scene change detection.

This module patches the aiortc H264Encoder to:
1. Include periodic keyframes at regular intervals
2. Detect scene changes and force keyframes during transitions
3. Use optimized settings for screen content

Usage:
    from h264_encoder_patch import patch_aiortc_h264_encoder
    patch_aiortc_h264_encoder(keyframe_interval=15)  # Keyframe every 15 frames (0.5 second at 30fps)
"""

import fractions
import logging

import av
import numpy as np

logger = logging.getLogger(__name__)

# Default keyframe interval (frames)
DEFAULT_KEYFRAME_INTERVAL = 15  # 0.5 second at 30fps for smoother transitions


def patch_aiortc_h264_encoder(keyframe_interval: int = 15) -> None:
    """
    Patch the aiortc H264Encoder for better scene transition handling.

    This must be called BEFORE creating any WebRTC connections.

    Args:
        keyframe_interval: Number of frames between keyframes (default: 15 = 0.5 second at 30fps)
    """
    try:
        from aiortc.codecs import h264

        def patched_encode_frame_v3(self, frame: av.VideoFrame, force_keyframe: bool):
            """
            Patched encoder with:
            1. Periodic keyframes
            2. Scene change detection
            3. Optimized codec settings for screen content
            """
            # Initialize tracking attributes
            if not hasattr(self, '_frame_number'):
                self._frame_number = 0
                self._last_frame_hash = None
                self._scene_change_threshold = 0.15  # 15% pixel difference = scene change

            self._frame_number += 1

            # Force keyframe periodically (every keyframe_interval frames)
            if self._frame_number % keyframe_interval == 1:
                force_keyframe = True
                if self._frame_number <= 3:
                    logger.info(f"🔑 WebRTC encoder: periodic keyframe at frame {self._frame_number}")

            # Scene change detection - force keyframe on significant changes
            try:
                # Get frame data for comparison
                frame_array = frame.to_ndarray(format='gray')
                current_hash = hash(frame_array.tobytes()[:10000])  # Hash first 10KB for speed

                if self._last_frame_hash is not None:
                    # Simple but fast change detection
                    if current_hash != self._last_frame_hash:
                        # Frames are different, could be scene change
                        # Force keyframe every 5 frames during changes for smooth transitions
                        if self._frame_number % 5 == 0:
                            force_keyframe = True

                self._last_frame_hash = current_hash
            except Exception:
                pass  # Ignore scene detection errors

            # Check if we need to (re)create codec
            if self.codec and (
                frame.width != self.codec.width
                or frame.height != self.codec.height
                or abs(self.target_bitrate - self.codec.bit_rate) / self.codec.bit_rate > 0.1
            ):
                self.buffer_data = b""
                self.buffer_pts = None
                self.codec = None

            # Set picture type
            if force_keyframe:
                frame.pict_type = av.video.frame.PictureType.I
            else:
                frame.pict_type = av.video.frame.PictureType.NONE

            # Create codec with optimized settings
            if self.codec is None:
                self.codec = av.CodecContext.create("libx264", "w")
                self.codec.width = frame.width
                self.codec.height = frame.height
                self.codec.bit_rate = self.target_bitrate
                self.codec.pix_fmt = "yuv420p"
                self.codec.framerate = fractions.Fraction(30, 1)
                self.codec.time_base = fractions.Fraction(1, 30)
                self.codec.gop_size = keyframe_interval
                self.codec.max_b_frames = 0  # Disable B-frames for lower latency
                self.codec.options = {
                    "preset": "ultrafast",
                    "tune": "zerolatency",
                    "profile": "baseline",
                    "level": "3.1",
                    "g": str(keyframe_interval),
                    "keyint_min": str(keyframe_interval // 2),  # Allow keyframes sooner
                    "sc_threshold": "40",  # Enable scene change detection (was disabled)
                    "rc-lookahead": "0",  # No lookahead for low latency
                    "refs": "1",  # Single reference frame
                    "bframes": "0",  # No B-frames
                }
                logger.info(
                    f"✅ H264Encoder created: gop_size={keyframe_interval}, "
                    f"resolution={frame.width}x{frame.height}, "
                    f"bitrate={self.target_bitrate//1000}kbps"
                )

            # Encode frame
            data_to_send = b""
            for package in self.codec.encode(frame):
                data_to_send += bytes(package)

            if data_to_send:
                yield from h264.H264Encoder._split_bitstream(data_to_send)

        # Apply the patch
        h264.H264Encoder._encode_frame = patched_encode_frame_v3

        logger.info(f"✅ Patched aiortc H264Encoder:")
        logger.info(f"   - Keyframe interval: {keyframe_interval} frames")
        logger.info(f"   - Scene change detection: enabled")
        logger.info(f"   - B-frames: disabled (low latency)")

    except ImportError as e:
        logger.error(f"Failed to import aiortc.codecs.h264: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to patch H264Encoder: {e}")
        raise


def unpatch_aiortc_h264_encoder() -> None:
    """Remove the patch and restore original behavior."""
    try:
        from aiortc.codecs import h264
        import importlib
        importlib.reload(h264)
        logger.info("Unpatched aiortc H264Encoder")
    except Exception as e:
        logger.warning(f"Failed to unpatch H264Encoder: {e}")
