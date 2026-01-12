"""限额判断服务.

说明:
- 只包含纯业务判断
- 不涉及 IO
"""

from __future__ import annotations

from typing import Any


def build_abs_delta_breaches(total_delta: float, abs_delta_limit: float) -> list[dict[str, Any]]:
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
