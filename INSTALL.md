# LKV373 HDMI-over-IP Receiver Installation & Setup Guide

## Requirements

- **Operating System:** Windows 10/11 or Linux
- **Python Version:** Python 3.10+
- **Network:** 1Gbps Ethernet interface connected to the LKV373 transmitter network switch or direct cable.

---

## Installation Steps

1. **Clone or Extract the Repository:**
   ```bash
   cd d:\hdmi
   ```

2. **Install Python Dependencies:**
   ```bash
   python -m pip install PySide6 opencv-python pillow numpy PyYAML pytest
   ```

3. **Verify Installation & Run Tests:**
   ```bash
   python -m pytest lkv373_receiver/tests
   ```

---

## Usage Examples

### 1. Live Receiver Mode
Receive multicast stream on group `226.2.2.2:2068`:
```bash
python main.py --group 226.2.2.2 --port 2068 --interface 192.168.168.100
```

### 2. Fullscreen HDMI Output Mode
Display full screen on specific monitor index:
```bash
python main.py --fullscreen --monitor 0
```

### 3. PCAP Offline Playback Mode
Play back captured Wireshark `.pcapng` or `.pcap` file at ~30 FPS:
```bash
python main.py --pcap hdmi.pcapng
```

### 4. Extract Frames to Images
Extract JPEG files from PCAP file:
```bash
python tools/extract_frames.py sample_capture.bin --output-dir extracted_frames
```

### 5. Run Network Diagnostics & PCAP Analysis
Analyze traffic breakdown and protocol statistics:
```bash
python tools/analyze_pcap.py sample_capture.bin
```
