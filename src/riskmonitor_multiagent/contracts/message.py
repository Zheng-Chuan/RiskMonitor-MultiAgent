"""
多 Agent 协作消息契约定义.

定义 Message Bus 的消息格式，包括消息类型、发送者、接收者、内容等.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from riskmonitor_multiagent.utils import is_non_empty_str

# 契约版本
MESSAGE_SCHEMA_VERSION = "message.v1"


class MessageType(Enum):
    """消息类型枚举."""

    REQUEST = "request"           # 请求：向某个 Agent 提问
    RESPONSE = "response"         # 响应：回答请求
    BROADCAST = "broadcast"       # 广播：告诉所有 Agent
    INTERRUPT = "interrupt"       # 中断：暂停当前流程
    FEEDBACK = "feedback"         # 反馈：给其他 Agent 提意见
    TOOL_CALL = "tool_call"       # 工具调用请求
    TOOL_RESULT = "tool_result"   # 工具调用结果


def validate_message(message: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    验证消息格式.

    检查项:
    - message_id 为非空字符串
    - message_type 为有效的 MessageType
    - from_agent 为非空字符串
    - content 为字典
    - timestamp_ms 为正整数
    - 如果有 to_agent，必须为非空字符串
    - 如果有 in_reply_to，必须为非空字符串
    """
    if not isinstance(message, dict):
        return False, ["message must be dict"]

    errors: list[str] = []

    # 检查 message_id
    if not is_non_empty_str(message.get("message_id")):
        errors.append("bad_message_id")

    # 检查 message_type
    msg_type = message.get("message_type")
    try:
        MessageType(msg_type)
    except ValueError:
        errors.append("bad_message_type")

    # 检查 from_agent
    if not is_non_empty_str(message.get("from_agent")):
        errors.append("bad_from_agent")

    # 检查 content
    content = message.get("content")
    if content is not None and not isinstance(content, dict):
        errors.append("bad_content")

    # 检查 timestamp_ms
    ts = message.get("timestamp_ms")
    if ts is None:
        errors.append("missing_timestamp_ms")
    else:
        try:
            i = int(ts)
            if i <= 0:
                errors.append("bad_timestamp_ms")
        except (TypeError, ValueError):
            errors.append("bad_timestamp_ms")

    # 检查 to_agent（可选）
    to_agent = message.get("to_agent")
    if to_agent is not None and not is_non_empty_str(to_agent):
        errors.append("bad_to_agent")

    # 检查 in_reply_to（可选）
    in_reply_to = message.get("in_reply_to")
    if in_reply_to is not None and not is_non_empty_str(in_reply_to):
        errors.append("bad_in_reply_to")

    return len(errors) == 0, errors


def normalize_message(message: dict[str, Any]) -> dict[str, Any]:
    """
    归一化消息，补充缺失字段.

    主要处理:
    - 补充缺失的基础字段
    - 确保 content 为字典
    """
    out = dict(message) if isinstance(message, dict) else {}

    # 基础默认值
    out.setdefault("schema_version", MESSAGE_SCHEMA_VERSION)
    out.setdefault("message_type", MessageType.REQUEST.value)
    out.setdefault("content", {})
    out.setdefault("degraded", False)
    out.setdefault("degraded_reason", None)

    return out
