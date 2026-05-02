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
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms, set_gauge
from riskmonitor_multiagent.orchestration.observation_tools import (
    observe_chroma_health,
    observe_kafka_lag_estimate,
    observe_mysql_health,
    observe_service_metrics,
)
from riskmonitor_multiagent.orchestration.tool_registry import SideEffectPolicy, ToolMeta, get_tool_meta
from riskmonitor_multiagent.services import alert_rules_service
from riskmonitor_multiagent.services.breach_service import build_abs_delta_breaches
from riskmonitor_multiagent.services.exposure_service import compute_exposure
from riskmonitor_multiagent.tools.tool_helpers import (
    normalize_as_of,
    normalize_limit_offset,
    normalize_positions,
    normalize_str,
    validate_optional_yyyy_mm_dd,
)


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

RBAC_POLICY_VERSION = "rbac_policy.v1"

_SEVERITY_RANK = {"INFO": 1, "WARNING": 2, "CRITICAL": 3}


def _severity_at_least(actual: Any, minimum: Any) -> bool:
    if not isinstance(actual, str) or not isinstance(minimum, str):
        return False
    a = _SEVERITY_RANK.get(actual.strip().upper())
    m = _SEVERITY_RANK.get(minimum.strip().upper())
    if a is None or m is None:
        return False
    return int(a) >= int(m)


def _get_side_effect_policy(meta: ToolMeta) -> SideEffectPolicy:
    pol = meta.side_effect_policy
    return pol if isinstance(pol, SideEffectPolicy) else SideEffectPolicy()


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


def _get_service_metrics(_: dict[str, Any]) -> dict[str, Any]:
    return observe_service_metrics()


def _mysql_health(_: dict[str, Any]) -> dict[str, Any]:
    return observe_mysql_health()


def _chroma_health(_: dict[str, Any]) -> dict[str, Any]:
    return observe_chroma_health()


def _kafka_lag(params: dict[str, Any]) -> dict[str, Any]:
    ts = params.get("message_ts_ms")
    out = observe_kafka_lag_estimate(message_ts_ms=int(ts) if isinstance(ts, (int, str)) and str(ts).isdigit() else None)
    lag_ms = out.get("lag_ms")
    if isinstance(lag_ms, int):
        set_gauge("rm_kafka_message_lag_ms", float(lag_ms))
    return out


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


def _query_all_positions(_: dict[str, Any]) -> dict[str, Any]:
    positions = positions_repository.fetch_all_positions()
    normalized_positions = normalize_positions(positions)
    return {
        "position_count": len(normalized_positions),
        "positions": normalized_positions,
    }


def _query_positions_by_trader(params: dict[str, Any]) -> dict[str, Any]:
    trader_id = params.get("trader_id")
    if not isinstance(trader_id, str) or not trader_id.strip():
        raise ValueError("trader_id required")
    start_date = params.get("start_date")
    end_date = params.get("end_date")
    validate_optional_yyyy_mm_dd(start_date if isinstance(start_date, str) else None, "start_date")
    validate_optional_yyyy_mm_dd(end_date if isinstance(end_date, str) else None, "end_date")
    limit, offset = normalize_limit_offset(params.get("limit"), params.get("offset"))
    positions = positions_repository.fetch_positions_by_trader(
        trader_id=trader_id.strip(),
        start_date=start_date if isinstance(start_date, str) else None,
        end_date=end_date if isinstance(end_date, str) else None,
        limit=limit,
        offset=offset,
    )
    normalized_positions = normalize_positions(positions)
    total_delta = sum(float(pos.get("delta") or 0.0) for pos in normalized_positions)
    return {
        "trader_id": trader_id.strip(),
        "position_count": len(normalized_positions),
        "total_delta": float(total_delta),
        "positions": normalized_positions,
        "message": f"未找到交易员 {trader_id.strip()} 的头寸记录." if not normalized_positions else None,
    }


def _calculate_total_delta(_: dict[str, Any]) -> dict[str, Any]:
    total_delta = positions_repository.fetch_total_delta()
    desk_deltas = positions_repository.fetch_desk_delta_summary()
    normalized_desks = [
        {
            "desk": desk.get("desk"),
            "desk_delta": float(desk.get("desk_delta") or 0.0),
            "position_count": int(desk.get("position_count") or 0),
        }
        for desk in desk_deltas
    ]
    return {
        "total_delta": float(total_delta),
        "by_desk": normalized_desks,
    }


