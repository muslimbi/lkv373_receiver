# LKV373 / Lenkeng HDMI-over-IP MJPEG Receiver

High-performance Python receiver and real-time viewer for LKV373 and Lenkeng HDMI-over-IP hardware transmitters. Encapsulated MJPEG frames sent via UDP multicast on group `226.2.2.2:2068` are received, reassembled, decoded, and rendered with sub-frame latency and diagnostic statistics.

---

## Features

- **Live Multicast Receiver:** Binds to `226.2.2.2:2068` on Windows and Linux with configurable network interface selection.
- **Stateful JPEG Reassembler:** Handles 16-bit frame sequence rollover, chunk re-ordering, packet loss, duplicate detection, and missing chunk timeout cleanup.
- **Direct Low-Latency JPEG Decoding:** Decodes raw JPEG frames directly to GPU/display buffers using OpenCV without intermediate transcoding.
- **PySide6 Real-Time Viewer:**
  - Real-time video rendering (1280x1024 or auto-resolution).
  - Multi-monitor selection (`--monitor 0`, `--monitor 1`).
  - Fullscreen output toggle (`F11` or `--fullscreen`).
  - On-screen HUD Overlay (`D` or `Tab`) with live FPS, packet rate, packet/frame loss, duplicate count, decode latency, and frame sequence numbers.
- **PCAP / PCAPNG Offline Playback Engine:** Play back Wireshark captures (`--pcap hdmi.pcapng`) at 30 FPS.
- **Frame Extractor Tool:** Export all reassembled JPEG images to disk (`python tools/extract_frames.py capture.pcapng`).
- **Network Diagnostic Analyzer:** Command-line tool to inspect captures (`python tools/analyze_pcap.py capture.pcapng`).
- **Modular Audio Receiver:** Listens on UDP port 2066 for audio payload packets.

---

## Architecture Overview

```
+---------------------------+
| LKV373 HDMI Transmitter   |
+---------------------------+
              │
              ▼ Multicast (UDP 226.2.2.2:2068)
+---------------------------+
| Network Receiver          | (lkv373_receiver/receiver/multicast.py)
+---------------------------+
              │
              ▼ 4-Byte LKV373 Header (Frame #, Chunk #)
+---------------------------+
| Packet Parser             | (lkv373_receiver/receiver/packet.py)
+---------------------------+
              │
              ▼ Chunk Array
+---------------------------+
| Frame Reassembler         | (lkv373_receiver/receiver/reassembler.py)
+---------------------------+
              │
              ▼ Validated JPEG Buffer (FF D8 ... FF D9)
+---------------------------+
| Direct JPEG Decoder       | (lkv373_receiver/video/jpeg_decoder.py)
+---------------------------+
              │
              ▼ BGR Image Frame
+---------------------------+
| PySide6 Video Renderer    | (lkv373_receiver/video/renderer.py)
+---------------------------+
              │
              ▼
    PC Monitor / HDMI Display
```

---

## Quick Start

### 1. Live Multicast Streaming Mode
```bash
python main.py --group 226.2.2.2 --port 2068 --interface 192.168.168.100
```

### 2. Playback Wireshark PCAP Capture
```bash
python main.py --pcap hdmi.pcapng
```

### 3. Extract JPEG Frames
```bash
python tools/extract_frames.py sample_capture.bin --output-dir extracted_frames
```

### 4. Run Diagnostic Network Analysis
```bash
python tools/analyze_pcap.py sample_capture.bin
```

---

## Unit Testing

Run the pytest test suite:
```bash
python -m pytest lkv373_receiver/tests
```
