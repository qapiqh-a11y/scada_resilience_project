import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


FIELDNAMES = [
    "elapsed_s",
    "http_code",
    "latency_ms",
    "response_status",
    "breaker",
    "error",
]


def request_once(url, timeout, started_at):
    request_started = time.monotonic()
    elapsed = request_started - started_at
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            code = response.status
        return {
            "elapsed_s": f"{elapsed:.3f}",
            "http_code": code,
            "latency_ms": f"{(time.monotonic() - request_started) * 1000:.1f}",
            "response_status": payload.get("status", "unknown"),
            "breaker": payload.get("breaker", ""),
            "error": "",
        }
    except urllib.error.HTTPError as error:
        code = error.code
        label = type(error).__name__
    except Exception as error:
        code = 0
        label = type(error).__name__
    return {
        "elapsed_s": f"{elapsed:.3f}",
        "http_code": code,
        "latency_ms": f"{(time.monotonic() - request_started) * 1000:.1f}",
        "response_status": "failed",
        "breaker": "",
        "error": label,
    }


def run(url, output, duration=120.0, rate=20.0, timeout=1.5, workers=80):
    started_at = time.monotonic()
    total = int(duration * rate)
    futures = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for index in range(total):
            target = started_at + index / rate
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            futures.append(executor.submit(request_once, url, timeout, started_at))
        rows = [future.result() for future in as_completed(futures)]
    rows.sort(key=lambda row: float(row["elapsed_s"]))
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/work")
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--timeout", type=float, default=1.5)
    parser.add_argument("--workers", type=int, default=80)
    args = parser.parse_args()
    rows = run(args.url, args.output, args.duration, args.rate, args.timeout, args.workers)
    print(f"output={args.output} requests={len(rows)}")


if __name__ == "__main__":
    main()
