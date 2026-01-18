"""限额判断服务.

说明:
- 只包含纯业务判断
- 不涉及 IO
"""

from __future__ import annotations

from typing import Any


def build_abs_delta_breaches(total_delta: float, abs_delta_limit: float) -> list[dict[str, Any]]:
    """
    检查总 Delta 是否超过绝对值限额.

    Args:
        total_delta: 总 Delta
        abs_delta_limit: Delta 绝对值限额

    Returns:
        违规记录列表 (如果未违规为空列表)
    """
    breaches: list[dict[str, Any]] = []
    if abs(float(total_delta)) > float(abs_delta_limit):
        breaches.append(
            {
                "type": "ABS_DELTA_LIMIT",
                "metric": "total_delta",
                "value": float(total_delta),
                "threshold": float(abs_delta_limit),
                "message": "desk total_delta breached abs_delta_limit",
            }
        )
    return breaches
