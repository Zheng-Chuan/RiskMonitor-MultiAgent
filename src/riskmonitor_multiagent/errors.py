"""错误处理模块.

提供统一的错误处理功能：
- 错误分级
- 可恢复/不可恢复错误区分
- 死信队列
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """错误严重程度."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """错误类别."""
    # 可恢复错误
    TRANSIENT = "transient"  # 临时错误
    RETRYABLE = "retryable"  # 可重试
    RECOVERABLE = "recoverable"  # 可恢复

    # 不可恢复错误
    CONFIGURATION = "configuration"  # 配置错误
    VALIDATION = "validation"  # 验证错误
    PERMANENT = "permanent"  # 永久错误
    Fatal = "fatal"  # 致命错误


@dataclass
class ErrorRecord:
    """错误记录."""
    error_id: str
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    source: str
    exception: Optional[BaseException] | None = None
    context: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self) -> None:
        if not hasattr(self, "error_id") or self.error_id is None:
            self.error_id = f"err_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    def is_recoverable(self) -> bool:
        """是否可恢复."""
        return self.category in {
            ErrorCategory.TRANSIENT,
            ErrorCategory.RETRYABLE,
            ErrorCategory.RECOVERABLE,
        }

    def should_retry(self) -> bool:
        """是否应该重试."""
        if not self.is_recoverable():
            return False
        return self.retry_count < self.max_retries


class DeadLetterQueue:
    """死信队列（纯内存实现）."""

    def __init__(self, max_size: int = 1000) -> None:
        self._queue: list[ErrorRecord] = []
        self._max_size = max_size
        self._lock = None  # 暂不实现线程安全

    def add(self, record: ErrorRecord) -> None:
        """添加错误记录."""
        self._queue.append(record)
        if len(self._queue) > self._max_size:
            self._queue.pop(0)
        logger.warning(f"Error added to DLQ: {record.error_id} - {record.message}")

    def get_all(self) -> list[ErrorRecord]:
        """获取所有错误记录."""
        return list(self._queue)

    def get_recoverable(self) -> list[ErrorRecord]:
        """获取可恢复的错误."""
        return [r for r in self._queue if r.is_recoverable()]

    def clear(self) -> None:
        """清空队列."""
        self._queue.clear()

    def size(self) -> int:
        """获取队列大小."""
        return len(self._queue)


# 全局死信队列
_dlq: Optional[DeadLetterQueue] | None = None


def get_dead_letter_queue() -> DeadLetterQueue:
    """获取全局死信队列."""
    global _dlq
    if _dlq is None:
        _dlq = DeadLetterQueue()
    return _dlq


def reset_dead_letter_queue() -> None:
    """重置死信队列."""
    global _dlq
    _dlq = None
