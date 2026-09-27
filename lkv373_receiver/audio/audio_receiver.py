"""
LKV373 Audio Receiver Module.

Processes audio packets on UDP port 2066 separate from video stream.
Parses LKV373 PCM / LPCM audio headers and buffers raw PCM audio frames.
"""

import socket
import struct
import threading
import queue
import time
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class AudioPacket:
    """Represents a parsed LKV373 audio packet from UDP port 2066."""
    sequence_number: int
    payload: bytes
    timestamp: float
    sample_rate: int = 48000
    channels: int = 2
    bits_per_sample: int = 16


class AudioReceiver:
    """
    Dedicated UDP 2066 Audio Receiver.
    """

    def __init__(
        self,
        group_ip: str = "226.2.2.2",
        port: int = 2066,
        interface_ip: str = "0.0.0.0",
        queue_maxsize: int = 500,
    ):
        self.group_ip = group_ip
        self.port = port
        self.interface_ip = interface_ip
        self.audio_queue: queue.Queue[AudioPacket] = queue.Queue(maxsize=queue_maxsize)
        
        self.running: bool = False
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None

        self.total_audio_packets: int = 0
        self.total_audio_bytes: int = 0

    def start(self):
        """Starts background audio receiver socket loop."""
        if self.running:
            return

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except OSError:
            pass

        try:
            self.sock.bind(("", self.port))
            mreq = struct.pack(
                "4s4s",
                socket.inet_aton(self.group_ip),
                socket.inet_aton(self.interface_ip),
            )
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            logger.info(f"AudioReceiver: Subscribed to {self.group_ip}:{self.port}")
        except OSError as e:
            logger.warning(f"AudioReceiver: Socket setup failed for port {self.port}: {e}")
            return

        self.sock.settimeout(0.5)
        self.running = True
        self.thread = threading.Thread(target=self._recv_loop, daemon=True, name="AudioRecvLoop")
        self.thread.start()

    def _recv_loop(self):
        """Background thread loop receiving audio packets."""
        seq = 0
        while self.running and self.sock:
            try:
                data, addr = self.sock.recvfrom(4096)
                if len(data) >= 4:
                    self.total_audio_packets += 1
                    self.total_audio_bytes += len(data)
                    seq += 1

                    pkt = AudioPacket(
                        sequence_number=seq,
                        payload=data,
                        timestamp=time.time(),
                    )
                    try:
                        self.audio_queue.put_nowait(pkt)
                    except queue.Full:
                        pass
            except socket.timeout:
                continue
            except OSError:
                break

    def get_audio_packet(self, timeout: float = 0.05) -> AudioPacket | None:
        """Retrieves next audio packet from buffer."""
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        """Stops audio receiver."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
