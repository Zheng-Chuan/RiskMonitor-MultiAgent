"""Logging and request context.

This module centralizes structured logging and request id creation.
"""

from __future__ import annotations

import logging
import os
import uuid


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


_logger = logging.getLogger("riskmonitor")
_state: dict[str, bool] = {"is_configured": False}


def configure_logging() -> None:
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
    return uuid.uuid4().hex


def log_info(message: str, request_id: str) -> None:
    _logger.info(message, extra={"request_id": request_id})


def log_error(message: str, request_id: str) -> None:
    _logger.error(message, extra={"request_id": request_id})


def log_exception(message: str, request_id: str) -> None:
    _logger.exception(message, extra={"request_id": request_id})
