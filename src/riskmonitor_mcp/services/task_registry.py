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
    return uuid.uuid4().hex


async def set_task(task_id: str, patch: dict[str, Any]) -> None:
    async with _tasks_lock:
        current = _tasks.get(task_id, {})
        current.update(patch)
        _tasks[task_id] = current


async def get_task(task_id: str) -> Optional[dict[str, Any]]:
    async with _tasks_lock:
        item = _tasks.get(task_id)
        return dict(item) if item is not None else None
