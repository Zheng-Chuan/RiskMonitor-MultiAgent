from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from riskmonitor_multiagent.contracts.agent_messages import (
    AGENT_COMMAND_SCHEMA_VERSION,
    AGENT_RECEIPT_SCHEMA_VERSION,
    validate_agent_command,
)
from riskmonitor_multiagent.data_access import alerts_repository
from riskmonitor_multiagent.data_access import positions_repository
from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms
from riskmonitor_multiagent.orchestration.observation_tools import (
    observe_chroma_health,
    observe_kafka_lag_estimate,
    observe_mysql_health,
    observe_service_metrics,
)
from riskmonitor_multiagent.orchestration.tool_registry import ToolMeta, get_tool_meta


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: dict[str, Any]
    evidence: dict[str, Any]
    artifacts: list[dict[str, Any]]
    error: Optional[str]
    latency_ms: float


_ENGINEER_ALLOWLIST: dict[str, Callable[[dict[str, Any]], ToolResult]] = {}
_ANALYST_ALLOWLIST: dict[str, Callable[[dict[str, Any]], ToolResult]] = {}
_MANAGER_ALLOWLIST: dict[str, Callable[[dict[str, Any]], ToolResult]] = {}


def _wrap(action: str, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], ToolResult]:
    def _inner(params: dict[str, Any]) -> ToolResult:
        start = time.monotonic()
        try:
            out = fn(params)
            latency_ms = (time.monotonic() - start) * 1000.0
            return ToolResult(
                ok=True,
                output={"action": action, "result": out},
                evidence={"action": action},
                artifacts=[{"kind": "tool_result", "action": action}],
                error=None,
                latency_ms=float(latency_ms),
            )
        except Exception as e:  # pylint: disable=broad-except
            latency_ms = (time.monotonic() - start) * 1000.0
            return ToolResult(
                ok=False,
                output={"action": action, "result": None},
                evidence={"action": action},
                artifacts=[{"kind": "tool_error", "action": action}],
                error=str(e),
                latency_ms=float(latency_ms),
            )

    return _inner


def _collect_metrics(_: dict[str, Any]) -> dict[str, Any]:
    return observe_service_metrics()


def _mysql_health(_: dict[str, Any]) -> dict[str, Any]:
    return observe_mysql_health()


def _chroma_health(_: dict[str, Any]) -> dict[str, Any]:
    return observe_chroma_health()


def _kafka_lag(params: dict[str, Any]) -> dict[str, Any]:
    ts = params.get("message_ts_ms")
    return observe_kafka_lag_estimate(message_ts_ms=int(ts) if isinstance(ts, (int, str)) and str(ts).isdigit() else None)


def _query_positions_by_desk(params: dict[str, Any]) -> dict[str, Any]:
    desk = params.get("desk")
    if not isinstance(desk, str) or not desk.strip():
        raise ValueError("desk required")
    limit = params.get("limit", 50)
    offset = params.get("offset", 0)
    start_date = params.get("start_date")
    end_date = params.get("end_date")
    positions = positions_repository.fetch_positions_by_desk(
        desk_name=desk,
        start_date=start_date if isinstance(start_date, str) else None,
        end_date=end_date if isinstance(end_date, str) else None,
        limit=int(limit),
        offset=int(offset),
    )
    return {"desk": desk, "position_count": len(positions), "positions": positions}


def _search_similar_alerts(params: dict[str, Any]) -> dict[str, Any]:
    query = params.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query required")
    top_k = params.get("top_k", 5)
    store = ChromaVectorStore()
    results = store.query_alerts(query_text=query, top_k=int(top_k))
    return {
        "query": query,
        "top_k": int(top_k),
        "results": [
            {"alert_id": r.metadata.get("alert_id") or r.doc_id, "similarity": r.similarity, "metadata": r.metadata}
            for r in results
        ],
    }


def _write_alert(params: dict[str, Any]) -> dict[str, Any]:
    alert = params.get("alert")
    if not isinstance(alert, dict):
        raise ValueError("alert required")
    alert_id = alert.get("alert_id")
    if not isinstance(alert_id, str) or not alert_id.strip():
        raise ValueError("alert_id required")
    alerts_repository.save_alert(alert)
    return {"saved": True, "alert_id": alert_id}


_ENGINEER_ALLOWLIST.update(
    {
        "collect_metrics": _wrap("collect_metrics", _collect_metrics),
        "mysql_health": _wrap("mysql_health", _mysql_health),
        "chroma_health": _wrap("chroma_health", _chroma_health),
        "kafka_lag": _wrap("kafka_lag", _kafka_lag),
    }
)

_ANALYST_ALLOWLIST.update(
    {
        "search_similar_alerts": _wrap("search_similar_alerts", _search_similar_alerts),
        "query_positions_by_desk": _wrap("query_positions_by_desk", _query_positions_by_desk),
    }
)

_MANAGER_ALLOWLIST.update(
    {
        "write_alert": _wrap("write_alert", _write_alert),
    }
)


def _rbac_policy_version() -> str:
    return "rbac_policy.v1"


def _is_approved(params: dict[str, Any]) -> bool:
    approval = params.get("approval")
    if not isinstance(approval, dict):
        return False
    return approval.get("approved") is True


