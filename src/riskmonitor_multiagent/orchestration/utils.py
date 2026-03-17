"""Orchestrator 公共工具函数.

用于减少代码重复，提供通用的辅助函数。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from riskmonitor_multiagent.utils.validation import has_evidence_refs


def _ensure_evidence_refs(output: Any, primary_keys: Optional[list[str]] = None) -> None:
    """
    确保输出有 evidence 引用（通过检查文本中的 command_id）.

    Args:
        output: Agent 输出字典
        primary_keys: 主要字段列表，用于查找文本中的 command_id
    """
    if not isinstance(output, dict):
        return

    # 如果已有证据，直接返回
    existing_evidence = output.get("evidence", {})
    if isinstance(existing_evidence, dict) and len(existing_evidence) > 0:
        return

    # 从主要字段中提取 command_id
    command_ids: set[str] = set()
    keys_to_check = primary_keys if primary_keys else ["summary", "report", "reason", "notes", "output"]

    for key in keys_to_check:
        text = output.get(key)
        if isinstance(text, str):
            # 匹配 cmd:xxx 格式的 command_id
            matches = re.findall(r"cmd:[A-Za-z0-9_-]+", text)
            for m in matches:
                cmd_id = m.replace("cmd:", "")
                command_ids.add(cmd_id)

    if command_ids:
        output["evidence"] = {"receipt_command_ids": sorted(command_ids)}
