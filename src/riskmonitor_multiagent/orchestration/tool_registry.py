from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

ToolCapability = Literal["read_only", "side_effect", "pii", "admin"]


@dataclass(frozen=True)
class ToolMeta:
    action: str
    capability: ToolCapability
    owner: str
    description: str
    risk_level: str
    default_timeout_ms: int


_TOOL_REGISTRY: dict[str, ToolMeta] = {
    "collect_metrics": ToolMeta(
        action="collect_metrics",
        capability="read_only",
        owner="system_engineer",
        description="collect service metrics",
        risk_level="low",
        default_timeout_ms=1000,
    ),
    "mysql_health": ToolMeta(
        action="mysql_health",
        capability="read_only",
        owner="system_engineer",
        description="mysql health check",
        risk_level="low",
        default_timeout_ms=1000,
    ),
    "chroma_health": ToolMeta(
        action="chroma_health",
        capability="read_only",
        owner="system_engineer",
        description="chroma health check",
        risk_level="low",
        default_timeout_ms=1000,
    ),
    "kafka_lag": ToolMeta(
        action="kafka_lag",
        capability="read_only",
        owner="system_engineer",
        description="kafka lag estimate",
        risk_level="low",
        default_timeout_ms=1000,
    ),
    "query_positions_by_desk": ToolMeta(
        action="query_positions_by_desk",
        capability="read_only",
        owner="risk_analyst",
        description="query positions by desk",
        risk_level="low",
        default_timeout_ms=1500,
    ),
    "search_similar_alerts": ToolMeta(
        action="search_similar_alerts",
        capability="read_only",
        owner="risk_analyst",
        description="search similar alerts in chroma",
        risk_level="low",
        default_timeout_ms=1500,
    ),
    "write_alert": ToolMeta(
        action="write_alert",
        capability="side_effect",
        owner="manager",
        description="write alert record to database",
        risk_level="high",
        default_timeout_ms=2000,
    ),
}


def get_tool_meta(action: str) -> Optional[ToolMeta]:
    if not isinstance(action, str) or not action:
        return None
    return _TOOL_REGISTRY.get(action)


def is_side_effect_action(action: str) -> bool:
    meta = get_tool_meta(action)
    return bool(meta is not None and meta.capability == "side_effect")

