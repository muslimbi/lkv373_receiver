# HDMI-over-IP Encapsulation & Hardware Specification

## Hardware Overview: NTI ST-IPHD-LC Series
- **Local Unit (Transmitter)**: HDMI Input -> MJPEG Encoder -> 1000Mbps RJ45 Gigabit Ethernet
- **Remote Unit (Receiver)**: 1000Mbps RJ45 Gigabit Ethernet -> MJPEG Decoder -> HDMI Output
- **Max Bit Rate**: 80 Mbps
- **Encoding Latency**: 33 ms at 30 FPS
- **Supported Input Resolutions**: `480i@60Hz, 480p@60Hz, 576i@50Hz, 576p@50Hz, 720p@50/60Hz, 1080i@50/60Hz, 1080p@50/60Hz`
- **Supported Output Resolutions**: `480p@60Hz, 576p@50Hz, 720p@50/60Hz, 1080p@50/60Hz`

---

## Encapsulation Protocol (HDbitT / Lenkeng Standard)

- **Header Length**: 16 Bytes
- **Header Layout**:
  - `0x00 - 0x01`: Magic Identifier (`"TH"` / `0x5448`, `"HD"` / `0x4844`, or `"PK"` / `0x504B`)
  - `0x02 - 0x03`: Packet Type Flags (Big-endian uint16, `0x0001` = Video Data)
  - `0x04 - 0x07`: Frame Counter (Big-endian uint32)
  - `0x08 - 0x0B`: Packet Sequence Index within Frame (Big-endian uint32, starting at 0)
  - `0x0C - 0x0F`: Reserved / Timestamp (Big-endian uint32)
- **Payload**: Raw Motion-JPEG (MJPEG) Video Chunk (1008 bytes)
- **Frame Boundaries**:
  - Start of Frame: Packet Index `0` + `0xFFD8` JPEG SOI header
  - End of Frame: `0xFFD9` JPEG EOI trailer
