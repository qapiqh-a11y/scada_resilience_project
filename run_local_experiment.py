import argparse
from datetime import datetime, timezone
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from loadgen import run
from metrics import calculate, format_result


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def wait_for(url, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"service did not become ready: {url}")


def fault_schedule(path, start, duration):
    time.sleep(start)
    path.write_text(json.dumps({"delay_ms": 2000}), encoding="utf-8")
    time.sleep(duration)
    path.write_text("{}", encoding="utf-8")


def stop_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def execute(mode, duration, rate, fault_start, fault_duration):
    RESULTS.mkdir(exist_ok=True)
    fault_file = RESULTS / "fault.json"
    fault_file.write_text("{}", encoding="utf-8")
    log_path = RESULTS / f"{mode}.log"
    csv_path = RESULTS / f"{mode}.csv"

    dep_env = os.environ.copy()
    dep_env["FAULT_FILE"] = str(fault_file)
    core_env = os.environ.copy()
    core_env.update(
        {
            "PATTERN": mode,
            "DEP_URL": "http://127.0.0.1:8001/work",
            "TIMEOUT_S": "1.0",
            "FAILURE_THRESHOLD": "3",
            "RECOVERY_TIMEOUT_S": "5.0",
        }
    )

    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"started_utc={datetime.now(timezone.utc).isoformat()}\n")
        log.write(
            f"mode={mode} duration_s={duration:g} rate_rps={rate:g} "
            f"fault_start_s={fault_start:g} fault_duration_s={fault_duration:g} "
            "fault_delay_ms=2000 client_timeout_s=1.5\n"
        )
        log.flush()
        dep = subprocess.Popen(
            [sys.executable, str(ROOT / "dep.py")],
            cwd=ROOT,
            env=dep_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        core = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py")],
            cwd=ROOT,
            env=core_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_for("http://127.0.0.1:8001/health")
            wait_for("http://127.0.0.1:8000/health")
            scheduler = threading.Thread(
                target=fault_schedule,
                args=(fault_file, fault_start, fault_duration),
                daemon=True,
            )
            scheduler.start()
            run(
                "http://127.0.0.1:8000/work",
                str(csv_path),
                duration=duration,
                rate=rate,
                timeout=1.5,
            )
            scheduler.join(timeout=fault_start + fault_duration + 5)
        finally:
            stop_process(core)
            stop_process(dep)
            fault_file.unlink(missing_ok=True)

    result = calculate(csv_path)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(format_result(result) + "\n")
    print(format_result(result))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["off", "on"])
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--fault-start", type=float, default=30.0)
    parser.add_argument("--fault-duration", type=float, default=30.0)
    args = parser.parse_args()
    execute(args.mode, args.duration, args.rate, args.fault_start, args.fault_duration)


if __name__ == "__main__":
    main()
