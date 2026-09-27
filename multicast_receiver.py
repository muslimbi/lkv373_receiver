"""
Multicast UDP Receiver module for HDMI-over-IP streams.
Handles IPv4 multicast group joining, socket configuration, packet reception thread,
bounded queueing, and real-time network diagnostic statistics.
"""

import socket
import struct
import sys
import time
import threading
import queue
import logging
from typing import Optional, Tuple, Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class MulticastReceiver:
    """
    High-performance IPv4 Multicast UDP Receiver.
    Default HDMI Receiver IP: 192.168.168.10
    """

    def __init__(
        self,
        group: str = "226.2.2.2",
        port: int = 2068,
        interface_ip: str = "192.168.168.10",
        buffer_size_mb: int = 8,
        max_queue_size: int = 5000
    ):
        self.group = group
        self.port = port
        self.interface_ip = interface_ip
        self.buffer_size = buffer_size_mb * 1024 * 1024
        self.max_queue_size = max_queue_size

        self.socket: Optional[socket.socket] = None
        self.packet_queue: queue.Queue[Tuple[bytes, float]] = queue.Queue(maxsize=max_queue_size)
        self.running = False
        self.receiver_thread: Optional[threading.Thread] = None

        # Network Statistics
        self.stats_lock = threading.Lock()
        self.reset_stats()

    def reset_stats(self):
        with self.stats_lock:
            self.total_packets = 0
            self.total_bytes = 0
            self.dropped_queue_packets = 0
            self.start_time = time.time()
            self.last_stat_time = time.time()
            self.last_byte_count = 0
            self.current_mbps = 0.0
            self.current_pps = 0.0

    def _create_multicast_socket(self) -> socket.socket:
        """Configures and binds cross-platform multicast socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # Allow reuse of local addresses & ports
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass

        # Set Receive Buffer Size to prevent OS kernel drop under high bitrate
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.buffer_size)
        except OSError as e:
            logging.warning(f"Could not set SO_RCVBUF to {self.buffer_size} bytes: {e}")

        # Bind socket to port.
        bind_addr = "" if sys.platform.startswith("win") else self.group
        sock.bind((bind_addr, self.port))

        # Join Multicast Group on interface_ip (fallback to 0.0.0.0 if interface IP not bound locally)
        joined = False
        target_if = self.interface_ip
        try:
            mreq = struct.pack("4s4s", socket.inet_aton(self.group), socket.inet_aton(target_if))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            joined = True
            logging.info(f"Successfully joined multicast group {self.group}:{self.port} on interface {target_if}")
        except OSError as e:
            logging.warning(f"Could not join multicast on specified interface {target_if}: {e}. Falling back to 0.0.0.0")

        if not joined:
            try:
                mreq = struct.pack("4s4s", socket.inet_aton(self.group), socket.inet_aton("0.0.0.0"))
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                self.interface_ip = "0.0.0.0"
                logging.info(f"Joined multicast group {self.group}:{self.port} on fallback interface 0.0.0.0")
            except OSError as e:
                logging.error(f"Failed to join multicast group {self.group} on 0.0.0.0: {e}")
                raise

        # Set socket timeout so thread can periodically check running status
        sock.settimeout(1.0)
        return sock

    def start(self):
        """Starts the multicast receiver background thread."""
        if self.running:
            logging.warning("MulticastReceiver is already running.")
            return

        logging.info(f"Joining multicast group {self.group}:{self.port} (Receiver IP: {self.interface_ip})...")
        self.socket = self._create_multicast_socket()
        self.running = True
        self.reset_stats()

        self.receiver_thread = threading.Thread(target=self._receive_loop, daemon=True, name="MulticastRxThread")
        self.receiver_thread.start()
        logging.info("Multicast receiver thread started successfully.")

    def _receive_loop(self):
        """Background thread loop for receiving UDP packets."""
        while self.running and self.socket:
            try:
                data, addr = self.socket.recvfrom(65535)
                rx_time = time.time()
                if not data:
                    continue

                with self.stats_lock:
                    self.total_packets += 1
                    self.total_bytes += len(data)
                    self.last_sender_ip = addr[0]

                # Push to non-blocking queue
                try:
                    self.packet_queue.put_nowait((data, rx_time))
                except queue.Full:
                    with self.stats_lock:
                        self.dropped_queue_packets += 1

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logging.error(f"Error receiving multicast socket packet: {e}")
                break

    def get_packet(self, timeout: float = 0.1) -> Optional[Tuple[bytes, float]]:
        """Retrieves next packet from queue (blocking with timeout)."""
        try:
            return self.packet_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Calculates and returns current network receiver statistics."""
        with self.stats_lock:
            now = time.time()
            dt = now - self.last_stat_time
            if dt >= 0.5:
                bytes_diff = self.total_bytes - self.last_byte_count
                self.current_mbps = (bytes_diff * 8) / (dt * 1e6)
                self.current_pps = self.total_packets / max(1.0, now - self.start_time)
                self.last_stat_time = now
                self.last_byte_count = self.total_bytes

            return {
                "total_packets": self.total_packets,
                "total_bytes": self.total_bytes,
                "queue_size": self.packet_queue.qsize(),
                "dropped_queue_packets": self.dropped_queue_packets,
                "mbps": round(self.current_mbps, 2),
                "pps": int(self.current_pps),
                "group": self.group,
                "port": self.port,
                "interface": self.interface_ip,
                "sender_ip": getattr(self, "last_sender_ip", "192.168.168.55")
            }

    def stop(self):
        """Stops the receiver thread and leaves multicast group gracefully."""
        if not self.running:
            return
        logging.info("Stopping multicast receiver...")
        self.running = False

        if self.socket:
            try:
                mreq = struct.pack("4s4s", socket.inet_aton(self.group), socket.inet_aton(self.interface_ip))
                self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
            except Exception:
                pass
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

        if self.receiver_thread and self.receiver_thread.is_alive():
            self.receiver_thread.join(timeout=2.0)
        logging.info("Multicast receiver stopped.")
