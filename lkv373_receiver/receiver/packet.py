"""
LKV373 / Lenkeng HDMI-over-IP Packet Parser.

Parses individual UDP video packets containing 4-byte headers:
- Offset 0-1: Frame Number (uint16, big-endian)
- Offset 2-3: Chunk Number (uint16, big-endian)
- Bit 15 of Chunk Number (0x8000): End of frame flag
- Bits 0-14 of Chunk Number (0x7FFF): 0-indexed chunk index
- Offset 4+: JPEG chunk payload
"""

import struct
from dataclasses import dataclass
import time


@dataclass
class VideoPacket:
    """Represents a single parsed video packet from the LKV373 stream."""
    frame_number: int       # 16-bit unsigned (0..65535)
    raw_chunk_number: int   # Raw 16-bit unsigned value
    chunk_index: int        # chunk_number & 0x7FFF
    is_last: bool           # (chunk_number & 0x8000) != 0
    payload: bytes          # JPEG data chunk (starts at byte offset 4)
    timestamp: float        # Capture timestamp (seconds)


def parse_packet(data: bytes, timestamp: float | None = None) -> VideoPacket | None:
    """
    Parses raw UDP packet bytes into a VideoPacket object.
    
    Default LKV373 Format (4-byte header):
    - Offset 0-1: Frame Number (uint16, big-endian)
    - Offset 2-3: Chunk Number (uint16, big-endian)
    - Offset 4+: JPEG payload chunk
    
    Fallback HDbitT Format (16-byte header):
    - Prefix: 'TH' (0x5448)
    - Offset 6-7: Frame Number
    - Offset 10-11: Chunk Number
    - Offset 16+: JPEG payload chunk
    """
    if len(data) < 4:
        return None

    if timestamp is None:
        timestamp = time.time()

    if data.startswith(b"TH") and len(data) >= 16:
        frame_number = struct.unpack(">H", data[6:8])[0]
        raw_chunk = struct.unpack(">H", data[10:12])[0]
        payload = data[16:]
    else:
        frame_number, raw_chunk = struct.unpack(">HH", data[:4])
        payload = data[4:]

    chunk_index = raw_chunk & 0x7FFF
    is_last = (raw_chunk & 0x8000) != 0

    return VideoPacket(
        frame_number=frame_number,
        raw_chunk_number=raw_chunk,
        chunk_index=chunk_index,
        is_last=is_last,
        payload=payload,
        timestamp=timestamp,
    )
