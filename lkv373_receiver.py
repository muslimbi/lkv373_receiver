#!/usr/bin/env python3
"""
LKV373 / Lenkeng HDMI-over-IP Receiver

Supports:
    1. Live multicast UDP reception
    2. PCAP/PCAPNG playback
    3. JPEG frame reassembly
    4. OpenCV display
    5. Frame saving
    6. Statistics
    7. Source-IP filtering

Known LKV373 video format:
    UDP destination: 226.2.2.2
    UDP port:        2068

Packet payload:
    Bytes 0-1 : Frame number, big endian
    Bytes 2-3 : Chunk number, big endian
                 MSB = final chunk
    Bytes 4+  : JPEG data

Tested protocol assumption:
    JPEG SOI = FF D8
    JPEG EOI = FF D9
"""

import argparse
import socket
import struct
import sys
import time
from collections import OrderedDict

import cv2


DEFAULT_GROUP = "226.2.2.2"
DEFAULT_PORT = 2068

MAX_FRAME_BUFFERS = 32
DEFAULT_FRAME_TIMEOUT = 2.0
DEFAULT_SOCKET_BUFFER = 8 * 1024 * 1024


# ------------------------------------------------------------
# LKV373 Decoder
# ------------------------------------------------------------

class LKV373Decoder:
    def __init__(
        self,
        frame_timeout=DEFAULT_FRAME_TIMEOUT,
        max_frames=MAX_FRAME_BUFFERS,
        save_dir=None,
    ):
        self.frame_timeout = frame_timeout
        self.max_frames = max_frames
        self.save_dir = save_dir

        self.frames = OrderedDict()

        self.frames_completed = 0
        self.frames_decoded = 0
        self.frames_failed = 0
        self.packets_received = 0
        self.bytes_received = 0

        self.last_frame_time = time.time()

        if self.save_dir:
            import os
            os.makedirs(self.save_dir, exist_ok=True)

    # --------------------------------------------------------
    # Packet processing
    # --------------------------------------------------------

    def process_packet(self, payload):
        self.packets_received += 1
        self.bytes_received += len(payload)

        if len(payload) < 5:
            return None

        frame_no = struct.unpack(">H", payload[0:2])[0]
        chunk_raw = struct.unpack(">H", payload[2:4])[0]

        is_last = bool(chunk_raw & 0x8000)
        chunk_no = chunk_raw & 0x7FFF

        jpeg_data = payload[4:]

        if not jpeg_data:
            return None

        now = time.time()

        # Create frame buffer
        if frame_no not in self.frames:
            self.frames[frame_no] = {
                "chunks": {},
                "created": now,
                "last": now,
            }

        frame = self.frames[frame_no]
        frame["chunks"][chunk_no] = jpeg_data
        frame["last"] = now

        # Keep frame buffer bounded
        while len(self.frames) > self.max_frames:
            self.frames.popitem(last=False)

        # Final chunk received
        if is_last:
            result = self._complete_frame(frame_no)

            if result is not None:
                return result

        self.cleanup(now)

        return None

    # --------------------------------------------------------
    # Complete JPEG
    # --------------------------------------------------------

    def _complete_frame(self, frame_no):
        frame = self.frames.get(frame_no)

        if not frame:
            return None

        chunks = frame["chunks"]

        if not chunks:
            return None

        # Sort chunks by chunk number
        ordered_chunks = []

        for chunk_no in sorted(chunks.keys()):
            ordered_chunks.append(chunks[chunk_no])

        jpeg = b"".join(ordered_chunks)

        # JPEG validation
        if not jpeg.startswith(b"\xff\xd8"):
            self.frames_failed += 1
            del self.frames[frame_no]
            return None

        # Some captures may contain trailing data.
        eoi = jpeg.rfind(b"\xff\xd9")

        if eoi >= 0:
            jpeg = jpeg[:eoi + 2]

        if len(jpeg) < 100:
            self.frames_failed += 1
            del self.frames[frame_no]
            return None

        self.frames_completed += 1

        # Decode JPEG
        import numpy as np

        try:
            array = np.frombuffer(jpeg, dtype=np.uint8)
            image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        except Exception:
            image = None

        del self.frames[frame_no]

        if image is None:
            self.frames_failed += 1
            return None

        self.frames_decoded += 1
        self.last_frame_time = time.time()

        # Save JPEG
        if self.save_dir:
            filename = (
                f"{self.save_dir}/"
                f"frame_{self.frames_decoded:08d}_"
                f"{frame_no}.jpg"
            )

            try:
                cv2.imwrite(filename, image)
            except Exception as e:
                print(f"[WARN] Could not save frame: {e}")

        return image

    # --------------------------------------------------------
    # Remove old incomplete frames
    # --------------------------------------------------------

    def cleanup(self, now=None):
        if now is None:
            now = time.time()

        expired = []

        for frame_no, frame in self.frames.items():
            if now - frame["last"] > self.frame_timeout:
                expired.append(frame_no)

        for frame_no in expired:
            self.frames.pop(frame_no, None)

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    def stats(self):
        return {
            "packets": self.packets_received,
            "bytes": self.bytes_received,
            "completed": self.frames_completed,
            "decoded": self.frames_decoded,
            "failed": self.frames_failed,
            "buffers": len(self.frames),
        }


