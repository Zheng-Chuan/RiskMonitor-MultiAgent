from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from riskmonitor_multiagent.observability.metrics import inc_counter, set_gauge


def _as_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or not v.strip():
        return int(default)
    try:
        return int(v)
    except Exception:
        return int(default)


def _as_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or not v.strip():
        return float(default)
    try:
        return float(v)
    except Exception:
        return float(default)


@dataclass
class _BucketCfg:
    capacity: float
    refill_per_s: float


class TokenBucket:
    def __init__(self, *, capacity: float, refill_per_s: float, now_fn: Callable[[], float] | None = None) -> None:
        self._capacity = float(max(0.0, capacity))
        self._refill_per_s = float(max(0.0, refill_per_s))
        self._now = now_fn or time.monotonic
        self._tokens = float(self._capacity)
        self._ts = float(self._now())
        self._lock = threading.Lock()

    def try_consume(self, amount: float) -> bool:
        need = float(max(0.0, amount))
        if need <= 0.0:
            return True
        with self._lock:
            now = float(self._now())
            elapsed = max(0.0, now - self._ts)
            if elapsed > 0.0 and self._refill_per_s > 0.0:
                self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_s)
            self._ts = now
            if need > self._capacity:
                return False
            if self._tokens >= need:
                self._tokens -= need
                return True
            return False

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return {"capacity": float(self._capacity), "tokens": float(self._tokens), "refill_per_s": float(self._refill_per_s)}


class LLMCostGovernor:
    def __init__(self, *, now_fn: Callable[[], float] | None = None) -> None:
        self._now_fn = now_fn or time.monotonic
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def _cfg_for_priority(self, priority: str) -> Optional[_BucketCfg]:
        p = (priority or "default").strip().lower()
        if p in {"non_critical", "noncritical", "query"}:
            per_min = _as_float("LLM_RATE_LIMIT_TOKENS_PER_MIN_NON_CRITICAL", 8000.0)
            burst = _as_float("LLM_RATE_LIMIT_BURST_TOKENS_NON_CRITICAL", per_min)
        else:
            per_min = _as_float("LLM_RATE_LIMIT_TOKENS_PER_MIN_DEFAULT", 60000.0)
            burst = _as_float("LLM_RATE_LIMIT_BURST_TOKENS_DEFAULT", per_min)
        if per_min <= 0.0 or burst <= 0.0:
            return None
        return _BucketCfg(capacity=float(burst), refill_per_s=float(per_min) / 60.0)

    def allow(
        self,
        *,
        agent: str,
        user_id: str,
        priority: str,
        estimated_tokens: int,
    ) -> tuple[bool, dict[str, object]]:
        cfg = self._cfg_for_priority(priority)
        if cfg is None:
            return True, {"enabled": False, "priority": priority}

        key = (priority or "default").strip().lower()
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                b = TokenBucket(capacity=cfg.capacity, refill_per_s=cfg.refill_per_s, now_fn=self._now_fn)
                self._buckets[key] = b

        ok = b.try_consume(float(max(0, int(estimated_tokens))))
        snap = b.snapshot()
        set_gauge("rm_llm_rate_limit_tokens_available", float(snap.get("tokens") or 0.0), labels={"priority": key})
        if not ok:
            inc_counter(
                "rm_llm_rate_limited_total",
                labels={"agent": agent or "unknown", "user": user_id or "unknown", "priority": key},
            )
        return ok, {"enabled": True, "priority": key, "bucket": snap}


_GOVERNOR = None


def get_llm_cost_governor() -> LLMCostGovernor:
    global _GOVERNOR  # pylint: disable=global-statement
    if _GOVERNOR is None:
        _GOVERNOR = LLMCostGovernor()
    return _GOVERNOR

