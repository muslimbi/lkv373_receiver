"""
Packet Parser module for HDMI-over-IP receiver.
Parses low-level network packets, extracts encapsulation headers, sequence numbers,
frame boundaries, and identifies payload types based on packet evidence.
"""

import struct
import math
import logging
from typing import Tuple, Optional, Dict, Any
from protocol import CodecType, EncapsulationType, StreamInfo, JPEG_SOI, JPEG_EOI, MPEG_TS_SYNC_BYTE

class ParsedPacket:
    """Class representing a parsed network packet with extracted metadata and payload."""
    def __init__(
        self,
        raw_payload: bytes,
        header_len: int = 0,
        seq_num: Optional[int] = None,
        frame_num: Optional[int] = None,
        timestamp: Optional[int] = None,
        is_frame_start: bool = False,
        is_frame_end: bool = False,
        payload_offset: int = 0
    ):
        self.raw_payload = raw_payload
        self.header_len = header_len
        self.seq_num = seq_num
        self.frame_num = frame_num
        self.timestamp = timestamp
        self.is_frame_start = is_frame_start
        self.is_frame_end = is_frame_end
        self.payload_offset = payload_offset

    @property
    def video_data(self) -> bytes:
        return self.raw_payload[self.payload_offset:]

class PacketParser:
    """
    Analyzes UDP packet payloads to detect encapsulation headers and extract frame data.
    Does NOT assume any format upfront; inspects actual byte patterns adaptively.
    """

    def __init__(self):
        self.detected_encapsulation = EncapsulationType.UNKNOWN
        self.detected_codec = CodecType.UNKNOWN
        self.auto_header_len: Optional[int] = None

    @staticmethod
    def calculate_entropy(data: bytes) -> float:
        """Calculates Shannon entropy of byte sequence (0.0 to 8.0). High entropy indicates compression or encryption."""
        if not data:
            return 0.0
        entropy = 0.0
        length = len(data)
        freqs = {}
        for b in data:
            freqs[b] = freqs.get(b, 0) + 1
        for count in freqs.values():
            p = count / length
            entropy -= p * math.log2(p)
        return entropy

    def parse_packet(self, data: bytes) -> ParsedPacket:
        """
        Parses a single raw UDP payload data buffer and returns a ParsedPacket object.
        Adaptively detects header offsets for NTI ST-IPHD-LC and HDbitT extenders.
        """
        if not data or len(data) < 4:
            return ParsedPacket(data)

        # 1. MPEG-TS Check (188 byte packets or 7x188 = 1316 byte UDP packets starting with 0x47)
        if len(data) >= 188 and data[0] == MPEG_TS_SYNC_BYTE:
            return ParsedPacket(
                raw_payload=data,
                header_len=0,
                payload_offset=0,
                is_frame_start=False,
                is_frame_end=False
            )

        # 2. RTP Header Check (Version=2, top 2 bits == 10b, header len >= 12)
        if len(data) >= 12 and ((data[0] >> 6) & 0x03) == 2:
            pt = data[1] & 0x7F
            seq = struct.unpack(">H", data[2:4])[0]
            ts = struct.unpack(">I", data[4:8])[0]
            marker = (data[1] & 0x80) != 0
            csrc_count = data[0] & 0x0F
            rtp_hdr_len = 12 + (csrc_count * 4)
            return ParsedPacket(
                raw_payload=data,
                header_len=rtp_hdr_len,
                seq_num=seq,
                timestamp=ts,
                is_frame_end=marker,
                payload_offset=rtp_hdr_len
            )

        # 3. Dynamic Video SOI Marker Scan (JPEG Start of Image 0xFFD8 or H264 NAL Start Code)
        # Search for 0xFFD8 in the first 32 bytes to discover exact header length
        soi_idx = data[:32].find(JPEG_SOI)
        if soi_idx != -1:
            if self.auto_header_len is None or self.auto_header_len != soi_idx:
                self.auto_header_len = soi_idx
                logging.info(f"[PacketParser] Auto-discovered JPEG payload header offset: {soi_idx} bytes")

            # Extract sequence number / frame number from header if present
            seq_num = None
            frame_num = None
            if soi_idx >= 12 and len(data) >= 12:
                try:
                    frame_num = struct.unpack(">I", data[4:8])[0]
                    seq_num = struct.unpack(">I", data[8:12])[0]
                except Exception:
                    pass

            return ParsedPacket(
                raw_payload=data,
                header_len=soi_idx,
                seq_num=seq_num if seq_num is not None else 0,
                frame_num=frame_num,
                is_frame_start=True,
                payload_offset=soi_idx
            )

        # 4. HDbitT / Lenkeng 16-byte Header Check (Magic 'TH', 'HD', 'PK', or general 16b header)
        if len(data) > 16:
            magic = data[0:2]
            if magic in (b"\x54\x48", b"\x48\x44", b"\x50\x4b") or self.auto_header_len == 16:
                try:
                    frame_num = struct.unpack(">I", data[4:8])[0]
                    pkt_num = struct.unpack(">I", data[8:12])[0]
                    is_start = (pkt_num == 0)
                    is_end = (JPEG_EOI in data[-10:])
                    return ParsedPacket(
                        raw_payload=data,
                        header_len=16,
                        seq_num=pkt_num,
                        frame_num=frame_num,
                        is_frame_start=is_start,
                        is_frame_end=is_end,
                        payload_offset=16
                    )
                except Exception:
                    pass

        # 5. Use learned auto_header_len for intermediate packet chunks
        offset = self.auto_header_len if self.auto_header_len is not None else 0

        # Check for frame end indicator (JPEG EOI 0xFFD9)
        is_end = JPEG_EOI in data[-10:]

        # Extract sequence counter candidate if offset >= 4
        seq_num = None
        if offset >= 12 and len(data) >= 12:
            try:
                seq_num = struct.unpack(">I", data[8:12])[0]
            except Exception:
                pass
        elif offset >= 4 and len(data) >= 4:
            try:
                seq_num = struct.unpack(">I", data[0:4])[0]
            except Exception:
                pass

        return ParsedPacket(
            raw_payload=data,
            header_len=offset,
            seq_num=seq_num,
            is_frame_start=False,
            is_frame_end=is_end,
            payload_offset=offset
        )

    def detect_stream_characteristics(self, sample_packets: list[bytes]) -> StreamInfo:
        """
        Analyzes a batch of sample raw packets to determine protocol, header structure, and likely codec.
        """
        if not sample_packets:
            return StreamInfo(notes="No packets provided for analysis")

        ts_count = 0
        h264_count = 0
        h265_count = 0
        mjpeg_count = 0
        rtp_count = 0
        hdbitt_count = 0
        entropies = []

        for pkt in sample_packets:
            parsed = self.parse_packet(pkt)
            video_data = parsed.video_data
            entropies.append(self.calculate_entropy(pkt))

            if len(pkt) >= 188 and pkt[0] == MPEG_TS_SYNC_BYTE:
                ts_count += 1
            if len(pkt) >= 12 and ((pkt[0] >> 6) & 0x03) == 2:
                rtp_count += 1
            if len(pkt) > 16 and (pkt[0:2] in (b"\x54\x48", b"\x48\x44", b"\x50\x4b") or self.auto_header_len == 16):
                hdbitt_count += 1

            if b"\x00\x00\x00\x01\x67" in video_data or b"\x00\x00\x01\x67" in video_data or b"\x00\x00\x00\x01\x65" in video_data:
                h264_count += 1
            elif b"\x00\x00\x00\x01\x40" in video_data or b"\x00\x00\x01\x40" in video_data:
                h265_count += 1
            elif JPEG_SOI in video_data or JPEG_EOI in video_data or b"JFIF" in video_data or JPEG_SOI in pkt[:32]:
                mjpeg_count += 1

        total = len(sample_packets)
        avg_entropy = sum(entropies) / total if total > 0 else 0.0

        codec = CodecType.UNKNOWN
        encap = EncapsulationType.RAW_UDP
        confidence = 0.5
        notes = f"Average packet entropy: {avg_entropy:.2f} bits/byte."

        if ts_count / total > 0.5:
            codec = CodecType.MPEG_TS
            encap = EncapsulationType.MPEG_TS_UDP
            confidence = 0.95
            notes += " Strong MPEG-TS 0x47 sync byte presence."
        elif h264_count > 0:
            codec = CodecType.H264
            confidence = 0.90
            notes += " Detected H.264 Annex-B NAL headers."
        elif h265_count > 0:
            codec = CodecType.H265
            confidence = 0.90
            notes += " Detected H.265 NAL headers."
        elif mjpeg_count > 0:
            codec = CodecType.MJPEG
            confidence = 0.95
            hdr_info = f" Header length: {self.auto_header_len} bytes." if self.auto_header_len is not None else ""
            notes += f" Detected JPEG/JFIF SOI/EOI frame boundary markers.{hdr_info}"
        elif avg_entropy > 7.5:
            codec = CodecType.PROPRIETARY
            confidence = 0.60
            notes += " High entropy payload."

        if rtp_count / total > 0.8:
            encap = EncapsulationType.RTP
        elif hdbitt_count / total > 0.5 or self.auto_header_len == 16:
            encap = EncapsulationType.HDbitT

        return StreamInfo(
            codec=codec,
            encapsulation=encap,
            header_size=self.auto_header_len if self.auto_header_len is not None else 0,
            confidence=confidence,
            notes=notes
        )
