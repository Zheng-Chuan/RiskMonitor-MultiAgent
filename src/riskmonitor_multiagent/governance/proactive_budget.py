"""
system_event 主动协作预算与熔断.
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class ProactiveBudgetDecision:
    allowed: bool
    reason: str
    evidence: dict[str, Any]


class ProactiveBudgetManager:
    """主动协作预算管理器."""

    def __init__(self) -> None:
        self._event_window_s = self._int_env("PROACTIVE_EVENT_WINDOW_S", 60)
        self._event_burst_limit = self._int_env("PROACTIVE_EVENT_BURST_LIMIT", 5)
        self._max_concurrent_runs = self._int_env("PROACTIVE_MAX_CONCURRENT_RUNS", 2)
        self._token_window_s = self._int_env("PROACTIVE_TOKEN_WINDOW_S", 300)
        self._token_budget = self._int_env("PROACTIVE_TOKEN_BUDGET", 4000)
        self._failure_threshold = self._int_env("PROACTIVE_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 3)
        self._open_s = self._int_env("PROACTIVE_CIRCUIT_BREAKER_OPEN_S", 60)
        self._event_timestamps: deque[int] = deque()
        self._token_reservations: deque[tuple[int, int]] = deque()
        self._active_runs: dict[str, int] = {}
        self._consecutive_failures = 0
        self._circuit_open_until_ms = 0

    def evaluate_and_reserve(self, *, run_id: str, event: dict[str, Any]) -> ProactiveBudgetDecision:
        now = self._now_ms()
        self._cleanup(now)
        estimated_tokens = self._estimate_tokens(event)
        evidence = self.snapshot()
        evidence["estimated_tokens"] = estimated_tokens

        if self._circuit_open_until_ms > now:
            evidence["circuit_open_until_ms"] = self._circuit_open_until_ms
            return ProactiveBudgetDecision(False, "circuit_breaker_open", evidence)

        if len(self._event_timestamps) >= self._event_burst_limit:
            return ProactiveBudgetDecision(False, "event_burst_limit_exceeded", evidence)

        if len(self._active_runs) >= self._max_concurrent_runs:
            return ProactiveBudgetDecision(False, "concurrent_proactive_runs_exceeded", evidence)

        if self._used_tokens() + estimated_tokens > self._token_budget:
            return ProactiveBudgetDecision(False, "proactive_token_budget_exceeded", evidence)

        self._event_timestamps.append(now)
        self._active_runs[run_id] = now
        self._token_reservations.append((now, estimated_tokens))
        evidence = self.snapshot()
        evidence["estimated_tokens"] = estimated_tokens
        return ProactiveBudgetDecision(True, "allowed", evidence)

    def release_run(self, *, run_id: str, status: str) -> None:
        self._active_runs.pop(run_id, None)
        if status in {"completed", "success"}:
            self._consecutive_failures = 0
            return
        if status in {"blocked", "throttled"}:
            return

        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._circuit_open_until_ms = self._now_ms() + self._open_s * 1000

    def snapshot(self) -> dict[str, Any]:
        now = self._now_ms()
        self._cleanup(now)
        return {
            "event_burst_limit": self._event_burst_limit,
            "event_window_s": self._event_window_s,
            "events_in_window": len(self._event_timestamps),
            "max_concurrent_runs": self._max_concurrent_runs,
            "active_runs": len(self._active_runs),
            "token_budget": self._token_budget,
            "token_window_s": self._token_window_s,
            "reserved_tokens": self._used_tokens(),
            "consecutive_failures": self._consecutive_failures,
            "circuit_open_until_ms": self._circuit_open_until_ms,
        }

    def _estimate_tokens(self, event: dict[str, Any]) -> int:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        raw = str(payload.get("content") or payload.get("summary") or payload)
        return max(1, len(raw) // 4)

    def _used_tokens(self) -> int:
        return sum(tokens for _, tokens in self._token_reservations)

    def _cleanup(self, now_ms: int) -> None:
        event_cutoff = now_ms - self._event_window_s * 1000
        while self._event_timestamps and self._event_timestamps[0] < event_cutoff:
            self._event_timestamps.popleft()

        token_cutoff = now_ms - self._token_window_s * 1000
        while self._token_reservations and self._token_reservations[0][0] < token_cutoff:
            self._token_reservations.popleft()

        if self._circuit_open_until_ms <= now_ms and self._circuit_open_until_ms != 0:
            self._circuit_open_until_ms = 0
            self._consecutive_failures = 0

    def _int_env(self, name: str, default: int) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return value if value > 0 else default

    def _now_ms(self) -> int:
        return int(time.time() * 1000)


def get_proactive_budget_manager() -> ProactiveBudgetManager:
    global _PROACTIVE_BUDGET_MANAGER
    if _PROACTIVE_BUDGET_MANAGER is None:
        _PROACTIVE_BUDGET_MANAGER = ProactiveBudgetManager()
    return _PROACTIVE_BUDGET_MANAGER


def reset_proactive_budget_manager() -> None:
    global _PROACTIVE_BUDGET_MANAGER
    _PROACTIVE_BUDGET_MANAGER = None


_PROACTIVE_BUDGET_MANAGER: ProactiveBudgetManager | None = None


__all__ = [
    "ProactiveBudgetDecision",
    "ProactiveBudgetManager",
    "get_proactive_budget_manager",
    "reset_proactive_budget_manager",
]
