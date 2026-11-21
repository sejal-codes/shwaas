"""Tiny thread-safe TTL cache with a size cap (saves API calls and keeps memory bounded)."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable, Hashable


class TTLCache:
    def __init__(self, ttl_s: float, max_entries: int, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl_s
        self._max = max_entries
        self._clock = clock
        self._data: OrderedDict[Hashable, tuple[float, object]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable):
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if self._clock() >= expires_at:
                del self._data[key]
                return None
            return value

    def set(self, key: Hashable, value: object) -> None:
        with self._lock:
            self._data[key] = (self._clock() + self._ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)
