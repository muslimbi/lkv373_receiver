"""
Unit tests for MulticastReceiver.
"""

import pytest
from multicast_receiver import MulticastReceiver

def test_multicast_receiver_init():
    receiver = MulticastReceiver(group="226.2.2.2", port=2068, interface_ip="127.0.0.1")
    assert receiver.group == "226.2.2.2"
    assert receiver.port == 2068
    stats = receiver.get_stats()
    assert stats["total_packets"] == 0
    assert stats["total_bytes"] == 0
    assert stats["queue_size"] == 0
