"""
Unit tests for VideoPacket parser.
"""

import pytest
import struct
from lkv373_receiver.receiver.packet import parse_packet, VideoPacket


def test_parse_normal_packet():
    # Frame 0x1234 (4660), Chunk 0x0005 (chunk_index=5, is_last=False)
    header = struct.pack(">HH", 0x1234, 0x0005)
    payload = b"hello_jpeg_chunk"
    raw = header + payload

    pkt = parse_packet(raw)
    assert pkt is not None
    assert pkt.frame_number == 0x1234
    assert pkt.chunk_index == 5
    assert pkt.is_last is False
    assert pkt.payload == payload


def test_parse_final_chunk():
    # Frame 0x0001, Chunk 0x800A (chunk_index=10, is_last=True)
    header = struct.pack(">HH", 0x0001, 0x800A)
    payload = b"final_jpeg_chunk"
    raw = header + payload

    pkt = parse_packet(raw)
    assert pkt is not None
    assert pkt.frame_number == 1
    assert pkt.chunk_index == 10
    assert pkt.is_last is True
    assert pkt.payload == payload


def test_parse_malformed_short_packet():
    raw = b"\x00\x01\x02"  # Less than 4 bytes
    pkt = parse_packet(raw)
    assert pkt is None


def test_parse_hdbitt_preamble_fallback():
    # 'TH' (0x5448) preamble format
    # Offset 0-1: 54 48
    # Offset 6-7: Frame 0x0002
    # Offset 10-11: Chunk 0x8003
    raw = bytearray(16)
    raw[0:2] = b"TH"
    struct.pack_into(">H", raw, 6, 2)
    struct.pack_into(">H", raw, 10, 0x8003)
    raw.extend(b"hdbitt_data")

    pkt = parse_packet(bytes(raw))
    assert pkt is not None
    assert pkt.frame_number == 2
    assert pkt.chunk_index == 3
    assert pkt.is_last is True
    assert pkt.payload == b"hdbitt_data"
