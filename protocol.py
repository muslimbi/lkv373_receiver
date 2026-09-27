"""
HDMI-over-IP Protocol Definitions & Signatures.
Defines supported protocol structures, magic headers, and codec signatures.
"""

import enum
from typing import Optional, Dict, Any

class CodecType(enum.Enum):
    UNKNOWN = "UNKNOWN"
    H264 = "H.264/AVC"
    H265 = "H.265/HEVC"
    MJPEG = "MJPEG"
    MPEG_TS = "MPEG-TS"
    RAW_YUV = "RAW YUV/RGB"
    PROPRIETARY = "PROPRIETARY"
    ENCRYPTED = "ENCRYPTED"

class EncapsulationType(enum.Enum):
    UNKNOWN = "UNKNOWN"
    RAW_UDP = "RAW_UDP"
    RTP = "RTP"
    MPEG_TS_UDP = "MPEG_TS_UDP"
    HDbitT = "HDbitT / Lenkeng"
    CUSTOM_HEADER = "CUSTOM_HEADER"

# Common Magic Signatures
MPEG_TS_SYNC_BYTE = 0x47
JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"

# H.264 Annex-B NAL start codes
H264_START_CODE_3 = b"\x00\x00\x01"
H264_START_CODE_4 = b"\x00\x00\x00\x01"

# HDbitT / Lenkeng 16-byte header signature pattern (LKV373, etc.)
# Typically starts with magic bytes like 0x54 0x48 (TH) or 0x48 0x44 (HD) or sequence markers
HDBITT_MAGIC_1 = b"\x54\x48"
HDBITT_MAGIC_2 = b"\x48\x44"

class StreamInfo:
    def __init__(
        self,
        codec: CodecType = CodecType.UNKNOWN,
        encapsulation: EncapsulationType = EncapsulationType.UNKNOWN,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
        header_size: int = 0,
        has_sequence_number: bool = False,
        has_frame_number: bool = False,
        confidence: float = 0.0,
        notes: str = ""
    ):
        self.codec = codec
        self.encapsulation = encapsulation
        self.width = width
        self.height = height
        self.fps = fps
        self.header_size = header_size
        self.has_sequence_number = has_sequence_number
        self.has_frame_number = has_frame_number
        self.confidence = confidence
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "codec": self.codec.value,
            "encapsulation": self.encapsulation.value,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "header_size": self.header_size,
            "has_sequence_number": self.has_sequence_number,
            "has_frame_number": self.has_frame_number,
            "confidence": self.confidence,
            "notes": self.notes
        }
