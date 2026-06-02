"""Tiny local webhook receiver for testing alert pushes.

Listens on a port and writes each received POST body to data/last_webhook.json,
so you can verify the alert payload end-to-end without a real Make.com/Slack URL.

    python scripts/local_webhook_receiver.py --port 9099
"""

from __future__ import annotations

import argparse
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "last_webhook.json"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(body)
        print(f"[receiver] captured {len(body)} bytes -> {OUT}", flush=True)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9099)
    args = ap.parse_args()
    print(f"[receiver] listening on http://127.0.0.1:{args.port}/hook", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
