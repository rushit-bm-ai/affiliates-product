"""Lightweight HTTP API that triggers the recon pipeline from the dashboard UI.

Endpoints:
  POST /api/refresh         — start a pipeline run (202 started / 409 already_running)
  GET  /api/refresh-status  — current status (idle / running / success / error)

Runs on port 8765. Managed by refresh_server.service (systemd).
"""

import json
import os
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(BASE_DIR, "computed", "refresh_status.json")
C1B_STATUS_FILE = os.path.join(BASE_DIR, "computed", "c1b_refresh_status.json")
C1B_SCRIPT = os.path.join(BASE_DIR, "c1b", "c1b_dashboard.py")
PORT = 8765
IST = timezone(timedelta(hours=5, minutes=30))

_lock = threading.Lock()
_running = False

_c1b_lock = threading.Lock()
_c1b_running = False


def _now_ist():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")


def _write_status(data):
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f)


def _write_c1b_status(data):
    os.makedirs(os.path.dirname(C1B_STATUS_FILE), exist_ok=True)
    with open(C1B_STATUS_FILE, "w") as f:
        json.dump(data, f)


def _run_pipeline():
    global _running
    started = _now_ist()
    _write_status({"status": "running", "started_at": started, "finished_at": None})
    try:
        result = subprocess.run(
            ["python3", "run_recon.py"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        lines = (result.stdout + result.stderr).strip().splitlines()
        _write_status({
            "status": "success" if result.returncode == 0 else "error",
            "started_at": started,
            "finished_at": _now_ist(),
            "exit_code": result.returncode,
            "output_tail": "\n".join(lines[-8:]),
        })
    except Exception as e:
        _write_status({
            "status": "error",
            "started_at": started,
            "finished_at": _now_ist(),
            "error": str(e),
        })
    finally:
        with _lock:
            _running = False


def _run_c1b_pipeline():
    global _c1b_running
    started = _now_ist()
    _write_c1b_status({"status": "running", "started_at": started, "finished_at": None})
    try:
        result = subprocess.run(
            ["python3", C1B_SCRIPT],
            cwd=os.path.dirname(C1B_SCRIPT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        lines = (result.stdout + result.stderr).strip().splitlines()
        _write_c1b_status({
            "status": "success" if result.returncode == 0 else "error",
            "started_at": started,
            "finished_at": _now_ist(),
            "exit_code": result.returncode,
            "output_tail": "\n".join(lines[-8:]),
        })
    except Exception as e:
        _write_c1b_status({
            "status": "error",
            "started_at": started,
            "finished_at": _now_ist(),
            "error": str(e),
        })
    finally:
        with _c1b_lock:
            _c1b_running = False


class _Handler(BaseHTTPRequestHandler):
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/refresh":
            global _running
            with _lock:
                if _running:
                    self._json(409, {"status": "already_running"})
                    return
                _running = True
            threading.Thread(target=_run_pipeline, daemon=True).start()
            self._json(202, {"status": "started"})
        elif self.path == "/api/refresh-c1b":
            global _c1b_running
            with _c1b_lock:
                if _c1b_running:
                    self._json(409, {"status": "already_running"})
                    return
                _c1b_running = True
            threading.Thread(target=_run_c1b_pipeline, daemon=True).start()
            self._json(202, {"status": "started"})
        else:
            self._json(404, {"error": "not found"})

    def do_GET(self):
        if self.path == "/api/refresh-status":
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE) as f:
                    data = json.load(f)
            else:
                data = {"status": "idle"}
            self._json(200, data)
        elif self.path == "/api/c1b-refresh-status":
            if os.path.exists(C1B_STATUS_FILE):
                with open(C1B_STATUS_FILE) as f:
                    data = json.load(f)
            else:
                data = {"status": "idle"}
            self._json(200, data)
        else:
            self._json(404, {"error": "not found"})

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # suppress per-request access log


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), _Handler)
    print(f"[refresh_server] Listening on :{PORT}")
    server.serve_forever()
