"""MCP 工具函数统一走 tool_executor 主路径."""

from __future__ import annotations

from typing import Any, Optional

from mcp.server import FastMCP
from mcp.server.fastmcp import Context

from riskmonitor_multiagent.orchestration.tool_executor import execute_agent_command, new_agent_command
from riskmonitor_multiagent.orchestration.tool_registry import get_tool_meta
from riskmonitor_multiagent.services.auth_service import get_headers_from_ctx, is_authorized
from riskmonitor_multiagent.services.logging_service import new_request_id
from riskmonitor_multiagent.tools.errors import error_payload
from riskmonitor_multiagent.utils.ids import new_command_id


def register_tools(mcp: FastMCP) -> None:
    """注册所有 MCP 工具."""
    mcp.tool()(query_all_positions)
    mcp.tool()(query_positions_by_trader)
    mcp.tool()(query_positions_by_desk)
    mcp.tool()(calculate_total_delta)
    mcp.tool()(monitor_desk_exposure)
    mcp.tool()(submit_alerts)
    mcp.tool()(get_service_metrics)
    mcp.tool()(search_similar_alerts)


def _unauthorized_result(request_id: str) -> dict[str, Any]:
    return {"request_id": request_id, **error_payload("UNAUTHORIZED", "未授权", request_id)}


def _receipt_error_to_public_result(*, request_id: str, error: str | None) -> dict[str, Any]:
    if error == "approval_required":
        return {"request_id": request_id, **error_payload("APPROVAL_REQUIRED", "需要审批", request_id)}
    if error == "approval_reason_required":
        return {"request_id": request_id, **error_payload("APPROVAL_REQUIRED", "审批缺少理由", request_id)}
    if error in {"rbac_denied", "policy_denied"}:
        return {"request_id": request_id, **error_payload("PERMISSION_DENIED", "权限拒绝", request_id)}
    if error == "invalid_command":
        return {"request_id": request_id, **error_payload("INVALID_INPUT", "命令参数非法", request_id)}
    if error in {"unknown_action", "handler_missing"}:
        return {"request_id": request_id, **error_payload("TOOL_UNAVAILABLE", "工具不可用", request_id)}
    message = error or "工具执行失败"
    return {"request_id": request_id, **error_payload("INTERNAL_ERROR", message, request_id)}


def _execute_mcp_tool(
    *,
    action: str,
    params: dict[str, Any],
    ctx: Context = None,
) -> dict[str, Any]:
    request_id = str(params.get("request_id") or new_request_id())
    if ctx is not None and not is_authorized(get_headers_from_ctx(ctx)):
        return _unauthorized_result(request_id)

    meta = get_tool_meta(action)
    if meta is None:
        return {"request_id": request_id, **error_payload("TOOL_UNAVAILABLE", "工具未注册", request_id)}

    command = new_agent_command(
        run_id=f"mcp:{request_id}",
        command_id=new_command_id(),
        target_agent=meta.owner,
        action=action,
        params={**params, "request_id": request_id},
        timeout_ms=meta.default_timeout_ms,
        expected_output_schema="mcp_tool_result.v1",
    )
    receipt = execute_agent_command(command)
    if receipt.get("ok") is not True:
        return _receipt_error_to_public_result(request_id=request_id, error=receipt.get("error"))

    outputs = receipt.get("outputs")
    if isinstance(outputs, dict):
        result = outputs.get("result")
        if isinstance(result, dict):
            public_result = dict(result)
            public_result.setdefault("request_id", request_id)
            return public_result
    return {"request_id": request_id}


def search_similar_alerts(query: str, top_k: int = 5, ctx: Context = None) -> dict[str, Any]:
    return _execute_mcp_tool(
        action="search_similar_alerts",
        params={"query": query, "top_k": top_k},
        ctx=ctx,
    )


def query_all_positions(ctx: Context = None) -> dict[str, Any]:
    return _execute_mcp_tool(action="query_all_positions", params={}, ctx=ctx)


def query_positions_by_trader(
    trader_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    ctx: Context = None,
) -> dict[str, Any]:
    return _execute_mcp_tool(
        action="query_positions_by_trader",
        params={
            "trader_id": trader_id,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
            "offset": offset,
        },
        ctx=ctx,
    )


async def query_positions_by_desk(
    desk_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    ctx: Context = None,
) -> dict[str, Any]:
    return _execute_mcp_tool(
        action="query_positions_by_desk",
        params={
            "desk": desk_name,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
            "offset": offset,
        },
        ctx=ctx,
    )


async def calculate_total_delta(ctx: Context = None) -> dict[str, Any]:
    return _execute_mcp_tool(action="calculate_total_delta", params={}, ctx=ctx)


async def monitor_desk_exposure(
    desk: str,
    as_of: Optional[str] = None,
    market_snapshot_url: Optional[str] = None,
    market_snapshot: Optional[dict[str, Any]] = None,
    abs_delta_limit: float = 1000000.0,
    ctx: Context = None,
) -> dict[str, Any]:
    return _execute_mcp_tool(
        action="monitor_desk_exposure",
        params={
            "desk": desk,
            "as_of": as_of,
            "market_snapshot_url": market_snapshot_url,
            "market_snapshot": market_snapshot,
            "abs_delta_limit": abs_delta_limit,
        },
        ctx=ctx,
    )


def submit_alerts(
    alerts: list[dict[str, Any]],
    request_id: Optional[str] = None,
    approval: Optional[dict[str, Any]] = None,
    ctx: Context = None,
) -> dict[str, Any]:
    return _execute_mcp_tool(
        action="submit_alerts",
        params={
            "alerts": alerts,
            "request_id": request_id,
            "approval": approval,
        },
        ctx=ctx,
    )


async def get_service_metrics(ctx: Context = None) -> dict[str, Any]:
    return _execute_mcp_tool(action="get_service_metrics", params={}, ctx=ctx)
