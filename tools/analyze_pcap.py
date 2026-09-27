"""
PCAP / PCAPNG & Binary Traffic Analyzer.
Analyzes captured HDMI-over-IP network traffic files to identify header formats,
sequence numbers, frame boundaries, payload entropy, and video codecs.
"""

import sys
import os
import struct
import argparse
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from packet_parser import PacketParser
from protocol import StreamInfo

def parse_pcap_file(filepath: str) -> list[bytes]:
    """Reads UDP payloads from standard PCAP / PCAPNG file or length-prefixed binary dump."""
    payloads = []
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return []

    with open(filepath, "rb") as f:
        data = f.read()

    if not data:
        return []

    # 1. Check for standard PCAP magic bytes (0xa1b2c3d4 or 0xd4c3b2a1)
    if data.startswith(b"\xa1\xb2\xc3\xd4") or data.startswith(b"\xd4\xc3\xb2\xa1"):
        endian = ">" if data.startswith(b"\xa1\xb2\xc3\xd4") else "<"
        offset = 24 # Skip global header
        while offset < len(data) - 16:
            ts_sec, ts_usec, incl_len, orig_len = struct.unpack(f"{endian}IIII", data[offset:offset+16])
            offset += 16
            packet_data = data[offset:offset+incl_len]
            offset += incl_len

            # Extract UDP payload if IPv4 (0x0800) + UDP (proto 17)
            if len(packet_data) > 42:
                ip_idx = packet_data.find(b"\x45\x00")
                if ip_idx != -1 and len(packet_data) >= ip_idx + 28:
                    udp_payload = packet_data[ip_idx + 28:]
                    if udp_payload:
                        payloads.append(udp_payload)

    # 2. Check for 4-byte length prefixed binary dump (created by capture_multicast.py)
    else:
        offset = 0
        file_len = len(data)
        is_length_prefixed = True

        # Quick validation of 4-byte length prefix structure
        temp_off = 0
        while temp_off < min(file_len, 2000):
            if temp_off + 4 > file_len:
                break
            pkt_len = int.from_bytes(data[temp_off:temp_off+4], "big")
            if not (10 <= pkt_len <= 65535):
                is_length_prefixed = False
                break
            temp_off += 4 + pkt_len

        if is_length_prefixed and temp_off > 0:
            offset = 0
            while offset + 4 <= file_len:
                pkt_len = int.from_bytes(data[offset:offset+4], "big")
                offset += 4
                if offset + pkt_len <= file_len:
                    payloads.append(data[offset:offset+pkt_len])
                    offset += pkt_len
                else:
                    break
        else:
            # Fallback to chunking
            chunk_size = 1024
            for i in range(0, file_len, chunk_size):
                chunk = data[i:i+chunk_size]
                if chunk:
                    payloads.append(chunk)

    return payloads

def analyze_capture(filepath: str):
    print(f"Analyzing capture file: {filepath}")
    payloads = parse_pcap_file(filepath)
    if not payloads:
        print("No UDP payloads extracted or empty capture.")
        return

    print(f"Total UDP Packets Extracted: {len(payloads)}")
    sizes = [len(p) for p in payloads]
    avg_size = sum(sizes) / len(sizes)
    min_size = min(sizes)
    max_size = max(sizes)
    print(f"Payload Sizes: Min={min_size} bytes, Max={max_size} bytes, Avg={avg_size:.1f} bytes")

    # Analyze first 5 packets hex dump
    print("\n--- FIRST 5 PACKETS HEADER DUMP (First 32 bytes) ---")
    for i, p in enumerate(payloads[:5]):
        hex_dump = " ".join(f"{b:02x}" for b in p[:32])
        ascii_dump = "".join(chr(b) if 32 <= b <= 126 else "." for b in p[:32])
        print(f"Pkt #{i+1:03d} [{len(p)}b]: {hex_dump} | {ascii_dump}")

    parser = PacketParser()
    info: StreamInfo = parser.detect_stream_characteristics(payloads)

    print("\n--- PROTOCOL DISCOVERY REPORT ---")
    print(f"Detected Codec:        {info.codec.value}")
    print(f"Detected Encapsulation: {info.encapsulation.value}")
    print(f"Confidence Level:       {info.confidence * 100:.1f}%")
    print(f"Notes:                 {info.notes}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze HDMI-over-IP PCAP/Capture file")
    parser.add_argument("pcap_file", help="Path to pcap, pcapng, or raw capture file")
    args = parser.parse_args()
    analyze_capture(args.pcap_file)
