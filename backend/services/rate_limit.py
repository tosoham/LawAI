"""
A cap on how often one account may spend money.

`API_RATE_LIMIT` and `API_RATE_LIMIT_PERIOD` have been in `.env.example` since
the beginning and were **read by nothing** -- documented, configurable, and
entirely imaginary. That was survivable while the only URL was localhost. It
stops being survivable the moment a public address sits in front of a paid LLM
key, where an unauthenticated `POST /agent/query` is an open tap on someone's
account and each pull also costs eight to thirteen seconds of a single-process
service's time.

**A fixed window, in process, keyed by account.** Not a token bucket and not
Redis, because both would be answering a question nobody has asked yet: one
Space is one process, so a dict is the whole of the shared state, and a fixed
window is trivially explainable to the person who hits it. The honest cost of a
fixed window is that someone can spend twice the budget across a boundary --
irrelevant when the budget exists to stop a runaway loop or a scraper, not to
meter billing to the request.

**Keyed by account rather than by IP.** An IP is shared by everyone behind one
office NAT and changes for a phone between cells, so an IP limit punishes the
wrong people and misses the right ones. Answering requires sign-in precisely so
this key exists.

It does not survive a restart. That is correct for what it defends against: a
restart is not a way to get more budget when the thing being stopped is a loop
running now.

The dict retains one deque per key ever seen, which is bounded by the number of
accounts because answering requires sign-in. An earlier version had a cleanup
branch after the append that could never fire -- `hits` is non-empty by
construction at that point -- so it was removed rather than left looking like a
guard.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status


def _limit() -> int:
    return int(os.getenv("API_RATE_LIMIT", "100"))


def _period() -> int:
    return int(os.getenv("API_RATE_LIMIT_PERIOD", "60"))


class RateLimiter:
    """Requests per key per window, counted in memory."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """
        Take one request from ``key``'s budget.

        Returns whether it was allowed and how many seconds until the window
        clears, so the caller can say something useful rather than just "no".
        """
        limit, period = _limit(), _period()
        if limit <= 0:
            return True, 0

        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= period:
                hits.popleft()
            if len(hits) >= limit:
                return False, max(1, int(period - (now - hits[0])))
            hits.append(now)
            return True, 0

    def reset(self) -> None:
        """For tests. Nothing in production should need this."""
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def enforce(key: str) -> None:
    """Raise 429 if ``key`` has spent its budget."""
    allowed, retry_after = limiter.check(key)
    if allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            f"Too many questions in a short period. Try again in "
            f"{retry_after} seconds."
        ),
        headers={"Retry-After": str(retry_after)},
    )
