"""
Direct low-latency JPEG Decoder using OpenCV / Pillow.

Decodes raw reconstructed JPEG bytes directly to BGR / RGB NumPy arrays
without intermediary transcoding or external codecs.
"""

import time
import numpy as np
import cv2
from PIL import Image
import io
from dataclasses import dataclass


@dataclass
class DecodedFrame:
    """Represents a successfully decoded video frame."""
    frame_number: int
    image: np.ndarray        # BGR NumPy array (H, W, 3)
    width: int
    height: int
    decode_time_ms: float
    timestamp: float


class JPEGDecoder:
    """
    Direct low-latency JPEG decoder.
    """

    def __init__(self, use_opencv: bool = True):
        self.use_opencv = use_opencv
        self.total_decodes: int = 0
        self.decode_errors: int = 0

    def decode(self, jpeg_data: bytes, frame_number: int = 0, timestamp: float | None = None) -> DecodedFrame | None:
        """
        Decodes raw JPEG bytes into a DecodedFrame.
        
        Returns None if decoding fails.
        """
        if not jpeg_data:
            return None

        if timestamp is None:
            timestamp = time.time()

        start_time = time.perf_counter()

        image: np.ndarray | None = None
        try:
            if self.use_opencv:
                # Fast C++ JPEG decode via OpenCV
                np_arr = np.frombuffer(jpeg_data, dtype=np.uint8)
                image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            else:
                # Fallback to Pillow
                pil_img = Image.open(io.BytesIO(jpeg_data))
                rgb_arr = np.array(pil_img)
                image = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
        except Exception:
            image = None

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        if image is None or image.size == 0:
            self.decode_errors += 1
            return None

        h, w = image.shape[:2]
        self.total_decodes += 1

        return DecodedFrame(
            frame_number=frame_number,
            image=image,
            width=w,
            height=h,
            decode_time_ms=elapsed_ms,
            timestamp=timestamp,
        )
