import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FAULT_FILE = os.getenv("FAULT_FILE", "/tmp/scada/fault.json")
PORT = int(os.getenv("DEP_PORT", "8001"))


def read_fault():
    try:
        with open(FAULT_FILE, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


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
            self.send_json(200, {"status": "ok"})
            return
        if self.path != "/work":
            self.send_json(404, {"status": "not_found"})
            return

        fault = read_fault()
        time.sleep(float(fault.get("delay_ms", 0)) / 1000)
        code = int(fault.get("http_code", 200))
        if code >= 500:
            self.send_json(code, {"status": "dependency_error"})
            return
        self.send_json(200, {"status": "ok", "command": "accepted"})

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
