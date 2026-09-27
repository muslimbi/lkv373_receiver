# Installation & Setup Guide

## System Requirements
- **Operating System**: Windows 10/11 or Linux (Ubuntu 20.04+)
- **Python Version**: Python 3.9+ (Python 3.13 recommended)
- **FFmpeg**: Installed and accessible on system PATH

---

## Python Environment Setup

1. **Clone or Open Project Directory**:
   ```cmd
   cd /d d:\hdmi
   ```

2. **Install Required Python Packages**:
   ```cmd
   pip install numpy opencv-python pytest pillow psutil ffmpy
   ```

3. **Verify FFmpeg Installation**:
   ```cmd
   ffmpeg -version
   ```

---

## Network Adapter Configuration (Standard Multicast LAN)

*Note: No VLAN tagging is required for standard operation.*

### Windows:
1. Open **Network Connections** (`ncpa.cpl`).
2. Select the Ethernet interface connected to the HDMI network.
3. Configure static IP address for the HDMI Receiver:
   - **IP Address**: `192.168.168.10`
   - **Subnet Mask**: `255.255.255.0`

### Linux:
```bash
# Configure receiver IP address on standard network interface
sudo ip addr add 192.168.168.10/24 dev eth0
sudo ip link set dev eth0 up

# Add multicast route
sudo ip route add 226.2.2.2 dev eth0
```
