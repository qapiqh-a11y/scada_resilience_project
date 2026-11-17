import csv
import tempfile
import unittest
from pathlib import Path

from metrics import calculate


class MetricsTests(unittest.TestCase):
    def write_rows(self, rows):
        temp = tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", delete=False)
        with temp:
            writer = csv.DictWriter(
                temp,
                fieldnames=["elapsed_s", "http_code", "latency_ms", "response_status"],
            )
            writer.writeheader()
            writer.writerows(rows)
        self.addCleanup(Path(temp.name).unlink, missing_ok=True)
        return temp.name

    def test_reference_example_from_assignment(self):
        codes = [200] * 8 + [500, 500, 500, 503, 503, 500] + [200] * 6
        latencies = [38, 39, 39, 40, 40, 41, 42, 43, 44, 45, 46, 47, 51, 180, 1000, 1001, 1001, 1002, 1003, 1004]
        rows = [
            {
                "elapsed_s": index // 2,
                "http_code": code,
                "latency_ms": latency,
                "response_status": "failed" if code >= 500 else "ok",
            }
            for index, (code, latency) in enumerate(zip(codes, latencies))
        ]
        result = calculate(self.write_rows(rows))
        self.assertAlmostEqual(result["POFOD"], 0.30)
        self.assertAlmostEqual(result["ROCOF_per_h"], 360.0)
        self.assertAlmostEqual(result["AVAIL"], 0.70)
        self.assertEqual(result["p50_ms"], 45.0)
        self.assertEqual(result["p95_ms"], 1003.0)
        self.assertEqual(result["p99_ms"], 1004.0)

    def test_degraded_responses_are_counted_separately(self):
        rows = [
            {"elapsed_s": 0, "http_code": 200, "latency_ms": 10, "response_status": "ok"},
            {"elapsed_s": 1, "http_code": 200, "latency_ms": 5, "response_status": "degraded"},
        ]
        result = calculate(self.write_rows(rows))
        self.assertEqual(result["failures"], 0)
        self.assertEqual(result["degraded"], 1)

    def test_failures_less_than_two_seconds_apart_form_one_episode(self):
        rows = [
            {"elapsed_s": 0.0, "http_code": 500, "latency_ms": 10, "response_status": "failed"},
            {"elapsed_s": 0.5, "http_code": 200, "latency_ms": 10, "response_status": "ok"},
            {"elapsed_s": 1.5, "http_code": 503, "latency_ms": 10, "response_status": "failed"},
            {"elapsed_s": 3.5, "http_code": 500, "latency_ms": 10, "response_status": "failed"},
        ]
        result = calculate(self.write_rows(rows))
        self.assertAlmostEqual(result["ROCOF_per_h"], 1600.0)

    def test_availability_is_measured_per_second(self):
        rows = [
            {"elapsed_s": 0.0, "http_code": 500, "latency_ms": 10, "response_status": "failed"},
            {"elapsed_s": 0.5, "http_code": 200, "latency_ms": 10, "response_status": "ok"},
            {"elapsed_s": 1.0, "http_code": 500, "latency_ms": 10, "response_status": "failed"},
            {"elapsed_s": 1.5, "http_code": 500, "latency_ms": 10, "response_status": "failed"},
        ]
        result = calculate(self.write_rows(rows))
        self.assertEqual(result["AVAIL"], 0.5)


if __name__ == "__main__":
    unittest.main()
