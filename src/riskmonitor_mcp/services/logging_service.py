"""Logging and request context.

This module centralizes structured logging and request id creation.
"""

from __future__ import annotations

import logging
import os
import uuid


class _RequestIdFilter(logging.Filter):
    """
    日志过滤器.
    确保每条日志都有 request_id 字段, 如果没有则设为 "-".
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


_logger = logging.getLogger("riskmonitor")
_state: dict[str, bool] = {"is_configured": False}


def configure_logging() -> None:
    """
    配置全局日志系统.
    设置日志级别、格式和过滤器.
    """
    if _state["is_configured"]:
        return

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
    )

    for handler in logging.getLogger().handlers:
        handler.addFilter(_RequestIdFilter())

    _state["is_configured"] = True


def new_request_id() -> str:
    """生成新的唯一请求 ID (UUID hex)."""
    return uuid.uuid4().hex


def log_info(message: str, request_id: str) -> None:
    """记录 INFO 级别日志, 附带 request_id."""
    _logger.info(message, extra={"request_id": request_id})


def log_error(message: str, request_id: str) -> None:
    """记录 ERROR 级别日志, 附带 request_id."""
    _logger.error(message, extra={"request_id": request_id})


def log_exception(message: str, request_id: str) -> None:
    """记录 EXCEPTION 级别日志 (包含堆栈), 附带 request_id."""
    _logger.exception(message, extra={"request_id": request_id})