# ------------------------------------------------------------
# Multicast Socket
# ------------------------------------------------------------

def create_multicast_socket(group, port, interface_ip):
    """
    Create Windows/Linux compatible multicast socket.

    interface_ip MUST be the IPv4 address of the Ethernet
    adapter connected to the HDMI-over-IP network.
    """

    if not interface_ip:
        raise ValueError(
            "You must specify the local Ethernet interface IP.\n"
            "Example:\n"
            "    --interface 192.168.168.10"
        )

    if interface_ip == "0.0.0.0":
        raise ValueError(
            "Do not use 0.0.0.0 as --interface.\n"
            "Use the IPv4 address of your Ethernet adapter."
        )

    print()
    print("Creating multicast socket...")
    print(f"  Multicast group : {group}")
    print(f"  UDP port        : {port}")
    print(f"  Local interface : {interface_ip}")

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
        socket.IPPROTO_UDP,
    )

    # Allow reuse
    sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )

    # Large receive buffer
    try:
        sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_RCVBUF,
            DEFAULT_SOCKET_BUFFER,
        )
    except OSError:
        pass

    # Bind to UDP port
    sock.bind(("", port))

    # Explicit multicast membership
    local_addr = socket.inet_aton(interface_ip)
    multicast_addr = socket.inet_aton(group)

    membership = multicast_addr + local_addr

    sock.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_ADD_MEMBERSHIP,
        membership,
    )

    # Explicit multicast interface
    try:
        sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_IF,
            local_addr,
        )
    except OSError:
        pass

    # Non-blocking-ish timeout
    sock.settimeout(0.2)

    print("  Multicast membership : OK")
    print("  Socket               : OK")
    print()

    return sock


# ------------------------------------------------------------
# Display
# ------------------------------------------------------------

def display_frame(
    frame,
    fullscreen=False,
    window_name="LKV373 HDMI Receiver",
):
    if frame is None:
        return

    if fullscreen:
        cv2.namedWindow(
            window_name,
            cv2.WINDOW_NORMAL,
        )

        try:
            cv2.setWindowProperty(
                window_name,
                cv2.WND_PROP_FULLSCREEN,
                cv2.WINDOW_FULLSCREEN,
            )
        except Exception:
            pass

    cv2.imshow(window_name, frame)


# ------------------------------------------------------------
# Live Receiver
# ------------------------------------------------------------

