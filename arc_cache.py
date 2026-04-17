from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import threading
import time
from typing import Generic, Hashable, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


@dataclass
class _CacheItem(Generic[V]):
    value: V
    expires_at: float


class AdaptiveReplacementTTLCache(Generic[K, V]):
    """ARC cache with TTL-aware live entries."""

    def __init__(self, capacity: int):
        self.capacity = max(0, int(capacity))
        self._target_t1 = 0.0
        self._t1: OrderedDict[K, _CacheItem[V]] = OrderedDict()
        self._t2: OrderedDict[K, _CacheItem[V]] = OrderedDict()
        self._b1: OrderedDict[K, None] = OrderedDict()
        self._b2: OrderedDict[K, None] = OrderedDict()
        self._lock = threading.RLock()

    def _now(self) -> float:
        return time.monotonic()

    def _prune_expired(self) -> None:
        now = self._now()
        self._prune_store(self._t1, now)
        self._prune_store(self._t2, now)

    @staticmethod
    def _prune_store(store: OrderedDict[K, _CacheItem[V]], now: float) -> None:
        expired_keys = [
            key for key, item in store.items() if item.expires_at <= now
        ]
        for key in expired_keys:
            del store[key]

    @staticmethod
    def _move_to_ghost(
        source: OrderedDict[K, _CacheItem[V]],
        target: OrderedDict[K, None],
    ) -> bool:
        if not source:
            return False

        key, _ = source.popitem(last=False)
        target[key] = None
        return True

    def _adapt_for_b1_hit(self) -> None:
        delta = max(1.0, len(self._b2) / max(1, len(self._b1)))
        self._target_t1 = min(float(self.capacity), self._target_t1 + delta)

    def _adapt_for_b2_hit(self) -> None:
        delta = max(1.0, len(self._b1) / max(1, len(self._b2)))
        self._target_t1 = max(0.0, self._target_t1 - delta)

    def _replace(self, incoming_key: K) -> None:
        if not self._t1 and not self._t2:
            return

        should_evict_from_t1 = self._t1 and (
            (incoming_key in self._b2 and len(self._t1) == int(self._target_t1))
            or len(self._t1) > self._target_t1
        )

        if should_evict_from_t1:
            self._move_to_ghost(self._t1, self._b1)
            return

        if not self._move_to_ghost(self._t2, self._b2):
            self._move_to_ghost(self._t1, self._b1)

    def _enforce_ghost_limits(self) -> None:
        while len(self._b1) > self.capacity:
            self._b1.popitem(last=False)
        while len(self._b2) > self.capacity:
            self._b2.popitem(last=False)

    def get(self, key: K) -> V | None:
        if self.capacity == 0:
            return None

        with self._lock:
            self._prune_expired()

            if key in self._t1:
                item = self._t1.pop(key)
                self._t2[key] = item
                return item.value

            if key in self._t2:
                item = self._t2.pop(key)
                self._t2[key] = item
                return item.value

            return None

    def put(self, key: K, value: V, ttl_seconds: float) -> bool:
        if self.capacity == 0:
            return False

        ttl_seconds = float(ttl_seconds)
        if ttl_seconds <= 0:
            return False

        with self._lock:
            self._prune_expired()
            item = _CacheItem(value=value, expires_at=self._now() + ttl_seconds)

            if key in self._t1:
                self._t1.pop(key)
                self._t2[key] = item
                return True

            if key in self._t2:
                self._t2.pop(key)
                self._t2[key] = item
                return True

            if key in self._b1:
                self._adapt_for_b1_hit()
                self._replace(key)
                self._b1.pop(key, None)
                self._t2[key] = item
                self._enforce_ghost_limits()
                return True

            if key in self._b2:
                self._adapt_for_b2_hit()
                self._replace(key)
                self._b2.pop(key, None)
                self._t2[key] = item
                self._enforce_ghost_limits()
                return True

            if len(self._t1) + len(self._b1) == self.capacity:
                if len(self._t1) < self.capacity:
                    if self._b1:
                        self._b1.popitem(last=False)
                    self._replace(key)
                else:
                    self._move_to_ghost(self._t1, self._b1)
            else:
                total_lists_size = (
                    len(self._t1)
                    + len(self._t2)
                    + len(self._b1)
                    + len(self._b2)
                )
                if len(self._t1) + len(self._b1) < self.capacity and total_lists_size >= self.capacity:
                    if total_lists_size >= 2 * self.capacity and self._b2:
                        self._b2.popitem(last=False)
                    self._replace(key)

            self._t1[key] = item
            self._enforce_ghost_limits()
            return True

    def stats(self) -> dict:
        with self._lock:
            self._prune_expired()
            return {
                "capacity": self.capacity,
                "live_entries": len(self._t1) + len(self._t2),
                "recent_entries": len(self._t1),
                "frequent_entries": len(self._t2),
                "recent_ghosts": len(self._b1),
                "frequent_ghosts": len(self._b2),
                "target_recent_size": round(self._target_t1, 2),
            }
