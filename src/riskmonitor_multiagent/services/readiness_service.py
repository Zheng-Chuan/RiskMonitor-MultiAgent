"""Readiness state.

说明:
- 提供 /ready 所需的最小 readiness 状态
- 支持在 shutdown 前将 readiness 置为 not ready
"""

from __future__ import annotations

import threading
from typing import Optional


_lock = threading.Lock()
_state: dict[str, Optional[object]] = {
    "is_shutting_down": False,
    "shutdown_reason": None,
}


def mark_shutting_down(reason: str) -> None:
    """
    标记服务正在关闭.
    调用后 readiness 检查将返回 False.

    Args:
        reason: 关闭原因 (如 received signal)
    """
    with _lock:
        _state["is_shutting_down"] = True
        _state["shutdown_reason"] = reason


def is_shutting_down() -> bool:
    """检查服务是否正在关闭."""
    with _lock:
        return bool(_state["is_shutting_down"])


def shutdown_reason() -> Optional[str]:
    """获取关闭原因."""
    with _lock:
        return _state["shutdown_reason"]  # type: ignore[return-value]


def _reset_for_tests() -> None:
    """重置状态 (仅用于测试)."""
    with _lock:
        _state["is_shutting_down"] = False
        _state["shutdown_reason"] = None
