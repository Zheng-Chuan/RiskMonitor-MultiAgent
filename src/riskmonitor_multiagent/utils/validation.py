"""验证工具函数."""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


def is_non_empty_str(value: Any) -> bool:
    """检查值是否为非空字符串."""
    return isinstance(value, str) and bool(value.strip())


def is_valid_list(value: Any, item_type: type[T] | None = None) -> bool:
    """
    检查值是否为有效的列表.

    Args:
        value: 要检查的值
        item_type: 可选的列表项类型检查

    Returns:
        是否为有效列表
    """
    if not isinstance(value, list):
        return False
    if item_type is None:
        return True
    return all(isinstance(x, item_type) for x in value)


def has_evidence_refs(evidence: Any) -> bool:
    """
    检查 evidence 字典是否包含有效的引用.

    检查以下字段:
    - receipt_command_ids: 回执命令ID列表
    - fields: 引用字段列表
    - rag_hit_ids: RAG命中文档ID列表

    Args:
        evidence: evidence 字典

    Returns:
        是否包含至少一个有效引用
    """
    if not isinstance(evidence, dict):
        return False

    # 检查 receipt_command_ids
    receipt_ids = evidence.get("receipt_command_ids")
    if isinstance(receipt_ids, list):
        if any(is_non_empty_str(x) for x in receipt_ids):
            return True

    # 检查 fields
    fields = evidence.get("fields")
    if isinstance(fields, list):
        if any(is_non_empty_str(x) for x in fields):
            return True

    # 检查 rag_hit_ids
    rag_hits = evidence.get("rag_hit_ids")
    if isinstance(rag_hits, list):
        if any(is_non_empty_str(x) for x in rag_hits):
            return True

    return False