def _monitor_desk_exposure(params: dict[str, Any]) -> dict[str, Any]:
    desk = normalize_str(params.get("desk") if isinstance(params.get("desk"), str) else None, "")
    if not desk:
        raise ValueError("desk required")

    as_of = normalize_as_of(params.get("as_of") if isinstance(params.get("as_of"), str) else None)
    market_snapshot_url = normalize_str(params.get("market_snapshot_url") if isinstance(params.get("market_snapshot_url"), str) else None, "embedded")
    snapshot = (
        params.get("market_snapshot")
        if isinstance(params.get("market_snapshot"), dict)
        else {"as_of": as_of, "prices": {}, "fx_rates": {"USD": 1.0}}
    )
    abs_delta_limit = float(params.get("abs_delta_limit") or 1000000.0)
    positions = positions_repository.fetch_positions_by_desk_for_monitoring(desk)
    total_delta, total_pv_usd, by_currency = compute_exposure(positions, snapshot)
    breaches = build_abs_delta_breaches(total_delta=total_delta, abs_delta_limit=abs_delta_limit)
    abs_delta = abs(total_delta)
    request_id = params.get("request_id") if isinstance(params.get("request_id"), str) else ""
    alert_records = alert_rules_service.evaluate_desk_delta_breach(
        desk=desk,
        abs_delta=abs_delta,
        threshold=abs_delta_limit,
        request_id=request_id,
    )
    formatted_alerts = alert_rules_service.format_alerts_for_response(alert_records)
    return {
        "as_of": as_of,
        "desk": desk,
        "exposure": {
            "pv_usd": float(total_pv_usd),
            "total_delta": float(total_delta),
            "total_vega": 0.0,
            "by_currency": by_currency,
            "position_count": len(positions),
        },
        "limits": {"abs_delta_limit": float(abs_delta_limit)},
        "breaches": breaches,
        "alerts": formatted_alerts,
        "market_snapshot": {
            "source_url": market_snapshot_url,
            "as_of": snapshot.get("as_of"),
        },
    }


def _search_similar_alerts(params: dict[str, Any]) -> dict[str, Any]:
    from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore

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


def _submit_alerts(params: dict[str, Any]) -> dict[str, Any]:
    alerts = params.get("alerts")
    if not isinstance(alerts, list):
        raise ValueError("alerts required")
    if not alerts:
        return {"saved": 0}
    alerts_repository.save_alerts_batch(alerts)
    return {"saved": len(alerts)}


_ENGINEER_ALLOWLIST.update(
    {
        "collect_metrics": _wrap("collect_metrics", _collect_metrics),
        "get_service_metrics": _wrap("get_service_metrics", _get_service_metrics),
        "mysql_health": _wrap("mysql_health", _mysql_health),
        "chroma_health": _wrap("chroma_health", _chroma_health),
        "kafka_lag": _wrap("kafka_lag", _kafka_lag),
    }
)

_ANALYST_ALLOWLIST.update(
    {
        "query_all_positions": _wrap("query_all_positions", _query_all_positions),
        "query_positions_by_trader": _wrap("query_positions_by_trader", _query_positions_by_trader),
        "calculate_total_delta": _wrap("calculate_total_delta", _calculate_total_delta),
        "monitor_desk_exposure": _wrap("monitor_desk_exposure", _monitor_desk_exposure),
        "search_similar_alerts": _wrap("search_similar_alerts", _search_similar_alerts),
        "query_positions_by_desk": _wrap("query_positions_by_desk", _query_positions_by_desk),
    }
)

_MANAGER_ALLOWLIST.update(
    {
        "write_alert": _wrap("write_alert", _write_alert),
        "submit_alerts": _wrap("submit_alerts", _submit_alerts),
    }
)


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


def _is_allowed_by_meta(*, meta: ToolMeta, target_agent: str) -> bool:
    if isinstance(meta.allowed_targets, tuple) and len(meta.allowed_targets) > 0:
        return target_agent in set(meta.allowed_targets)
    if meta.owner in {"system_engineer", "risk_analyst", "manager"}:
        return target_agent == meta.owner
    return True