def run_live(args):

    try:
        sock = create_multicast_socket(
            args.group,
            args.port,
            args.interface,
        )
    except Exception as e:
        print()
        print("[ERROR] Could not create multicast socket.")
        print(e)
        print()
        print("Check:")
        print("  1. Ethernet adapter IP")
        print("  2. VLAN configuration")
        print("  3. Windows Firewall")
        print("  4. HDMI transmitter network connection")
        print()
        return 1

    decoder = LKV373Decoder(
        frame_timeout=args.frame_timeout,
        max_frames=args.max_buffers,
        save_dir=args.save_frames,
    )

    print("Waiting for UDP video packets...")
    print("Press Q or ESC to quit.")
    print()

    first_packet = True

    last_stats = time.time()

    try:

        while True:

            try:
                data, addr = sock.recvfrom(65535)

            except socket.timeout:

                decoder.cleanup()

                key = cv2.waitKey(1) & 0xFF

                if key in (27, ord("q"), ord("Q")):
                    break

                continue

            except KeyboardInterrupt:
                break

            except OSError as e:
                print(f"[ERROR] Socket error: {e}")
                break

            # --------------------------------------------
            # First packet diagnostic
            # --------------------------------------------

            if first_packet:
                first_packet = False

                print("==============================================")
                print("FIRST UDP PACKET RECEIVED")
                print("==============================================")
                print(f"Source       : {addr[0]}:{addr[1]}")
                print(f"Destination  : {args.group}:{args.port}")
                print(f"Packet size  : {len(data)} bytes")
                print(
                    "Payload head : "
                    + data[:16].hex(" ")
                )
                print("==============================================")
                print()

                if args.source and addr[0] != args.source:
                    print(
                        f"[INFO] Packet source {addr[0]} "
                        f"does not match --source {args.source}"
                    )

            # --------------------------------------------
            # Source filter
            # --------------------------------------------

            if args.source:
                if addr[0] != args.source:
                    continue

            # --------------------------------------------
            # Decode
            # --------------------------------------------

            frame = decoder.process_packet(data)

            if frame is not None:

                display_frame(
                    frame,
                    fullscreen=args.fullscreen,
                )

                key = cv2.waitKey(1) & 0xFF

                if key in (27, ord("q"), ord("Q")):
                    break

                if (
                    args.max_frames > 0
                    and decoder.frames_decoded >= args.max_frames
                ):
                    break

            # --------------------------------------------
            # Periodic stats
            # --------------------------------------------

            if args.stats:

                now = time.time()

                if now - last_stats >= 1:

                    s = decoder.stats()

                    print(
                        f"\r"
                        f"Packets={s['packets']} "
                        f"Frames={s['decoded']} "
                        f"Failed={s['failed']} "
                        f"Buffers={s['buffers']} ",
                        end="",
                        flush=True,
                    )

                    last_stats = now

    finally:

        print()
        print()
        print("Stopping receiver...")

        try:
            # Leave multicast group
            local_addr = socket.inet_aton(args.interface)
            multicast_addr = socket.inet_aton(args.group)

            membership = multicast_addr + local_addr

            sock.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_DROP_MEMBERSHIP,
                membership,
            )

        except Exception:
            pass

        sock.close()

        cv2.destroyAllWindows()

        s = decoder.stats()

        print()
        print("========== FINAL STATISTICS ==========")
        print(f"Packets received : {s['packets']}")
        print(f"Bytes received   : {s['bytes']}")
        print(f"Frames completed : {s['completed']}")
        print(f"Frames decoded   : {s['decoded']}")
        print(f"Frames failed    : {s['failed']}")
        print("======================================")

    return 0


# ------------------------------------------------------------
# PCAP Receiver
# ------------------------------------------------------------

def run_pcap(args):

    try:
        from scapy.all import PcapReader, UDP, IP
    except ImportError:
        print(
            "Scapy is required for PCAP mode.\n"
            "Install with:\n"
            "    pip install scapy"
        )
        return 1

    print()
    print(f"Opening PCAP: {args.pcap}")
    print()

    decoder = LKV373Decoder(
        frame_timeout=args.frame_timeout,
        max_frames=args.max_buffers,
        save_dir=args.save_frames,
    )

    packet_count = 0

    try:

        reader = PcapReader(args.pcap)

        for packet in reader:

            if not packet.haslayer(UDP):
                continue

            udp = packet[UDP]

            if udp.dport != args.port:
                continue

            if packet.haslayer(IP):

                ip = packet[IP]

                if ip.dst != args.group:
                    continue

                if args.source and ip.src != args.source:
                    continue

            payload = bytes(udp.payload)

            packet_count += 1

            frame = decoder.process_packet(payload)

            if frame is not None:

                display_frame(
                    frame,
                    fullscreen=args.fullscreen,
                )

                key = cv2.waitKey(
                    max(1, int(1000 / args.fps))
                ) & 0xFF

                if key in (27, ord("q"), ord("Q")):
                    break

                if (
                    args.max_frames > 0
                    and decoder.frames_decoded >= args.max_frames
                ):
                    break

        reader.close()

    except FileNotFoundError:
        print(f"[ERROR] PCAP not found: {args.pcap}")
        return 1

    except Exception as e:
        print(f"[ERROR] PCAP processing failed: {e}")
        return 1

    finally:

        cv2.destroyAllWindows()

    print()
    print("========== PCAP STATISTICS ==========")
    print(f"UDP video packets : {packet_count}")
    print(f"Frames completed  : {decoder.frames_completed}")
    print(f"Frames decoded    : {decoder.frames_decoded}")
    print(f"Frames failed     : {decoder.frames_failed}")
    print("=====================================")

    return 0


