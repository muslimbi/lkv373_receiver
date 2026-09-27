# HDMI-over-IP Multicast Video Receiver & Display System

A high-performance, modular Python/C++ HDMI-over-IP receiver system that captures multicast UDP streams (`226.2.2.2:2068`), reverse-engineers protocol encapsulation headers, reassembles fragmented video frames, decodes compressed streams (MJPEG, H.264, H.265, MPEG-TS), and outputs real-time low-latency video to computer displays and HDMI monitors.

---

## Key Features

- **Live UDP Multicast Receiver**: Cross-platform IPv4 socket management (`226.2.2.2:2068`), multi-threaded rx loop, socket buffer tuning (`8MB RCVBUF`), and real-time network throughput metrics.
- **Protocol Discovery & Packet Parsing**: Zero-assumption header inspection supporting HDbitT/Lenkeng (16-byte headers), RTP (12-byte headers), MPEG-TS (0x47 sync byte), custom sequence headers, and Shannon entropy analysis.
- **Frame Reassembly Engine**: Robust frame boundary detection, packet sequence reordering, packet loss tracking, duplicate removal, and stream restart recovery.
- **Hardware-Accelerated Video Decoding**: Decodes MJPEG, H.264, H.265, and MPEG-TS with hardware acceleration flags (`DXVA2`, `D3D11VA`, `NVDEC`, `QSV`) and CPU fallback.
- **Low-Latency Dual-Mode Video Viewer**:
  - **Mode 1**: Windowed low-latency viewer with HUD performance stats.
  - **Mode 2**: Fullscreen output to secondary monitor / HDMI connected TV display.
- **Diagnostic Toolkit (`tools/`)**: Includes PCAP analyzer, payload dumper, codec signature scanner, live stream recorder, and synthetic HDMI transmitter simulator.
- **Automated Test Suite (`tests/`)**: Unit tests covering packet parsing, reassembly, signature detection, and socket metrics.

---

## Architecture Overview

```
HDMI Transmitter (192.168.168.55)
       ↓ UDP Multicast 226.2.2.2:2068
Network Receiver Thread (`multicast_receiver.py`)
       ↓ Raw Packets (Bounded Queue)
Protocol & Header Parser (`packet_parser.py`)
       ↓ Parsed Packets
Frame Reassembler (`frame_reassembler.py`)
       ↓ Reassembled Frame Payload
Video Decoder (`video_decoder.py`)
       ↓ BGR Image Frame
Video Viewer & HDMI Output (`video_viewer.py`)
```

---

## Quickstart

### 1. Run Live Multicast Receiver
```cmd
python hdmi_receiver.py --group 226.2.2.2 --port 2068 --interface 192.168.168.10
```

### 2. Fullscreen HDMI Output Mode
```cmd
python hdmi_receiver.py --fullscreen
```

### 3. Run Offline File Playback / Analysis
```cmd
python hdmi_receiver.py --input-file sample_capture.bin
```

---

## Keyboard Controls (Viewer)

- `F` or `F11`: Toggle Fullscreen HDMI output mode
- `S`: Toggle HUD stats overlay (FPS, Codec, Bitrate, Packet Loss, Latency)
- `Q` or `ESC`: Exit receiver

---

## Diagnostic Tools (`tools/`)

```cmd
# 1. Analyze PCAP or binary capture file
python tools/analyze_pcap.py capture.bin

# 2. Inspect raw packet headers & entropy
python tools/inspect_payload.py capture.bin --count 5

# 3. Detect video codec signature
python tools/detect_codec.py capture.bin

# 4. Extract reassembled video frames
python tools/dump_frames.py capture.bin --output-dir extracted_frames

# 5. Record live multicast stream to file
python tools/capture_multicast.py --group 226.2.2.2 --port 2068 --output live_capture.bin --duration 10

# 6. Run synthetic HDMI transmitter simulator (for offline testing)
python tools/simulate_transmitter.py --fps 30
```

---

## Running Automated Tests

```cmd
python -m pytest tests/
```

---

## Project Structure

```
d:\hdmi\
├── hdmi_receiver.py          # Main application entry point
├── multicast_receiver.py     # Multicast socket rx thread
├── packet_parser.py          # Header parser & protocol discovery
├── frame_reassembler.py      # Frame reassembler & packet loss handler
├── video_decoder.py          # Video decoder engine (MJPEG/H.264/H.265)
├── video_viewer.py           # Real-time windowed & fullscreen HDMI display
├── protocol.py               # Protocol definitions & enums
├── protocol_report.md        # Protocol discovery report
├── ARCHITECTURE.md           # Architecture documentation
├── PROTOCOL.md               # Encapsulation specifications
├── INSTALL.md                # Installation & setup guide
├── TROUBLESHOOTING.md        # Multicast & diagnostic guide
├── tools/                    # Command-line diagnostic tools
│   ├── analyze_pcap.py
│   ├── capture_multicast.py
│   ├── inspect_payload.py
│   ├── detect_codec.py
│   ├── dump_frames.py
│   └── simulate_transmitter.py
└── tests/                    # Automated pytest test suite
    ├── test_packet_parser.py
    ├── test_frame_reassembler.py
    ├── test_codec_detector.py
    └── test_multicast_receiver.py
```