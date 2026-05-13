"""Backward-compatible entry point — delegates to dashboard/refresh_server.py."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Re-export everything from the canonical location
from dashboard.refresh_server import _Handler, _run_pipeline, _run_c1b_pipeline, PORT
from http.server import HTTPServer

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), _Handler)
    print(f"[refresh_server] Listening on :{PORT}")
    server.serve_forever()
