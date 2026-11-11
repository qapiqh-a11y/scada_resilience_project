import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import core

PORT = int(os.getenv("CORE_PORT", "8000"))


class Handler(BaseHTTPRequestHandler):
    def send_json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self):
        if self.path == "/health":
            state = core.breaker.snapshot()
            self.send_json(200, {"status": "ok", "breaker": state["state"]})
            return
        if self.path != "/work":
            self.send_json(404, {"status": "not_found"})
            return
        try:
            self.send_json(200, core.do_work())
        except Exception as error:
            self.send_json(503, {"status": "error", "error": type(error).__name__})

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
