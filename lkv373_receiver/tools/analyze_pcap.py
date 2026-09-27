"""
PCAP / PCAPNG & Binary Traffic Analyzer Command-Line Tool.

Reports detailed metrics for LKV373 streams:
- Source & Destination IPs
- Source & Destination Ports
- Total Packet Counts & Payload Sizes
- Frame & Chunk Numbers Range
- Reconstructed JPEG Count & Resolution
- Estimated Frame Rate
- Audio and Control Traffic Breakdown
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from lkv373_receiver.diagnostics.pcap_analyzer import PCAPAnalyzer


def main():
    parser = argparse.ArgumentParser(description="Analyze LKV373 HDMI-over-IP PCAP/PCAPNG or Binary file")
    parser.add_argument("pcap_file", help="Path to pcap, pcapng, or binary capture file")
    args = parser.parse_args()

    filepath = args.pcap_file
    print(f"\n==================================================")
    print(f" LKV373 PCAP / CAPTURE FILE DIAGNOSTIC REPORT ")
    print(f"==================================================")
    print(f"File: {filepath}")

    analyzer = PCAPAnalyzer(filepath)
    res = analyzer.analyze()

    print(f"File Size:              {res.file_size_bytes:,} bytes")
    print(f"Total UDP Packets:      {res.total_packets:,}")
    print(f"  - Video Packets (2068): {res.video_packets_count:,}")
    print(f"  - Audio Packets (2066): {res.audio_packets_count:,}")
    print(f"  - Control Pkts (2065/7):{res.control_packets_count:,}")
    print(f"  - Other UDP Packets:  {res.other_packets_count:,}")
    print(f"\nNetwork Summary:")
    print(f"  Source IPs:           {', '.join(res.src_ips) if res.src_ips else 'N/A'}")
    print(f"  Destination IPs:      {', '.join(res.dst_ips) if res.dst_ips else 'N/A'}")
    print(f"  UDP Destination Ports:{res.ports_summary}")
    print(f"Payload Size (bytes):  Min={res.payload_sizes['min']}, Max={res.payload_sizes['max']}, Avg={res.payload_sizes['avg']}")

    print(f"\nVideo Stream Analysis:")
    print(f"  Frame Numbers Range:  {res.frame_numbers_range[0]} -> {res.frame_numbers_range[1]}")
    print(f"  Reconstructed JPEGs:  {res.reconstructed_jpegs_count}")
    if res.detected_resolution:
        print(f"  Detected Resolution: {res.detected_resolution[0]}x{res.detected_resolution[1]}")
    else:
        print(f"  Detected Resolution: Unknown / Could not decode header")
    print(f"  Estimated Frame Rate: ~{res.estimated_fps} FPS")

    if res.jpeg_sizes:
        avg_jpg = sum(res.jpeg_sizes) / len(res.jpeg_sizes)
        print(f"  JPEG Frame Sizes:     Min={min(res.jpeg_sizes):,}b, Max={max(res.jpeg_sizes):,}b, Avg={avg_jpg:,.0f}b")

    if res.notes:
        print(f"\nNotes:")
        for note in res.notes:
            print(f"  * {note}")
    print(f"==================================================\n")


if __name__ == "__main__":
    main()