def _is_allowed_by_role(*, meta: ToolMeta, target_agent: str) -> bool:
    if target_agent in ("system_engineer", "risk_analyst"):
        return meta.capability == "read_only"
    if target_agent == "manager":
        return meta.capability in ("read_only", "side_effect")
    return False


def execute_agent_command(cmd: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    ok_cmd, errors = validate_agent_command(cmd)
    if not ok_cmd:
        inc_counter("rm_agent_command_invalid_total")
        return {
            "schema_version": AGENT_RECEIPT_SCHEMA_VERSION,
            "run_id": cmd.get("run_id"),
            "command_id": cmd.get("command_id"),
            "target_agent": cmd.get("target_agent"),
            "ok": False,
            "latency_ms": 0.0,
            "evidence": {"command_errors": errors},
            "artifacts": [],
            "error": "invalid_command",
            "output": None,
        }

    action = cmd.get("action")
    params = cmd.get("params") if isinstance(cmd.get("params"), dict) else {}
    target = cmd.get("target_agent")
    timeout_ms = cmd.get("timeout_ms")

    meta = get_tool_meta(str(action))
    if meta is None:
        inc_counter("rm_agent_command_denied_total", labels={"target_agent": str(target), "action": str(action)})
        return {
            "schema_version": AGENT_RECEIPT_SCHEMA_VERSION,
            "run_id": cmd["run_id"],
            "command_id": cmd["command_id"],
            "target_agent": target,
            "ok": False,
            "latency_ms": 0.0,
            "evidence": {"action": action, "timeout_ms": timeout_ms, "reason": "unknown_action", "policy_version": _rbac_policy_version()},
            "artifacts": [],
            "error": "unknown_action",
            "output": None,
        }

    if not _is_allowed_by_role(meta=meta, target_agent=str(target)):
        inc_counter("rm_agent_command_denied_total", labels={"target_agent": str(target), "action": str(action)})
        return {
            "schema_version": AGENT_RECEIPT_SCHEMA_VERSION,
            "run_id": cmd["run_id"],
            "command_id": cmd["command_id"],
            "target_agent": target,
            "ok": False,
            "latency_ms": 0.0,
            "evidence": {
                "action": action,
                "timeout_ms": timeout_ms,
                "reason": "rbac_denied",
                "capability": meta.capability,
                "policy_version": _rbac_policy_version(),
            },
            "artifacts": [],
            "error": "rbac_denied",
            "output": None,
        }

    if meta.capability == "side_effect" and not _is_approved(params):
        inc_counter("rm_agent_command_denied_total", labels={"target_agent": str(target), "action": str(action)})
        return {
            "schema_version": AGENT_RECEIPT_SCHEMA_VERSION,
            "run_id": cmd["run_id"],
            "command_id": cmd["command_id"],
            "target_agent": target,
            "ok": False,
            "latency_ms": 0.0,
            "evidence": {
                "action": action,
                "timeout_ms": timeout_ms,
                "reason": "approval_required",
                "capability": meta.capability,
                "policy_version": _rbac_policy_version(),
            },
            "artifacts": [],
            "error": "approval_required",
            "output": None,
        }

    allowlist = (
        _ENGINEER_ALLOWLIST
        if target == "system_engineer"
        else _ANALYST_ALLOWLIST
        if target == "risk_analyst"
        else _MANAGER_ALLOWLIST
        if target == "manager"
        else {}
    )
    handler = allowlist.get(action)
    if handler is None:
        inc_counter("rm_agent_command_denied_total", labels={"target_agent": str(target), "action": str(action)})
        return {
            "schema_version": AGENT_RECEIPT_SCHEMA_VERSION,
            "run_id": cmd["run_id"],
            "command_id": cmd["command_id"],
            "target_agent": target,
            "ok": False,
            "latency_ms": 0.0,
            "evidence": {
                "action": action,
                "timeout_ms": timeout_ms,
                "reason": "handler_missing",
                "capability": meta.capability,
                "policy_version": _rbac_policy_version(),
            },
            "artifacts": [],
            "error": "handler_missing",
            "output": None,
        }

    result = handler(params)
    observe_ms("rm_agent_command", (time.monotonic() - started) * 1000.0, labels={"target_agent": str(target), "action": str(action)})
    inc_counter("rm_agent_command_total", labels={"target_agent": str(target), "action": str(action), "ok": str(bool(result.ok)).lower()})
    return {
        "schema_version": AGENT_RECEIPT_SCHEMA_VERSION,
        "run_id": cmd["run_id"],
        "command_id": cmd["command_id"],
        "target_agent": target,
        "ok": bool(result.ok),
        "latency_ms": float(result.latency_ms),
        "evidence": dict(result.evidence),
        "artifacts": list(result.artifacts),
        "error": result.error,
        "output": dict(result.output) if isinstance(result.output, dict) else None,
    }


def new_agent_command(
    *,
    run_id: str,
    command_id: str,
    target_agent: str,
    action: str,
    params: dict[str, Any],
    timeout_ms: int,
    expected_output_schema: str,
) -> dict[str, Any]:
    return {
        "schema_version": AGENT_COMMAND_SCHEMA_VERSION,
        "run_id": run_id,
        "command_id": command_id,
        "target_agent": target_agent,
        "action": action,
        "params": params,
        "timeout_ms": int(timeout_ms),
        "expected_output_schema": expected_output_schema,
    }
