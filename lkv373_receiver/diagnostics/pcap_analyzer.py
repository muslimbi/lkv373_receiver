"""
PCAP, PCAPNG & Binary Dump Analyzer for LKV373 Streams.

Reads capture files and extracts UDP packets, parsing IP, ports, VLAN tags,
LKV373 video frame sequences, audio packets, and control streams.
"""

import os
import struct
import socket
from dataclasses import dataclass, field
from collections import Counter
import cv2
import numpy as np


@dataclass
class ExtractedPacket:
    """Represents an extracted UDP packet from a PCAP/PCAPNG file."""
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    payload: bytes
    timestamp: float = 0.0
    vlan_id: int | None = None


@dataclass
class PCAPAnalysisResult:
    """Comprehensive analysis report of a PCAP capture file."""
    filepath: str
    file_size_bytes: int
    total_packets: int
    video_packets_count: int
    audio_packets_count: int
    control_packets_count: int
    other_packets_count: int
    src_ips: list[str]
    dst_ips: list[str]
    ports_summary: dict[str, int]
    payload_sizes: dict[str, int]  # min, max, avg
    frame_numbers_range: tuple[int, int]
    reconstructed_jpegs_count: int
    jpeg_sizes: list[int]
    detected_resolution: tuple[int, int] | None
    estimated_fps: float
    notes: list[str] = field(default_factory=list)


