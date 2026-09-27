# Multicast & Video Receiver Troubleshooting Guide

## Diagnostic Steps for Common Issues

### Issue 1: No Packets Received (`0 pps`, `0 Mbps`)

#### Root Causes & Fixes:
1. **Wrong Network Interface**:
   - Explicitly specify your local HDMI Receiver network interface IP address:
     ```cmd
     python hdmi_receiver.py --interface 192.168.168.10
     ```
2. **Windows Firewall Blocking Multicast**:
   - Allow Python through Windows Defender Firewall or execute in Administrator PowerShell:
     ```powershell
     New-NetFirewallRule -DisplayName "HDMI Receiver Multicast" -Direction Inbound -Protocol UDP -LocalPort 2068 -Action Allow
     ```
3. **IGMP / Multicast Snooping Issues**:
   - Verify network switch supports IGMP snooping and multicast forwarding for group `226.2.2.2`.

---

## Useful Diagnostic Commands

### Windows:
```cmd
# List network interfaces and IP addresses
ipconfig /all

# Display active IPv4 routes and multicast group routing
route print

# Check active UDP listening ports
netstat -ano -p udp
```

### Linux:
```bash
# Check interface IP addresses and VLAN status
ip addr show

# Check joined multicast groups
ip maddr show

# Capture live UDP packets with tcpdump
sudo tcpdump -i eth0 udp port 2068 -X -c 10
```

---

## Diagnostic Tools Included in Project

```cmd
# 1. Analyze packet capture file
python tools/analyze_pcap.py capture.bin

# 2. Inspect raw packet headers and payload entropy
python tools/inspect_payload.py capture.bin --count 5

# 3. Perform automated codec signature detection
python tools/detect_codec.py capture.bin

# 4. Extract reassembled video frames to disk
python tools/dump_frames.py capture.bin --output-dir extracted_frames

# 5. Run mock HDMI transmitter simulator (for offline testing)
python tools/simulate_transmitter.py --fps 30
```
