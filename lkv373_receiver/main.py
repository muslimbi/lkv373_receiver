"""
LKV373 / Lenkeng HDMI-over-IP MJPEG Receiver Main Application.

Live Multicast Receiver & PCAP Playback Engine:
1. Connects to multicast socket 226.2.2.2:2068 (or reads PCAP capture file)
2. Parses 4-byte LKV373 packet header (Frame Number, Chunk Number)
3. Stateful low-latency JPEG reassembly
4. Direct JPEG decoding
5. PySide6 real-time display with diagnostic stats overlay
"""

import sys
import os
import argparse
import time
import cv2
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lkv373_receiver.receiver.multicast import MulticastReceiver
from lkv373_receiver.receiver.packet import parse_packet
from lkv373_receiver.receiver.reassembler import FrameReassembler
from lkv373_receiver.video.jpeg_decoder import JPEGDecoder
from lkv373_receiver.video.renderer import VideoRenderer
from lkv373_receiver.diagnostics.statistics import StreamStatistics
from lkv373_receiver.diagnostics.pcap_analyzer import PCAPAnalyzer
from lkv373_receiver.audio.audio_receiver import AudioReceiver

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("LKV373")


def run_live_receiver(args, stats: StreamStatistics, reassembler: FrameReassembler, decoder: JPEGDecoder, renderer: VideoRenderer | None, video_writer: cv2.VideoWriter | None):
    """Runs live UDP multicast receiver loop."""
    receiver = MulticastReceiver(
        group_ip=args.group,
        port=args.port,
        interface_ip=args.interface,
        source_ip=args.source,
    )
    receiver.start()

    # Optional Audio Receiver on 2066
    audio_receiver = AudioReceiver(group_ip=args.group, port=2066, interface_ip=args.interface)
    audio_receiver.start()

    logger.info(f"Live Multicast Receiver Started -> Group: {args.group}:{args.port}, Interface: {args.interface}")
    logger.info("Press Ctrl+C or close window to exit.")

    save_dir = Path("saved_frames") if args.save_frames else None
    if save_dir:
        save_dir.mkdir(exist_ok=True)

    frame_counter = 0

    try:
        while receiver.running:
            item = receiver.get_packet(timeout=0.05)
            if not item:
                continue

            raw_bytes, src_ip, recv_time = item
            stats.record_packet(recv_time)

            pkt = parse_packet(raw_bytes, recv_time)
            if not pkt:
                continue

            frame = reassembler.process_packet(pkt)
            if frame and frame.jpeg_data:
                frame_counter += 1
                decoded = decoder.decode(frame.jpeg_data, frame.frame_number, frame.last_updated)
                
                if decoded:
                    stats.record_frame(
                        frame_number=decoded.frame_number,
                        width=decoded.width,
                        height=decoded.height,
                        decode_latency_ms=decoded.decode_time_ms,
                        timestamp=decoded.timestamp,
                    )

                    # Option 1: Save JPEG frames
                    if save_dir:
                        file_path = save_dir / f"frame_{frame_counter:06d}_fn{frame.frame_number}.jpg"
                        with open(file_path, "wb") as f:
                            f.write(frame.jpeg_data)

                    # Option 2: Record MP4 video
                    if args.save_video:
                        if video_writer is None:
                            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                            video_writer = cv2.VideoWriter(args.save_video, fourcc, 30.0, (decoded.width, decoded.height))
                            logger.info(f"Initialized VideoWriter: {args.save_video} ({decoded.width}x{decoded.height} @ 30fps)")
                        video_writer.write(decoded.image)

                    # Option 3: Render to Screen
                    if renderer:
                        renderer.render_frame(decoded.image)

    except KeyboardInterrupt:
        logger.info("Stopping Live Receiver...")
    finally:
        receiver.stop()
        audio_receiver.stop()
        if renderer:
            renderer.close()
        if video_writer:
            video_writer.release()


