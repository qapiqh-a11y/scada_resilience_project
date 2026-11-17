import csv
import json
import math
import statistics
import sys


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)] if ordered else 0


def observation_duration(rows):
    if not rows:
        return 0
    times = sorted({float(row["elapsed_s"]) for row in rows})
    if len(times) == 1:
        return 0
    positive_steps = [right - left for left, right in zip(times, times[1:]) if right > left]
    sample_interval = statistics.median(positive_steps) if positive_steps else 0
    return times[-1] - times[0] + sample_interval


def is_failed(row):
    return int(row["http_code"]) == 0 or int(row["http_code"]) >= 500


def failure_episodes(failures, max_gap_s=2.0):
    timestamps = sorted(float(row["elapsed_s"]) for row in failures)
    if not timestamps:
        return 0
    return 1 + sum(
        current - previous >= max_gap_s
        for previous, current in zip(timestamps, timestamps[1:])
    )


def available_second_ratio(rows, duration):
    if not rows or duration <= 0:
        return 0
    seconds = max(1, int(round(duration)))
    available = {
        min(seconds - 1, int(float(row["elapsed_s"])))
        for row in rows
        if not is_failed(row)
    }
    return len(available) / seconds


def calculate(path):
    with open(path, newline="", encoding="utf-8") as handle:
        rows = sorted(csv.DictReader(handle), key=lambda row: float(row["elapsed_s"]))
    failures = [row for row in rows if is_failed(row)]
    duration = observation_duration(rows)
    episodes = failure_episodes(failures)
    latencies = [float(row["latency_ms"]) for row in rows]
    degraded = sum(row.get("response_status") == "degraded" for row in rows)
    return {
        "requests": len(rows),
        "failures": len(failures),
        "degraded": degraded,
        "duration_s": duration,
        "POFOD": len(failures) / len(rows) if rows else 0,
        "ROCOF_per_h": episodes / duration * 3600 if duration else 0,
        "AVAIL": available_second_ratio(rows, duration),
        "p50_ms": percentile(latencies, 0.50),
        "p95_ms": percentile(latencies, 0.95),
        "p99_ms": percentile(latencies, 0.99),
    }


def format_result(result):
    parts = []
    for key, value in result.items():
        parts.append(f"{key}={value:.6g}" if isinstance(value, float) else f"{key}={value}")
    return " ".join(parts)


if __name__ == "__main__":
    result = calculate(sys.argv[1])
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_result(result))
