"""
PySide6 Real-Time Video Renderer and Window Manager.

Displays decoded MJPEG video frames with low latency, supporting:
- Fullscreen mode
- Multi-monitor / specific monitor targeting
- Interactive real-time diagnostic overlay (FPS, packet counters, loss, latency)
- Dynamic window resizing and scaling
"""

import sys
import time
import numpy as np
import cv2
import logging

from PySide6.QtCore import Qt, QTimer, Signal, Slot, QPoint
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QPen, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QWidget, QVBoxLayout

from ..diagnostics.statistics import StreamStatistics

logger = logging.getLogger(__name__)


class VideoDisplayWidget(QWidget):
    """
    Custom widget for hardware-accelerated QPainter frame rendering and HUD overlay.
    """

    def __init__(self, stats: StreamStatistics, parent=None):
        super().__init__(parent)
        self.stats = stats
        self.current_pixmap: QPixmap | None = None
        self.show_overlay: bool = True
        self.setMouseTracking(True)
        self.setMinimumSize(640, 480)

    def set_frame(self, image_bgr: np.ndarray):
        """Converts BGR NumPy array to QPixmap and triggers repaint."""
        h, w, ch = image_bgr.shape
        bytes_per_line = ch * w
        
        # Convert OpenCV BGR -> RGB QImage
        rgb_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        q_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.current_pixmap = QPixmap.fromImage(q_img)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fill background black
        painter.fillRect(self.rect(), Qt.black)

        # Render video pixmap scaled while maintaining aspect ratio
        if self.current_pixmap and not self.current_pixmap.isNull():
            scaled_pixmap = self.current_pixmap.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = (self.width() - scaled_pixmap.width()) // 2
            y = (self.height() - scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, scaled_pixmap)

        # Render HUD Diagnostic Overlay
        if self.show_overlay:
            self._draw_overlay(painter)

    def _draw_overlay(self, painter: QPainter):
        """Draws semi-transparent diagnostic statistics HUD."""
        summary = self.stats.get_summary_dict()

        lines = [
            f"LKV373 HDMI-over-IP Stream",
            f"Group: {summary['group']}:{summary['port']} ({summary['interface']})",
            f"Resolution: {summary['resolution']} @ {summary['fps']} FPS",
            f"Bitrate/Packets: {summary['pps']} pkts/s | Total: {summary['packets']:,}",
            f"Packet Loss: {summary['missing_chunks']} pkts ({summary['packet_loss_pct']}%)",
            f"Frame Loss: {summary['incomplete_frames']} frames ({summary['frame_loss_pct']}%)",
            f"Duplicates: {summary['duplicates']} | Out-of-Order: {summary['out_of_order']}",
            f"Current Frame #: {summary['current_frame']} | Decode: {summary['decode_latency_ms']} ms",
        ]

        font = QFont("Consolas", 10, QFont.Bold)
        painter.setFont(font)

        box_padding = 10
        line_height = 20
        box_width = 460
        box_height = len(lines) * line_height + box_padding * 2

        # Draw semi-transparent dark background card
        bg_color = QColor(15, 23, 42, 210)  # Dark slate blue
        border_color = QColor(56, 189, 248, 200)  # Cyan border

        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 1.5))
        painter.drawRoundedRect(15, 15, box_width, box_height, 8, 8)

        # Draw text lines
        text_color = QColor(241, 245, 249)
        highlight_color = QColor(56, 189, 248)

        for i, line in enumerate(lines):
            y_pos = 15 + box_padding + (i + 1) * line_height - 5
            if i == 0:
                painter.setPen(highlight_color)
            else:
                painter.setPen(text_color)
            painter.drawText(25, y_pos, line)


class MainWindow(QMainWindow):
    """
    Main Application Window for HDMI-over-IP Video Stream Display.
    """

    def __init__(
        self,
        stats: StreamStatistics,
        title: str = "LKV373 HDMI-over-IP Receiver",
        fullscreen: bool = False,
        monitor_index: int = 0,
    ):
        super().__init__()
        self.stats = stats
        self.setWindowTitle(title)
        self.resize(1280, 1024)

        self.display_widget = VideoDisplayWidget(stats, self)
        self.setCentralWidget(self.display_widget)

        # Keyboard shortcuts
        self.shortcut_fullscreen = QShortcut(QKeySequence("F11"), self)
        self.shortcut_fullscreen.activated.connect(self.toggle_fullscreen)

        self.shortcut_fullscreen_alt = QShortcut(QKeySequence("F"), self)
        self.shortcut_fullscreen_alt.activated.connect(self.toggle_fullscreen)

        self.shortcut_overlay = QShortcut(QKeySequence("D"), self)
        self.shortcut_overlay.activated.connect(self.toggle_overlay)

        # Set Monitor Display
        self.set_monitor(monitor_index)

        if fullscreen:
            self.showFullScreen()

    def set_monitor(self, monitor_index: int):
        """Positions window on specified monitor screen."""
        screens = QApplication.screens()
        if 0 <= monitor_index < len(screens):
            target_screen = screens[monitor_index]
            geom = target_screen.geometry()
            self.move(geom.x() + 50, geom.y() + 50)
            logger.info(f"Targeting monitor #{monitor_index}: {target_screen.name()} ({geom.width()}x{geom.height()})")

    @Slot()
    def toggle_fullscreen(self):
        """Toggles fullscreen state."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    @Slot()
    def toggle_overlay(self):
        """Toggles stats HUD overlay."""
        self.display_widget.show_overlay = not self.display_widget.show_overlay
        self.display_widget.update()

    def mouseDoubleClickEvent(self, event):
        """Double click toggles fullscreen."""
        self.toggle_fullscreen()

    def update_frame(self, image_bgr: np.ndarray):
        """Receives new decoded frame and updates display."""
        self.display_widget.set_frame(image_bgr)


class VideoRenderer:
    """
    High-level Video Renderer supporting PySide6 GUI Application
    with fallback to OpenCV highgui.
    """

    def __init__(
        self,
        stats: StreamStatistics,
        title: str = "LKV373 HDMI-over-IP Receiver",
        fullscreen: bool = False,
        monitor_index: int = 0,
        use_pyside: bool = True,
    ):
        self.stats = stats
        self.title = title
        self.fullscreen = fullscreen
        self.monitor_index = monitor_index
        self.use_pyside = use_pyside

        self.app: QApplication | None = None
        self.window: MainWindow | None = None

        if self.use_pyside:
            try:
                self.app = QApplication.instance() or QApplication(sys.argv)
                self.window = MainWindow(
                    stats=stats,
                    title=title,
                    fullscreen=fullscreen,
                    monitor_index=monitor_index,
                )
                self.window.show()
            except Exception as e:
                logger.warning(f"PySide6 initialization failed, falling back to OpenCV display: {e}")
                self.use_pyside = False

    def render_frame(self, image_bgr: np.ndarray):
        """Renders single video frame."""
        if self.use_pyside and self.window:
            self.window.update_frame(image_bgr)
            if self.app:
                self.app.processEvents()
        else:
            # OpenCV Fallback
            cv2.imshow(self.title, image_bgr)
            if self.fullscreen:
                cv2.setWindowProperty(self.title, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            cv2.waitKey(1)

    def close(self):
        """Closes display windows."""
        if self.use_pyside and self.window:
            self.window.close()
        else:
            cv2.destroyAllWindows()
