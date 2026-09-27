"""
Audio stream subpackage for LKV373 UDP 2066 audio streams.
"""

from .audio_receiver import AudioReceiver, AudioPacket

__all__ = ["AudioReceiver", "AudioPacket"]
