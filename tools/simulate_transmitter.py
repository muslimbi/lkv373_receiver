"""
Simulated HDMI Transmitter Tool.
Generates live UDP multicast stream (226.2.2.2:2068) with synthetic HDMI video frames
and header structures for testing and validating the receiver pipeline without hardware.
"""

import socket
import struct
import time
import math
import cv2
import numpy as np
import argparse

def generate_test_pattern(frame_num: int, width: int = 1280, height: int = 720) -> np.ndarray:
    """Generates a dynamic HDMI test pattern frame with bouncing graphics, text, and timestamp."""
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # Color background gradient
    t = frame_num * 0.05
    r_val = int((math.sin(t) + 1) * 60)
    g_val = int((math.sin(t + 2) + 1) * 60)
    b_val = int((math.sin(t + 4) + 1) * 60)
    img[:, :] = (b_val, g_val, r_val)

    # Bouncing ball graphic
    cx = int((math.sin(frame_num * 0.08) * 0.4 + 0.5) * width)
    cy = int((math.cos(frame_num * 0.08) * 0.4 + 0.5) * height)
    cv2.circle(img, (cx, cy), 50, (0, 255, 255), -1)
    cv2.circle(img, (cx, cy), 52, (255, 255, 255), 2)

    # HDMI Transmitter Test Pattern Header
    cv2.putText(img, "HDMI TRANSMITTER SIMULATOR (226.2.2.2:2068)", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
    cv2.putText(img, f"Frame Number: {frame_num:06d} | Resolution: {width}x{height}", (50, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
    time_str = time.strftime("%Y-%m-%d %H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"
    cv2.putText(img, f"System Time: {time_str}", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)

    # Grid lines
    for x in range(0, width, 160):
        cv2.line(img, (x, 0), (x, height), (40, 40, 40), 1)
    for y in range(0, height, 120):
        cv2.line(img, (0, y), (width, y), (40, 40, 40), 1)

    return img

def run_transmitter(
    group: str = "226.2.2.2",
    port: int = 2068,
    interface: str = "0.0.0.0",
    fps: int = 30,
    packet_payload_size: int = 1000,
    header_type: str = "hdbitt"
):
    print(f"Starting HDMI Transmitter Simulator -> {group}:{port} @ {fps} FPS (Header: {header_type})")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    if interface != "0.0.0.0":
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface))

    frame_num = 0
    seq_num = 0
    frame_interval = 1.0 / fps

    try:
        while True:
            t0 = time.time()
            frame_num += 1

            # Generate synthetic test frame and encode to MJPEG JPEG byte buffer
            frame_img = generate_test_pattern(frame_num)
            success, jpeg_buf = cv2.imencode(".jpg", frame_img, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not success:
                continue

            frame_bytes = jpeg_buf.tobytes()
            total_len = len(frame_bytes)

            # Fragment frame bytes into ~1000-byte UDP payloads
            offset = 0
            total_packets = (total_len + packet_payload_size - 1) // packet_payload_size

            for pkt_idx in range(total_packets):
                seq_num += 1
                chunk = frame_bytes[offset:offset + packet_payload_size]
                offset += packet_payload_size

                if header_type == "hdbitt":
                    # 16-byte HDbitT header: 'TH' magic (2b), type (2b), frame_num (4b), pkt_idx (4b), reserved (4b)
                    hdr = struct.pack(">2sHII4s", b"TH", 0x0001, frame_num, pkt_idx, b"\x00\x00\x00\x00")
                elif header_type == "custom":
                    # 8-byte header: seq_num (4b), frame_num (4b)
                    hdr = struct.pack(">II", seq_num, frame_num)
                else:
                    # Raw UDP
                    hdr = b""

                packet_data = hdr + chunk
                sock.sendto(packet_data, (group, port))

            elapsed = time.time() - t0
            sleep_time = max(0.001, frame_interval - elapsed)
            time.sleep(sleep_time)

            if frame_num % 60 == 0:
                print(f"Transmitted Frame #{frame_num} ({total_len} bytes in {total_packets} UDP packets)")

    except KeyboardInterrupt:
        print("\nTransmitter stopped by user.")
    finally:
        sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HDMI Transmitter Multicast Simulator")
    parser.add_argument("--group", default="226.2.2.2", help="Multicast group IP")
    parser.add_argument("--port", type=int, default=2068, help="UDP port")
    parser.add_argument("--interface", default="0.0.0.0", help="Interface IP")
    parser.add_argument("--fps", type=int, default=30, help="Target FPS")
    parser.add_argument("--header", choices=["hdbitt", "custom", "raw"], default="hdbitt", help="Header style")

    args = parser.parse_args()
    run_transmitter(args.group, args.port, args.interface, args.fps, header_type=args.header)
