"""
告警数据访问层

Week4: 可观测与告警闭环
提供告警记录的数据库操作
"""

from typing import List, Dict, Any, Optional
from sqlalchemy import text
from riskmonitor_multiagent.data_access.mysql_engine import get_engine
from riskmonitor_multiagent.data_access.errors import map_mysql_error


def save_alert(alert: Dict[str, Any]) -> None:
    """
    保存告警记录到数据库

    参数:
        alert: 告警字典, 包含所有字段

    异常:
        DataAccessError: 数据库操作失败
    """
    engine = get_engine()

    sql = text("""
        INSERT INTO alerts (
            alert_id, request_id, alert_type, severity, desk, trader_id,
            metric_name, metric_value, threshold_value, breach_amount,
            message, created_at, acknowledged, acknowledged_at, acknowledged_by
        ) VALUES (
            :alert_id, :request_id, :alert_type, :severity, :desk, :trader_id,
            :metric_name, :metric_value, :threshold_value, :breach_amount,
            :message, :created_at, :acknowledged, :acknowledged_at, :acknowledged_by
        )
    """)

    try:
        with engine.begin() as conn:
            conn.execute(sql, alert)
    except Exception as e:
        raise map_mysql_error(e, operation="save_alert") from e


def save_alerts_batch(alerts: List[Dict[str, Any]]) -> None:
    """
    批量保存告警记录

    参数:
        alerts: 告警列表

    异常:
        DataAccessError: 数据库操作失败
    """
    if not alerts:
        return

    engine = get_engine()

    sql = text("""
        INSERT INTO alerts (
            alert_id, request_id, alert_type, severity, desk, trader_id,
            metric_name, metric_value, threshold_value, breach_amount,
            message, created_at, acknowledged, acknowledged_at, acknowledged_by
        ) VALUES (
            :alert_id, :request_id, :alert_type, :severity, :desk, :trader_id,
            :metric_name, :metric_value, :threshold_value, :breach_amount,
            :message, :created_at, :acknowledged, :acknowledged_at, :acknowledged_by
        )
    """)

    try:
        with engine.begin() as conn:
            for alert in alerts:
                conn.execute(sql, alert)
    except Exception as e:
        raise map_mysql_error(e, operation="save_alerts_batch") from e


def get_alert_by_id(alert_id: str) -> Optional[Dict[str, Any]]:
    """
    根据 alert_id 查询告警记录

    参数:
        alert_id: 告警ID

    返回:
        告警字典, 如果不存在返回 None

    异常:
        DataAccessError: 数据库操作失败
    """
    engine = get_engine()

    sql = text("""
        SELECT * FROM alerts WHERE alert_id = :alert_id
    """)

    try:
        with engine.connect() as conn:
            result = conn.execute(sql, {"alert_id": alert_id}).mappings()
            row = result.fetchone()
            if row:
                return dict(row)
            return None
    except Exception as e:
        raise map_mysql_error(e, operation="get_alert_by_id") from e


def get_alerts_by_request_id(request_id: str) -> List[Dict[str, Any]]:
    """
    根据 request_id 查询所有关联的告警记录

    参数:
        request_id: 请求ID

    返回:
        告警列表

    异常:
        DataAccessError: 数据库操作失败
    """
    engine = get_engine()

    sql = text("""
        SELECT * FROM alerts
        WHERE request_id = :request_id
        ORDER BY created_at DESC
    """)

    try:
        with engine.connect() as conn:
            result = conn.execute(sql, {"request_id": request_id}).mappings()
            return [dict(row) for row in result.fetchall()]
    except Exception as e:
        raise map_mysql_error(e, operation="get_alerts_by_request_id") from e


def get_recent_alerts(
    limit: int = 100,
    severity: Optional[str] = None,
    desk: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    查询最近的告警记录

    参数:
        limit: 返回记录数上限
        severity: 可选, 按告警级别过滤
        desk: 可选, 按交易台过滤

    返回:
        告警列表

    异常:
        DataAccessError: 数据库操作失败
    """
    engine = get_engine()

    conditions = []
    params = {"limit": limit}

    if severity:
        conditions.append("severity = :severity")
        params["severity"] = severity

    if desk:
        conditions.append("desk = :desk")
        params["desk"] = desk

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    sql = text(f"""
        SELECT * FROM alerts
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT :limit
    """)

    try:
        with engine.connect() as conn:
            result = conn.execute(sql, params).mappings()
            return [dict(row) for row in result.fetchall()]
    except Exception as e:
        raise map_mysql_error(e, operation="get_recent_alerts") from e
