"""日志与请求上下文.

说明:
- 统一结构化日志配置
- 统一 request_id 生成
"""

from __future__ import annotations

import logging
import os
import uuid
import json


class _RequestIdFilter(logging.Filter):  # pylint: disable=too-few-public-methods
    """
    日志过滤器.
    确保每条日志都有 request_id 字段, 如果没有则设为 "-".
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


class JsonFormatter(logging.Formatter):  # pylint: disable=too-few-public-methods
    """JSON 格式日志格式化器."""

    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id
        return json.dumps(log_record)


_logger = logging.getLogger("riskmonitor")
_state: dict[str, bool] = {"is_configured": False}


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger."""
    return logging.getLogger(name)


def configure_logging() -> None:
    """
    配置全局日志系统.
    设置日志级别,格式和过滤器.
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
    """生成新的唯一请求 ID(UUID hex)."""
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
