"""
Unit tests for PacketParser.
"""

import pytest
import struct
from packet_parser import PacketParser, ParsedPacket
from protocol import CodecType, EncapsulationType

def test_packet_entropy():
    parser = PacketParser()
    # Zero entropy for identical bytes
    assert parser.calculate_entropy(b"\x00" * 100) == 0.0
    # High entropy for pseudorandom/varied bytes
    high_entropy_data = bytes(range(256)) * 4
    assert parser.calculate_entropy(high_entropy_data) > 7.9

def test_hdbitt_header_parsing():
    parser = PacketParser()
    # Construct synthetic HDbitT header: 'TH' (2b), type 1 (2b), frame 42 (4b), packet 0 (4b), reserved (4b) + payload
    hdr = struct.pack(">2sHII4s", b"TH", 1, 42, 0, b"\x00\x00\x00\x00")
    payload = hdr + b"\xff\xd8\xff\xe0\x00\x10JFIF"
    parsed = parser.parse_packet(payload)

    assert parsed.header_len == 16
    assert parsed.frame_num == 42
    assert parsed.seq_num == 0
    assert parsed.is_frame_start is True
    assert parsed.video_data.startswith(b"\xff\xd8")

def test_rtp_header_parsing():
    parser = PacketParser()
    # Construct RTP V=2, PT=96, Seq=1234, TS=5678, SSRC=9999
    rtp_hdr = struct.pack(">BBHII", 0x80, 96, 1234, 5678, 9999)
    payload = rtp_hdr + b"\x00\x00\x00\x01\x67SPS_DATA"
    parsed = parser.parse_packet(payload)

    assert parsed.header_len == 12
    assert parsed.seq_num == 1234
    assert parsed.timestamp == 5678

def test_stream_characteristics_detection():
    parser = PacketParser()
    # Generate batch of synthetic HDbitT JPEG packets
    packets = []
    for f in range(5):
        hdr = struct.pack(">2sHII4s", b"TH", 1, f, 0, b"\x00\x00\x00\x00")
        packets.append(hdr + b"\xff\xd8\xff\xe0" + b"\x00" * 500 + b"\xff\xd9")

    info = parser.detect_stream_characteristics(packets)
    assert info.codec == CodecType.MJPEG
    assert info.encapsulation == EncapsulationType.HDbitT
    assert info.confidence >= 0.8
