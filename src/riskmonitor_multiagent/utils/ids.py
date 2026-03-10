"""ID 生成工具函数."""

from __future__ import annotations

import time
import uuid


def new_run_id(event_id: str = "event") -> str:
    """
    生成新的运行 ID.

    Args:
        event_id: 事件标识

    Returns:
        格式: {timestamp}-{uuid4[:8]}-{event_id}
    """
    ts = int(time.time())
    uid = uuid.uuid4().hex[:8]
    return f"{ts}-{uid}-{event_id}"


def new_command_id(prefix: str = "cmd") -> str:
    """
    生成新的命令 ID.

    Args:
        prefix: ID 前缀

    Returns:
        格式: {prefix}-{uuid4[:12]}
    """
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}-{uid}"
