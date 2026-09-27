"""
Unit tests for Codec & Signature Detection.
"""

import pytest
from packet_parser import PacketParser
from protocol import CodecType

def test_h264_signature_detection():
    parser = PacketParser()
    packets = [
        b"\x00\x00\x00\x01\x67\x42\x00\x0a" + b"\x00" * 200, # SPS NAL
        b"\x00\x00\x00\x01\x68\xce\x3c\x80" + b"\x00" * 200, # PPS NAL
        b"\x00\x00\x00\x01\x65\x88\x84\x00" + b"\x00" * 200, # IDR NAL
    ]
    info = parser.detect_stream_characteristics(packets)
    assert info.codec == CodecType.H264
    assert info.confidence >= 0.8

def test_mpeg_ts_signature_detection():
    parser = PacketParser()
    packets = [
        b"\x47\x00\x11\x10" + b"\xff" * 184,
        b"\x47\x01\x00\x10" + b"\xff" * 184,
    ]
    info = parser.detect_stream_characteristics(packets)
    assert info.codec == CodecType.MPEG_TS
    assert info.confidence >= 0.9
