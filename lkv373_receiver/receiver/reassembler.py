"""
LKV373 JPEG Frame Reassembler.

Reassembles fragmented UDP video chunks into complete JPEG frames.
Handles packet loss, duplicates, out-of-order chunks, sequence rollover,
and corrupted frames.
"""

from dataclasses import dataclass, field
import time
from typing import Callable
from .packet import VideoPacket


@dataclass
class ReassembledFrame:
    """Represents a reassembled frame structure."""
    frame_number: int
    chunks: dict[int, bytes] = field(default_factory=dict)
    total_chunks: int | None = None
    received_bytes: int = 0
    first_seen: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    last_chunk_index: int = -1
    out_of_order_count: int = 0
    duplicate_count: int = 0
    is_complete: bool = False
    jpeg_data: bytes | None = None


class FrameReassembler:
    """
    Stateful frame reassembler for LKV373 UDP MJPEG video stream.
    
    Maintains a bounded window of active frame buffers to prevent memory growth.
    """

    def __init__(
        self,
        max_active_frames: int = 4,
        frame_timeout_ms: float = 200.0,
        strict_jpeg: bool = True,
        on_frame_complete: Callable[[ReassembledFrame], None] | None = None,
    ):
        self.max_active_frames = max_active_frames
        self.frame_timeout_sec = frame_timeout_ms / 1000.0
        self.strict_jpeg = strict_jpeg
        self.on_frame_complete = on_frame_complete

        # Active frame buffers keyed by frame_number (0..65535)
        self.active_frames: dict[int, ReassembledFrame] = {}

        # Global stream stats
        self.total_received_packets: int = 0
        self.total_duplicate_packets: int = 0
        self.total_out_of_order_packets: int = 0
        self.total_completed_frames: int = 0
        self.total_incomplete_frames: int = 0
        self.total_corrupted_jpegs: int = 0
        self.total_missing_chunks: int = 0
        self.last_completed_frame_num: int = -1

    def process_packet(self, packet: VideoPacket) -> ReassembledFrame | None:
        """
        Processes a parsed VideoPacket.
        
        Returns a ReassembledFrame if a frame is completed by this packet,
        otherwise returns None.
        """
        self.total_received_packets += 1
        fn = packet.frame_number
        now = packet.timestamp

        # Flush aged / stale active frames, infer total_chunks for older frames if frame number advanced
        completed_from_cleanup = self._cleanup_stale_frames(current_time=now, current_frame_num=fn)

        # Get or initialize frame buffer
        if fn not in self.active_frames:
            # Enforce max active frame limit
            if len(self.active_frames) >= self.max_active_frames:
                self._evict_oldest_frame()

            self.active_frames[fn] = ReassembledFrame(frame_number=fn, first_seen=now, last_updated=now)

        frame = self.active_frames[fn]
        frame.last_updated = now

        # Check duplicate chunk
        if packet.chunk_index in frame.chunks:
            frame.duplicate_count += 1
            self.total_duplicate_packets += 1
            return completed_from_cleanup

        # Check out of order chunk
        if frame.chunks and packet.chunk_index < frame.last_chunk_index:
            frame.out_of_order_count += 1
            self.total_out_of_order_packets += 1

        frame.last_chunk_index = max(frame.last_chunk_index, packet.chunk_index)
        frame.chunks[packet.chunk_index] = packet.payload
        frame.received_bytes += len(packet.payload)

        # Handle explicit last chunk flag
        if packet.is_last:
            frame.total_chunks = packet.chunk_index + 1

        # Check if frame is ready to reassemble
        if frame.total_chunks is not None and len(frame.chunks) == frame.total_chunks:
            completed_frame = self._assemble_and_validate(fn)
            if completed_frame:
                if self.on_frame_complete:
                    self.on_frame_complete(completed_frame)
                return completed_frame

        return completed_from_cleanup

    def _assemble_and_validate(self, frame_num: int) -> ReassembledFrame | None:
        """Concatenates sorted chunks and validates JPEG SOI/EOI markers."""
        frame = self.active_frames.pop(frame_num, None)
        if not frame or frame.total_chunks is None:
            return None

        # Sort chunks 0 .. total_chunks - 1
        sorted_chunks = []
        for idx in range(frame.total_chunks):
            chunk_data = frame.chunks.get(idx)
            if chunk_data is None:
                # Missing chunk inside supposedly complete frame
                self.total_incomplete_frames += 1
                self.total_missing_chunks += 1
                return None
            sorted_chunks.append(chunk_data)

        raw_jpeg = b"".join(sorted_chunks)

        # Verify JPEG SOI (0xFF 0xD8) and EOI (0xFF 0xD9)
        if not raw_jpeg.startswith(b"\xff\xd8"):
            self.total_corrupted_jpegs += 1
            return None

        eoi_idx = raw_jpeg.rfind(b"\xff\xd9")
        if eoi_idx == -1:
            if self.strict_jpeg:
                self.total_corrupted_jpegs += 1
                return None
            clean_jpeg = raw_jpeg
        else:
            # Trim trailing padding past FF D9
            clean_jpeg = raw_jpeg[: eoi_idx + 2]

        frame.is_complete = True
        frame.jpeg_data = clean_jpeg
        self.total_completed_frames += 1
        self.last_completed_frame_num = frame_num

        return frame

    def _cleanup_stale_frames(self, current_time: float, current_frame_num: int) -> ReassembledFrame | None:
        """Flushes incomplete frames that have timed out or are superseded by newer frames."""
        to_remove = []
        assembled_frame = None

        for fn, frame in list(self.active_frames.items()):
            # 1. Check if frame sequence advanced to a newer frame
            diff = (current_frame_num - fn) & 0xFFFF
            if 0 < diff < 32768:
                # Frame number advanced. If frame is not marked total_chunks, set total_chunks to max_chunk_index + 1
                if frame.total_chunks is None and frame.last_chunk_index >= 0:
                    # If all chunks 0..last_chunk_index are present, attempt assembly
                    if len(frame.chunks) == frame.last_chunk_index + 1:
                        frame.total_chunks = frame.last_chunk_index + 1
                        res = self._assemble_and_validate(fn)
                        if res:
                            if self.on_frame_complete:
                                self.on_frame_complete(res)
                            assembled_frame = res
                            continue

            # 2. Timeout check
            if current_time - frame.last_updated > self.frame_timeout_sec:
                to_remove.append(fn)
                continue

            # 3. Sequence distance check (16-bit rollover aware)
            if 0 < diff < 32768 and diff > 30:  # More than 30 frames behind
                to_remove.append(fn)

        for fn in to_remove:
            frame = self.active_frames.pop(fn, None)
            if frame:
                self.total_incomplete_frames += 1
                if frame.total_chunks:
                    missing = frame.total_chunks - len(frame.chunks)
                    self.total_missing_chunks += max(0, missing)
                else:
                    self.total_missing_chunks += 1

        return assembled_frame

    def _evict_oldest_frame(self):
        """Evicts the oldest active frame when capacity is reached."""
        if not self.active_frames:
            return

        oldest_fn = min(self.active_frames.keys(), key=lambda fn: self.active_frames[fn].first_seen)
        frame = self.active_frames.pop(oldest_fn, None)
        if frame:
            self.total_incomplete_frames += 1

    def reset(self):
        """Resets reassembler state and statistics."""
        self.active_frames.clear()
        self.total_received_packets = 0
        self.total_duplicate_packets = 0
        self.total_out_of_order_packets = 0
        self.total_completed_frames = 0
        self.total_incomplete_frames = 0
        self.total_corrupted_jpegs = 0
        self.total_missing_chunks = 0
        self.last_completed_frame_num = -1
