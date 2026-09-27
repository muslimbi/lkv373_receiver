"""
Video Viewer module for HDMI-over-IP receiver.
Supports Mode 1 (Windowed Viewer) and Mode 2 (Fullscreen HDMI output to monitor),
with low-latency rendering, interactive HUD stats overlay, and keyboard shortcuts.
"""

import cv2
import time
import numpy as np
from typing import Optional, Dict, Any

class VideoViewer:
    """
    Real-time video renderer and display manager.
    """

    def __init__(
        self,
        window_name: str = "HDMI-over-IP Receiver",
        width: int = 1280,
        height: int = 720,
        fullscreen: bool = False,
        show_hud: bool = True
    ):
        self.window_name = window_name
        self.width = width
        self.height = height
        self.fullscreen = fullscreen
        self.show_hud = show_hud

        self.last_frame_time = time.time()
        self.fps_alpha = 0.1
        self.current_fps = 0.0
        self.frame_count = 0
        self.is_running = True

        self._init_window()

    def _init_window(self):
        """Initializes the rendering window."""
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, self.width, self.height)
        if self.fullscreen:
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    def toggle_fullscreen(self):
        """Toggles between windowed and fullscreen display modes."""
        self.fullscreen = not self.fullscreen
        val = cv2.WINDOW_FULLSCREEN if self.fullscreen else cv2.WINDOW_NORMAL
        cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, val)
        if not self.fullscreen:
            cv2.resizeWindow(self.window_name, self.width, self.height)

    def toggle_hud(self):
        """Toggles stats HUD overlay."""
        self.show_hud = not self.show_hud

    def render(self, frame: np.ndarray, stats: Optional[Dict[str, Any]] = None) -> bool:
        """
        Renders a decoded video frame to screen with stats overlay.
        Returns False if user requested application exit (Q/ESC), True otherwise.
        """
        if frame is None:
            return self.is_running

        # Calculate FPS
        now = time.time()
        dt = now - self.last_frame_time
        self.last_frame_time = now
        if dt > 0:
            inst_fps = 1.0 / dt
            self.current_fps = (1 - self.fps_alpha) * self.current_fps + self.fps_alpha * inst_fps
        self.frame_count += 1

        rendered_frame = frame.copy()

        # Draw HUD stats overlay if enabled
        if self.show_hud:
            self._draw_hud(rendered_frame, stats)

        cv2.imshow(self.window_name, rendered_frame)

        # Handle Keyboard Input
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord('q'), ord('Q')): # ESC or Q
            self.is_running = False
            return False
        elif key in (ord('f'), ord('F')):
            self.toggle_fullscreen()
        elif key in (ord('s'), ord('S')):
            self.toggle_hud()

        return True

    def _draw_hud(self, img: np.ndarray, stats: Optional[Dict[str, Any]]):
        """Overlay performance statistics on frame."""
        h, w, _ = img.shape

        lines = [
            f"HDMI-over-IP Receiver | {w}x{h} @ {self.current_fps:.1f} FPS",
        ]

        if stats:
            if "codec" in stats:
                lines.append(f"Src: {stats.get('sender_ip', '192.168.168.55')}:2068 -> {stats.get('codec')}")
                lines.append(f"Encap: {stats.get('encapsulation', 'UDP')}")
            if "mbps" in stats:
                lines.append(f"Bitrate: {stats['mbps']} Mbps | Rate: {stats.get('pps', 0)} pps")
            if "total_packets" in stats:
                lines.append(f"Packets Rx: {stats['total_packets']} | Drops: {stats.get('dropped_packets', 0)}")
            if "latency_ms" in stats:
                lines.append(f"Est Latency: {stats['latency_ms']:.1f} ms")

        lines.append("Shortcuts: [F] Fullscreen | [S] Toggle HUD | [Q] Quit")

        # Draw semi-transparent background overlay box
        overlay_height = 25 * len(lines) + 15
        cv2.rectangle(img, (10, 10), (520, 10 + overlay_height), (0, 0, 0), cv2.FILLED)

        # Draw text lines
        y_pos = 32
        for line in lines:
            cv2.putText(
                img,
                line,
                (20, y_pos),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                1,
                cv2.LINE_AA
            )
            y_pos += 24

    def close(self):
        """Closes OpenCV window."""
        self.is_running = False
        cv2.destroyWindow(self.window_name)
        cv2.destroyAllWindows()
