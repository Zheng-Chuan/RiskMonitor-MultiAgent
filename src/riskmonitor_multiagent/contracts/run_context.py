"""
运行上下文契约.

为用户显式任务和系统事件提供统一 run 上下文.
"""

from __future__ import annotations

from typing import Any

from riskmonitor_multiagent.utils import is_non_empty_str
from riskmonitor_multiagent.utils.ids import new_run_id

RUN_CONTEXT_SCHEMA_VERSION = "run_context.v1"
ENTRY_TYPE_VALUES = {"user_task", "system_event"}


def normalize_run_context(run_context: dict[str, Any]) -> dict[str, Any]:
    """归一化运行上下文."""
    out = dict(run_context) if isinstance(run_context, dict) else {}
    out.setdefault("schema_version", RUN_CONTEXT_SCHEMA_VERSION)
    out.setdefault("run_id", new_run_id("run"))
    out.setdefault("entry_type", "user_task")
    out.setdefault("task_id", None)
    out.setdefault("trigger_event_id", None)
    out.setdefault("trigger_reason", None)
    out.setdefault("trigger_evidence", {})
    out.setdefault("route_decision", {})
    out.setdefault("metadata", {})
    return out


def validate_run_context(run_context: dict[str, Any]) -> tuple[bool, list[str]]:
    """验证运行上下文."""
    if not isinstance(run_context, dict):
        return False, ["run_context must be dict"]

    errors: list[str] = []
    if run_context.get("schema_version") not in {None, RUN_CONTEXT_SCHEMA_VERSION}:
        errors.append("bad_schema_version")

    if not is_non_empty_str(run_context.get("run_id")):
        errors.append("bad_run_id")

    if run_context.get("entry_type") not in ENTRY_TYPE_VALUES:
        errors.append("bad_entry_type")

    task_id = run_context.get("task_id")
    if task_id is not None and not is_non_empty_str(task_id):
        errors.append("bad_task_id")

    trigger_event_id = run_context.get("trigger_event_id")
    if trigger_event_id is not None and not is_non_empty_str(trigger_event_id):
        errors.append("bad_trigger_event_id")

    trigger_reason = run_context.get("trigger_reason")
    if trigger_reason is not None and not is_non_empty_str(trigger_reason):
        errors.append("bad_trigger_reason")

    if not isinstance(run_context.get("trigger_evidence"), dict):
        errors.append("bad_trigger_evidence")

    if not isinstance(run_context.get("route_decision"), dict):
        errors.append("bad_route_decision")

    if not isinstance(run_context.get("metadata"), dict):
        errors.append("bad_metadata")

    return len(errors) == 0, errors


def new_run_context(
    *,
    entry_type: str,
    task_id: str | None = None,
    trigger_event_id: str | None = None,
    trigger_reason: str | None = None,
    trigger_evidence: dict[str, Any] | None = None,
    route_decision: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """创建标准运行上下文."""
    return normalize_run_context(
        {
            "run_id": run_id or new_run_id("run"),
            "entry_type": entry_type,
            "task_id": task_id,
            "trigger_event_id": trigger_event_id,
            "trigger_reason": trigger_reason,
            "trigger_evidence": trigger_evidence or {},
            "route_decision": route_decision or {},
            "metadata": metadata or {},
        }
    )
