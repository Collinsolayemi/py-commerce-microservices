#!/usr/bin/env python3
"""Dependency-free local storefront and same-origin API proxy.

Run from any directory: python3 frontend/server.py
Override PORT (default 3000), USER_SERVICE_URL, PRODUCT_SERVICE_URL,
and ORDER_SERVICE_URL to target another local service setup.
"""
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SERVICES = {
    "users": os.environ.get("USER_SERVICE_URL", "http://127.0.0.1:8001").rstrip("/"),
    "products": os.environ.get("PRODUCT_SERVICE_URL", "http://127.0.0.1:8002").rstrip("/"),
    "orders": os.environ.get("ORDER_SERVICE_URL", "http://127.0.0.1:8003").rstrip("/"),
}
MAX_BODY_BYTES = 1_048_576


class StorefrontHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self.proxy()
        # Only serve the web assets, never local configuration, Python, or test files.
        path = urlsplit(self.path).path
        if path not in ("/", "/index.html", "/styles.css", "/app.js", "/api.js", "/store.js", "/motion.js") and not path.startswith("/assets/"):
            return self.send_error(404)
        if ".." in path or "%" in path or "\\" in path:
            return self.send_error(404)
        return super().do_HEAD() if self.command == "HEAD" else super().do_GET()

    def do_HEAD(self):
        # Route through the same allowlist; a HEAD request must not expose extra files.
        return self.do_GET()

    def do_POST(self):
        return self.proxy()

    def do_PATCH(self):
        return self.proxy()

    def do_DELETE(self):
        return self.proxy()

    def json_error(self, code, message):
        payload = json.dumps({"detail": message}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def proxy(self):
        path = self.path.removeprefix("/api")
        service = urlsplit(path).path.strip("/").split("/")[0]
        if not self.path.startswith("/api/") or service not in SERVICES:
            return self.json_error(404, "Unknown API route.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.json_error(400, "Invalid request size.")
        if length < 0 or length > MAX_BODY_BYTES:
            return self.json_error(413, "Request is too large.")
        headers = {key: self.headers[key] for key in ("Authorization", "Content-Type", "Accept") if key in self.headers}
        request = Request(SERVICES[service] + path, data=self.rfile.read(length) if length else None, method=self.command, headers=headers)
        try:
            with urlopen(request, timeout=12) as response:
                return self.forward(response.status, response.headers, response.read())
        except HTTPError as error:
            return self.forward(error.code, error.headers, error.read())
        except (URLError, TimeoutError, OSError):
            return self.json_error(502, f"The {service} service is unavailable. Start the backend services and try again.")

    def forward(self, status, headers, data):
        self.send_response(status)
        for key in ("Content-Type", "WWW-Authenticate"):
            if headers.get(key):
                self.send_header(key, headers[key])
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    host = os.environ.get("HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), StorefrontHandler)
    print(f"FORME storefront: http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
