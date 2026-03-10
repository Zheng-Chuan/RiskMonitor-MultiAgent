"""
工具函数包.

提供项目中各模块共享的通用工具函数和类型定义.
"""

from riskmonitor_multiagent.utils.text import clean_llm_output, truncate_text, truncate_context
from riskmonitor_multiagent.utils.validation import is_non_empty_str, is_valid_list, has_evidence_refs
from riskmonitor_multiagent.utils.json import safe_json_loads, safe_json_dumps
from riskmonitor_multiagent.utils.ids import new_run_id, new_command_id
from riskmonitor_multiagent.utils.time import now_ms, elapsed_ms

__all__ = [
    # 文本处理
    "clean_llm_output",
    "truncate_text",
    "truncate_context",
    # 验证工具
    "is_non_empty_str",
    "is_valid_list",
    "has_evidence_refs",
    # JSON 处理
    "safe_json_loads",
    "safe_json_dumps",
    # ID 生成
    "new_run_id",
    "new_command_id",
    # 时间工具
    "now_ms",
    "elapsed_ms",
]
