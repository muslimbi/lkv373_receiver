"""
Frame Reassembler module for HDMI-over-IP receiver.
Reconstructs complete video frames from fragmented UDP packets. Handles packet loss,
reordering, duplicate packets, frame boundaries, and stream resets.
"""

import time
import collections
from typing import Optional, List, Dict, Tuple, Generator
from packet_parser import ParsedPacket, PacketParser
from protocol import JPEG_SOI, JPEG_EOI

class FrameData:
    """Represents a reassembled video frame."""
    def __init__(
        self,
        frame_num: int,
        data: bytes,
        timestamp: float,
        is_complete: bool = True,
        missing_packets: int = 0
    ):
        self.frame_num = frame_num
        self.data = data
        self.timestamp = timestamp
        self.is_complete = is_complete
        self.missing_packets = missing_packets

class FrameReassembler:
    """
    Stateful reassembler that buffers incoming parsed packets and outputs complete video frames.
    """

    def __init__(
        self,
        max_frame_buffer_size: int = 10,
        frame_timeout_sec: float = 0.2,
        allow_incomplete_frames: bool = True
    ):
        self.max_frame_buffer_size = max_frame_buffer_size
        self.frame_timeout_sec = frame_timeout_sec
        self.allow_incomplete_frames = allow_incomplete_frames

        self.current_frame_id: Optional[int] = None
        self.current_packets: Dict[int, bytes] = {} # seq_num / index -> data
        self.last_seq_num: Optional[int] = None
        self.last_frame_timestamp: float = time.time()

        # Metrics & Statistics
        self.stats = {
            "total_packets_processed": 0,
            "total_frames_reassembled": 0,
            "incomplete_frames_delivered": 0,
            "dropped_packets": 0,
            "out_of_order_packets": 0,
            "duplicate_packets": 0,
            "stream_restarts": 0
        }

    def reset(self):
        """Resets the reassembler internal state."""
        self.current_frame_id = None
        self.current_packets.clear()
        self.last_seq_num = None
        self.last_frame_timestamp = time.time()

    def process_packet(self, packet: ParsedPacket) -> List[FrameData]:
        """
        Processes an incoming packet and returns a list of reassembled frames (if any are ready).
        """
        self.stats["total_packets_processed"] += 1
        output_frames: List[FrameData] = []
        now = time.time()

        # Check for stream restart or long timeout gap
        if now - self.last_frame_timestamp > self.frame_timeout_sec and self.current_packets:
            # Flush current incomplete frame before resetting
            flushed_frame = self._flush_current_frame(is_complete=False)
            if flushed_frame:
                output_frames.append(flushed_frame)
            self.stats["stream_restarts"] += 1

        seq = packet.seq_num
        frame_id = packet.frame_num

        # 1. Packet Reordering & Duplicate Detection if sequence numbers exist
        if seq is not None and self.last_seq_num is not None:
            if seq == self.last_seq_num:
                self.stats["duplicate_packets"] += 1
                return output_frames
            elif seq < self.last_seq_num and (self.last_seq_num - seq) < 30000:
                self.stats["out_of_order_packets"] += 1
            elif seq > self.last_seq_num + 1:
                gap = seq - (self.last_seq_num + 1)
                self.stats["dropped_packets"] += gap

        self.last_seq_num = seq if seq is not None else self.last_seq_num
        self.last_frame_timestamp = now

        # 2. Determine Frame Boundaries
        # Case A: Explicit frame index provided by header
        if frame_id is not None:
            if self.current_frame_id is None:
                self.current_frame_id = frame_id
            elif frame_id != self.current_frame_id:
                # Frame transition detected! Flush previous frame.
                frame = self._flush_current_frame(is_complete=True)
                if frame:
                    output_frames.append(frame)
                self.current_frame_id = frame_id

            packet_key = seq if seq is not None else len(self.current_packets)
            self.current_packets[packet_key] = packet.video_data

            if packet.is_frame_end:
                frame = self._flush_current_frame(is_complete=True)
                if frame:
                    output_frames.append(frame)

            return output_frames

        # Case B: Stream-based frame boundaries (e.g. NAL start codes or JPEG SOI/EOI)
        video_data = packet.video_data

        # Check if new frame starts in this packet
        is_start = packet.is_frame_start or video_data.startswith(b"\x00\x00\x00\x01") or video_data.startswith(b"\x00\x00\x01") or video_data.startswith(JPEG_SOI)
        is_end = packet.is_frame_end or JPEG_EOI in video_data[-10:]

        if is_start and self.current_packets:
            # Emit completed frame before starting new one
            frame = self._flush_current_frame(is_complete=True)
            if frame:
                output_frames.append(frame)

        packet_key = seq if seq is not None else len(self.current_packets)
        self.current_packets[packet_key] = video_data

        if is_end:
            frame = self._flush_current_frame(is_complete=True)
            if frame:
                output_frames.append(frame)

        return output_frames

    def _flush_current_frame(self, is_complete: bool) -> Optional[FrameData]:
        """Assembles buffered packet data into a single FrameData object and clears buffer."""
        if not self.current_packets:
            return None

        # Sort packets by sequence number / key
        sorted_keys = sorted(self.current_packets.keys())
        frame_bytes = bytearray()
        missing_count = 0

        prev_k = None
        for k in sorted_keys:
            if prev_k is not None and isinstance(k, int) and isinstance(prev_k, int):
                if k > prev_k + 1:
                    missing_count += (k - prev_k - 1)
            frame_bytes.extend(self.current_packets[k])
            prev_k = k

        frame_num = self.current_frame_id if self.current_frame_id is not None else self.stats["total_frames_reassembled"] + 1

        self.current_packets.clear()
        self.current_frame_id = None

        if not is_complete and not self.allow_incomplete_frames:
            return None

        self.stats["total_frames_reassembled"] += 1
        if not is_complete or missing_count > 0:
            self.stats["incomplete_frames_delivered"] += 1

        return FrameData(
            frame_num=frame_num,
            data=bytes(frame_bytes),
            timestamp=time.time(),
            is_complete=(is_complete and missing_count == 0),
            missing_packets=missing_count
        )
