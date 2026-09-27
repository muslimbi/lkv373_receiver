"""
Payload Inspection Tool for HDMI-over-IP Reverse Engineering.
Performs hex dumps, entropy analysis, magic signature searches, and field candidate detection.
"""

import sys
import os
import argparse
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from packet_parser import PacketParser, ParsedPacket

def hex_dump(data: bytes, max_len: int = 128) -> str:
    lines = []
    chunk_len = 16
    sub = data[:max_len]
    for i in range(0, len(sub), chunk_len):
        chunk = sub[i:i+chunk_len]
        hex_str = " ".join(f"{b:02X}" for b in chunk)
        ascii_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"{i:04X}:  {hex_str:<48}  |{ascii_str}|")
    return "\n".join(lines)

def inspect_payload_file(filepath: str, max_packets: int = 10):
    print(f"--- INSPECTING PAYLOAD FILE: {filepath} ---")
    if not os.path.exists(filepath):
        print(f"Error: File {filepath} does not exist.")
        return

    from analyze_pcap import parse_pcap_file
    packets = parse_pcap_file(filepath)
    if not packets:
        print("No packets found.")
        return

    parser = PacketParser()
    print(f"Total Packets Loaded: {len(packets)}")
    print(f"Displaying top {min(max_packets, len(packets))} packets:\n")

    for idx, pkt in enumerate(packets[:max_packets]):
        entropy = parser.calculate_entropy(pkt)
        parsed = parser.parse_packet(pkt)
        print(f"=== PACKET #{idx+1} [Length: {len(pkt)} bytes | Entropy: {entropy:.3f} bits/byte] ===")
        print(f"Header Len Candidate: {parsed.header_len} | Seq: {parsed.seq_num} | Frame#: {parsed.frame_num} | Start: {parsed.is_frame_start} | End: {parsed.is_frame_end}")
        print("Header & Payload Hex Dump:")
        print(hex_dump(pkt, max_len=96))
        print("-" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect raw packet payload headers and entropy")
    parser.add_argument("file", help="Path to capture file")
    parser.add_argument("--count", type=int, default=10, help="Number of packets to inspect")
    args = parser.parse_args()
    inspect_payload_file(args.file, args.count)
