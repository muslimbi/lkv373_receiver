"""
UDP Multicast Socket Receiver.

Handles joining multicast groups on specified network interfaces
and buffering incoming UDP packets in a thread-safe, bounded queue.
"""

import socket
import struct
import threading
import queue
import time
import logging

logger = logging.getLogger(__name__)


class MulticastReceiver:
    """
    Standard UDP Multicast Socket Receiver supporting Windows and Linux.
    Runs a dedicated background thread to read UDP packets into a bounded queue.
    """

    def __init__(
        self,
        group_ip: str = "226.2.2.2",
        port: int = 2068,
        interface_ip: str = "192.168.168.10",
        source_ip: str | None = None,
        buffer_size: int = 2097152,  # 2MB socket buffer
        queue_maxsize: int = 2000,
    ):
        self.group_ip = group_ip
        self.port = port
        self.interface_ip = interface_ip or "192.168.168.10"
        self.source_ip = source_ip
        self.buffer_size = buffer_size

        self.sock: socket.socket | None = None
        self.packet_queue: queue.Queue[tuple[bytes, str, float]] = queue.Queue(maxsize=queue_maxsize)
        self.running = False
        self.thread: threading.Thread | None = None
        self.dropped_queue_overflows = 0

    def start(self):
        """Initializes socket, joins multicast group, and starts receiver thread."""
        if self.running:
            return

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # Allow multiple sockets to bind to the same port
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except (AttributeError, OSError):
            pass

        # Windows-specific socket options
        try:
            if hasattr(socket, "SO_REUSEPORT"):
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass

        # Set receive buffer size
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.buffer_size)
        except OSError as e:
            logger.warning(f"Could not set socket buffer size to {self.buffer_size}: {e}")

        # Bind to port
        try:
            # On Windows, binding to '' or '0.0.0.0' works reliably for multicast
            self.sock.bind(("", self.port))
        except OSError as e:
            logger.error(f"Failed to bind UDP socket to port {self.port}: {e}")
            raise

        # Join Multicast Group
        try:
            mreq = struct.pack(
                "4s4s",
                socket.inet_aton(self.group_ip),
                socket.inet_aton(self.interface_ip),
            )
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            
            # Set multicast outgoing/IGMP interface (CRITICAL for Windows multi-homed systems)
            if self.interface_ip and self.interface_ip != "0.0.0.0":
                try:
                    local_addr = socket.inet_aton(self.interface_ip)
                    self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, local_addr)
                except OSError as e:
                    logger.warning(f"Failed to set IP_MULTICAST_IF on {self.interface_ip}: {e}")

            logger.info(
                f"Joined multicast group {self.group_ip}:{self.port} on interface {self.interface_ip}"
            )
        except OSError as e:
            logger.error(f"Failed to join multicast group {self.group_ip}: {e}")
            raise

        self.sock.settimeout(0.5)
        self.running = True
        self.thread = threading.Thread(target=self._recv_loop, daemon=True, name="MulticastRecvLoop")
        self.thread.start()

    def _recv_loop(self):
        """Background thread loop receiving packets from socket."""
        while self.running and self.sock:
            try:
                data, addr = self.sock.recvfrom(65535)
                recv_time = time.time()
                src_host = addr[0]

                if not hasattr(self, "_first_packet_logged"):
                    logger.info(
                        f"FIRST UDP PACKET RECEIVED from {src_host}:{addr[1]} ({len(data)} bytes)"
                    )
                    self._first_packet_logged = True

                # Optional source IP filter
                if self.source_ip and src_host != self.source_ip:
                    if not hasattr(self, "_mismatch_logged"):
                        logger.warning(
                            f"Received UDP packet from {src_host}:{addr[1]}, but source filter is set to {self.source_ip}! Dropping packet due to mismatch."
                        )
                        self._mismatch_logged = True
                    continue

                try:
                    self.packet_queue.put_nowait((data, src_host, recv_time))
                except queue.Full:
                    self.dropped_queue_overflows += 1
            except socket.timeout:
                continue
            except OSError:
                if not self.running:
                    break
                time.sleep(0.01)

    def get_packet(self, timeout: float | None = 0.05) -> tuple[bytes, str, float] | None:
        """Retrieves next packet from the queue."""
        try:
            return self.packet_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        """Stops the receiver thread and closes socket."""
        self.running = False
        if self.sock:
            try:
                # Leave multicast group
                mreq = struct.pack(
                    "4s4s",
                    socket.inet_aton(self.group_ip),
                    socket.inet_aton(self.interface_ip),
                )
                self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.thread = None
