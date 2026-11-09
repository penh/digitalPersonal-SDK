#!/usr/bin/env python3
"""
Zero-Dependency Python HTTP & Web Server for DigitalPersona 4500.
Uses Python's standard library `http.server` (NO extra pip installs required!).
Provides:
  - REST API for JavaScript (`/health`, `/scan`, `/enroll`, `/verify`, `/identify`)
  - Full CORS support for browser frontends (React, Vue, Vanilla JS)
  - Serves `web_client.html` and `dp4500-client.js` directly

Run:
  python3 examples/http_server.py
  (or with simulation: python3 examples/http_server.py --mock)
Then open http://127.0.0.1:8000 in your browser!
"""

import sys
import os
import json
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dp4500 import UareU4500, ReaderManager, FingerprintTemplate
from dp4500.backends.mock import MockBackend

# Global configuration
USE_MOCK = "--mock" in sys.argv
READER_BACKEND = MockBackend() if USE_MOCK else None
PORT = int(os.environ.get("PORT", 8000))

# PyInstaller bundle support
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BUNDLE_DIR = Path(sys._MEIPASS)
    EXAMPLES_DIR = BUNDLE_DIR / "examples" if (BUNDLE_DIR / "examples").exists() else BUNDLE_DIR
else:
    EXAMPLES_DIR = Path(__file__).resolve().parent


class BiometricHTTPRequestHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """Respond to CORS preflight requests."""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Serve status or frontend assets."""
        path = self.path.split("?")[0]

        if path in ("", "/", "/index.html"):
            # Serve the web client HTML demo
            html_file = EXAMPLES_DIR / "web_client.html"
            if html_file.exists():
                content = html_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(content)
                return

        elif path in ("/dp4500-client.js", "/examples/dp4500-client.js"):
            js_file = EXAMPLES_DIR / "dp4500-client.js"
            if js_file.exists():
                content = js_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(content)
                return

        elif path == "/health":
            try:
                backend = READER_BACKEND
                devs = ReaderManager.list_readers() if not USE_MOCK else MockBackend().list_devices()
                data = [
                    {
                        "name": d.name,
                        "driver": d.driver,
                        "device_id": d.device_id,
                        "vendor_id": f"0x{d.vendor_id:04x}",
                        "product_id": f"0x{d.product_id:04x}",
                    }
                    for d in devs
                ]
                self._send_json(200, data)
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        """Handle fingerprint capture, enrollment, verification, identification."""
        path = self.path.split("?")[0]
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            req = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            req = {}

        try:
            if path == "/scan":
                print("[USB Device] Received /scan request -> activating scanner...")
                with UareU4500(backend=READER_BACKEND) as reader:
                    print(f"[USB Device] Reader '{reader.name}' open. Red light ON. Waiting for finger...")
                    img = reader.capture(wait_for_finger=True, timeout_ms=25000)
                    print(f"[USB Device] Capture successful! Image: {img.width}x{img.height} @ {img.dpi} DPI")
                    self._send_json(200, {
                        "width": img.width,
                        "height": img.height,
                        "dpi": img.dpi,
                        "quality_score": img.quality_score,
                        "image_base64": f"data:image/png;base64,{img.to_base64(format='PNG')}",
                    })

            elif path == "/enroll":
                username = req.get("username", "user")
                finger_name = req.get("finger_name", "right_index")
                stages = int(req.get("stages", 5))

                print(f"[USB Device] Received /enroll request for '{username}' ({stages} touches)...")
                with UareU4500(backend=READER_BACKEND) as reader:
                    tpl = reader.enroll(
                        stages=stages,
                        username=username,
                        finger_name=finger_name,
                        timeout_ms=30000,
                    )
                    print(f"[USB Device] Enrollment complete for '{username}'.")
                    self._send_json(200, {
                        "username": username,
                        "finger_name": finger_name,
                        "template_base64": tpl.to_base64(),
                        "template_size": tpl.size,
                    })

            elif path == "/verify":
                b64_tpl = req.get("template_base64")
                if not b64_tpl:
                    self._send_json(400, {"error": "Missing 'template_base64' in request body"})
                    return

                tpl = FingerprintTemplate.from_base64(b64_tpl)
                print(f"[USB Device] Received /verify request for user '{tpl.username or 'unknown'}'...")
                with UareU4500(backend=READER_BACKEND) as reader:
                    print("[USB Device] Reader active. Place finger to verify...")
                    res = reader.verify(tpl, timeout_ms=25000)
                    print(f"[USB Device] Verification result: {res.matched} (Score: {res.score:.2f})")
                    self._send_json(200, {
                        "matched": res.matched,
                        "score": round(res.score, 4),
                        "details": res.details,
                    })

            elif path == "/identify":
                candidates_raw = req.get("candidates", [])
                if not candidates_raw:
                    self._send_json(400, {"error": "Missing 'candidates' array"})
                    return

                templates = []
                user_ids = []
                for c in candidates_raw:
                    templates.append(FingerprintTemplate.from_base64(c["template_base64"]))
                    user_ids.append(c["user_id"])

                with UareU4500(backend=READER_BACKEND) as reader:
                    res = reader.identify(templates)
                    matched_user = user_ids[res.index] if res.matched and res.index is not None else None
                    self._send_json(200, {
                        "matched": res.matched,
                        "user_id": matched_user,
                        "score": round(res.score, 4),
                    })

            else:
                self._send_json(404, {"error": f"Unknown endpoint: {path}"})

        except Exception as e:
            self._send_json(500, {"detail": str(e)})


class BiometricServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main():
    server = BiometricServer(("127.0.0.1", PORT), BiometricHTTPRequestHandler)
    mode = "MOCK (Simulation)" if USE_MOCK else "PHYSICAL USB HARDWARE (libfprint 05ba:000a)"
    print("=" * 65)
    print(f" DigitalPersona 4500 - Biometric Server running on:")
    print(f"  👉 Web Console: http://127.0.0.1:{PORT}")
    print(f"  👉 REST API:     http://127.0.0.1:{PORT}/health, /scan, /enroll...")
    print(f"  Device Mode:     {mode}")
    if not USE_MOCK:
        print("  Notice:          Physical scanner red optical light will turn ON")
        print("                   whenever a scan, enroll, or verify request runs!")
    print("=" * 65)
    print("Ready and listening. Press Ctrl+C to stop.")

    if "--no-browser" not in sys.argv and not os.environ.get("HEADLESS"):
        import webbrowser
        import threading
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    main()
