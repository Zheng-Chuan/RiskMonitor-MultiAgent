"""头寸数据访问.

说明:
- 封装 positions 表的只读查询
- 统一连接获取与资源释放
- 返回 dict 行结构以兼容上层逻辑
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

import pymysql

from riskmonitor_mcp.data_access.errors import DataAccessError, map_mysql_error
from riskmonitor_mcp.data_access.mysql_engine import get_engine


def fetch_all_positions() -> list[dict[str, Any]]:
    conn = get_engine().raw_connection()
    cursor = None
    try:
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute(
                """
                SELECT position_id, trader_id, desk, security_id,
                       quantity, delta, entry_date, currency
                FROM positions
                ORDER BY entry_date DESC
                """
            )
            return list(cursor.fetchall())
        except pymysql.MySQLError as e:
            raise map_mysql_error(e, operation="fetch_all_positions") from e
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            conn.close()


async def fetch_positions_by_desk_for_monitoring_with_retry(
    desk: str,
) -> list[dict[str, Any]]:
    # 监控链路查询通常是热点, 在此处集中实现最小重试策略.
    db_retries = int(os.getenv("MYSQL_RETRIES", "1"))
    last_error: Optional[BaseException] = None

    for attempt in range(db_retries + 1):
        try:
            return fetch_positions_by_desk_for_monitoring(desk)
        except DataAccessError as e:
            last_error = e
            if not e.retriable:
                raise
            if attempt >= db_retries:
                break
            await asyncio.sleep(min(0.2 * (attempt + 1), 1.0))

    if isinstance(last_error, DataAccessError):
        raise last_error
    raise DataAccessError(
        code="DB_QUERY_FAILED",
        retriable=True,
        message="mysql query failed op=fetch_positions_by_desk_for_monitoring_with_retry",
        cause=last_error,
    )


def fetch_positions_by_trader(
    trader_id: str,
    start_date: Optional[str],
    end_date: Optional[str],
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    query = (
        """
        SELECT position_id, trader_id, desk, security_id,
               quantity, delta, entry_date, currency
        FROM positions
        WHERE trader_id = %s
        """
    )
    params: list[Any] = [trader_id]

    if start_date is not None:
        query += " AND entry_date >= %s"
        params.append(start_date)
    if end_date is not None:
        query += " AND entry_date <= %s"
        params.append(end_date)

    query += " ORDER BY entry_date DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    conn = get_engine().raw_connection()
    cursor = None
    try:
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute(query, tuple(params))
            return list(cursor.fetchall())
        except pymysql.MySQLError as e:
            raise map_mysql_error(e, operation="fetch_positions_by_trader") from e
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            conn.close()


def fetch_positions_by_desk(
    desk_name: str,
    start_date: Optional[str],
    end_date: Optional[str],
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    query = (
        """
        SELECT position_id, trader_id, desk, security_id,
               quantity, delta, entry_date, currency
        FROM positions
        WHERE desk = %s
        """
    )
    params: list[Any] = [desk_name]

    if start_date is not None:
        query += " AND entry_date >= %s"
        params.append(start_date)
    if end_date is not None:
        query += " AND entry_date <= %s"
        params.append(end_date)

    query += " ORDER BY entry_date DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    conn = get_engine().raw_connection()
    cursor = None
    try:
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute(query, tuple(params))
            return list(cursor.fetchall())
        except pymysql.MySQLError as e:
            raise map_mysql_error(e, operation="fetch_positions_by_desk") from e
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            conn.close()


def fetch_positions_by_desk_for_monitoring(desk: str) -> list[dict[str, Any]]:
    conn = get_engine().raw_connection()
    cursor = None
    try:
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute(
                """
                SELECT position_id, trader_id, desk, security_id,
                       quantity, delta, entry_date, currency
                FROM positions
                WHERE desk = %s
                """,
                (desk,),
            )
            return list(cursor.fetchall())
        except pymysql.MySQLError as e:
            raise map_mysql_error(e, operation="fetch_positions_by_desk_for_monitoring") from e
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            conn.close()


def fetch_total_delta() -> float:
    conn = get_engine().raw_connection()
    cursor = None
    try:
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("SELECT SUM(delta) as total_delta FROM positions")
            row = cursor.fetchone()
            if row is None:
                return 0.0
            value = row.get("total_delta")
            return float(value) if value else 0.0
        except pymysql.MySQLError as e:
            raise map_mysql_error(e, operation="fetch_total_delta") from e
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            conn.close()


def fetch_desk_delta_summary() -> list[dict[str, Any]]:
    conn = get_engine().raw_connection()
    cursor = None
    try:
        try:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute(
                """
                SELECT desk, SUM(delta) as desk_delta, COUNT(*) as position_count
                FROM positions
                GROUP BY desk
                ORDER BY ABS(SUM(delta)) DESC
                """
            )
            return list(cursor.fetchall())
        except pymysql.MySQLError as e:
            raise map_mysql_error(e, operation="fetch_desk_delta_summary") from e
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            conn.close()
