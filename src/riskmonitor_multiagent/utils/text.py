"""文本处理工具函数."""

from __future__ import annotations

import re
from typing import Any


def clean_llm_output(text: str) -> str:
    """
    清理 LLM 输出，提取有效 JSON 内容.

    处理常见问题:
    - 去除 markdown 代码块标记 (```json ... ```)
    - 去除前后的非 JSON 文本
    - 提取第一个 { 到最后一个 } 之间的内容

    Args:
        text: 原始 LLM 输出文本

    Returns:
        清理后的文本，应当是可解析的 JSON
    """
    text = text.strip()

    # 移除 markdown 代码块
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # 尝试提取 JSON 对象
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    # 移除常见的 LLM 前缀/后缀文本
    text = re.sub(r'^[^{]*', '', text)
    text = re.sub(r'[^}]*$', '', text)

    return text.strip()


def truncate_text(text: str, max_chars: int = 200, suffix: str = "...") -> str:
    """
    截断文本到指定长度.

    Args:
        text: 原始文本
        max_chars: 最大字符数
        suffix: 截断后添加的后缀

    Returns:
        截断后的文本
    """
    if not text or len(text) <= max_chars:
        return text
    return text[:max_chars - len(suffix)] + suffix


def truncate_context(context: dict[str, Any] | None, max_chars: int = 1500) -> dict[str, Any] | None:
    """
    截断 context 字典以减少 token 消耗.

    Args:
        context: 原始 context 字典
        max_chars: 最大字符数限制

    Returns:
        截断后的 context 字典
    """
    if context is None:
        return None

    ctx_str = str(context)
    if len(ctx_str) <= max_chars:
        return context

    # 截断策略：保留关键字段，截断长文本
    truncated = dict(context)
    for key in ["artifacts", "receipts", "plan"]:
        if key in truncated:
            val_str = str(truncated[key])
            if len(val_str) > max_chars // 3:
                truncated[key] = val_str[:max_chars // 3] + "...[truncated]"
    return truncated
