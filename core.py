import json
import os
import threading
import time
import urllib.request

PATTERN = os.getenv("PATTERN", "off").lower() == "on"
DEP_URL = os.getenv("DEP_URL", "http://127.0.0.1:8001/work")
TIMEOUT_S = float(os.getenv("TIMEOUT_S", "1.0"))
FAILURE_THRESHOLD = int(os.getenv("FAILURE_THRESHOLD", "3"))
RECOVERY_TIMEOUT_S = float(os.getenv("RECOVERY_TIMEOUT_S", "5.0"))


class CircuitBreaker:
    """Thread-safe Circuit Breaker with one probe in HALF_OPEN."""

    def __init__(self, threshold=FAILURE_THRESHOLD, recovery_timeout=RECOVERY_TIMEOUT_S):
        if threshold < 1:
            raise ValueError("threshold must be at least 1")
        self.threshold = threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state = "CLOSED"
        self.opened_at = 0.0
        self.half_open_probe_inflight = False
        self.lock = threading.Lock()

    def allow_request(self):
        with self.lock:
            if self.state == "CLOSED":
                return True
            if self.state == "HALF_OPEN":
                return False
            if time.monotonic() - self.opened_at < self.recovery_timeout:
                return False
            self.state = "HALF_OPEN"
            self.half_open_probe_inflight = True
            return True

    def success(self):
        with self.lock:
            self.failures = 0
            self.state = "CLOSED"
            self.half_open_probe_inflight = False

    def failure(self):
        with self.lock:
            self.failures += 1
            if self.state == "HALF_OPEN" or self.failures >= self.threshold:
                self.state = "OPEN"
                self.opened_at = time.monotonic()
                self.half_open_probe_inflight = False

    def snapshot(self):
        with self.lock:
            return {"state": self.state, "failures": self.failures}


breaker = CircuitBreaker()


def call_dep(timeout=10.0):
    with urllib.request.urlopen(DEP_URL, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def degraded_response(state=None):
    current = state or breaker.snapshot()["state"]
    return {
        "status": "degraded",
        "control": "manual",
        "breaker": current,
    }


def do_work():
    if not PATTERN:
        return call_dep()
    if not breaker.allow_request():
        return degraded_response()
    try:
        result = call_dep(timeout=TIMEOUT_S)
        breaker.success()
        result["breaker"] = "CLOSED"
        return result
    except Exception:
        breaker.failure()
        return degraded_response()
