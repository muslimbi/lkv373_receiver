"""
PacketParser compatibility wrapper.
"""
from lkv373_receiver.receiver.packet import VideoPacket, parse_packet

class PacketParser:
    def parse_packet(self, raw_bytes: bytes, timestamp: float = 0.0):
        return parse_packet(raw_bytes, timestamp)