# ------------------------------------------------------------
# Interface Detection
# ------------------------------------------------------------

def show_interfaces():
    print()
    print("Python cannot always reliably enumerate Windows NICs")
    print("without additional packages.")
    print()
    print("Use Windows:")
    print()
    print("    ipconfig")
    print()
    print("Find the IPv4 address of the Ethernet adapter connected")
    print("to the HDMI-over-IP network.")
    print()
    print("Example:")
    print()
    print("    IPv4 Address . . . . . : 192.168.168.10")
    print()
    print("Then run:")
    print()
    print("    python lkv373_receiver.py --interface 192.168.168.10")
    print()


# ------------------------------------------------------------
# Argument Parser
# ------------------------------------------------------------

def build_parser():

    parser = argparse.ArgumentParser(
        description="LKV373 HDMI-over-IP Receiver"
    )

    parser.add_argument(
        "--group",
        default=DEFAULT_GROUP,
        help=f"Multicast group (default: {DEFAULT_GROUP})",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"UDP video port (default: {DEFAULT_PORT})",
    )

    parser.add_argument(
        "--interface",
        default=None,
        help=(
            "Local Ethernet IPv4 address used for multicast. "
            "Example: 192.168.168.10"
        ),
    )

    parser.add_argument(
        "--source",
        default=None,
        help="Optional transmitter source IP filter",
    )

    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Display video fullscreen",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show live packet/frame statistics",
    )

    parser.add_argument(
        "--frame-timeout",
        type=float,
        default=DEFAULT_FRAME_TIMEOUT,
        help="Incomplete frame timeout in seconds",
    )

    parser.add_argument(
        "--max-buffers",
        type=int,
        default=MAX_FRAME_BUFFERS,
        help="Maximum incomplete frames kept in memory",
    )

    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Stop after decoding N frames; 0 = unlimited",
    )

    parser.add_argument(
        "--save-frames",
        default=None,
        help="Directory for saving decoded JPEG frames",
    )

    parser.add_argument(
        "--pcap",
        default=None,
        help="Read video from PCAP/PCAPNG instead of live network",
    )

    parser.add_argument(
        "--fps",
        type=float,
        default=30.0,
        help="PCAP playback FPS",
    )

    parser.add_argument(
        "--interfaces",
        action="store_true",
        help="Show interface instructions",
    )

    return parser


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():

    parser = build_parser()
    args = parser.parse_args()

    if args.interfaces:
        show_interfaces()
        return 0

    # PCAP mode
    if args.pcap:

        print()
        print("MODE: PCAP")
        print(f"Group : {args.group}")
        print(f"Port  : {args.port}")
        print()

        return run_pcap(args)

    # Live mode requires interface
    if not args.interface:

        print()
        print("ERROR: --interface is required for LIVE mode.")
        print()
        print("First run:")
        print()
        print("    ipconfig")
        print()
        print("Find the IPv4 address of the Ethernet adapter")
        print("connected to the HDMI-over-IP transmitter.")
        print()
        print("Then:")
        print()
        print(
            "    python lkv373_receiver.py "
            "--interface 192.168.168.10"
        )
        print()

        return 1

    print()
    print("==============================================")
    print("       LKV373 HDMI-over-IP RECEIVER")
    print("==============================================")
    print()
    print(f"Mode            : LIVE")
    print(f"Multicast       : {args.group}")
    print(f"UDP port        : {args.port}")
    print(f"Interface       : {args.interface}")

    if args.source:
        print(f"Source filter   : {args.source}")

    print()
    print("==============================================")
    print()

    return run_live(args)


if __name__ == "__main__":
    sys.exit(main())