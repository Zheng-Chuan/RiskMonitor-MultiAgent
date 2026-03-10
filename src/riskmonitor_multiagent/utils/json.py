"""JSON 处理工具函数."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def safe_json_loads(text: str, default: Any = None) -> Any:
    """
    安全地解析 JSON 字符串.

    Args:
        text: JSON 字符串
        default: 解析失败时的默认值

    Returns:
        解析后的对象，或默认值
    """
    if not text or not isinstance(text, str):
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.debug(f"JSON decode error: {e}")
        return default


def safe_json_dumps(obj: Any, default: str = "{}", ensure_ascii: bool = False) -> str:
    """
    安全地将对象转为 JSON 字符串.

    Args:
        obj: 要序列化的对象
        default: 序列化失败时的默认字符串
        ensure_ascii: 是否转义非 ASCII 字符

    Returns:
        JSON 字符串，或默认值
    """
    if obj is None:
        return default
    try:
        return json.dumps(obj, ensure_ascii=ensure_ascii, default=str)
    except (TypeError, ValueError) as e:
        logger.debug(f"JSON encode error: {e}")
        return default
