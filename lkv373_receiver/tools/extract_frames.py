"""
Extract JPEG Frames from PCAP/PCAPNG or Binary Capture Files.

Usage:
    python tools/extract_frames.py <capture_file> [--output-dir frames]
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from lkv373_receiver.diagnostics.pcap_analyzer import PCAPAnalyzer
from lkv373_receiver.receiver.packet import parse_packet
from lkv373_receiver.receiver.reassembler import FrameReassembler


def extract_frames(pcap_file: str, output_dir: str = "frames"):
    """Extracts all complete JPEG frames from capture file and saves as 000001.jpg, etc."""
    print(f"Reading capture file: {pcap_file}")
    analyzer = PCAPAnalyzer(pcap_file)
    packets = analyzer.extract_udp_packets()

    if not packets:
        print(f"No UDP packets found in {pcap_file}")
        return

    print(f"Extracted {len(packets)} UDP packets. Reassembling frames...")
    os.makedirs(output_dir, exist_ok=True)

    saved_count = 0
    frame_index = 1

    def on_frame_complete(frame):
        nonlocal saved_count, frame_index
        if frame.jpeg_data:
            filename = f"{frame_index:06d}.jpg"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(frame.jpeg_data)
            print(f"  Saved Frame {frame.frame_number} -> {filepath} ({len(frame.jpeg_data)} bytes)")
            saved_count += 1
            frame_index += 1

    reassembler = FrameReassembler(max_active_frames=10, on_frame_complete=on_frame_complete)

    video_packets = [p for p in packets if p.dst_port == 2068]
    if not video_packets:
        video_packets = packets

    start_time = time.perf_counter()
    for pkt in video_packets:
        vp = parse_packet(pkt.payload, pkt.timestamp)
        if vp:
            reassembler.process_packet(vp)

    elapsed = time.perf_counter() - start_time
    print("\n--- EXTRACTION COMPLETE ---")
    print(f"Total JPEG Frames Saved: {saved_count}")
    print(f"Output Directory:        {os.path.abspath(output_dir)}")
    print(f"Time Taken:             {elapsed:.2f} seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract JPEG frames from LKV373 PCAP/PCAPNG capture file")
    parser.add_argument("pcap_file", help="Path to pcap, pcapng, or binary capture file")
    parser.add_argument("--output-dir", "-o", default="frames", help="Output directory for extracted JPEG files")
    args = parser.parse_args()
    extract_frames(args.pcap_file, args.output_dir)
