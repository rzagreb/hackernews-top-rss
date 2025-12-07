import unittest
import time

import context  # noqa: F401

from src.rate_limiter import RateLimiter  # change "rate_limiter" to your module name


class TestRateLimiter(unittest.TestCase):
    def test_min_interval_conversion(self):
        limiter = RateLimiter(min_interval_ms=250)
        self.assertAlmostEqual(limiter.min_interval, 0.25)

    def test_start_sets_start_time(self):
        limiter = RateLimiter(min_interval_ms=100)
        self.assertIsNone(limiter._start)
        limiter.start()
        self.assertIsNotNone(limiter._start)

    def test_wait_if_needed_without_start_returns_quickly(self):
        limiter = RateLimiter(min_interval_ms=100)

        t0 = time.perf_counter()
        limiter.wait_if_needed(reset=False)
        elapsed = time.perf_counter() - t0

        # Should not sleep at all
        self.assertLess(elapsed, 0.01)
        self.assertIsNone(limiter._start)

    def test_wait_if_needed_sleeps_to_enforce_interval(self):
        interval_ms = 50
        limiter = RateLimiter(min_interval_ms=interval_ms)
        min_interval = interval_ms / 1000.0

        t0 = time.perf_counter()
        limiter.start()
        limiter.wait_if_needed(reset=False)
        elapsed = time.perf_counter() - t0

        # Should have taken at least the requested interval,
        # but not an extremely large amount longer
        self.assertGreaterEqual(elapsed, min_interval)
        self.assertLess(elapsed, min_interval + 0.2)
        self.assertIsNone(limiter._start)

    def test_wait_if_needed_after_interval_has_passed_does_not_sleep_much(self):
        interval_ms = 20
        limiter = RateLimiter(min_interval_ms=interval_ms)

        limiter.start()
        # Wait longer than the interval ourselves
        time.sleep(limiter.min_interval + 0.01)

        t0 = time.perf_counter()
        limiter.wait_if_needed(reset=False)
        elapsed = time.perf_counter() - t0

        # Should not sleep noticeably because interval already passed
        self.assertLess(elapsed, 0.02)
        self.assertIsNone(limiter._start)


if __name__ == "__main__":
    unittest.main()
