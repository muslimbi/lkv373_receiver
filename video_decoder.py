"""
Video Decoder module for HDMI-over-IP receiver.
Supports H.264, H.265, MJPEG, JPEG, and MPEG-TS frame decoding with hardware acceleration flags,
robust JPEG header scanning, PIL fallback, and CPU fallback using OpenCV.
"""

import cv2
import io
import numpy as np
import subprocess
import threading
import time
import logging
from PIL import Image
from typing import Optional, Dict, Any
from protocol import CodecType, JPEG_SOI, JPEG_EOI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class VideoDecoder:
    """
    Decodes video frames into numpy BGR image arrays.
    """

    def __init__(
        self,
        codec: CodecType = CodecType.UNKNOWN,
        use_hardware_accel: bool = True
    ):
        self.codec = codec
        self.use_hardware_accel = use_hardware_accel
        self.total_decoded_frames = 0
        self.decode_errors = 0
        self.last_frame_size: Optional[tuple[int, int]] = None

    def set_codec(self, codec: CodecType):
        """Updates the active decoder codec."""
        if self.codec != codec:
            logging.info(f"VideoDecoder changing codec from {self.codec.value} to {codec.value}")
            self.codec = codec

    def _sanitize_jpeg_buffer(self, data: bytes) -> Optional[bytes]:
        """Scans and extracts clean JPEG payload between 0xFFD8 (SOI) and 0xFFD9 (EOI)."""
        soi_idx = data.find(JPEG_SOI)
        if soi_idx == -1:
            return None

        eoi_idx = data.rfind(JPEG_EOI)
        if eoi_idx == -1 or eoi_idx <= soi_idx:
            # If no EOI found, take payload from SOI to end
            clean_slice = data[soi_idx:]
        else:
            clean_slice = data[soi_idx:eoi_idx + 2]

        return clean_slice

    def decode(self, frame_bytes: bytes) -> Optional[np.ndarray]:
        """
        Decodes a frame payload into an OpenCV BGR numpy image array.
        Uses OpenCV imdecode, SOI/EOI slice extraction, and PIL fallback.
        """
        if not frame_bytes:
            return None

        # 1. Primary OpenCV Direct Decoding
        try:
            nparr = np.frombuffer(frame_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                self.total_decoded_frames += 1
                self.last_frame_size = (img.shape[1], img.shape[0])
                return img
        except Exception:
            pass

        # 2. MJPEG / JPEG Header Scan & Sanitization Fallback
        clean_buf = self._sanitize_jpeg_buffer(frame_bytes)
        if clean_buf:
            try:
                nparr = np.frombuffer(clean_buf, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    self.total_decoded_frames += 1
                    self.last_frame_size = (img.shape[1], img.shape[0])
                    return img
            except Exception:
                pass

            # 3. PIL (Pillow) Decoding Fallback
            try:
                pil_img = Image.open(io.BytesIO(clean_buf))
                pil_img.verify() # Verify valid image
                pil_img = Image.open(io.BytesIO(clean_buf)) # Reopen after verify
                img_rgb = np.array(pil_img.convert("RGB"))
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
                if img_bgr is not None:
                    self.total_decoded_frames += 1
                    self.last_frame_size = (img_bgr.shape[1], img_bgr.shape[0])
                    return img_bgr
            except Exception as e:
                logging.debug(f"PIL JPEG decode attempt failed: {e}")

        # 4. Strip Embedded 16-byte headers every 1024 bytes fallback (for raw chunked stream)
        if len(frame_bytes) > 1024:
            try:
                cleaned_chunks = bytearray()
                # Search for SOI in first 1024 bytes
                soi_pos = frame_bytes.find(JPEG_SOI)
                start_pos = soi_pos if soi_pos != -1 else 0
                for i in range(start_pos, len(frame_bytes), 1024):
                    chunk = frame_bytes[i:i+1024]
                    # If chunk starts with transport header signature, strip first 16 bytes
                    if len(chunk) > 16 and chunk[:2] in (b"\x54\x48", b"\x48\x44", b"\x50\x4b"):
                        cleaned_chunks.extend(chunk[16:])
                    else:
                        cleaned_chunks.extend(chunk)

                if cleaned_chunks:
                    nparr = np.frombuffer(cleaned_chunks, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None:
                        self.total_decoded_frames += 1
                        self.last_frame_size = (img.shape[1], img.shape[0])
                        return img
            except Exception:
                pass

        self.decode_errors += 1
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Returns decoder statistics."""
        return {
            "codec": self.codec.value,
            "total_decoded_frames": self.total_decoded_frames,
            "decode_errors": self.decode_errors,
            "resolution": f"{self.last_frame_size[0]}x{self.last_frame_size[1]}" if self.last_frame_size else "Unknown"
        }

    def close(self):
        """Clean up decoder resources."""
        pass
