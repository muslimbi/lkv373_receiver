"""
HDMI-over-IP Multicast Receiver - Main Application.
Orchestrates multicast reception, protocol header parsing, frame reassembly,
video decoding, performance statistics, and real-time viewing / HDMI display.

Usage:
    python hdmi_receiver.py --group 226.2.2.2 --port 2068 --interface 0.0.0.0
    python hdmi_receiver.py --fullscreen
    python hdmi_receiver.py --input-file capture.bin
"""

import sys
import os
import time
import signal
import argparse
import logging
import cv2
import numpy as np

from multicast_receiver import MulticastReceiver
from packet_parser import PacketParser
from frame_reassembler import FrameReassembler
from video_decoder import VideoDecoder
from video_viewer import VideoViewer
from protocol import CodecType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

def run_hdmi_receiver(args):
    print("=" * 65)
    print("      HDMI-OVER-IP RECEIVER & VIDEO DISPLAY SYSTEM      ")
    print("=" * 65)
    print(f"Target Multicast: {args.group}:{args.port}")
    print(f"Network Interface: {args.interface}")
    print(f"Display Mode:      {'FULLSCREEN HDMI MODE' if args.fullscreen else 'WINDOWED MODE'}")
    print("Press [F] for Fullscreen | [S] Toggle HUD | [Q] / [ESC] to Quit")
    print("=" * 65)

    parser = PacketParser()
    reassembler = FrameReassembler()
    decoder = VideoDecoder()
    viewer = VideoViewer(
        width=args.width,
        height=args.height,
        fullscreen=args.fullscreen,
        show_hud=not args.no_hud
    )

    receiver = None
    stream_detected = False
    sample_packets = []
    stream_info = None

    if args.input_file:
        print(f"\n[Mode: Offline File Playback: {args.input_file}]")
        from tools.analyze_pcap import parse_pcap_file
        packets_pool = parse_pcap_file(args.input_file)
        if not packets_pool:
            print("Error: No packets loaded from file.")
            return
        print(f"Loaded {len(packets_pool)} packets from capture file.")
    else:
        print(f"\n[Mode: Live Multicast Reception -> {args.group}:{args.port}]")
        receiver = MulticastReceiver(
            group=args.group,
            port=args.port,
            interface_ip=args.interface
        )
        receiver.start()

    running = True

    def sig_handler(sig, frame):
        nonlocal running
        print("\nShutdown signal received...")
        running = False

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    try:
        packet_idx = 0
        while running and viewer.is_running:
            # 1. Fetch Next Packet (from live receiver socket or offline file)
            if receiver:
                pkt_tuple = receiver.get_packet(timeout=0.1)
                if not pkt_tuple:
                    continue
                raw_pkt, rx_time = pkt_tuple
            else:
                if packet_idx >= len(packets_pool):
                    print("Reached end of capture file. Looping playback...")
                    packet_idx = 0
                    reassembler.reset()
                raw_pkt = packets_pool[packet_idx]
                packet_idx += 1
                rx_time = time.time()
                time.sleep(0.001)

            # 2. Protocol Discovery Stage (Analyze initial 30 packets)
            if not stream_detected:
                sample_packets.append(raw_pkt)
                if len(sample_packets) >= 30:
                    stream_info = parser.detect_stream_characteristics(sample_packets)
                    print("\n" + "=" * 50)
                    print(f" PROTOCOL IDENTIFIED: {stream_info.codec.value}")
                    print(f" Encapsulation:       {stream_info.encapsulation.value}")
                    print(f" Confidence:          {stream_info.confidence * 100:.1f}%")
                    print(f" Evidence:            {stream_info.notes}")
                    print("=" * 50 + "\n")
                    decoder.set_codec(stream_info.codec)
                    stream_detected = True

            # 3. Parse Packet Header
            parsed_pkt = parser.parse_packet(raw_pkt)

            # 4. Reassemble Frame
            reassembled_frames = reassembler.process_packet(parsed_pkt)

            for frame_data in reassembled_frames:
                # 5. Decode Frame
                decoded_img = decoder.decode(frame_data.data)

                # Fallback visual frame if undecodable video elementary stream
                if decoded_img is None:
                    # Create informative diagnostic display frame
                    decoded_img = np.zeros((args.height, args.width, 3), dtype=np.uint8)
                    cv2.putText(
                        decoded_img,
                        f"STREAM ACTIVE | {stream_info.codec.value if stream_info else 'REASSEMBLING'}",
                        (60, 200),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.1,
                        (0, 255, 0),
                        2
                    )
                    cv2.putText(
                        decoded_img,
                        f"Frame #{frame_data.frame_num} ({len(frame_data.data)} bytes)",
                        (60, 270),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.9,
                        (255, 255, 255),
                        2
                    )
                    if stream_info and stream_info.codec == CodecType.PROPRIETARY:
                        cv2.putText(
                            decoded_img,
                            "Proprietary/Encrypted Stream - Decapsulating Payload...",
                            (60, 340),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 165, 255),
                            2
                        )

                # 6. Gather Statistics for HUD
                net_stats = receiver.get_stats() if receiver else {}
                dec_stats = decoder.get_stats()
                reassem_stats = reassembler.stats

                combined_stats = {
                    "codec": dec_stats["codec"],
                    "encapsulation": stream_info.encapsulation.value if stream_info else "UDP",
                    "sender_ip": net_stats.get("sender_ip", "192.168.168.55"),
                    "mbps": net_stats.get("mbps", 0.0),
                    "pps": net_stats.get("pps", 0),
                    "total_packets": net_stats.get("total_packets", packet_idx),
                    "dropped_packets": reassem_stats["dropped_packets"],
                    "latency_ms": 33.0 + (time.time() - frame_data.timestamp) * 1000.0
                }

                # 7. Render Video Display
                res = viewer.render(decoded_img, combined_stats)
                if not res:
                    running = False
                    break

    except Exception as e:
        logging.error(f"Execution error in main receiver loop: {e}", exc_info=True)
    finally:
        print("\nShutting down HDMI Receiver pipeline...")
        if receiver:
            receiver.stop()
        viewer.close()
        decoder.close()
        print("Shutdown complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HDMI-over-IP Receiver & Display System")
    parser.add_argument("--group", default="226.2.2.2", help="Multicast group IP address")
    parser.add_argument("--port", type=int, default=2068, help="UDP destination port")
    parser.add_argument("--interface", default="192.168.168.10", help="Local network adapter IP (HDMI Receiver IP)")
    parser.add_argument("--fullscreen", action="store_true", help="Launch in fullscreen HDMI output mode")
    parser.add_argument("--width", type=int, default=1280, help="Window display width")
    parser.add_argument("--height", type=int, default=720, help="Window display height")
    parser.add_argument("--no-hud", action="store_true", help="Disable statistics HUD overlay")
    parser.add_argument("--input-file", help="Path to offline capture file for analysis/playback")

    args = parser.parse_args()
    run_hdmi_receiver(args)
