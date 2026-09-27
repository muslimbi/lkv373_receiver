"""
Live Multicast Stream Capture Tool.
Captures live multicast UDP packets from 226.2.2.2:2068 and saves them to file.
"""

import sys
import os
import time
import argparse
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from multicast_receiver import MulticastReceiver

def capture_multicast_stream(group: str, port: int, interface: str, output_file: str, duration_sec: int):
    print(f"Starting Live Multicast Capture on {group}:{port} (Interface: {interface})")
    print(f"Saving output to: {output_file} (Duration: {duration_sec}s)")

    receiver = MulticastReceiver(group=group, port=port, interface_ip=interface)
    receiver.start()

    start_t = time.time()
    packet_count = 0
    total_bytes = 0

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

    with open(output_file, "wb") as f:
        try:
            while time.time() - start_t < duration_sec:
                pkt_data = receiver.get_packet(timeout=0.5)
                if pkt_data:
                    payload, timestamp = pkt_data
                    # Write 4-byte length prefix + payload
                    f.write(len(payload).to_bytes(4, byteorder="big"))
                    f.write(payload)
                    packet_count += 1
                    total_bytes += len(payload)

                    if packet_count % 500 == 0:
                        stats = receiver.get_stats()
                        print(f"Captured {packet_count} packets ({total_bytes / 1024 / 1024:.2f} MB) | Rate: {stats['mbps']} Mbps")
        except KeyboardInterrupt:
            print("\nCapture interrupted by user.")
        finally:
            receiver.stop()

    print(f"\nCapture complete! Total Packets: {packet_count}, Saved: {total_bytes / 1024 / 1024:.2f} MB to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture live HDMI-over-IP multicast stream")
    parser.add_argument("--group", default="226.2.2.2", help="Multicast group IP")
    parser.add_argument("--port", type=int, default=2068, help="UDP port")
    parser.add_argument("--interface", default="192.168.168.10", help="Local interface IP")
    parser.add_argument("--output", default="capture.bin", help="Output file path")
    parser.add_argument("--duration", type=int, default=10, help="Capture duration in seconds")

    args = parser.parse_args()
    capture_multicast_stream(args.group, args.port, args.interface, args.output, args.duration)
