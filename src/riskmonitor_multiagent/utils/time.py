"""时间工具函数."""

from __future__ import annotations

import time
from typing import Callable


def now_ms() -> int:
    """获取当前时间戳(毫秒)."""
    return int(time.time() * 1000)


def elapsed_ms(start_time: float) -> float:
    """
    计算从 start_time 到当前时间的毫秒数.

    Args:
        start_time: monotonic 时间戳(秒)

    Returns:
        毫秒数
    """
    return (time.monotonic() - start_time) * 1000.0


class Timer:
    """
    简单的上下文管理器计时器.

    用法:
        with Timer() as timer:
            # 执行操作
            pass
        print(f"耗时: {timer.elapsed_ms}ms")
    """

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: object) -> None:
        self.elapsed_ms = (time.monotonic() - self._start) * 1000.0


def measure_time(func: Callable) -> Callable:
    """
    装饰器:测量函数执行时间.

    用法:
        @measure_time
        def my_function():
            pass
    """
    def wrapper(*args: object, **kwargs: object) -> object:
        start = time.monotonic()
        result = func(*args, **kwargs)
        elapsed = (time.monotonic() - start) * 1000.0
        return result
    return wrapper
