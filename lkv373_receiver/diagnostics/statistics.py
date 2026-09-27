"""
Real-time Stream Statistics and Performance Monitor.

Tracks metrics such as FPS, packet rate, packet loss, frame loss,
decoding latency, and resolution for diagnostic rendering overlays.
"""

import time
from collections import deque


class StreamStatistics:
    """
    Computes real-time statistics for network traffic, reassembly, and rendering.
    """

    def __init__(self, window_seconds: float = 2.0):
        self.window_seconds = window_seconds

        # Time-series sliding windows (timestamps)
        self.packet_timestamps = deque()
        self.frame_timestamps = deque()

        # Cumulative counters
        self.total_packets: int = 0
        self.total_completed_frames: int = 0
        self.total_incomplete_frames: int = 0
        self.total_duplicate_packets: int = 0
        self.total_out_of_order_packets: int = 0
        self.total_missing_chunks: int = 0
        self.total_decode_errors: int = 0

        # Current state
        self.current_frame_number: int = 0
        self.current_width: int = 0
        self.current_height: int = 0
        self.last_decode_latency_ms: float = 0.0
        self.last_frame_interval_ms: float = 0.0
        self.last_frame_time: float = 0.0

        # Network parameters
        self.group_ip: str = "226.2.2.2"
        self.port: int = 2068
        self.interface_ip: str = "0.0.0.0"

    def record_packet(self, timestamp: float | None = None):
        """Records a received packet timestamp."""
        if timestamp is None:
            timestamp = time.time()
        self.total_packets += 1
        self.packet_timestamps.append(timestamp)
        self._prune_windows(timestamp)

    def record_frame(
        self,
        frame_number: int,
        width: int,
        height: int,
        decode_latency_ms: float = 0.0,
        timestamp: float | None = None,
    ):
        """Records a completed and decoded frame."""
        if timestamp is None:
            timestamp = time.time()

        if self.last_frame_time > 0:
            self.last_frame_interval_ms = (timestamp - self.last_frame_time) * 1000.0
        self.last_frame_time = timestamp

        self.current_frame_number = frame_number
        self.current_width = width
        self.current_height = height
        self.last_decode_latency_ms = decode_latency_ms
        self.total_completed_frames += 1

        self.frame_timestamps.append(timestamp)
        self._prune_windows(timestamp)

    def _prune_windows(self, now: float):
        """Removes entries older than window_seconds."""
        cutoff = now - self.window_seconds
        while self.packet_timestamps and self.packet_timestamps[0] < cutoff:
            self.packet_timestamps.popleft()
        while self.frame_timestamps and self.frame_timestamps[0] < cutoff:
            self.frame_timestamps.popleft()

    @property
    def packets_per_second(self) -> float:
        """Calculates current packet rate."""
        if len(self.packet_timestamps) < 2:
            return 0.0
        duration = self.packet_timestamps[-1] - self.packet_timestamps[0]
        if duration <= 0:
            return 0.0
        return (len(self.packet_timestamps) - 1) / duration

    @property
    def fps(self) -> float:
        """Calculates current frames per second (FPS)."""
        if len(self.frame_timestamps) < 2:
            return 0.0
        duration = self.frame_timestamps[-1] - self.frame_timestamps[0]
        if duration <= 0:
            return 0.0
        return (len(self.frame_timestamps) - 1) / duration

    @property
    def packet_loss_percent(self) -> float:
        """Estimates packet loss percentage based on received vs missing chunks."""
        total_expected = self.total_packets + self.total_missing_chunks
        if total_expected <= 0:
            return 0.0
        return (self.total_missing_chunks / total_expected) * 100.0

    @property
    def frame_loss_percent(self) -> float:
        """Estimates frame loss percentage."""
        total = self.total_completed_frames + self.total_incomplete_frames
        if total <= 0:
            return 0.0
        return (self.total_incomplete_frames / total) * 100.0

    def get_summary_dict(self) -> dict:
        """Returns statistical metrics dictionary."""
        return {
            "group": self.group_ip,
            "port": self.port,
            "interface": self.interface_ip,
            "fps": round(self.fps, 1),
            "pps": round(self.packets_per_second, 1),
            "packets": self.total_packets,
            "completed_frames": self.total_completed_frames,
            "incomplete_frames": self.total_incomplete_frames,
            "missing_chunks": self.total_missing_chunks,
            "duplicates": self.total_duplicate_packets,
            "out_of_order": self.total_out_of_order_packets,
            "decode_errors": self.total_decode_errors,
            "packet_loss_pct": round(self.packet_loss_percent, 2),
            "frame_loss_pct": round(self.frame_loss_percent, 2),
            "current_frame": self.current_frame_number,
            "resolution": f"{self.current_width}x{self.current_height}",
            "decode_latency_ms": round(self.last_decode_latency_ms, 2),
        }
