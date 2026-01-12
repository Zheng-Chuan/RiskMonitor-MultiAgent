"""
告警数据访问层

Week4: 可观测与告警闭环
提供告警记录的数据库操作
"""

from typing import List, Dict, Any, Optional
from sqlalchemy import text
from riskmonitor_mcp.data_access.mysql_engine import get_engine
from riskmonitor_mcp.data_access.errors import map_mysql_error


def save_alert(alert: Dict[str, Any]) -> None:
    """
    保存告警记录到数据库

    Args:
        alert: 告警字典, 包含所有字段

    Raises:
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
        with engine.connect() as conn:
            conn.execute(sql, alert)
            conn.commit()
    except Exception as e:
        raise map_mysql_error(e, operation="save_alert") from e


def save_alerts_batch(alerts: List[Dict[str, Any]]) -> None:
    """
    批量保存告警记录

    Args:
        alerts: 告警列表

    Raises:
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
        with engine.connect() as conn:
            conn.execute(sql, alerts)
            conn.commit()
    except Exception as e:
        raise map_mysql_error(e, operation="save_alerts_batch") from e


def get_alert_by_id(alert_id: str) -> Optional[Dict[str, Any]]:
    """
    根据 alert_id 查询告警记录

    Args:
        alert_id: 告警ID

    Returns:
        告警字典, 如果不存在返回 None

    Raises:
        DataAccessError: 数据库操作失败
    """
    engine = get_engine()
    
    sql = text("""
        SELECT * FROM alerts WHERE alert_id = :alert_id
    """)

    try:
        with engine.connect() as conn:
            result = conn.execute(sql, {"alert_id": alert_id})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
    except Exception as e:
        raise map_mysql_error(e, operation="get_alert_by_id") from e


def get_alerts_by_request_id(request_id: str) -> List[Dict[str, Any]]:
    """
    根据 request_id 查询所有关联的告警记录

    Args:
        request_id: 请求ID

    Returns:
        告警列表

    Raises:
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
            result = conn.execute(sql, {"request_id": request_id})
            return [dict(row._mapping) for row in result.fetchall()]
    except Exception as e:
        raise map_mysql_error(e, operation="get_alerts_by_request_id") from e


def get_recent_alerts(
    limit: int = 100,
    severity: Optional[str] = None,
    desk: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    查询最近的告警记录

    Args:
        limit: 返回记录数上限
        severity: 可选, 按告警级别过滤
        desk: 可选, 按交易台过滤

    Returns:
        告警列表

    Raises:
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
            result = conn.execute(sql, params)
            return [dict(row._mapping) for row in result.fetchall()]
    except Exception as e:
        raise map_mysql_error(e, operation="get_recent_alerts") from e
