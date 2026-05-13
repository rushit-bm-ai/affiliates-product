"""Backward-compatible entry point — delegates to recon/run.py."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from recon.run import main

if __name__ == "__main__":
    main()
