"""Data access health checks."""

from __future__ import annotations

from typing import Optional

import pymysql

from riskmonitor_mcp.data_access.errors import DataAccessError, map_mysql_error
from riskmonitor_mcp.data_access.mysql_engine import get_engine


def check_mysql_ready() -> tuple[bool, str, Optional[DataAccessError]]:
    # 返回 (ok, message, error)
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
        mapped = map_mysql_error(e, operation="check_mysql_ready")
        return False, mapped.message, mapped
    except Exception as e:  # pylint: disable=broad-except
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
        finally:
            if conn is not None:
                conn.close()