def run_pcap_mode(args, stats: StreamStatistics, reassembler: FrameReassembler, decoder: JPEGDecoder, renderer: VideoRenderer | None, video_writer: cv2.VideoWriter | None):
    """Runs PCAP / PCAPNG playback mode."""
    pcap_path = args.pcap
    logger.info(f"Reading PCAP file: {pcap_path}")

    analyzer = PCAPAnalyzer(pcap_path)
    packets = analyzer.extract_udp_packets()

    if not packets:
        logger.error(f"No UDP packets extracted from {pcap_path}")
        return

    video_packets = [p for p in packets if p.dst_port == args.port]
    if not video_packets:
        video_packets = packets

    logger.info(f"Loaded {len(video_packets)} video packets out of {len(packets)} total UDP packets. Starting playback...")

    save_dir = Path("saved_frames") if args.save_frames else None
    if save_dir:
        save_dir.mkdir(exist_ok=True)

    frame_counter = 0
    target_frame_interval = 1.0 / 30.0  # 30 FPS pacing (~33.3ms)

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
                    file_path = save_dir / f"pcap_frame_{frame_counter:06d}.jpg"
                    with open(file_path, "wb") as f:
                        f.write(frame.jpeg_data)

                if args.save_video:
                    if video_writer is None:
                        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                        video_writer = cv2.VideoWriter(args.save_video, fourcc, 30.0, (decoded.width, decoded.height))
                        logger.info(f"Initialized VideoWriter: {args.save_video} ({decoded.width}x{decoded.height} @ 30fps)")
                    video_writer.write(decoded.image)

                if renderer:
                    renderer.render_frame(decoded.image)

                # Real-time pacing (30 FPS)
                time.sleep(target_frame_interval)

    logger.info("PCAP Playback Finished.")
    if renderer:
        time.sleep(1.0)
        renderer.close()
    if video_writer:
        video_writer.release()


def main():
    parser = argparse.ArgumentParser(description="LKV373 / Lenkeng HDMI-over-IP MJPEG Receiver")
    
    # Network options
    parser.add_argument("--group", default="226.2.2.2", help="Multicast group IP (default: 226.2.2.2)")
    parser.add_argument("--port", type=int, default=2068, help="UDP video port (default: 2068)")
    parser.add_argument("--interface", default="0.0.0.0", help="Network interface IP to bind (e.g. 192.168.168.100)")
    parser.add_argument("--source", default=None, help="Filter by transmitter source IP (e.g. 192.168.168.55)")
    
    # PCAP mode
    parser.add_argument("--pcap", default=None, help="Path to PCAP/PCAPNG capture file for playback")
    
    # Output options
    parser.add_argument("--save-frames", action="store_true", help="Save reassembled JPEG frames to disk")
    parser.add_argument("--save-video", default=None, help="Path to save MP4 video recording (e.g. output.mp4)")
    
    # Display options
    parser.add_argument("--fullscreen", action="store_true", help="Start viewer in fullscreen mode")
    parser.add_argument("--monitor", type=int, default=0, help="Target monitor index for fullscreen (0-indexed)")
    parser.add_argument("--no-gui", action="store_true", help="Disable GUI display window (headless mode)")

    args = parser.parse_args()

    # Shared Stream Statistics
    stats = StreamStatistics()
    stats.group_ip = args.group
    stats.port = args.port
    stats.interface_ip = args.interface

    # Core Pipeline
    reassembler = FrameReassembler(max_active_frames=4)
    decoder = JPEGDecoder(use_opencv=True)

    # Renderer setup
    renderer = None
    if not args.no_gui:
        renderer = VideoRenderer(
            stats=stats,
            title="LKV373 HDMI-over-IP MJPEG Receiver",
            fullscreen=args.fullscreen,
            monitor_index=args.monitor,
            use_pyside=True,
        )

    # Video Recording setup
    video_writer = None

    if args.pcap:
        run_pcap_mode(args, stats, reassembler, decoder, renderer, video_writer)
    else:
        run_live_receiver(args, stats, reassembler, decoder, renderer, video_writer)


if __name__ == "__main__":
    main()