def _resolve_approval_state(*, meta: ToolMeta, params: dict[str, Any], ok: bool, error: str | None) -> str:
    if meta.capability != "side_effect":
        return "not_required"
    if not _get_side_effect_policy(meta).require_approval:
        return "not_required"
    if _is_approved(params):
        return "approved" if ok else "approved_but_failed"
    if error == "approval_required":
        return "required"
    return "not_approved"


def _build_receipt(
    *,
    cmd: dict[str, Any],
    meta: ToolMeta | None,
    ok: bool,
    latency_ms: float,
    evidence: dict[str, Any],
    artifacts: list[dict[str, Any]],
    error: str | None,
    outputs: dict[str, Any] | None,
    status: str,
) -> dict[str, Any]:
    tool_name = str(cmd.get("action") or "")
    params = cmd.get("params") if isinstance(cmd.get("params"), dict) else {}
    target_agent = cmd.get("target_agent")
    side_effect = bool(meta is not None and meta.capability == "side_effect")
    approval_state = _resolve_approval_state(meta=meta, params=params, ok=ok, error=error) if meta is not None else "unknown"
    normalized_outputs = dict(outputs) if isinstance(outputs, dict) else None
    return {
        "schema_version": AGENT_RECEIPT_SCHEMA_VERSION,
        "run_id": cmd.get("run_id"),
        "command_id": cmd.get("command_id"),
        "target_agent": target_agent,
        "tool_name": tool_name,
        "inputs": dict(params),
        "outputs": normalized_outputs,
        "status": status,
        "ok": bool(ok),
        "latency_ms": float(latency_ms),
        "evidence": dict(evidence),
        "artifacts": list(artifacts),
        "error": error,
        "output": normalized_outputs,
        "side_effect": side_effect,
        "approval_state": approval_state,
    }


