# LKV373 / Lenkeng HDMI-over-IP MJPEG Protocol Specification

## Protocol Overview

The LKV373 / Lenkeng HDMI-over-IP transmitter encapsulates HDMI video signals into raw Motion JPEG (MJPEG) frames transmitted over UDP multicast networks.

- **Multicast Group:** `226.2.2.2`
- **UDP Destination Port:** `2068` (Video Stream)
- **Audio Port:** `2066` (PCM Audio Stream)
- **Control Ports:** `UDP 2065 -> 2066` and `UDP 2067 -> 2067`
- **Observed Resolution:** `1280x1024` (or `1280x720` depending on input resolution)
- **Target Frame Rate:** ~30 FPS (33.3ms frame interval)
- **Video Codec:** JPEG / MJPEG (unencrypted)

---

## UDP Packet Structure

Each UDP video packet payload consists of a 4-byte encapsulation header followed by raw JPEG chunk data:

```
+-------------------+-------------------+-----------------------------------+
|  Byte 0 - Byte 1  |  Byte 2 - Byte 3  |          Byte 4 - End             |
|   Frame Number    |   Chunk Number    |         JPEG Chunk Data           |
| (uint16, big-end) | (uint16, big-end) | (Payload: 1000 - 1020 bytes typical)|
+-------------------+-------------------+-----------------------------------+
```

### Bit Flags & Chunk Indexing

- **Frame Number (Offset 0-1):** 16-bit big-endian sequence counter (`0x0000` to `0xFFFF`, rolling over to `0x0000`).
- **Chunk Number (Offset 2-3):** 16-bit big-endian integer.
  - **Bit 15 (`0x8000`):** End of Frame Marker Flag (`is_last = (chunk_number & 0x8000) != 0`).
  - **Bits 0-14 (`0x7FFF`):** 0-indexed Chunk Position (`chunk_index = chunk_number & 0x7FFF`).

---

## Frame Reassembly Workflow

1. **Packet Capture & Filtering:** Receive UDP packets on `226.2.2.2:2068`.
2. **Chunk Buffer Lookup:** Group chunks by `Frame Number` in active frame buffers.
3. **End Detection:** Identify final chunk via `0x8000` flag or sequence number advancement.
4. **Ordering & Concatenation:** Sort chunks by `chunk_index` (`0 .. total_chunks - 1`) and concatenate payloads starting at byte offset 4.
5. **JPEG Validation:**
   - **Start of Image (SOI):** Must start with bytes `0xFF 0xD8`.
   - **End of Image (EOI):** Must end with bytes `0xFF 0xD9` (trimming any trailing padding bytes).
6. **Direct Decoding & Rendering:** Decode valid JPEG byte array directly using OpenCV/PIL to display window without intermediate video container conversion.

---

## Audio & Control Streams

- **Audio (UDP 2066):** Carries uncompressed LPCM audio payload. Processed independently from the video pipeline.
- **Control Streams (UDP 2065 / 2067):** EDID handshaking and transmitter control telemetry.
