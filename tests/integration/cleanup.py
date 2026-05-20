"""测试数据清理工具.

提供按前缀/条件清理测试数据的工具函数，
配合 real_db_cursor fixture 使用（事务内操作，测试结束自动回滚）。

也可用于手动清理遗留的测试数据。
"""

from __future__ import annotations


def cleanup_test_positions(cursor, prefix: str = "test-pos-") -> int:
    """清理以指定前缀开头的 position 记录.

    Args:
        cursor: pymysql DictCursor
        prefix: position_id 前缀

    Returns:
        删除的行数
    """
    cursor.execute(
        "DELETE FROM positions WHERE position_id LIKE %s",
        (f"{prefix}%",),
    )
    return cursor.rowcount


def cleanup_test_alerts(cursor, prefix: str = "test-alert-") -> int:
    """清理以指定前缀开头的 alert 记录.

    Args:
        cursor: pymysql DictCursor
        prefix: alert_id 前缀

    Returns:
        删除的行数
    """
    cursor.execute(
        "DELETE FROM alerts WHERE alert_id LIKE %s",
        (f"{prefix}%",),
    )
    return cursor.rowcount


def cleanup_test_audit_events(cursor, actor: str = "test-user") -> int:
    """清理指定 actor 的 audit_event 记录.

    Args:
        cursor: pymysql DictCursor
        actor: actor 字段值

    Returns:
        删除的行数
    """
    cursor.execute(
        "DELETE FROM audit_events WHERE actor = %s",
        (actor,),
    )
    return cursor.rowcount


def cleanup_all_test_data(cursor) -> dict[str, int]:
    """清理所有测试数据（使用默认前缀/条件）.

    Returns:
        各表删除行数的字典
    """
    return {
        "positions": cleanup_test_positions(cursor),
        "alerts": cleanup_test_alerts(cursor),
        "audit_events": cleanup_test_audit_events(cursor),
    }
