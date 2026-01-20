"""
告警规则引擎服务

Week4: 可观测与告警闭环
提供告警规则评估和告警生成功能
"""

from typing import List, Dict, Any
from datetime import datetime
import uuid


def evaluate_desk_delta_breach(
    desk: str,
    abs_delta: float,
    threshold: float,
    request_id: str
) -> List[Dict[str, Any]]:
    """
    评估 desk delta 是否超限并生成告警

    参数:
        desk: 交易台名称
        abs_delta: delta 绝对值
        threshold: 阈值
        request_id: 请求ID

    返回:
        告警列表, 每个告警是一个字典
    """
    alerts = []

    if abs_delta > threshold:
        breach_amount = abs_delta - threshold
        severity = _determine_severity(breach_amount, threshold)

        alert = {
            "alert_id": str(uuid.uuid4()),
            "request_id": request_id,
            "alert_type": "DESK_DELTA_BREACH",
            "severity": severity,
            "desk": desk,
            "trader_id": None,
            "metric_name": "abs_delta",
            "metric_value": abs_delta,
            "threshold_value": threshold,
            "breach_amount": breach_amount,
            "message": (
                f"Desk {desk} delta breach: "
                f"abs_delta={abs_delta:.2f} exceeds threshold={threshold:.2f} "
                f"by {breach_amount:.2f}"
            ),
            "created_at": datetime.utcnow().isoformat(),
            "acknowledged": False,
            "acknowledged_at": None,
            "acknowledged_by": None
        }
        alerts.append(alert)

    return alerts


def _determine_severity(breach_amount: float, threshold: float) -> str:
    """
    根据超限金额确定告警级别

    参数:
        breach_amount: 超限金额
        threshold: 阈值

    返回:
        告警级别: INFO, WARNING, CRITICAL
    """
    breach_ratio = breach_amount / threshold

    if breach_ratio >= 0.5:  # 超限 50% 以上
        return "CRITICAL"
    if breach_ratio >= 0.2:  # 超限 20% 以上
        return "WARNING"
    return "INFO"


def format_alerts_for_response(alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    格式化告警列表用于 MCP 响应

    参数:
        alerts: 告警列表

    返回:
        格式化后的告警列表
    """
    return [
        {
            "alert_id": alert["alert_id"],
            "alert_type": alert["alert_type"],
            "severity": alert["severity"],
            "desk": alert["desk"],
            "metric_name": alert["metric_name"],
            "metric_value": alert["metric_value"],
            "threshold_value": alert["threshold_value"],
            "breach_amount": alert["breach_amount"],
            "message": alert["message"]
        }
        for alert in alerts
    ]
