"""
Unit tests for FrameReassembler.
"""

import pytest
from packet_parser import ParsedPacket
from frame_reassembler import FrameReassembler

def test_reassembler_frame_reconstruction():
    reassembler = FrameReassembler()

    # Packet 1 (Start of Frame 100)
    p1 = ParsedPacket(
        raw_payload=b"HDR_16_BYTES____" + b"\xff\xd8FRAME1_PART1_",
        header_len=16,
        seq_num=0,
        frame_num=100,
        is_frame_start=True,
        payload_offset=16
    )
    # Packet 2 (End of Frame 100)
    p2 = ParsedPacket(
        raw_payload=b"HDR_16_BYTES____" + b"FRAME1_PART2_\xff\xd9",
        header_len=16,
        seq_num=1,
        frame_num=100,
        is_frame_end=True,
        payload_offset=16
    )

    f1 = reassembler.process_packet(p1)
    assert len(f1) == 0 # Buffer packet 1

    f2 = reassembler.process_packet(p2)
    assert len(f2) == 1 # Reassembled frame 100!
    frame = f2[0]
    assert frame.frame_num == 100
    assert frame.data == b"\xff\xd8FRAME1_PART1_FRAME1_PART2_\xff\xd9"
    assert frame.is_complete is True

def test_reassembler_packet_loss_tracking():
    reassembler = FrameReassembler()

    p1 = ParsedPacket(raw_payload=b"P1", seq_num=1, frame_num=1, payload_offset=0)
    p3 = ParsedPacket(raw_payload=b"P3", seq_num=3, frame_num=1, is_frame_end=True, payload_offset=0)

    reassembler.process_packet(p1)
    frames = reassembler.process_packet(p3)

    assert len(frames) == 1
    assert frames[0].missing_packets == 1
    assert reassembler.stats["dropped_packets"] == 1
