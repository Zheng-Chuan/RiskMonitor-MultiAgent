"""Readiness state.

说明:
- 提供 /ready 所需的最小 readiness 状态
- 支持在 shutdown 前将 readiness 置为 not ready
"""

from __future__ import annotations

import threading
from typing import Optional


_lock = threading.Lock()
_is_shutting_down = False
_shutdown_reason: Optional[str] = None


def mark_shutting_down(reason: str) -> None:
    global _is_shutting_down
    global _shutdown_reason
    with _lock:
        _is_shutting_down = True
        _shutdown_reason = reason


def is_shutting_down() -> bool:
    with _lock:
        return bool(_is_shutting_down)


def shutdown_reason() -> Optional[str]:
    with _lock:
        return _shutdown_reason


def _reset_for_tests() -> None:
    global _is_shutting_down
    global _shutdown_reason
    with _lock:
        _is_shutting_down = False
        _shutdown_reason = None
