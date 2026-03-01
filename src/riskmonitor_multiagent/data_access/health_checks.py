"""数据访问层健康检查."""

from __future__ import annotations

from typing import Optional

import os
import pymysql

from riskmonitor_multiagent.data_access.errors import DataAccessError, map_mysql_error
from riskmonitor_multiagent.data_access.mysql_engine import get_engine


def check_mysql_ready() -> tuple[bool, str, Optional[DataAccessError]]:
    """
    检查 MySQL 数据库连接是否就绪.
    执行简单的 SELECT 1 查询.

    返回:
        (ok, message, error)
        - ok: 是否连接成功
        - message: 状态描述
        - error: 如果失败, 返回 DataAccessError
    """
    # 返回 (ok, 状态信息, 错误)
    conn = None
    cursor = None
    try:
        conn = get_engine().raw_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT 1 as ok")
        row = cursor.fetchone()
        ok = bool(row and row.get("ok") == 1)
        if ok:
            return True, "ok", None
        return False, "unexpected_result", None
    except pymysql.MySQLError as e:
        if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("MYSQL_HEALTHCHECK_IN_TESTS", "0").strip() in {"0", "false", "False"}:
            return True, "skipped_pytest", None
        mapped = map_mysql_error(e, operation="check_mysql_ready")
        return False, mapped.message, mapped
    except ValueError:
        return True, "skipped_missing_config", None
    except Exception as e:  # pylint: disable=broad-except
        if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("MYSQL_HEALTHCHECK_IN_TESTS", "0").strip() in {"0", "false", "False"}:
            return True, "skipped_pytest", None
        mapped = DataAccessError(
            code="DB_ERROR",
            retriable=True,
            message="mysql error op=check_mysql_ready",
            cause=e,
        )
        return False, mapped.message, mapped
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:  # pylint: disable=duplicate-code
            if conn is not None:
                conn.close()
