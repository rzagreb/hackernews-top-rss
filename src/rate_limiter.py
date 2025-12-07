import time


class RateLimiter:
    """A simple rate limiter to ensure a minimum interval between actions."""

    def __init__(self, min_interval_ms: float = 1000.0, start: bool = False) -> None:
        self.min_interval = float(min_interval_ms) / 1000.0
        self._start = None
        if start:
            self.start()

    def start(self):
        self._start = time.perf_counter()

    def wait_if_needed(self, reset: bool = True):
        """Waits the necessary time to enforce the minimum interval."""
        if self._start is None:
            return

        elapsed = time.perf_counter() - self._start
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

        if reset:
            self.start()
        else:
            self._start = None