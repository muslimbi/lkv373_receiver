"""
PCAP Traffic Analyzer Tool Wrapper.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lkv373_receiver.tools.analyze_pcap import main

if __name__ == "__main__":
    main()
