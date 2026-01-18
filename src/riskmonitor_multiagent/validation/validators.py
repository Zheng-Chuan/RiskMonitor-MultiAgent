"""输入验证器.

提供统一的参数验证功能, 防止恶意输入和参数错误.
"""

from __future__ import annotations



import re
from typing import Optional


class ValidationError(ValueError):
    """验证错误."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def validate_desk_name(desk: str) -> str:
    """验证交易台名称.

    Args:
        desk: 交易台名称

    Returns:
        验证后的交易台名称

    Raises:
        ValidationError: 如果验证失败
    """
    if not desk or not desk.strip():
        raise ValidationError("desk", "desk name cannot be empty")

    desk = desk.strip()

    if len(desk) > 100:
        raise ValidationError("desk", "desk name too long (max 100 characters)")

    # 只允许字母、数字、空格、连字符和下划线
    if not re.match(r'^[a-zA-Z0-9\s\-_]+$', desk):
        raise ValidationError(
            "desk",
            "desk name can only contain letters, numbers, spaces, hyphens and underscores"
        )

    return desk


def validate_trader_id(trader_id: str) -> str:
    """验证交易员 ID.

    Args:
        trader_id: 交易员 ID

    Returns:
        验证后的交易员 ID

    Raises:
        ValidationError: 如果验证失败
    """
    if not trader_id or not trader_id.strip():
        raise ValidationError("trader_id", "trader_id cannot be empty")

    trader_id = trader_id.strip()

    if len(trader_id) > 50:
        raise ValidationError("trader_id", "trader_id too long (max 50 characters)")

    # 只允许字母、数字、连字符和下划线
    if not re.match(r'^[a-zA-Z0-9\-_]+$', trader_id):
        raise ValidationError(
            "trader_id",
            "trader_id can only contain letters, numbers, hyphens and underscores"
        )

    return trader_id


def validate_positive_number(value: float, field: str, max_value: Optional[float] = None) -> float:
    """验证正数.

    Args:
        value: 数值
        field: 字段名称
        max_value: 最大值(可选)

    Returns:
        验证后的数值

    Raises:
        ValidationError: 如果验证失败
    """
    if not isinstance(value, (int, float)):
        raise ValidationError(field, f"{field} must be a number")

    if value <= 0:
        raise ValidationError(field, f"{field} must be positive")

    if max_value is not None and value > max_value:
        raise ValidationError(field, f"{field} must be <= {max_value}")

    return float(value)


def validate_non_negative_number(  # pylint: disable=line-too-long
    value: float, field: str, max_value: Optional[float] = None
) -> float:
    """验证非负数.

    Args:
        value: 数值
        field: 字段名称
        max_value: 最大值(可选)

    Returns:
        验证后的数值

    Raises:
        ValidationError: 如果验证失败
    """
    if not isinstance(value, (int, float)):
        raise ValidationError(field, f"{field} must be a number")

    if value < 0:
        raise ValidationError(field, f"{field} must be non-negative")

    if max_value is not None and value > max_value:
        raise ValidationError(field, f"{field} must be <= {max_value}")

    return float(value)


def validate_integer_range(value: int, field: str, min_value: int, max_value: int) -> int:
    """验证整数范围.

    Args:
        value: 整数值
        field: 字段名称
        min_value: 最小值
        max_value: 最大值

    Returns:
        验证后的整数值

    Raises:
        ValidationError: 如果验证失败
    """
    if not isinstance(value, int):
        raise ValidationError(field, f"{field} must be an integer")

    if value < min_value or value > max_value:
        raise ValidationError(field, f"{field} must be between {min_value} and {max_value}")

    return value


def validate_date_string(date_str: Optional[str], field: str) -> Optional[str]:
    """验证日期字符串格式.

    Args:
        date_str: 日期字符串(YYYY-MM-DD 格式)
        field: 字段名称

    Returns:
        验证后的日期字符串

    Raises:
        ValidationError: 如果验证失败
    """
    if date_str is None:
        return None

    date_str = date_str.strip()

    if not date_str:
        return None

    # 验证 YYYY-MM-DD 格式
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        raise ValidationError(field, f"{field} must be in YYYY-MM-DD format")

    return date_str


def validate_task_id(task_id: str) -> str:
    """验证任务 ID.

    Args:
        task_id: 任务 ID

    Returns:
        验证后的任务 ID

    Raises:
        ValidationError: 如果验证失败
    """
    if not task_id or not task_id.strip():
        raise ValidationError("task_id", "task_id cannot be empty")

    task_id = task_id.strip()

    if len(task_id) > 64:
        raise ValidationError("task_id", "task_id too long (max 64 characters)")

    # 只允许十六进制字符
    if not re.match(r'^[a-fA-F0-9]+$', task_id):
        raise ValidationError("task_id", "task_id must be a hexadecimal string")

    return task_id


def validate_limit_offset(limit: int, offset: int) -> tuple[int, int]:
    """验证分页参数.

    Args:
        limit: 每页数量
        offset: 偏移量

    Returns:
        验证后的 (limit, offset)

    Raises:
        ValidationError: 如果验证失败
    """
    limit = validate_integer_range(limit, "limit", 1, 1000)
    offset = validate_integer_range(offset, "offset", 0, 1000000)

    return limit, offset
