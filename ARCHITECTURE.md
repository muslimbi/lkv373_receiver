# HDMI-over-IP Receiver Architecture

## High-Level Pipeline Architecture

The HDMI-over-IP receiver is designed as an asynchronous, multi-threaded pipeline using bounded thread-safe queues to ensure low latency and prevent memory growth.

```
       [ HDMI Transmitter ]
                │
                ▼ (UDP Multicast 226.2.2.2:2068)
  ┌───────────────────────────┐
  │     MulticastReceiver     │  <-- Dedicated Network Rx Thread
  └─────────────┬─────────────┘
                │ Raw Packets (Bounded Queue)
                ▼
  ┌───────────────────────────┐
  │       PacketParser        │  <-- Encapsulation Header & Codec Signature Parser
  └─────────────┬─────────────┘
                │ Parsed Packets
                ▼
  ┌───────────────────────────┐
  │     FrameReassembler      │  <-- Sequence Reordering, Loss Tracking & Boundary Detection
  └─────────────┬─────────────┘
                │ Reassembled Frame Payload (Bounded Queue)
                ▼
  ┌───────────────────────────┐
  │       VideoDecoder        │  <-- Hardware Accelerated / CPU Decoder (FFmpeg/OpenCV)
  └─────────────┬─────────────┘
                │ Decoded BGR Frame Array
                ▼
  ┌───────────────────────────┐
  │        VideoViewer        │  <-- Real-time Windowed / Fullscreen HDMI Output + HUD Overlay
  └───────────────────────────┘
```

---

## Component Responsibilities

1. **`multicast_receiver.py`**:
   - Manages non-blocking IPv4 UDP multicast sockets.
   - Configures socket buffer (`SO_RCVBUF = 8MB`) to eliminate OS kernel drop under high bitrates.
   - Runs a dedicated background thread putting packets into a bounded queue.
   - Collects network metrics (Mbps throughput, pps packet rate, total bytes).

2. **`packet_parser.py`**:
   - Inspects raw UDP packet headers.
   - Detects transport signatures (HDbitT 16-byte header, RTP 12-byte header, MPEG-TS 0x47 sync byte).
   - Computes Shannon entropy and identifies video payload codec signatures (H.264/H.265 NALUs, MJPEG JPEGs).

3. **`frame_reassembler.py`**:
   - Reconstructs fragmented UDP packets into complete video frame buffers.
   - Handles sequence reordering, missing packet tracking, stream restarts, and frame boundaries.

4. **`video_decoder.py`**:
   - Decodes compressed frame buffers (MJPEG / H.264 / H.265 / MPEG-TS) into OpenCV BGR numpy arrays.
   - Employs hardware acceleration options (DXVA2, D3D11VA, NVDEC, QSV) with CPU decoding fallbacks.

5. **`video_viewer.py`**:
   - Low-latency real-time display rendering via OpenCV GUI.
   - Supports Mode 1 (Windowed display) and Mode 2 (Fullscreen output to HDMI display).
   - Draws interactive performance HUD overlay.

6. **`hdmi_receiver.py`**:
   - Main CLI / GUI application orchestrating the entire live or offline analysis pipeline.
