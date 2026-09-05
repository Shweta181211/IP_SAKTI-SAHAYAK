"""Per-client rate limiting for the endpoints that cost upstream calls.

Why this exists: `/query` costs three to four LLM round trips and `/compare`
costs two, all billed against a shared free-tier allowance that is 50 requests
per day on an account without credits. Both endpoints are unauthenticated. A
single script - or one enthusiastic person holding down a key - can exhaust the
day's quota for everyone, and the failure looks like the product being broken.

A fixed-window counter in process memory, deliberately:

  * No Redis, no dependency, nothing to deploy. This runs as one process.
  * A sliding window or token bucket would be more elegant and is not warranted;
    the goal is to stop runaway usage, not to meter fairly to the request.
  * State is per-process, so it resets on restart. That is acceptable for the
    threat being addressed and would not be for billing.

The limits are set well above what a person demonstrating the tool would ever
hit, and well below what a loop would.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

# Generous for a human, restrictive for a script. A live demo runs perhaps a
# dozen questions in ten minutes; a runaway loop does that in seconds.
WINDOW_SECONDS = 60.0
DEFAULT_LIMIT = 12

# Stop the bucket dict growing without bound behind a proxy that varies the
# client address. Entries are only pruned on write, so there is no timer.
MAX_TRACKED_CLIENTS = 4096


@dataclass
class _Window:
    started: float
    count: int = 0


@dataclass
class RateLimiter:
    """Fixed-window request counter, keyed by client address."""

    limit: int = DEFAULT_LIMIT
    window: float = WINDOW_SECONDS
    _buckets: dict[str, _Window] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _prune(self, now: float) -> None:
        stale = [key for key, w in self._buckets.items() if now - w.started > self.window]
        for key in stale:
            del self._buckets[key]

    def check(self, key: str) -> tuple[bool, int]:
        """Record a request. Returns (allowed, seconds until the window resets)."""
        now = time.monotonic()
        with self._lock:
            if len(self._buckets) > MAX_TRACKED_CLIENTS:
                self._prune(now)
            bucket = self._buckets.get(key)
            if bucket is None or now - bucket.started >= self.window:
                self._buckets[key] = _Window(started=now, count=1)
                return True, 0
            bucket.count += 1
            if bucket.count > self.limit:
                return False, max(1, int(self.window - (now - bucket.started)))
            return True, 0

    def reset(self) -> None:
        """Clear all state. For tests."""
        with self._lock:
            self._buckets.clear()


def client_key(request: Request) -> str:
    """Identify the caller.

    `request.client.host` is the direct peer, which behind a proxy is the proxy.
    We therefore prefer the first hop in X-Forwarded-For when it is present.

    That header is trivially spoofable by a direct caller, so this is NOT a
    security control - it is quota protection. Someone determined to get around
    it can, and the daily cap upstream is the real backstop. What it reliably
    stops is the accident: a retry loop, a stuck page, a load test.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(limiter: RateLimiter, request: Request) -> None:
    """Raise 429 when the caller is over their limit. A limit of 0 disables it."""
    if limiter.limit <= 0:
        return
    allowed, retry_after = limiter.check(client_key(request))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                "Too many requests. Each question costs several upstream model calls, "
                f"so this endpoint is limited. Please wait {retry_after}s and try again."
            ),
            headers={"Retry-After": str(retry_after)},
        )
