"""数据访问层错误.

说明:
- 统一 DB 相关异常, 便于 tools 层输出稳定的 error.code
- data_access 只负责 IO 与错误翻译, 不输出 HTTP 或 MCP 格式
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx
import pymysql


@dataclass
class DataAccessError(RuntimeError):
    """
    数据访问层通用异常.
    封装底层 DB/HTTP 错误, 提供统一的错误码和重试建议.
    """
    # 错误码用于上层错误映射(例如 DB_TIMEOUT, UPSTREAM_ERROR)
    code: str
    # 是否建议重试
    retriable: bool
    # 具体错误信息
    message: str
    # 原始异常
    cause: Optional[BaseException] = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _is_timeout_error(err: pymysql.MySQLError) -> bool:
    """判断是否为 MySQL 超时错误."""
    msg = str(err).lower()
    return "timeout" in msg or "timed out" in msg


def map_mysql_error(err: pymysql.MySQLError, operation: str) -> DataAccessError:
    """
    将 pymysql 异常映射为 DataAccessError.

    参数:
        err: 原始 pymysql 异常
        operation: 操作名称, 用于日志

    返回:
        封装后的 DataAccessError
    """
    # 统一把 pymysql 的异常翻译成稳定错误码
    if _is_timeout_error(err):
        return DataAccessError(
            code="DB_TIMEOUT",
            retriable=True,
            message=f"mysql timeout op={operation}",
            cause=err,
        )

    if isinstance(err, (pymysql.err.OperationalError, pymysql.err.InterfaceError)):
        return DataAccessError(
            code="DB_UNAVAILABLE",
            retriable=True,
            message=f"mysql unavailable op={operation}",
            cause=err,
        )

    if isinstance(err, (pymysql.err.ProgrammingError, pymysql.err.InternalError)):
        return DataAccessError(
            code="DB_QUERY_FAILED",
            retriable=False,
            message=f"mysql query failed op={operation}",
            cause=err,
        )

    return DataAccessError(
        code="DB_ERROR",
        retriable=True,
        message=f"mysql error op={operation}",
        cause=err,
    )


def map_http_error(err: BaseException, operation: str) -> DataAccessError:
    """
    将 httpx 异常映射为 DataAccessError.

    参数:
        err: 原始 httpx 异常或 BaseException
        operation: 操作名称

    返回:
        封装后的 DataAccessError
    """
    # 统一把 httpx 异常翻译成稳定错误码, 用于上游行情快照请求.
    if isinstance(err, httpx.TimeoutException):
        return DataAccessError(
            code="UPSTREAM_TIMEOUT",
            retriable=True,
            message=f"upstream timeout op={operation}",
            cause=err,
        )

    if isinstance(err, httpx.HTTPStatusError):
        status_code = getattr(getattr(err, "response", None), "status_code", None)
        return DataAccessError(
            code="UPSTREAM_BAD_STATUS",
            retriable=(status_code is None or int(status_code) >= 500),
            message=f"upstream bad status op={operation} status={status_code}",
            cause=err,
        )

    if isinstance(err, httpx.RequestError):
        return DataAccessError(
            code="UPSTREAM_UNAVAILABLE",
            retriable=True,
            message=f"upstream unavailable op={operation}",
            cause=err,
        )

    if isinstance(err, ValueError):
        return DataAccessError(
            code="UPSTREAM_BAD_RESPONSE",
            retriable=False,
            message=f"upstream bad response op={operation}",
            cause=err,
        )

    return DataAccessError(
        code="UPSTREAM_ERROR",
        retriable=True,
        message=f"upstream error op={operation}",
        cause=err,
    )
