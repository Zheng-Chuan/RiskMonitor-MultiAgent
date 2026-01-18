"""Tool error payload helpers."""

from __future__ import annotations

from typing import Any


def error_payload(code: str, message: str, request_id: str) -> dict[str, Any]:
    """
    构造标准错误响应 Payload.

    Args:
        code: 错误码 (如 INTERNAL_ERROR, NOT_FOUND)
        message: 错误描述
        request_id: 请求追踪 ID

    Returns:
        包含 is_error=True 和 error 详情的字典
    """
    return {
        "is_error": True,
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        },
    }
