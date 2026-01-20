"""告警生成服务.

说明:
- 基于 breaches 生成 alert payload
- 不涉及 IO
"""

from __future__ import annotations

import uuid
from typing import Any


def build_alerts(
    desk: str,
    as_of: str,
    breaches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    根据 Breaches 生成告警列表.
    目前实现为简单的聚合告警.

    参数:
        desk: 交易台名称
        as_of: 计算日期
        breaches: 违规记录列表

    返回:
        告警列表
    """
    alerts: list[dict[str, Any]] = []
    if breaches:
        alerts.append(
            {
                "alert_id": uuid.uuid4().hex,
                "severity": "high",
                "desk": desk,
                "as_of": as_of,
                "breach_count": len(breaches),
                "message": "desk exposure breach detected",
            }
        )
    return alerts
