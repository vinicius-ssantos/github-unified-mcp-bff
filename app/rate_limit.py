"""In-memory sliding-window rate limiter (per-user or per-IP)."""
from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock


class _SlidingWindow:
    def __init__(self) -> None:
        self._ts: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, key: str, *, max_requests: int, window: int) -> bool:
        now = time.monotonic()
        with self._lock:
            ts = [t for t in self._ts[key] if now - t < window]
            if len(ts) >= max_requests:
                self._ts[key] = ts
                return False
            ts.append(now)
            self._ts[key] = ts
            return True


_limiter = _SlidingWindow()


def check_rate_limit(key: str, max_requests: int, window: int) -> bool:
    """Return True if the request is within the rate limit, False if exceeded."""
    return _limiter.is_allowed(key, max_requests=max_requests, window=window)
