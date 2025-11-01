"""Utilities for throttling high-frequency touch and button events."""

from __future__ import annotations

import threading
import time
from typing import Dict

__all__ = ["Debouncer"]


class Debouncer:
    """Allow events through only if enough time has elapsed since the last one."""

    def __init__(self, interval_ms: float = 50.0) -> None:
        self.interval = max(0.0, float(interval_ms)) / 1000.0
        self._last: Dict[str, float] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Return ``True`` if the event with ``key`` may proceed."""

        now = time.perf_counter()
        with self._lock:
            last = self._last.get(key, 0.0)
            if now - last >= self.interval:
                self._last[key] = now
                return True
        return False
