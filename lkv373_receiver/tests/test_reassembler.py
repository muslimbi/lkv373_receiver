"""
Unit tests for FrameReassembler stateful frame assembly logic.
"""

import pytest
from lkv373_receiver.receiver.packet import VideoPacket
from lkv373_receiver.receiver.reassembler import FrameReassembler


def make_packet(frame_num: int, chunk_idx: int, is_last: bool, payload: bytes, ts: float = 100.0) -> VideoPacket:
    raw_chunk = (0x8000 if is_last else 0x0000) | (chunk_idx & 0x7FFF)
    return VideoPacket(
        frame_number=frame_num,
        raw_chunk_number=raw_chunk,
        chunk_index=chunk_idx,
        is_last=is_last,
        payload=payload,
        timestamp=ts,
    )


def test_normal_frame_reassembly():
    reassembler = FrameReassembler(strict_jpeg=False)

    # Valid fake JPEG stream: b'\xff\xd8' + payload + b'\xff\xd9'
    chunk0 = b"\xff\xd8HEADER_DATA_"
    chunk1 = b"BODY_DATA_"
    chunk2 = b"TRAILER_DATA\xff\xd9"

    pkt0 = make_packet(1, 0, False, chunk0)
    pkt1 = make_packet(1, 1, False, chunk1)
    pkt2 = make_packet(1, 2, True, chunk2)

    assert reassembler.process_packet(pkt0) is None
    assert reassembler.process_packet(pkt1) is None

    completed = reassembler.process_packet(pkt2)
    assert completed is not None
    assert completed.is_complete is True
    assert completed.frame_number == 1
    assert completed.jpeg_data == chunk0 + chunk1 + chunk2


def test_out_of_order_chunks():
    reassembler = FrameReassembler(strict_jpeg=False)

    chunk0 = b"\xff\xd8AAA"
    chunk1 = b"BBB"
    chunk2 = b"CCC\xff\xd9"

    pkt2 = make_packet(5, 2, True, chunk2)
    pkt0 = make_packet(5, 0, False, chunk0)
    pkt1 = make_packet(5, 1, False, chunk1)

    assert reassembler.process_packet(pkt2) is None
    assert reassembler.process_packet(pkt0) is None

    completed = reassembler.process_packet(pkt1)
    assert completed is not None
    assert completed.is_complete is True
    assert completed.jpeg_data == b"\xff\xd8AAABBBCCC\xff\xd9"
    assert reassembler.total_out_of_order_packets > 0


def test_duplicate_chunk_handling():
    reassembler = FrameReassembler(strict_jpeg=False)

    chunk0 = b"\xff\xd8HEADER"
    pkt0 = make_packet(10, 0, False, chunk0)
    
    reassembler.process_packet(pkt0)

    # Duplicate chunk 0
    res = reassembler.process_packet(pkt0)
    assert res is None
    assert reassembler.total_duplicate_packets == 1


def test_missing_chunk_discard():
    reassembler = FrameReassembler(strict_jpeg=True, frame_timeout_ms=100.0)

    chunk0 = b"\xff\xd8PARTIAL"
    # Chunk 1 missing!
    chunk2 = b"END\xff\xd9"

    pkt0 = make_packet(20, 0, False, chunk0, ts=10.0)
    pkt2 = make_packet(20, 2, True, chunk2, ts=10.0)

    reassembler.process_packet(pkt0)
    reassembler.process_packet(pkt2)

    # Trigger timeout cleanup via new packet far in future
    pkt_future = make_packet(25, 0, False, b"\xff\xd8NEXT", ts=10.5)
    reassembler.process_packet(pkt_future)

    assert reassembler.total_incomplete_frames > 0


def test_frame_number_rollover():
    reassembler = FrameReassembler(strict_jpeg=False)

    # 16-bit sequence number 65535 -> 0
    chunk_last = b"\xff\xd8FRAME_65535\xff\xd9"
    pkt_65535 = make_packet(65535, 0, True, chunk_last)

    completed = reassembler.process_packet(pkt_65535)
    assert completed is not None
    assert completed.frame_number == 65535

    chunk_zero = b"\xff\xd8FRAME_00000\xff\xd9"
    pkt_0 = make_packet(0, 0, True, chunk_zero)

    completed_zero = reassembler.process_packet(pkt_0)
    assert completed_zero is not None
    assert completed_zero.frame_number == 0


def test_invalid_jpeg_magic_rejection():
    reassembler = FrameReassembler(strict_jpeg=True)

    # Corrupted header: Not b'\xff\xd8'
    chunk0 = b"INVALID_HEADER_DATA\xff\xd9"
    pkt0 = make_packet(30, 0, True, chunk0)

    res = reassembler.process_packet(pkt0)
    assert res is None
    assert reassembler.total_corrupted_jpegs == 1
