"""
HDMI-over-IP Multicast Receiver - Main Application.
Orchestrates multicast reception, protocol header parsing, frame reassembly,
video decoding, performance statistics, and real-time viewing / HDMI display.

Usage:
    python hdmi_receiver.py --group 226.2.2.2 --port 2068 --interface 0.0.0.0
    python hdmi_receiver.py --fullscreen
    python hdmi_receiver.py --input-file hdmi.pcapng
"""

import sys
import os
import time
import signal
import argparse
import logging
import cv2
import numpy as np

# Ensure current directory is in python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from lkv373_receiver.receiver.multicast import MulticastReceiver
from lkv373_receiver.receiver.packet import parse_packet
from lkv373_receiver.receiver.reassembler import FrameReassembler
from lkv373_receiver.video.jpeg_decoder import JPEGDecoder
from lkv373_receiver.video.renderer import VideoRenderer
from lkv373_receiver.diagnostics.statistics import StreamStatistics
from lkv373_receiver.diagnostics.pcap_analyzer import PCAPAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("HDMIReceiver")


def run_hdmi_receiver(args):
    print("=" * 65)
    print("      HDMI-OVER-IP RECEIVER & VIDEO DISPLAY SYSTEM      ")
    print("=" * 65)
    print(f"Target Multicast: {args.group}:{args.port}")
    print(f"Network Interface: {args.interface}")
    print(f"Display Mode:      {'FULLSCREEN HDMI MODE' if args.fullscreen else 'WINDOWED MODE'}")
    print("Press [F11] / [F] for Fullscreen | [D] / [Tab] Toggle HUD | [Q] / [ESC] to Quit")
    print("=" * 65)

    stats = StreamStatistics()
    stats.group_ip = args.group
    stats.port = args.port
    stats.interface_ip = args.interface

    reassembler = FrameReassembler(max_active_frames=4)
    decoder = JPEGDecoder(use_opencv=True)

    renderer = None
    if not args.no_gui:
        renderer = VideoRenderer(
            stats=stats,
            title="LKV373 HDMI-over-IP Receiver",
            fullscreen=args.fullscreen,
            monitor_index=args.monitor,
            use_pyside=True,
        )

    video_writer = None
    if args.save_video:
        logger.info(f"Video recording enabled -> {args.save_video}")

    save_dir = None
    if args.save_frames:
        save_dir = os.path.join(os.path.dirname(__file__), "saved_frames")
        os.makedirs(save_dir, exist_ok=True)

    pcap_file = getattr(args, "input_file", None) or getattr(args, "pcap", None)
    if pcap_file:
        print(f"\n[Mode: Offline File Playback: {pcap_file}]")
        analyzer = PCAPAnalyzer(pcap_file)
        packets = analyzer.extract_udp_packets()

        if not packets:
            print(f"Error: No UDP packets found in {pcap_file}")
            return

        video_packets = [p for p in packets if p.dst_port == args.port]
        if not video_packets:
            video_packets = packets

        print(f"Loaded {len(video_packets)} video packets from capture file. Starting playback...")

        frame_counter = 0
        target_interval = 1.0 / 30.0

        for pkt in video_packets:
            now = time.time()
            stats.record_packet(now)

            vp = parse_packet(pkt.payload, now)
            if not vp:
                continue

            frame = reassembler.process_packet(vp)
            if frame and frame.jpeg_data:
                frame_counter += 1
                decoded = decoder.decode(frame.jpeg_data, frame.frame_number, now)
                
                if decoded:
                    stats.record_frame(
                        frame_number=decoded.frame_number,
                        width=decoded.width,
                        height=decoded.height,
                        decode_latency_ms=decoded.decode_time_ms,
                        timestamp=now,
                    )

                    if save_dir:
                        out_path = os.path.join(save_dir, f"frame_{frame_counter:06d}.jpg")
                        with open(out_path, "wb") as f:
                            f.write(frame.jpeg_data)

                    if args.save_video:
                        if video_writer is None:
                            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                            video_writer = cv2.VideoWriter(args.save_video, fourcc, 30.0, (decoded.width, decoded.height))
                            logger.info(f"Initialized VideoWriter: {args.save_video} ({decoded.width}x{decoded.height} @ 30fps)")
                        video_writer.write(decoded.image)

                    if renderer:
                        renderer.render_frame(decoded.image)

                    time.sleep(target_interval)

        print("\nPlayback complete.")
        if renderer:
            time.sleep(0.5)
            renderer.close()
        if video_writer:
            video_writer.release()
        return

    # Live Receiver Mode
    print(f"\n[Mode: Live Multicast Reception -> {args.group}:{args.port}]")
    receiver = MulticastReceiver(
        group_ip=args.group,
        port=args.port,
        interface_ip=args.interface,
        source_ip=args.source,
    )
    receiver.start()

    frame_counter = 0

    try:
        while receiver.running:
            item = receiver.get_packet(timeout=0.05)
            if not item:
                continue

            raw_bytes, src_ip, recv_time = item
            stats.record_packet(recv_time)

            vp = parse_packet(raw_bytes, recv_time)
            if not vp:
                continue

            frame = reassembler.process_packet(vp)
            if frame and frame.jpeg_data:
                frame_counter += 1
                decoded = decoder.decode(frame.jpeg_data, frame.frame_number, recv_time)

                if decoded:
                    stats.record_frame(
                        frame_number=decoded.frame_number,
                        width=decoded.width,
                        height=decoded.height,
                        decode_latency_ms=decoded.decode_time_ms,
                        timestamp=recv_time,
                    )

                    if save_dir:
                        out_path = os.path.join(save_dir, f"frame_{frame_counter:06d}.jpg")
                        with open(out_path, "wb") as f:
                            f.write(frame.jpeg_data)

                    if args.save_video:
                        if video_writer is None:
                            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                            video_writer = cv2.VideoWriter(args.save_video, fourcc, 30.0, (decoded.width, decoded.height))
                            logger.info(f"Initialized VideoWriter: {args.save_video} ({decoded.width}x{decoded.height} @ 30fps)")
                        video_writer.write(decoded.image)

                    if renderer:
                        renderer.render_frame(decoded.image)

    except KeyboardInterrupt:
        print("\nStopping receiver...")
    finally:
        receiver.stop()
        if renderer:
            renderer.close()
        if video_writer:
            video_writer.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HDMI-over-IP Receiver & Display System")
    parser.add_argument("--group", default="226.2.2.2", help="Multicast group IP address")
    parser.add_argument("--port", type=int, default=2068, help="UDP destination port")
    parser.add_argument("--interface", default="192.168.168.10", help="Local network adapter IP")
    parser.add_argument("--source", default=None, help="Filter by transmitter IP")
    parser.add_argument("--fullscreen", action="store_true", help="Launch in fullscreen HDMI output mode")
    parser.add_argument("--monitor", type=int, default=0, help="Target monitor index for fullscreen")
    parser.add_argument("--no-gui", action="store_true", help="Disable GUI window")
    parser.add_argument("--input-file", default=None, help="Path to offline capture file")
    parser.add_argument("--pcap", default=None, help="Path to offline PCAP/PCAPNG capture file")
    parser.add_argument("--save-frames", action="store_true", help="Save extracted JPEG frames to disk")
    parser.add_argument("--save-video", default=None, help="Save decoded stream to MP4 video file (e.g. hdmi_decoded.mp4)")

    args = parser.parse_args()
    run_hdmi_receiver(args)
