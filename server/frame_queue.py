"""
Thread-safe frame queue with drop-oldest policy for low-latency streaming.
"""

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Optional
import time


@dataclass
class VideoFrame:
    """Represents a single video frame with metadata."""
    timestamp: int  # Microseconds
    data: bytes  # H264 NAL unit(s)
    is_keyframe: bool = False
    sps_pps: Optional[bytes] = None  # Decoder config (SPS/PPS)
    received_at: float = 0.0  # Local receive time


class FrameQueue:
    """
    Bounded async queue for video frames with drop-oldest policy.

    When the queue is full, the oldest frame is automatically dropped
    to prevent latency accumulation.
    """

    def __init__(self, max_size: int = 3):
        self.queue: deque[VideoFrame] = deque(maxlen=max_size)
        self.max_size = max_size
        self.lock = asyncio.Lock()
        self.event = asyncio.Event()

        # Statistics
        self.stats = {
            'received': 0,
            'dropped': 0,
            'sent': 0,
            'keyframes': 0,
        }

        # Current decoder config
        self.current_sps_pps: Optional[bytes] = None

    async def put(self, frame: VideoFrame) -> None:
        """
        Add a frame to the queue.
        If queue is full, oldest frame is automatically dropped.
        """
        async with self.lock:
            was_full = len(self.queue) == self.max_size
            if was_full:
                self.stats['dropped'] += 1

            frame.received_at = time.time()
            self.queue.append(frame)
            self.stats['received'] += 1

            if frame.is_keyframe:
                self.stats['keyframes'] += 1

            if frame.sps_pps:
                self.current_sps_pps = frame.sps_pps

            self.event.set()

    async def get(self, timeout: Optional[float] = None) -> Optional[VideoFrame]:
        """
        Get the next frame from the queue.
        Blocks until a frame is available or timeout expires.
        """
        try:
            if timeout:
                await asyncio.wait_for(self._wait_for_frame(), timeout)
            else:
                await self._wait_for_frame()

            async with self.lock:
                if self.queue:
                    frame = self.queue.popleft()
                    self.stats['sent'] += 1
                    return frame
                return None
        except asyncio.TimeoutError:
            return None

    async def _wait_for_frame(self) -> None:
        """Wait until a frame is available."""
        while True:
            async with self.lock:
                if self.queue:
                    return
            self.event.clear()
            await self.event.wait()

    def get_latest(self) -> Optional[VideoFrame]:
        """
        Non-blocking get of the most recent frame.
        Does not remove the frame from the queue.
        """
        if self.queue:
            return self.queue[-1]
        return None

    def get_stats(self) -> dict:
        """Get queue statistics."""
        return {
            **self.stats,
            'queue_size': len(self.queue),
            'max_size': self.max_size,
        }

    def clear(self) -> None:
        """Clear all frames from the queue."""
        self.queue.clear()
        self.event.clear()

    def has_config(self) -> bool:
        """Check if decoder config (SPS/PPS) is available."""
        return self.current_sps_pps is not None

    def get_config(self) -> Optional[bytes]:
        """Get the current decoder config (SPS/PPS)."""
        return self.current_sps_pps
