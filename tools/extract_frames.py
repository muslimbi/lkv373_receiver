"""
Extract JPEG Frames Tool Wrapper.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lkv373_receiver.tools.extract_frames import extract_frames, argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract JPEG frames from LKV373 PCAP/PCAPNG capture file")
    parser.add_argument("pcap_file", help="Path to pcap, pcapng, or binary capture file")
    parser.add_argument("--output-dir", "-o", default="frames", help="Output directory for extracted JPEG files")
    args = parser.parse_args()
    extract_frames(args.pcap_file, args.output_dir)
