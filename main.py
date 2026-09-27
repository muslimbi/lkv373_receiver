"""
LKV373 / Lenkeng HDMI-over-IP Receiver Root Entrypoint.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from lkv373_receiver.main import main

if __name__ == "__main__":
    main()
