from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

ToolCapability = Literal["read_only", "side_effect", "pii", "admin"]

TOOL_REGISTRY_VERSION = "tool_registry.v1"


@dataclass(frozen=True)
class SideEffectPolicy:
    require_approval: bool = True
    require_reason: bool = False
    min_severity: Optional[str] = None


@dataclass(frozen=True)
class ToolMeta:
    action: str
    capability: ToolCapability
    owner: str
    description: str
    risk_level: str
    default_timeout_ms: int
    allowed_targets: Optional[tuple[str, ...]] = None
    side_effect_policy: Optional[SideEffectPolicy] = None


_TOOL_REGISTRY: dict[str, ToolMeta] = {
    "query_all_positions": ToolMeta(
        action="query_all_positions",
        capability="read_only",
        owner="mcp_tools",
        description="query all positions",
        risk_level="low",
        default_timeout_ms=2000,
    ),
    "query_positions_by_trader": ToolMeta(
        action="query_positions_by_trader",
        capability="read_only",
        owner="mcp_tools",
        description="query positions by trader",
        risk_level="low",
        default_timeout_ms=2000,
    ),
    "calculate_total_delta": ToolMeta(
        action="calculate_total_delta",
        capability="read_only",
        owner="mcp_tools",
        description="calculate total delta",
        risk_level="low",
        default_timeout_ms=2000,
    ),
    "monitor_desk_exposure": ToolMeta(
        action="monitor_desk_exposure",
        capability="read_only",
        owner="mcp_tools",
        description="monitor desk exposure and build alerts",
        risk_level="low",
        default_timeout_ms=3000,
    ),
    "get_service_metrics": ToolMeta(
        action="get_service_metrics",
        capability="read_only",
        owner="mcp_tools",
        description="get service metrics summary",
        risk_level="low",
        default_timeout_ms=1000,
    ),
    "submit_alerts": ToolMeta(
        action="submit_alerts",
        capability="side_effect",
        owner="mcp_tools",
        description="write alerts to database",
        risk_level="high",
        default_timeout_ms=3000,
        side_effect_policy=SideEffectPolicy(require_approval=True, require_reason=False, min_severity=None),
    ),
    "collect_metrics": ToolMeta(
        action="collect_metrics",
        capability="read_only",
        owner="system_engineer",
        description="collect service metrics",
        risk_level="low",
        default_timeout_ms=1000,
        allowed_targets=("system_engineer",),
    ),
    "mysql_health": ToolMeta(
        action="mysql_health",
        capability="read_only",
        owner="system_engineer",
        description="mysql health check",
        risk_level="low",
        default_timeout_ms=1000,
        allowed_targets=("system_engineer",),
    ),
    "chroma_health": ToolMeta(
        action="chroma_health",
        capability="read_only",
        owner="system_engineer",
        description="chroma health check",
        risk_level="low",
        default_timeout_ms=1000,
        allowed_targets=("system_engineer",),
    ),
    "kafka_lag": ToolMeta(
        action="kafka_lag",
        capability="read_only",
        owner="system_engineer",
        description="kafka lag estimate",
        risk_level="low",
        default_timeout_ms=1000,
        allowed_targets=("system_engineer",),
    ),
    "query_positions_by_desk": ToolMeta(
        action="query_positions_by_desk",
        capability="read_only",
        owner="risk_analyst",
        description="query positions by desk",
        risk_level="low",
        default_timeout_ms=1500,
        allowed_targets=("risk_analyst",),
    ),
    "search_similar_alerts": ToolMeta(
        action="search_similar_alerts",
        capability="read_only",
        owner="risk_analyst",
        description="search similar alerts in chroma",
        risk_level="low",
        default_timeout_ms=1500,
        allowed_targets=("risk_analyst",),
    ),
    "write_alert": ToolMeta(
        action="write_alert",
        capability="side_effect",
        owner="manager",
        description="write alert record to database",
        risk_level="high",
        default_timeout_ms=2000,
        allowed_targets=("manager",),
        side_effect_policy=SideEffectPolicy(require_approval=True, require_reason=True, min_severity="INFO"),
    ),
}


def get_tool_meta(action: str) -> Optional[ToolMeta]:
    if not isinstance(action, str) or not action:
        return None
    return _TOOL_REGISTRY.get(action)


def is_side_effect_action(action: str) -> bool:
    meta = get_tool_meta(action)
    return bool(meta is not None and meta.capability == "side_effect")
