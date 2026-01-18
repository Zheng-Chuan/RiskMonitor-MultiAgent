"""Tools 层通用辅助函数

说明
- 提供输入归一化与轻量校验
- 避免在各个 tool 入口重复写相同逻辑
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def normalize_limit_offset(
    limit: Optional[int],
    offset: Optional[int],
    *,
    default_limit: int = 100,
    max_limit: int = 1000,
) -> tuple[int, int]:
    """
    归一化分页参数.

    Args:
        limit: 每页数量
        offset: 偏移量
        default_limit: 默认每页数量
        max_limit: 最大每页数量

    Returns:
        (limit, offset)
    """
    normalized_limit = default_limit if limit is None else int(limit)
    normalized_limit = max(1, min(normalized_limit, int(max_limit)))

    normalized_offset = 0 if offset is None else int(offset)
    normalized_offset = max(0, normalized_offset)

    return normalized_limit, normalized_offset


def validate_optional_yyyy_mm_dd(date_str: Optional[str], field_name: str) -> None:
    """
    校验日期格式但不改变原值.

    Args:
        date_str: 日期字符串
        field_name: 字段名

    Raises:
        ValueError: 格式错误
    """
    if date_str is None:
        return
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from e


def normalize_as_of(as_of: Optional[str]) -> str:
    """
    归一化 as_of 为 ISO8601 Z 格式.

    Args:
        as_of: 时间字符串

    Returns:
        ISO8601 时间字符串
    """
    if as_of is None or not as_of.strip():
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return as_of.strip()


def normalize_str(value: Optional[str], default_value: str) -> str:
    """
    归一化字符串.

    Args:
        value: 输入字符串
        default_value: 默认值

    Returns:
        归一化后的字符串
    """
    if value is None or not value.strip():
        return default_value
    return value.strip()


def normalize_positions(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    将 repository 返回的原始 rows 归一化为可序列化的 dict.

    Args:
        positions: 原始头寸列表

    Returns:
        归一化后的头寸列表
    """
    normalized_positions: list[dict[str, Any]] = []

    for pos in positions:
        entry_date = pos.get("entry_date")
        normalized_positions.append(
            {
                "position_id": pos.get("position_id"),
                "trader_id": pos.get("trader_id"),
                "desk": pos.get("desk"),
                "security_id": pos.get("security_id"),
                "quantity": float(pos["quantity"]) if pos.get("quantity") is not None else None,
                "delta": float(pos["delta"]) if pos.get("delta") is not None else None,
                "entry_date": (
                    entry_date.isoformat() if hasattr(entry_date, "isoformat") else entry_date
                ),
                "currency": pos.get("currency"),
            }
        )

    return normalized_positions
