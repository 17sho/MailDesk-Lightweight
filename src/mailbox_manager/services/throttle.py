from __future__ import annotations

import random
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager


class ComplianceThrottle:
    """Bound concurrency and login cadence without rotating identities."""

    def __init__(
        self,
        *,
        max_concurrency_per_identity: int = 2,
        min_account_interval: float = 0.0,
        max_account_interval: float = 0.0,
    ) -> None:
        if not 1 <= max_concurrency_per_identity <= 50:
            raise ValueError("单身份并发数必须在 1 到 50 之间")
        if min_account_interval < 0 or max_account_interval < min_account_interval:
            raise ValueError("账号间隔范围不正确")
        self._maximum = max_concurrency_per_identity
        self._minimum_interval = min_account_interval
        self._maximum_interval = max_account_interval
        self._lock = threading.Lock()
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._next_start: dict[str, float] = {}

    @contextmanager
    def slot(self, identity: str, _account_key: str) -> Iterator[None]:
        with self._lock:
            semaphore = self._semaphores.setdefault(
                identity, threading.BoundedSemaphore(self._maximum)
            )
        semaphore.acquire()
        try:
            with self._lock:
                now = time.monotonic()
                reserved_start = max(now, self._next_start.get(identity, now))
                delay = reserved_start - now
                interval = (
                    random.uniform(self._minimum_interval, self._maximum_interval)
                    if self._maximum_interval
                    else 0.0
                )
                self._next_start[identity] = reserved_start + interval
            if delay:
                time.sleep(delay)
            yield
        finally:
            semaphore.release()