def execute_agent_command(cmd: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    ok_cmd, errors = validate_agent_command(cmd)
    if not ok_cmd:
        inc_counter("rm_agent_command_invalid_total")
        return _build_receipt(
            cmd=cmd,
            meta=None,
            ok=False,
            latency_ms=0.0,
            evidence={"command_errors": errors},
            artifacts=[],
            error="invalid_command",
            outputs=None,
            status="failed",
        )

    action = cmd.get("action")
    params = cmd.get("params") if isinstance(cmd.get("params"), dict) else {}
    target = cmd.get("target_agent")
    timeout_ms = cmd.get("timeout_ms")

    meta = get_tool_meta(str(action))
    if meta is None:
        inc_counter("rm_agent_command_denied_total", labels={"target_agent": str(target), "action": str(action)})
        return _build_receipt(
            cmd=cmd,
            meta=None,
            ok=False,
            latency_ms=0.0,
            evidence={"action": action, "timeout_ms": timeout_ms, "reason": "unknown_action", "policy_version": RBAC_POLICY_VERSION},
            artifacts=[],
            error="unknown_action",
            outputs=None,
            status="failed",
        )

    if not _is_allowed_by_role(meta=meta, target_agent=str(target)):
        inc_counter("rm_agent_command_denied_total", labels={"target_agent": str(target), "action": str(action)})
        inc_counter("rm_rbac_denied_total", labels={"target_agent": str(target), "action": str(action), "capability": meta.capability})
        return _build_receipt(
            cmd=cmd,
            meta=meta,
            ok=False,
            latency_ms=0.0,
            evidence={
                "action": action,
                "timeout_ms": timeout_ms,
                "reason": "rbac_denied",
                "capability": meta.capability,
                "policy_version": RBAC_POLICY_VERSION,
            },
            artifacts=[],
            error="rbac_denied",
            outputs=None,
            status="failed",
        )

    if not _is_allowed_by_meta(meta=meta, target_agent=str(target)):
        inc_counter("rm_agent_command_denied_total", labels={"target_agent": str(target), "action": str(action)})
        inc_counter("rm_rbac_denied_total", labels={"target_agent": str(target), "action": str(action), "capability": meta.capability})
        return _build_receipt(
            cmd=cmd,
            meta=meta,
            ok=False,
            latency_ms=0.0,
            evidence={
                "action": action,
                "timeout_ms": timeout_ms,
                "reason": "role_not_allowed",
                "capability": meta.capability,
                "owner": meta.owner,
                "allowed_targets": list(meta.allowed_targets) if isinstance(meta.allowed_targets, tuple) else None,
                "policy_version": RBAC_POLICY_VERSION,
            },
            artifacts=[],
            error="rbac_denied",
            outputs=None,
            status="failed",
        )

    if meta.capability == "side_effect":
        pol = _get_side_effect_policy(meta)
        ev = params.get("_event") if isinstance(params.get("_event"), dict) else {}
        severity = ev.get("severity") if isinstance(ev, dict) else None
        if pol.min_severity is not None and isinstance(severity, str) and not _severity_at_least(severity, pol.min_severity):
            inc_counter("rm_agent_command_denied_total", labels={"target_agent": str(target), "action": str(action)})
            return _build_receipt(
                cmd=cmd,
                meta=meta,
                ok=False,
                latency_ms=0.0,
                evidence={
                    "action": action,
                    "timeout_ms": timeout_ms,
                    "reason": "min_severity_not_met",
                    "capability": meta.capability,
                    "min_severity": pol.min_severity,
                    "severity": severity,
                    "policy_version": RBAC_POLICY_VERSION,
                },
                artifacts=[],
                error="policy_denied",
                outputs=None,
                status="failed",
            )
        if pol.require_reason and _is_approved(params):
            approval = params.get("approval") if isinstance(params.get("approval"), dict) else {}
            note = approval.get("note") if isinstance(approval, dict) else None
            if not isinstance(note, str) or not note.strip():
                inc_counter("rm_agent_command_denied_total", labels={"target_agent": str(target), "action": str(action)})
                inc_counter("rm_approval_required_total", labels={"target_agent": str(target), "action": str(action)})
                return _build_receipt(
                    cmd=cmd,
                    meta=meta,
                    ok=False,
                    latency_ms=0.0,
                    evidence={
                        "action": action,
                        "timeout_ms": timeout_ms,
                        "reason": "approval_reason_required",
                        "capability": meta.capability,
                        "policy_version": RBAC_POLICY_VERSION,
                    },
                    artifacts=[],
                    error="approval_reason_required",
                    outputs=None,
                    status="failed",
                )

    if meta.capability == "side_effect" and _get_side_effect_policy(meta).require_approval and not _is_approved(params):
        inc_counter("rm_agent_command_denied_total", labels={"target_agent": str(target), "action": str(action)})
        inc_counter("rm_approval_required_total", labels={"target_agent": str(target), "action": str(action)})
        return _build_receipt(
            cmd=cmd,
            meta=meta,
            ok=False,
            latency_ms=0.0,
            evidence={
                "action": action,
                "timeout_ms": timeout_ms,
                "reason": "approval_required",
                "capability": meta.capability,
                "policy_version": RBAC_POLICY_VERSION,
            },
            artifacts=[],
            error="approval_required",
            outputs=None,
            status="blocked",
        )

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
        return _build_receipt(
            cmd=cmd,
            meta=meta,
            ok=False,
            latency_ms=0.0,
            evidence={
                "action": action,
                "timeout_ms": timeout_ms,
                "reason": "handler_missing",
                "capability": meta.capability,
                "policy_version": RBAC_POLICY_VERSION,
            },
            artifacts=[],
            error="handler_missing",
            outputs=None,
            status="failed",
        )

    result = handler(params)
    if meta.capability == "side_effect":
        inc_counter(
            "rm_side_effect_executed_total",
            labels={"target_agent": str(target), "action": str(action), "ok": str(bool(result.ok)).lower()},
        )
    observe_ms("rm_agent_command", (time.monotonic() - started) * 1000.0, labels={"target_agent": str(target), "action": str(action)})
    inc_counter("rm_agent_command_total", labels={"target_agent": str(target), "action": str(action), "ok": str(bool(result.ok)).lower()})
    return _build_receipt(
        cmd=cmd,
        meta=meta,
        ok=bool(result.ok),
        latency_ms=float(result.latency_ms),
        evidence=dict(result.evidence),
        artifacts=list(result.artifacts),
        error=result.error,
        outputs=dict(result.output) if isinstance(result.output, dict) else None,
        status="completed" if result.ok else "failed",
    )


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
