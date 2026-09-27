"""
Frame Extractor & Dumper Tool.
Reassembles video frames from capture files and dumps raw frame files for verification.
"""

import sys
import os
import argparse
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from analyze_pcap import parse_pcap_file
from packet_parser import PacketParser
from frame_reassembler import FrameReassembler

def dump_frames_from_file(filepath: str, output_dir: str):
    print(f"Reassembling and dumping frames from {filepath} -> {output_dir}")
    packets = parse_pcap_file(filepath)
    if not packets:
        print("No packets found to process.")
        return

    os.makedirs(output_dir, exist_ok=True)
    parser = PacketParser()
    reassembler = FrameReassembler()

    frame_count = 0
    stream_bytes = bytearray()

    for raw_pkt in packets:
        parsed = parser.parse_packet(raw_pkt)
        frames = reassembler.process_packet(parsed)

        for frame in frames:
            frame_count += 1
            ext = ".jpg" if frame.data.startswith(b"\xff\xd8") else ".bin"
            out_filename = os.path.join(output_dir, f"frame_{frame_count:04d}{ext}")

            with open(out_filename, "wb") as f:
                f.write(frame.data)
            stream_bytes.extend(frame.data)

    # Save complete continuous stream output file
    raw_stream_path = os.path.join(output_dir, "extracted_stream.raw")
    with open(raw_stream_path, "wb") as f:
        f.write(stream_bytes)

    print(f"Successfully extracted {frame_count} frames to '{output_dir}' (Stream size: {len(stream_bytes) / 1024 / 1024:.2f} MB)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract and dump video frames from capture")
    parser.add_argument("file", help="Path to capture file")
    parser.add_argument("--output-dir", default="extracted_frames", help="Output directory")
    args = parser.parse_args()
    dump_frames_from_file(args.file, args.output_dir)
