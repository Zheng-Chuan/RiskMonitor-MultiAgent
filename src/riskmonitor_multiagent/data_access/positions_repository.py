"""头寸数据访问.

说明:
- 封装 positions 表的只读查询
- 统一连接获取与资源释放
- 返回 dict 行结构以兼容上层逻辑
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pymysql

from riskmonitor_multiagent.data_access.errors import DataAccessError, map_mysql_error
from riskmonitor_multiagent.data_access.mysql_engine import get_engine


def fetch_all_positions() -> list[dict[str, Any]]:  # pylint: disable=duplicate-code
    """
    获取所有头寸记录.
    按 entry_date 倒序排列.

    返回:
        头寸字典列表
    """
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
    retries: int = 3,
    delay: float = 0.5
) -> list[dict[str, Any]]:
    """
    带重试机制的 Desk 头寸查询.
    用于监控场景, 防止网络抖动导致查询失败.

    参数:
        desk: 交易台名称
        retries: 重试次数
        delay: 重试间隔(秒)

    返回:
        头寸列表
    """
    for i in range(retries):
        try:
            return fetch_positions_by_desk_for_monitoring(desk)
        except DataAccessError as e:
            if i == retries - 1:
                raise e
            await asyncio.sleep(delay)
    return []


def fetch_positions_by_trader(
    trader_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> list[dict[str, Any]]:
    """
    按 Trader ID 查询头寸.

    参数:
        trader_id: 交易员 ID
        start_date: 开始日期
        end_date: 结束日期
        limit: 限制条数
        offset: 偏移量

    返回:
        头寸列表
    """
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
    """
    按 Desk 查询头寸.

    参数:
        desk_name: 交易台名称
        start_date: 开始日期
        end_date: 结束日期
        limit: 限制条数
        offset: 偏移量

    返回:
        头寸列表
    """
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
    """
    按 Desk 查询头寸 (无重试版, 供底层调用).
    仅根据 desk 过滤, 不分页, 用于全量计算风险.

    参数:
        desk: 交易台名称

    返回:
        头寸列表
    """
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
    """
    获取整个组合的总 Delta.

    返回:
        总 Delta 值
    """
    conn = None
    cursor = None
    try:
        conn = get_engine().raw_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        sql = """
            SELECT SUM(delta) as total_delta
            FROM positions
        """
        cursor.execute(sql)
        row = cursor.fetchone()
        if row and row["total_delta"] is not None:
            return float(row["total_delta"])
        return 0.0
    except pymysql.MySQLError as e:
        raise map_mysql_error(e, operation="fetch_total_delta") from e
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            if conn is not None:
                conn.close()


def fetch_desk_delta_summary() -> list[dict[str, Any]]:
    """
    按 Desk 获取 Delta 汇总.

    返回:
        包含 desk, desk_delta, position_count 的列表
    """
    conn = None
    cursor = None
    try:
        conn = get_engine().raw_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        sql = """
            SELECT
                desk,
                SUM(delta) as desk_delta,
                COUNT(*) as position_count
            FROM positions
            GROUP BY desk
        """
        cursor.execute(sql)
        return cursor.fetchall()
    except pymysql.MySQLError as e:
        raise map_mysql_error(e, operation="fetch_desk_delta_summary") from e
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            if conn is not None:
                conn.close()
