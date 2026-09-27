#!/usr/bin/env python3
"""
LKV373 / Lenkeng HDMI-over-IP MJPEG receiver.

Video stream:
    IPv4 multicast 226.2.2.2
    UDP port 2068

Video packet format:
    bytes 0..1 : frame number, big-endian uint16
    bytes 2..3 : chunk number, big-endian uint16
                 bit 15 = final chunk flag
                 bits 0..14 = chunk index
    bytes 4..  : JPEG payload

Examples:
    python lkv373_receiver.py
    python lkv373_receiver.py --interface 192.168.168.100
    python lkv373_receiver.py --source 192.168.168.55
    python lkv373_receiver.py --fullscreen
    python lkv373_receiver.py --pcap hdmi.pcapng

Dependencies:
    pip install numpy opencv-python
    pip install scapy        # only needed for --pcap
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import cv2
import numpy as np


DEFAULT_GROUP = "226.2.2.2"
DEFAULT_PORT = 2068
DEFAULT_INTERFACE = "0.0.0.0"
DEFAULT_SOURCE = None


@dataclass
class FrameBuffer:
    frame_no: int
    chunks: Dict[int, bytes] = field(default_factory=dict)
    last_chunk: Optional[int] = None
    first_seen: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)

    def add(self, chunk_no: int, is_last: bool, payload: bytes) -> None:
        self.chunks.setdefault(chunk_no, payload)
        self.last_seen = time.monotonic()
        if is_last:
            self.last_chunk = chunk_no

    def is_complete(self) -> bool:
        if self.last_chunk is None:
            return False
        return all(i in self.chunks for i in range(self.last_chunk + 1))

    def build(self) -> bytes:
        if not self.is_complete():
            raise ValueError("Frame is incomplete")
        return b"".join(self.chunks[i] for i in range(self.last_chunk + 1))


class LKV373Reassembler:
    def __init__(self, frame_timeout: float = 0.25, max_frames: int = 8):
        self.frames: Dict[int, FrameBuffer] = {}
        self.frame_timeout = frame_timeout
        self.max_frames = max_frames

        self.packets = 0
        self.duplicates = 0
        self.completed_frames = 0
        self.dropped_frames = 0
        self.decode_errors = 0
        self.bytes_received = 0

    @staticmethod
    def parse_packet(packet: bytes):
        if len(packet) < 5:
            return None

        frame_no, raw_chunk = struct.unpack(">HH", packet[:4])
        is_last = bool(raw_chunk & 0x8000)
        chunk_no = raw_chunk & 0x7FFF
        payload = packet[4:]

        # Optional sanity check: video payload should be JPEG data or a JPEG
        # continuation. The first chunk normally starts with FF D8.
        return frame_no, chunk_no, is_last, payload

    def push(self, packet: bytes) -> Optional[bytes]:
        parsed = self.parse_packet(packet)
        if parsed is None:
            return None

        frame_no, chunk_no, is_last, payload = parsed
        self.packets += 1
        self.bytes_received += len(packet)

        fb = self.frames.get(frame_no)
        if fb is None:
            fb = FrameBuffer(frame_no)
            self.frames[frame_no] = fb

        if chunk_no in fb.chunks:
            self.duplicates += 1
        else:
            fb.add(chunk_no, is_last, payload)

        if is_last:
            fb.last_seen = time.monotonic()

        if fb.is_complete():
            try:
                jpeg = fb.build()
            finally:
                del self.frames[frame_no]

            # Some transmitters may put padding after JPEG EOI.
            end = jpeg.find(b"\xff\xd9")
            if end < 0:
                self.decode_errors += 1
                return None

            jpeg = jpeg[:end + 2]
            self.completed_frames += 1
            return jpeg

        self._cleanup()
        return None

    def _cleanup(self):
        now = time.monotonic()

        expired = [
            frame_no
            for frame_no, fb in self.frames.items()
            if now - fb.last_seen > self.frame_timeout
        ]
        for frame_no in expired:
            del self.frames[frame_no]
            self.dropped_frames += 1

        while len(self.frames) > self.max_frames:
            oldest = min(self.frames, key=lambda n: self.frames[n].first_seen)
            del self.frames[oldest]
            self.dropped_frames += 1


def decode_jpeg(jpeg: bytes):
    if not jpeg.startswith(b"\xff\xd8"):
        return None

    array = np.frombuffer(jpeg, dtype=np.uint8)
    return cv2.imdecode(array, cv2.IMREAD_COLOR)


def make_socket(group: str, port: int, interface: str) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Large receive buffer helps prevent packet loss on busy streams.
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    except OSError:
        pass

    sock.bind(("0.0.0.0", port))

    # interface=0.0.0.0 means the OS chooses the interface.
    iface_addr = interface if interface not in ("", "0.0.0.0") else "0.0.0.0"
    mreq = socket.inet_aton(group) + socket.inet_aton(iface_addr)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(0.10)
    return sock


def display_frame(frame, fullscreen: bool, window_name: str):
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    if fullscreen:
        cv2.setWindowProperty(
            window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN
        )

    cv2.imshow(window_name, frame)


def print_stats(reassembler: LKV373Reassembler, start: float, last_print: float):
    now = time.monotonic()
    if now - last_print < 1.0:
        return last_print

    elapsed = max(now - start, 0.001)
    pps = reassembler.packets / elapsed
    fps = reassembler.completed_frames / elapsed
    mbps = reassembler.bytes_received * 8 / elapsed / 1_000_000

    print(
        f"\rPackets: {reassembler.packets:,} | "
        f"Frames: {reassembler.completed_frames:,} | "
        f"FPS: {fps:5.1f} | "
        f"Packet/s: {pps:6.1f} | "
        f"Traffic: {mbps:6.2f} Mbps | "
        f"Dropped frames: {reassembler.dropped_frames} | "
        f"Duplicates: {reassembler.duplicates} | "
        f"Decode errors: {reassembler.decode_errors}",
        end="",
        flush=True,
    )
    return now


def run_live(args):
    print(f"Joining multicast {args.group}:{args.port}")
    print(f"Interface: {args.interface or 'automatic'}")
    if args.source:
        print(f"Source filter: {args.source}")

    sock = make_socket(args.group, args.port, args.interface or "0.0.0.0")
    reassembler = LKV373Reassembler(args.frame_timeout, args.max_frames)

    start = time.monotonic()
    last_stats = start
    window = "LKV373 HDMI Receiver"

    if not args.no_display:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        if args.fullscreen:
            cv2.setWindowProperty(
                window, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN
            )

    try:
        while True:
            try:
                packet, addr = sock.recvfrom(65535)
            except socket.timeout:
                last_stats = print_stats(reassembler, start, last_stats)
                if not args.no_display:
                    key = cv2.waitKey(1) & 0xFF
                    if key in (27, ord("q")):
                        break
                continue

            if args.source and addr[0] != args.source:
                continue

            jpeg = reassembler.push(packet)
            if jpeg is not None:
                frame = decode_jpeg(jpeg)
                if frame is None:
                    reassembler.decode_errors += 1
                elif not args.no_display:
                    # Overlay diagnostics if requested.
                    if args.stats:
                        h, w = frame.shape[:2]
                        text = (
                            f"{w}x{h}  "
                            f"frames={reassembler.completed_frames}  "
                            f"dropped={reassembler.dropped_frames}"
                        )
                        cv2.putText(
                            frame,
                            text,
                            (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.65,
                            (0, 255, 0),
                            2,
                            cv2.LINE_AA,
                        )

                    cv2.imshow(window, frame)

            last_stats = print_stats(reassembler, start, last_stats)

            if not args.no_display:
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sock.close()
        cv2.destroyAllWindows()

    print("\nFinal statistics:")
    print(f"  packets          : {reassembler.packets}")
    print(f"  frames           : {reassembler.completed_frames}")
    print(f"  dropped frames   : {reassembler.dropped_frames}")
    print(f"  duplicate chunks : {reassembler.duplicates}")
    print(f"  decode errors    : {reassembler.decode_errors}")


def run_pcap(args):
    try:
        from scapy.all import IP, UDP, rdpcap
    except ImportError:
        print(
            "PCAP mode requires Scapy.\n"
            "Install it with:\n"
            "    pip install scapy",
            file=sys.stderr,
        )
        sys.exit(2)

    print(f"Reading {args.pcap}")
    packets = rdpcap(args.pcap)

    reassembler = LKV373Reassembler(args.frame_timeout, args.max_frames)
    window = "LKV373 HDMI PCAP Playback"

    if not args.no_display:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        if args.fullscreen:
            cv2.setWindowProperty(
                window, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN
            )

    saved = 0
    start = time.monotonic()

    for p in packets:
        if not p.haslayer(IP) or not p.haslayer(UDP):
            continue

        ip = p[IP]
        udp = p[UDP]

        if ip.dst != args.group or int(udp.dport) != args.port:
            continue

        if args.source and ip.src != args.source:
            continue

        payload = bytes(udp.payload)
        jpeg = reassembler.push(payload)

        if jpeg is None:
            continue

        if args.save_frames:
            out_dir = args.save_frames
            import os
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"{saved:06d}.jpg")
            with open(path, "wb") as f:
                f.write(jpeg)

        frame = decode_jpeg(jpeg)
        if frame is None:
            reassembler.decode_errors += 1
            continue

        saved += 1

        if not args.no_display:
            cv2.imshow(window, frame)

            # Try to approximate capture playback rate.
            key = cv2.waitKey(max(1, int(1000 / max(args.fps, 1)))) & 0xFF
            if key in (27, ord("q")):
                break

    elapsed = max(time.monotonic() - start, 0.001)
    print("\nPCAP results:")
    print(f"  packets          : {reassembler.packets}")
    print(f"  frames           : {reassembler.completed_frames}")
    print(f"  decoded          : {saved}")
    print(f"  dropped frames   : {reassembler.dropped_frames}")
    print(f"  duplicate chunks : {reassembler.duplicates}")
    print(f"  decode errors    : {reassembler.decode_errors}")
    print(f"  playback time    : {elapsed:.2f}s")

    cv2.destroyAllWindows()


def build_parser():
    p = argparse.ArgumentParser(
        description="LKV373/Lenkeng HDMI-over-IP MJPEG receiver"
    )
    p.add_argument("--group", default=DEFAULT_GROUP)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument(
        "--interface",
        default=DEFAULT_INTERFACE,
        help="Local IPv4 interface for multicast, e.g. 192.168.168.100",
    )
    p.add_argument("--source", default=DEFAULT_SOURCE)
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--no-display", action="store_true")
    p.add_argument("--stats", action="store_true")
    p.add_argument("--frame-timeout", type=float, default=0.25)
    p.add_argument("--max-frames", type=int, default=8)

    p.add_argument(
        "--pcap",
        help="Read packets from a PCAP/PCAPNG instead of live multicast",
    )
    p.add_argument(
        "--save-frames",
        help="Directory where reconstructed JPEG frames are saved in PCAP mode",
    )
    p.add_argument(
        "--fps",
        type=float,
        default=30.0,
        help="PCAP playback FPS",
    )
    return p


def main():
    args = build_parser().parse_args()

    if args.pcap:
        run_pcap(args)
    else:
        run_live(args)


if __name__ == "__main__":
    main()
