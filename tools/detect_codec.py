"""
Codec Detection Tool.
Scans packet data to identify video stream codec (H.264/H.265/MJPEG/MPEG-TS/Proprietary).
"""

import sys
import os
import argparse
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from analyze_pcap import parse_pcap_file
from packet_parser import PacketParser

def detect_codec_in_file(filepath: str):
    print(f"Detecting Codec in: {filepath}")
    packets = parse_pcap_file(filepath)
    if not packets:
        print("No packets found for detection.")
        return

    parser = PacketParser()
    info = parser.detect_stream_characteristics(packets)

    print("\n================ CODEC DETECTION RESULTS ================")
    print(f"File:                   {filepath}")
    print(f"Total Packets Analyzed: {len(packets)}")
    print(f"Detected Codec:        {info.codec.value}")
    print(f"Encapsulation:          {info.encapsulation.value}")
    print(f"Confidence Level:       {info.confidence * 100:.1f}%")
    print(f"Details / Evidence:     {info.notes}")
    print("========================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect video codec in capture file")
    parser.add_argument("file", help="Path to capture file")
    args = parser.parse_args()
    detect_codec_in_file(args.file)
