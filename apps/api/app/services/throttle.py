"""A small in-memory sliding-window limiter.

Enough to stop someone using the sign-in form to flood an inbox. State lives in
the process, so it resets on deploy and is per server instance."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class Throttle:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: float, now: float | None = None) -> bool:
        """Record a hit and say whether it is within ``limit`` per window."""
        now = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and now - hits[0] >= window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True

    def clear(self) -> None:
        self._hits.clear()


sign_in_throttle = Throttle()
