"""
事件契约定义.

为 7.4 的事件驱动协作提供统一 schema.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from riskmonitor_multiagent.utils import is_non_empty_str

EVENT_SCHEMA_VERSION = "event.v1"
EVENT_PRIORITY_VALUES = {"low", "normal", "high", "critical"}


class EventType(Enum):
    """事件类型枚举."""

    TASK_CREATED = "task_created"
    TOOL_FINISHED = "tool_finished"
    RISK_BREACH_DETECTED = "risk_breach_detected"
    APPROVAL_REQUIRED = "approval_required"
    HUMAN_FEEDBACK_RECEIVED = "human_feedback_received"
    MODERATOR_DECISION = "moderator_decision"
    CONFLICT_DETECTED = "conflict_detected"
    ARBITRATION_RESOLVED = "arbitration_resolved"
    CRON_TRIGGERED = "cron_triggered"


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    """归一化事件并补默认值."""
    out = dict(event) if isinstance(event, dict) else {}
    out.setdefault("schema_version", EVENT_SCHEMA_VERSION)
    out.setdefault("event_id", f"evt_{uuid.uuid4().hex[:12]}")
    out.setdefault("event_type", EventType.TASK_CREATED.value)
    out.setdefault("source_agent", "unknown")
    out.setdefault("target_agent", None)
    out.setdefault("payload", {})
    out.setdefault("timestamp_ms", time.time_ns() // 1_000_000)
    out.setdefault("correlation_id", None)
    out.setdefault("causation_id", None)
    out.setdefault("priority", "normal")
    out.setdefault("requires_ack", False)
    return out


def validate_event(event: dict[str, Any]) -> tuple[bool, list[str]]:
    """验证事件结构."""
    if not isinstance(event, dict):
        return False, ["event must be dict"]

    errors: list[str] = []

    if event.get("schema_version") not in {None, EVENT_SCHEMA_VERSION}:
        errors.append("bad_schema_version")

    if not is_non_empty_str(event.get("event_id")):
        errors.append("bad_event_id")

    try:
        EventType(event.get("event_type"))
    except ValueError:
        errors.append("bad_event_type")

    if not is_non_empty_str(event.get("source_agent")):
        errors.append("bad_source_agent")

    target_agent = event.get("target_agent")
    if target_agent is not None and not is_non_empty_str(target_agent):
        errors.append("bad_target_agent")

    payload = event.get("payload")
    if payload is not None and not isinstance(payload, dict):
        errors.append("bad_payload")

    timestamp_ms = event.get("timestamp_ms")
    try:
        if int(timestamp_ms) <= 0:
            errors.append("bad_timestamp_ms")
    except (TypeError, ValueError):
        errors.append("bad_timestamp_ms")

    correlation_id = event.get("correlation_id")
    if correlation_id is not None and not is_non_empty_str(correlation_id):
        errors.append("bad_correlation_id")

    causation_id = event.get("causation_id")
    if causation_id is not None and not is_non_empty_str(causation_id):
        errors.append("bad_causation_id")

    if event.get("priority") not in EVENT_PRIORITY_VALUES:
        errors.append("bad_priority")

    requires_ack = event.get("requires_ack")
    if not isinstance(requires_ack, bool):
        errors.append("bad_requires_ack")

    return len(errors) == 0, errors


def new_event(
    *,
    event_type: EventType | str,
    source_agent: str,
    payload: dict[str, Any] | None = None,
    target_agent: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    priority: str = "normal",
    requires_ack: bool = False,
) -> dict[str, Any]:
    """构造标准事件."""
    event_value = event_type.value if isinstance(event_type, EventType) else str(event_type)
    return normalize_event(
        {
            "event_type": event_value,
            "source_agent": source_agent,
            "target_agent": target_agent,
            "payload": payload or {},
            "correlation_id": correlation_id,
            "causation_id": causation_id,
            "priority": priority,
            "requires_ack": requires_ack,
        }
    )
