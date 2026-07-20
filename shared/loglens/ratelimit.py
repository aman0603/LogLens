"""In-memory token-bucket rate limiter.

Appropriate for a single-instance deployment (no Redis/external store). Limits
requests per client key (IP or token subject) over a sliding window. Returns
429 when the bucket is exhausted. Thread-safe via a lock.
"""

import time
from threading import Lock
from typing import Dict, Tuple


class RateLimiter:
    def __init__(self, rate: int = 10, per: int = 1):
        """Allow ``rate`` requests per ``per`` seconds per key."""
        self.rate = rate
        self.per = per
        self._buckets: Dict[str, Tuple[float, int]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> Tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.time()
        with self._lock:
            tokens, updated = self._buckets.get(key, (self.rate, now))
            elapsed = now - updated
            # Refill tokens based on elapsed time.
            tokens = min(self.rate, tokens + elapsed * (self.rate / self.per))
            if tokens >= 1:
                tokens -= 1
                self._buckets[key] = (tokens, now)
                return True, 0
            retry_after = int((1 - tokens) * (self.per / self.rate)) + 1
            self._buckets[key] = (tokens, now)
            return False, max(retry_after, 1)
