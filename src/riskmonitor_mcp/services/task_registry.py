"""In process task registry.

This module stores background task state in memory.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional


_tasks: dict[str, dict[str, Any]] = {}
_tasks_lock = asyncio.Lock()


def new_task_id() -> str:
    """生成新的任务 ID."""
    return uuid.uuid4().hex


async def set_task(task_id: str, patch: dict[str, Any]) -> None:
    """
    更新任务状态.
    使用 patch 方式更新, 只修改提供的字段.

    Args:
        task_id: 任务 ID
        patch: 要更新的字段字典
    """
    async with _tasks_lock:
        current = _tasks.get(task_id, {})
        current.update(patch)
        _tasks[task_id] = current


async def get_task(task_id: str) -> Optional[dict[str, Any]]:
    """
    获取任务状态.

    Args:
        task_id: 任务 ID

    Returns:
        任务状态字典, 如果不存在返回 None
    """
    async with _tasks_lock:
        item = _tasks.get(task_id)
        return dict(item) if item is not None else None
