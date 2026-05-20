"""LLM Token 用量追踪与告警模块.

职责:
- 记录每次 LLM 调用的真实 token 消耗到 Prometheus 指标
- 输出结构化日志
- 维护滑动窗口内的累计用量
- 超过阈值时触发告警（仅告警不阻断）
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

from riskmonitor_multiagent.observability.metrics import (
    inc_counter,
    observe_ms,
    set_gauge,
)

logger = logging.getLogger(__name__)


def _safe_int(value: Any, default: int = 0) -> int:
    """防御性转换为 int，处理 None / 非数字类型."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    """防御性转换为 float."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return default


@dataclass
class TokenUsageRecord:
    """单次 LLM 调用的 token 用量记录."""

    timestamp: float
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float = 0.0
    cached: bool = False


class TokenTracker:
    """LLM Token 用量追踪器.

    - 线程安全
    - 滑动窗口（小时 + 日）累计统计
    - 超过阈值时仅告警（日志 + counter），不抛异常
    """

    def __init__(self, window_s: int = 3600, daily_window_s: int = 86400) -> None:
        self._window_s = int(window_s) if window_s and window_s > 0 else 3600
        self._daily_window_s = (
            int(daily_window_s) if daily_window_s and daily_window_s > 0 else 86400
        )

        self._hourly_threshold = _safe_env_int("LLM_TOKEN_ALERT_HOURLY", 100_000)
        self._daily_threshold = _safe_env_int("LLM_TOKEN_ALERT_DAILY", 2_000_000)

        self._lock: threading.Lock = threading.Lock()
        self._records: deque[TokenUsageRecord] = deque()
        self._daily_records: deque[TokenUsageRecord] = deque()

        self._hourly_alert_triggered: bool = False
        self._daily_alert_triggered: bool = False

    # ------------------------------------------------------------------ #
    # 公共 API
    # ------------------------------------------------------------------ #
    def record(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        latency_ms: float = 0.0,
        cached: bool = False,
    ) -> None:
        """记录一次 LLM 调用的 token 用量."""
        try:
            model_str = str(model) if model is not None else "unknown"
            p_tokens = _safe_int(prompt_tokens)
            c_tokens = _safe_int(completion_tokens)
            t_tokens = _safe_int(total_tokens)
            if t_tokens <= 0 and (p_tokens > 0 or c_tokens > 0):
                t_tokens = p_tokens + c_tokens
            latency = _safe_float(latency_ms)
            cached_bool = bool(cached)

            # 1) Prometheus counters
            label_model = {"model": model_str}
            try:
                if p_tokens > 0:
                    inc_counter(
                        "rm_llm_prompt_tokens_total", labels=label_model, value=p_tokens
                    )
                if c_tokens > 0:
                    inc_counter(
                        "rm_llm_completion_tokens_total",
                        labels=label_model,
                        value=c_tokens,
                    )
                if t_tokens > 0:
                    inc_counter(
                        "rm_llm_tokens_total", labels=label_model, value=t_tokens
                    )
                inc_counter(
                    "rm_llm_calls_total",
                    labels={"model": model_str, "cached": "true" if cached_bool else "false"},
                    value=1,
                )
            except Exception:  # pragma: no cover - 指标失败不阻断
                logger.debug("inc_counter failed in token_tracker", exc_info=True)

            # 2) latency 观测
            if latency > 0:
                try:
                    observe_ms("rm_llm_latency", latency, labels=label_model)
                except Exception:  # pragma: no cover
                    logger.debug("observe_ms failed in token_tracker", exc_info=True)

            # 3) 结构化日志
            logger.info(
                "llm_token_usage model=%s prompt=%d completion=%d total=%d "
                "latency_ms=%.2f cached=%s",
                model_str,
                p_tokens,
                c_tokens,
                t_tokens,
                latency,
                cached_bool,
            )

            # 4) 滑动窗口
            now = time.time()
            record = TokenUsageRecord(
                timestamp=now,
                model=model_str,
                prompt_tokens=p_tokens,
                completion_tokens=c_tokens,
                total_tokens=t_tokens,
                latency_ms=latency,
                cached=cached_bool,
            )

            with self._lock:
                self._records.append(record)
                self._daily_records.append(record)
                self._cleanup_locked(now)

                # 5) gauge
                hourly_total = sum(r.total_tokens for r in self._records)
                try:
                    set_gauge("rm_llm_tokens_used_last_hour", float(hourly_total))
                except Exception:  # pragma: no cover
                    logger.debug("set_gauge failed in token_tracker", exc_info=True)

                # 6) 检查告警
                self._check_alerts_locked()
        except Exception:  # pragma: no cover - 永不阻断调用方
            logger.warning("TokenTracker.record failed", exc_info=True)

    def total_in_window(self) -> int:
        """当前小时窗口（默认 3600s）的总 token 数."""
        with self._lock:
            self._cleanup_locked(time.time())
            return int(sum(r.total_tokens for r in self._records))

    def total_in_daily_window(self) -> int:
        """当前日窗口（默认 86400s）的总 token 数."""
        with self._lock:
            self._cleanup_locked(time.time())
            return int(sum(r.total_tokens for r in self._daily_records))

    def summary(self) -> dict[str, Any]:
        """返回完整的统计摘要."""
        with self._lock:
            self._cleanup_locked(time.time())
            records = list(self._records)
            daily_records = list(self._daily_records)
            hourly_alert = self._hourly_alert_triggered
            daily_alert = self._daily_alert_triggered

        total_tokens = sum(r.total_tokens for r in records)
        prompt_tokens = sum(r.prompt_tokens for r in records)
        completion_tokens = sum(r.completion_tokens for r in records)
        calls = len(records)

        by_model: dict[str, dict[str, int]] = {}
        for r in records:
            entry = by_model.setdefault(
                r.model,
                {
                    "total_tokens": 0,
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                },
            )
            entry["total_tokens"] += r.total_tokens
            entry["calls"] += 1
            entry["prompt_tokens"] += r.prompt_tokens
            entry["completion_tokens"] += r.completion_tokens

        daily_total = sum(r.total_tokens for r in daily_records)

        return {
            "window_hours": max(1, self._window_s // 3600),
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "calls": calls,
            "by_model": by_model,
            "alert_threshold_hourly": self._hourly_threshold,
            "alert_threshold_daily": self._daily_threshold,
            "hourly_alert_triggered": bool(hourly_alert),
            "daily_alert_triggered": bool(daily_alert),
            "daily_total_tokens": daily_total,
        }

    def reset(self) -> None:
        """重置所有内部状态（仅供测试用）."""
        with self._lock:
            self._records.clear()
            self._daily_records.clear()
            self._hourly_alert_triggered = False
            self._daily_alert_triggered = False
        try:
            set_gauge("rm_llm_tokens_used_last_hour", 0.0)
            set_gauge("rm_llm_hourly_alert_triggered", 0.0)
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #
    def _cleanup_locked(self, now: float) -> None:
        """在持有锁的情况下清理过期记录."""
        hourly_cutoff = now - self._window_s
        while self._records and self._records[0].timestamp < hourly_cutoff:
            self._records.popleft()

        daily_cutoff = now - self._daily_window_s
        while self._daily_records and self._daily_records[0].timestamp < daily_cutoff:
            self._daily_records.popleft()

    def _cleanup(self) -> None:
        """清理过期记录（公共入口，自带锁）."""
        with self._lock:
            self._cleanup_locked(time.time())

    def _check_alerts_locked(self) -> None:
        """在持有锁的情况下检查阈值并触发告警."""
        hourly_total = sum(r.total_tokens for r in self._records)
        daily_total = sum(r.total_tokens for r in self._daily_records)

        # 小时阈值
        if self._hourly_threshold > 0 and hourly_total > self._hourly_threshold:
            if not self._hourly_alert_triggered:
                logger.warning(
                    "llm_token_alert window=hourly total=%d threshold=%d",
                    hourly_total,
                    self._hourly_threshold,
                )
            self._hourly_alert_triggered = True
            try:
                inc_counter(
                    "rm_llm_token_alert_fired_total",
                    labels={"window": "hourly"},
                    value=1,
                )
            except Exception:  # pragma: no cover
                logger.debug("inc_counter alert failed", exc_info=True)
        else:
            self._hourly_alert_triggered = False

        # 日阈值
        if self._daily_threshold > 0 and daily_total > self._daily_threshold:
            if not self._daily_alert_triggered:
                logger.warning(
                    "llm_token_alert window=daily total=%d threshold=%d",
                    daily_total,
                    self._daily_threshold,
                )
            self._daily_alert_triggered = True
            try:
                inc_counter(
                    "rm_llm_token_alert_fired_total",
                    labels={"window": "daily"},
                    value=1,
                )
            except Exception:  # pragma: no cover
                logger.debug("inc_counter alert failed", exc_info=True)
        else:
            self._daily_alert_triggered = False

        # gauge
        try:
            set_gauge(
                "rm_llm_hourly_alert_triggered",
                1.0 if self._hourly_alert_triggered else 0.0,
            )
        except Exception:  # pragma: no cover
            logger.debug("set_gauge alert failed", exc_info=True)


# ---------------------------------------------------------------------- #
# 全局单例 + 便捷函数
# ---------------------------------------------------------------------- #
_TRACKER: Optional[TokenTracker] = None
_TRACKER_LOCK = threading.Lock()


def get_token_tracker() -> TokenTracker:
    """获取全局 TokenTracker 单例."""
    global _TRACKER
    if _TRACKER is None:
        with _TRACKER_LOCK:
            if _TRACKER is None:
                _TRACKER = TokenTracker()
    return _TRACKER


def reset_token_tracker() -> None:
    """重置全局单例（测试用）."""
    global _TRACKER
    with _TRACKER_LOCK:
        _TRACKER = None


def record_token_usage(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    latency_ms: float = 0.0,
    cached: bool = False,
) -> None:
    """便捷函数 - 记录一次 LLM token 用量."""
    get_token_tracker().record(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        cached=cached,
    )


__all__ = [
    "TokenUsageRecord",
    "TokenTracker",
    "get_token_tracker",
    "reset_token_tracker",
    "record_token_usage",
]
