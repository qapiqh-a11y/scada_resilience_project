import threading
import time
import unittest
from unittest.mock import patch

import core


class CircuitBreakerTests(unittest.TestCase):
    def setUp(self):
        core.PATTERN = True
        core.breaker = core.CircuitBreaker(threshold=3, recovery_timeout=0.02)

    def test_normal_dependency_closes_breaker(self):
        with patch("core.call_dep", return_value={"status": "ok"}):
            result = core.do_work()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(core.breaker.state, "CLOSED")

    def test_three_consecutive_failures_open_breaker(self):
        with patch("core.call_dep", side_effect=TimeoutError):
            for _ in range(3):
                core.do_work()
        self.assertEqual(core.breaker.state, "OPEN")

    def test_success_resets_consecutive_failure_counter(self):
        with patch("core.call_dep", side_effect=[TimeoutError(), {"status": "ok"}, TimeoutError()]):
            core.do_work()
            core.do_work()
            core.do_work()
        self.assertEqual(core.breaker.failures, 1)
        self.assertEqual(core.breaker.state, "CLOSED")

    def test_open_breaker_fails_fast(self):
        core.breaker.state = "OPEN"
        core.breaker.opened_at = time.monotonic()
        start = time.monotonic()
        result = core.do_work()
        self.assertLess(time.monotonic() - start, 0.05)
        self.assertEqual(result["status"], "degraded")

    def test_half_open_success_restores_service(self):
        core.breaker.state = "OPEN"
        core.breaker.opened_at = time.monotonic() - 1
        with patch("core.call_dep", return_value={"status": "ok"}):
            core.do_work()
        self.assertEqual(core.breaker.state, "CLOSED")

    def test_half_open_failure_reopens_breaker(self):
        core.breaker.state = "OPEN"
        core.breaker.opened_at = time.monotonic() - 1
        with patch("core.call_dep", side_effect=TimeoutError):
            result = core.do_work()
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(core.breaker.state, "OPEN")

    def test_only_one_half_open_probe_is_allowed(self):
        core.breaker.state = "OPEN"
        core.breaker.opened_at = time.monotonic() - 1
        probe_started = threading.Event()
        release_probe = threading.Event()

        def slow_success(timeout):
            probe_started.set()
            release_probe.wait(timeout=1)
            return {"status": "ok"}

        with patch("core.call_dep", side_effect=slow_success) as dependency:
            first_result = {}

            def first_request():
                first_result.update(core.do_work())

            thread = threading.Thread(target=first_request)
            thread.start()
            self.assertTrue(probe_started.wait(timeout=0.5))
            second = core.do_work()
            release_probe.set()
            thread.join(timeout=1)

        self.assertEqual(second["status"], "degraded")
        self.assertEqual(first_result["status"], "ok")
        dependency.assert_called_once()

    def test_timeout_returns_degraded_within_user_budget(self):
        def slow_timeout(timeout):
            time.sleep(0.05)
            raise TimeoutError

        start = time.monotonic()
        with patch("core.call_dep", side_effect=slow_timeout):
            result = core.do_work()
        self.assertLess(time.monotonic() - start, 1.5)
        self.assertEqual(result["status"], "degraded")

    def test_pattern_off_calls_dependency_directly(self):
        core.PATTERN = False
        with patch("core.call_dep", return_value={"status": "ok"}) as dependency:
            core.do_work()
        dependency.assert_called_once_with()

    def test_invalid_threshold_is_rejected(self):
        with self.assertRaises(ValueError):
            core.CircuitBreaker(threshold=0)


if __name__ == "__main__":
    unittest.main()