class PCAPAnalyzer:
    """
    Parser and Analyzer for PCAP, PCAPNG, and 4-byte length-prefixed raw dumps.
    """

    def __init__(self, filepath: str):
        self.filepath = filepath

    def extract_udp_packets(self) -> list[ExtractedPacket]:
        """Reads PCAP/PCAPNG/Binary file and extracts all UDP packets."""
        if not os.path.exists(self.filepath):
            return []

        with open(self.filepath, "rb") as f:
            data = f.read()

        if not data:
            return []

        packets = []

        # 1. Check Standard PCAP Magic Bytes (0xa1b2c3d4, 0xd4c3b2a1, 0xa1b23c4d, 0x4db2b2a1)
        if data.startswith(b"\xa1\xb2\xc3\xd4") or data.startswith(b"\xd4\xc3\xb2\xa1") or \
           data.startswith(b"\xa1\xb2\x3c\x4d") or data.startswith(b"\x4d\x3c\xb2\xa1"):
            endian = ">" if (data.startswith(b"\xa1\xb2\xc3\xd4") or data.startswith(b"\xa1\xb2\x3c\x4d")) else "<"
            offset = 24  # Skip global header
            data_len = len(data)

            while offset + 16 <= data_len:
                ts_sec, ts_usec, incl_len, orig_len = struct.unpack(f"{endian}IIII", data[offset:offset+16])
                offset += 16
                if offset + incl_len > data_len:
                    break
                packet_raw = data[offset:offset+incl_len]
                offset += incl_len

                ts = ts_sec + (ts_usec / 1e6)
                pkt = self._parse_raw_ethernet_packet(packet_raw, ts)
                if pkt:
                    packets.append(pkt)

        # 2. Check PCAPNG Block Magic (Section Header Block 0x0A0D0D0A)
        elif data.startswith(b"\x0a\x0d\x0d\x0a"):
            endian = "<"
            offset = 0
            data_len = len(data)

            while offset + 8 <= data_len:
                block_type_raw = data[offset:offset+4]
                block_type = struct.unpack(f"{endian}I", block_type_raw)[0]
                block_len = struct.unpack(f"{endian}I", data[offset+4:offset+8])[0]

                if block_len < 12 or offset + block_len > data_len:
                    break

                # Section Header Block (SHB - 0x0A0D0D0A)
                if block_type == 0x0A0D0D0A and block_len >= 12:
                    magic = data[offset+8:offset+12]
                    if magic == b"\x4d\x3c\x2b\x1a":
                        endian = "<"
                    elif magic == b"\x1a\x2b\x3c\x4d":
                        endian = ">"

                # Enhanced Packet Block (EPB - 0x00000006)
                elif block_type == 0x00000006 and block_len >= 32:
                    interface_id, ts_hi, ts_lo, cap_len, orig_len = struct.unpack(f"{endian}IIIII", data[offset+8:offset+28])
                    raw_ts = (ts_hi << 32) | ts_lo
                    ts = raw_ts / 1e9 if raw_ts > 1e12 else raw_ts / 1e6
                    pkt_data = data[offset+28 : offset+28+cap_len]
                    pkt = self._parse_raw_ethernet_packet(pkt_data, ts)
                    if pkt:
                        packets.append(pkt)

                # Simple Packet Block (SPB - 0x00000003)
                elif block_type == 0x00000003 and block_len >= 16:
                    orig_len = struct.unpack(f"{endian}I", data[offset+8:offset+12])[0]
                    cap_len = block_len - 16
                    pkt_data = data[offset+12 : offset+12+cap_len]
                    pkt = self._parse_raw_ethernet_packet(pkt_data, offset / 1000.0)
                    if pkt:
                        packets.append(pkt)

                # Move to next block (aligned to 32 bits)
                padded_len = (block_len + 3) & ~3
                offset += padded_len

        # 3. Fallback: Check 4-byte length-prefixed raw UDP payload dump
        else:
            offset = 0
            data_len = len(data)
            is_length_prefixed = True

            # Quick check
            temp_off = 0
            while temp_off < min(data_len, 4000):
                if temp_off + 4 > data_len:
                    break
                pkt_len = int.from_bytes(data[temp_off:temp_off+4], "big")
                if not (4 <= pkt_len <= 65535):
                    is_length_prefixed = False
                    break
                temp_off += 4 + pkt_len

            if is_length_prefixed and temp_off > 0:
                offset = 0
                while offset + 4 <= data_len:
                    pkt_len = int.from_bytes(data[offset:offset+4], "big")
                    offset += 4
                    if offset + pkt_len <= data_len:
                        payload = data[offset:offset+pkt_len]
                        offset += pkt_len
                        # Default mock headers for raw dumps
                        packets.append(ExtractedPacket(
                            src_ip="192.168.168.55",
                            dst_ip="226.2.2.2",
                            src_port=2068,
                            dst_port=2068,
                            payload=payload,
                            timestamp=offset / 100000.0
                        ))
                    else:
                        break
            else:
                # Raw chunking fallback
                chunk_size = 1024
                for i in range(0, data_len, chunk_size):
                    chunk = data[i:i+chunk_size]
                    if len(chunk) >= 4:
                        packets.append(ExtractedPacket(
                            src_ip="192.168.168.55",
                            dst_ip="226.2.2.2",
                            src_port=2068,
                            dst_port=2068,
                            payload=chunk,
                            timestamp=i / 100000.0
                        ))

        return packets

    def _parse_raw_ethernet_packet(self, raw: bytes, timestamp: float) -> ExtractedPacket | None:
        """Parses raw link-layer packet for IPv4 UDP headers."""
        if len(raw) < 34:
            return None

        # Check for VLAN 802.1Q (0x8100) or IPv4 (0x0800)
        vlan_id = None
        ip_offset = -1

        # Search for IPv4 header magic (0x45, 0x00)
        # Standard ethernet header is 14 bytes
        if raw[12:14] == b"\x81\x00" and len(raw) >= 18:
            # 802.1Q VLAN Tagged
            vlan_tci = struct.unpack(">H", raw[14:16])[0]
            vlan_id = vlan_tci & 0x0FFF
            if raw[16:18] == b"\x08\x00":
                ip_offset = 18
        elif raw[12:14] == b"\x08\x00":
            ip_offset = 14
        else:
            # Fallback scan for IPv4 header
            idx = raw.find(b"\x45\x00")
            if idx != -1:
                ip_offset = idx

        if ip_offset == -1 or len(raw) < ip_offset + 20:
            return None

        # Parse IPv4 Header
        version_ihl = raw[ip_offset]
        ihl = (version_ihl & 0x0F) * 4
        protocol = raw[ip_offset + 9]

        if protocol != 17:  # Must be UDP
            return None

        src_ip = socket.inet_ntoa(raw[ip_offset+12 : ip_offset+16])
        dst_ip = socket.inet_ntoa(raw[ip_offset+16 : ip_offset+20])

        udp_offset = ip_offset + ihl
        if len(raw) < udp_offset + 8:
            return None

        src_port, dst_port, udp_len, udp_chk = struct.unpack(">HHHH", raw[udp_offset:udp_offset+8])
        payload = raw[udp_offset+8 : udp_offset+udp_len]

        return ExtractedPacket(
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=src_port,
            dst_port=dst_port,
            payload=payload,
            timestamp=timestamp,
            vlan_id=vlan_id,
        )

    def analyze(self) -> PCAPAnalysisResult:
        """Executes full diagnostic analysis of the capture file."""
        packets = self.extract_udp_packets()
        file_size = os.path.getsize(self.filepath) if os.path.exists(self.filepath) else 0

        if not packets:
            return PCAPAnalysisResult(
                filepath=self.filepath,
                file_size_bytes=file_size,
                total_packets=0,
                video_packets_count=0,
                audio_packets_count=0,
                control_packets_count=0,
                other_packets_count=0,
                src_ips=[],
                dst_ips=[],
                ports_summary={},
                payload_sizes={"min": 0, "max": 0, "avg": 0},
                frame_numbers_range=(0, 0),
                reconstructed_jpegs_count=0,
                jpeg_sizes=[],
                detected_resolution=None,
                estimated_fps=0.0,
                notes=["No UDP packets extracted or file empty."]
            )

        src_ips = sorted(list(set(p.src_ip for p in packets)))
        dst_ips = sorted(list(set(p.dst_ip for p in packets)))
        port_counts = Counter(p.dst_port for p in packets)
        ports_summary = {str(k): v for k, v in port_counts.items()}

        video_packets = [p for p in packets if p.dst_port == 2068]
        audio_packets = [p for p in packets if p.dst_port == 2066]
        control_packets = [p for p in packets if p.dst_port in (2065, 2067)]
        other_packets = [p for p in packets if p not in video_packets and p not in audio_packets and p not in control_packets]

        payload_lens = [len(p.payload) for p in video_packets] if video_packets else [len(p.payload) for p in packets]
        payload_sizes = {
            "min": min(payload_lens) if payload_lens else 0,
            "max": max(payload_lens) if payload_lens else 0,
            "avg": round(sum(payload_lens) / len(payload_lens), 1) if payload_lens else 0,
        }

        # Frame reassembly test
        from ..receiver.packet import parse_packet
        from ..receiver.reassembler import FrameReassembler

        reassembled_jpegs = []
        frame_nums = []

        def on_complete(frame):
            if frame.jpeg_data:
                reassembled_jpegs.append(frame.jpeg_data)

        reassembler = FrameReassembler(max_active_frames=10, on_frame_complete=on_complete)

        for p in video_packets:
            vp = parse_packet(p.payload, p.timestamp)
            if vp:
                frame_nums.append(vp.frame_number)
                reassembler.process_packet(vp)

        fn_min = min(frame_nums) if frame_nums else 0
        fn_max = max(frame_nums) if frame_nums else 0

        jpeg_sizes = [len(j) for j in reassembled_jpegs]

        # Resolution detection via OpenCV
        detected_res = None
        if reassembled_jpegs:
            try:
                np_arr = np.frombuffer(reassembled_jpegs[0], dtype=np.uint8)
                img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if img is not None:
                    detected_res = (img.shape[1], img.shape[0])  # (W, H)
            except Exception:
                pass

        # Estimate FPS from timestamps
        estimated_fps = 30.0
        if len(video_packets) > 1 and video_packets[-1].timestamp > video_packets[0].timestamp:
            duration = video_packets[-1].timestamp - video_packets[0].timestamp
            if duration > 0 and reassembled_jpegs:
                estimated_fps = len(reassembled_jpegs) / duration

        notes = [
            f"Extracted {len(packets)} UDP packets.",
            f"Video packets on port 2068: {len(video_packets)}.",
            f"Successfully reconstructed {len(reassembled_jpegs)} complete JPEG frames.",
        ]

        return PCAPAnalysisResult(
            filepath=self.filepath,
            file_size_bytes=file_size,
            total_packets=len(packets),
            video_packets_count=len(video_packets),
            audio_packets_count=len(audio_packets),
            control_packets_count=len(control_packets),
            other_packets_count=len(other_packets),
            src_ips=src_ips,
            dst_ips=dst_ips,
            ports_summary=ports_summary,
            payload_sizes=payload_sizes,
            frame_numbers_range=(fn_min, fn_max),
            reconstructed_jpegs_count=len(reassembled_jpegs),
            jpeg_sizes=jpeg_sizes,
            detected_resolution=detected_res,
            estimated_fps=round(estimated_fps, 1),
            notes=notes,
        )
