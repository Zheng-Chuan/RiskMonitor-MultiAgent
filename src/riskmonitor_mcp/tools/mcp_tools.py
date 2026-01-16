"""MCP tool functions.

This module contains only tool entrypoints.
Database access is delegated to data_access.
Business logic is delegated to services.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import Optional

from mcp.server import FastMCP
from mcp.server.fastmcp import Context

from riskmonitor_mcp.data_access import positions_repository
from riskmonitor_mcp.data_access.market_snapshot_client import fetch_market_snapshot
from riskmonitor_mcp.data_access.errors import DataAccessError
from riskmonitor_mcp.data_access import alerts_repository
from riskmonitor_mcp.services.exposure_service import compute_exposure
from riskmonitor_mcp.services.breach_service import build_abs_delta_breaches
from riskmonitor_mcp.services import alert_rules_service
from riskmonitor_mcp.services.logging_service import (
    new_request_id,
    log_info,
    log_error,
    log_exception,
)
from riskmonitor_mcp.services.prometheus_metrics_service import record_request, get_metrics_summary
from riskmonitor_mcp.services.task_registry import new_task_id, set_task, get_task
from riskmonitor_mcp.tools.errors import error_payload
from riskmonitor_mcp.tools.tool_helpers import (
    normalize_as_of,
    normalize_limit_offset,
    normalize_positions,
    normalize_str,
    validate_optional_yyyy_mm_dd,
)


def register_tools(mcp: FastMCP) -> None:
    # 将 tool 注册到 MCP 实例. server 层只需要调用一次.
    mcp.tool()(query_all_positions)
    mcp.tool()(query_positions_by_trader)
    mcp.tool()(query_positions_by_desk)
    mcp.tool()(calculate_total_delta)
    mcp.tool()(monitor_desk_exposure)
    mcp.tool()(get_service_metrics)
    mcp.tool()(start_calculate_total_delta_task)
    mcp.tool()(get_task_status)
    mcp.tool()(cancel_task)


def query_all_positions() -> dict:
    """
    查询所有头寸.
    此工具通常仅用于调试或数据量极小的场景.

    Returns:
        包含所有头寸的字典
    """
    try:
        request_id = new_request_id()
        log_info("tool=query_all_positions start", request_id)
        positions = positions_repository.fetch_all_positions()

        if not positions:
            log_info("tool=query_all_positions empty", request_id)
            return {
                "position_count": 0,
                "positions": [],
                "message": "未找到任何头寸记录.",
                "request_id": request_id,
            }

        normalized_positions = normalize_positions(positions)

        log_info(f"tool=query_all_positions ok count={len(positions)}", request_id)
        return {
            "position_count": len(positions),
            "positions": normalized_positions,
            "request_id": request_id,
        }

    except DataAccessError as e:
        request_id = locals().get("request_id") or new_request_id()
        log_exception(f"tool=query_all_positions data_access_error code={e.code} err={str(e)}", request_id)
        return {
            "request_id": request_id,
            **error_payload(e.code, e.message, request_id),
        }

    except Exception as e:  # pylint: disable=broad-except
        request_id = locals().get("request_id") or new_request_id()
        log_error(f"tool=query_all_positions error={str(e)}", request_id)
        return {
            "request_id": request_id,
            **error_payload("INTERNAL_ERROR", f"查询所有头寸出错: {str(e)}", request_id),
        }


def query_positions_by_trader(
    trader_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """
    按 Trader ID 查询头寸.
    支持日期范围过滤和分页.

    Args:
        trader_id: 交易员ID
        start_date: 开始日期 (YYYY-MM-DD), 可选
        end_date: 结束日期 (YYYY-MM-DD), 可选
        limit: 返回记录数限制, 默认 100
        offset: 偏移量, 默认 0

    Returns:
        包含头寸列表和汇总信息的字典
    """
    try:
        request_id = new_request_id()
        log_info(f"tool=query_positions_by_trader start trader_id={trader_id}", request_id)
        limit, offset = normalize_limit_offset(limit, offset)
        validate_optional_yyyy_mm_dd(start_date, "start_date")
        validate_optional_yyyy_mm_dd(end_date, "end_date")

        positions = positions_repository.fetch_positions_by_trader(
            trader_id=trader_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        if not positions:
            log_info("tool=query_positions_by_trader empty", request_id)
            return {
                "trader_id": trader_id,
                "position_count": 0,
                "total_delta": 0.0,
                "positions": [],
                "message": f"未找到交易员 {trader_id} 的头寸记录.",
                "request_id": request_id,
            }

        total_delta = sum(float(pos["delta"]) for pos in positions)

        normalized_positions = normalize_positions(positions)

        log_info(f"tool=query_positions_by_trader ok count={len(positions)}", request_id)
        return {
            "trader_id": trader_id,
            "position_count": len(positions),
            "total_delta": float(total_delta),
            "positions": normalized_positions,
            "request_id": request_id,
        }

    except DataAccessError as e:
        request_id = locals().get("request_id") or new_request_id()
        log_exception(
            f"tool=query_positions_by_trader data_access_error code={e.code} err={str(e)}",
            request_id,
        )
        return {
            "trader_id": trader_id,
            "request_id": request_id,
            **error_payload(e.code, e.message, request_id),
        }

    except ValueError as e:
        request_id = locals().get("request_id") or new_request_id()
        log_error(f"tool=query_positions_by_trader invalid_input={str(e)}", request_id)
        return {
            "trader_id": trader_id,
            "request_id": request_id,
            **error_payload("INVALID_INPUT", str(e), request_id),
        }
    except Exception as e:  # pylint: disable=broad-except
        request_id = locals().get("request_id") or new_request_id()
        log_error(f"tool=query_positions_by_trader error={str(e)}", request_id)
        return {
            "trader_id": trader_id,
            "request_id": request_id,
            **error_payload("INTERNAL_ERROR", f"查询交易员 {trader_id} 头寸出错: {str(e)}", request_id),
        }


async def query_positions_by_desk(
    desk_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    ctx: Context = None,
) -> dict:
    """
    按 Desk 查询头寸.
    支持日期范围过滤和分页.

    Args:
        desk_name: 交易台名称
        start_date: 开始日期 (YYYY-MM-DD), 可选
        end_date: 结束日期 (YYYY-MM-DD), 可选
        limit: 返回记录数限制, 默认 100
        offset: 偏移量, 默认 0
        ctx: MCP 上下文 (用于进度报告)

    Returns:
        包含头寸列表和汇总信息的字典
    """
    try:
        request_id = new_request_id()
        log_info(f"tool=query_positions_by_desk start desk={desk_name}", request_id)

        if ctx is not None:
            await ctx.report_progress(0, 100, "开始处理请求")

        limit, offset = normalize_limit_offset(limit, offset)
        validate_optional_yyyy_mm_dd(start_date, "start_date")
        validate_optional_yyyy_mm_dd(end_date, "end_date")

        positions = positions_repository.fetch_positions_by_desk(
            desk_name=desk_name,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        if not positions:
            log_info("tool=query_positions_by_desk empty", request_id)
            return {
                "desk": desk_name,
                "position_count": 0,
                "trader_count": 0,
                "total_delta": 0.0,
                "positions": [],
                "message": f"未找到交易台 {desk_name} 的头寸记录.",
                "request_id": request_id,
            }

        total_delta = sum(float(pos["delta"]) for pos in positions)
        traders = set(pos["trader_id"] for pos in positions)

        normalized_positions = normalize_positions(positions)

        if ctx is not None:
            await ctx.report_progress(90, 100, "结果整理完成")

        log_info(f"tool=query_positions_by_desk ok count={len(positions)}", request_id)
        return {
            "desk": desk_name,
            "position_count": len(positions),
            "trader_count": len(traders),
            "total_delta": float(total_delta),
            "positions": normalized_positions,
            "request_id": request_id,
        }

    except asyncio.CancelledError:
        request_id = locals().get("request_id") or new_request_id()
        log_error("tool=query_positions_by_desk canceled", request_id)
        return {
            "desk": desk_name,
            "request_id": request_id,
            **error_payload("CANCELED", "请求已取消", request_id),
        }

    except DataAccessError as e:
        request_id = locals().get("request_id") or new_request_id()
        log_exception(f"tool=query_positions_by_desk data_access_error code={e.code} err={str(e)}", request_id)
        return {
            "desk": desk_name,
            "request_id": request_id,
            **error_payload(e.code, e.message, request_id),
        }

    except ValueError as e:
        request_id = locals().get("request_id") or new_request_id()
        log_error(f"tool=query_positions_by_desk invalid_input={str(e)}", request_id)
        return {
            "desk": desk_name,
            "request_id": request_id,
            **error_payload("INVALID_INPUT", str(e), request_id),
        }
    except Exception as e:  # pylint: disable=broad-except
        request_id = locals().get("request_id") or new_request_id()
        log_error(f"tool=query_positions_by_desk error={str(e)}", request_id)
        return {
            "desk": desk_name,
            "request_id": request_id,
            **error_payload("INTERNAL_ERROR", f"查询交易台 {desk_name} 头寸出错: {str(e)}", request_id),
        }


async def calculate_total_delta(ctx: Context = None) -> dict:
    """
    计算整个组合的总 Delta (按 Desk 汇总).
    这是一个重计算工具, 可能比较耗时.

    Args:
        ctx: MCP 上下文 (用于进度报告)

    Returns:
        包含总 Delta 和按 Desk 分组详情的字典
    """
    try:
        request_id = new_request_id()
        log_info("tool=calculate_total_delta start", request_id)

        if ctx is not None:
            await ctx.report_progress(0, 100, "开始处理请求")

        if ctx is not None:
            await ctx.report_progress(20, 100, "开始计算组合总 delta")

        total_delta = positions_repository.fetch_total_delta()

        if ctx is not None:
            await ctx.report_progress(50, 100, "开始按 desk 汇总")

        desk_deltas = positions_repository.fetch_desk_delta_summary()

        normalized_desks = []
        for desk in desk_deltas:
            normalized_desks.append(
                {
                    "desk": desk.get("desk"),
                    "desk_delta": float(desk["desk_delta"]) if desk.get("desk_delta") is not None else 0.0,
                    "position_count": int(desk["position_count"]) if desk.get("position_count") is not None else 0,
                }
            )

        if ctx is not None:
            await ctx.report_progress(95, 100, "结果整理完成")

        log_info(f"tool=calculate_total_delta ok desk_count={len(normalized_desks)}", request_id)
        return {
            "total_delta": float(total_delta),
            "by_desk": normalized_desks,
            "request_id": request_id,
        }

    except asyncio.CancelledError:
        request_id = locals().get("request_id") or new_request_id()
        log_error("tool=calculate_total_delta canceled", request_id)
        return {
            "request_id": request_id,
            **error_payload("CANCELED", "请求已取消", request_id),
        }

    except DataAccessError as e:
        request_id = locals().get("request_id") or new_request_id()
        log_exception(f"tool=calculate_total_delta data_access_error code={e.code} err={str(e)}", request_id)
        return {
            "request_id": request_id,
            **error_payload(e.code, e.message, request_id),
        }

    except Exception as e:  # pylint: disable=broad-except
        request_id = locals().get("request_id") or new_request_id()
        log_exception(f"tool=calculate_total_delta error={str(e)}", request_id)
        return {
            "request_id": request_id,
            **error_payload("INTERNAL_ERROR", f"计算总 delta 出错: {str(e)}", request_id),
        }


async def monitor_desk_exposure(
    desk: str,
    as_of: Optional[str] = None,
    market_snapshot_url: Optional[str] = None,
    abs_delta_limit: float = 1000000.0,
    ctx: Context = None,
) -> dict:
    """
    监控 Desk 风险敞口 (核心工具).
    1. 获取市场快照 (Market Snapshot).
    2. 获取 Desk 头寸.
    3. 计算风险 (Exposure).
    4. 检查是否违规 (Breach).
    5. 生成并持久化告警 (Alerts).

    Args:
        desk: 交易台名称
        as_of: 计算基准时间 (ISO8601), 可选
        market_snapshot_url: 市场快照服务地址, 可选
        abs_delta_limit: Delta 绝对值限额, 默认 1,000,000
        ctx: MCP 上下文 (用于进度报告)

    Returns:
        包含风险指标、违规记录和告警信息的字典
    """
    request_id = new_request_id()
    start = time.monotonic()

    try:
        as_of = normalize_as_of(as_of)
        market_snapshot_url = normalize_str(
            market_snapshot_url,
            os.getenv("MARKET_SNAPSHOT_URL", "http://127.0.0.1:9010/snapshot"),
        )

        if ctx is not None:
            await ctx.report_progress(0, 100, "开始处理请求")

        log_info(f"tool=monitor_desk_exposure start desk={desk} as_of={as_of}", request_id)

        snapshot = await fetch_market_snapshot(market_snapshot_url, request_id)
        if ctx is not None:
            await ctx.report_progress(20, 100, "market snapshot 已获取")

        positions = await positions_repository.fetch_positions_by_desk_for_monitoring_with_retry(desk)
        if ctx is not None:
            await ctx.report_progress(60, 100, "positions 已获取")

        total_delta, total_pv_usd, by_currency = compute_exposure(positions, snapshot)

        breaches = build_abs_delta_breaches(total_delta=total_delta, abs_delta_limit=abs_delta_limit)

        # Week4: 告警闭环 - 评估告警规则并持久化
        abs_delta = abs(total_delta)
        alert_records = alert_rules_service.evaluate_desk_delta_breach(
            desk=desk,
            abs_delta=abs_delta,
            threshold=abs_delta_limit,
            request_id=request_id
        )

        if alert_records:
            try:
                alerts_repository.save_alerts_batch(alert_records)
                log_info(f"tool=monitor_desk_exposure saved {len(alert_records)} alerts", request_id)
            except DataAccessError as alert_err:
                log_error(f"tool=monitor_desk_exposure failed to save alerts: {alert_err}", request_id)

        if ctx is not None:
            await ctx.report_progress(95, 100, "结果整理完成")

        latency_ms = (time.monotonic() - start) * 1000.0
        record_request("monitor_desk_exposure", latency_ms)
        log_info(f"tool=monitor_desk_exposure ok desk={desk} latency_ms={latency_ms:.2f}", request_id)

        # 格式化告警用于响应
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
            "latency_ms": float(latency_ms),
            "request_id": request_id,
        }

    except asyncio.CancelledError:
        latency_ms = (time.monotonic() - start) * 1000.0
        record_request("monitor_desk_exposure", latency_ms, is_error=True)
        log_error(f"tool=monitor_desk_exposure canceled latency_ms={latency_ms:.2f}", request_id)
        return {
            "desk": desk,
            "as_of": as_of,
            "latency_ms": float(latency_ms),
            "request_id": request_id,
            **error_payload("CANCELED", "请求已取消", request_id),
        }

    except DataAccessError as e:
        latency_ms = (time.monotonic() - start) * 1000.0
        record_request("monitor_desk_exposure", latency_ms, is_error=True)
        log_exception(
            f"tool=monitor_desk_exposure data_access_error code={e.code} err={str(e)} latency_ms={latency_ms:.2f}",
            request_id,
        )
        return {
            "desk": desk,
            "as_of": as_of,
            "latency_ms": float(latency_ms),
            "request_id": request_id,
            **error_payload(e.code, e.message, request_id),
        }
    except Exception as e:  # pylint: disable=broad-except
        latency_ms = (time.monotonic() - start) * 1000.0
        record_request("monitor_desk_exposure", latency_ms, is_error=True)
        log_exception(f"tool=monitor_desk_exposure error={str(e)} latency_ms={latency_ms:.2f}", request_id)
        return {
            "desk": desk,
            "as_of": as_of,
            "latency_ms": float(latency_ms),
            "request_id": request_id,
            **error_payload("INTERNAL_ERROR", f"monitor desk exposure 出错: {str(e)}", request_id),
        }


async def get_service_metrics() -> dict:
    """
    获取服务运行指标摘要.
    包括 API 延迟统计、请求计数等.

    Returns:
        指标摘要字典
    """
    return get_metrics_summary()


async def _run_task_calculate_total_delta(task_id: str) -> None:
    request_id = new_request_id()
    log_info(f"task=calculate_total_delta start task_id={task_id}", request_id)
    await set_task(task_id, {"status": "running", "request_id": request_id, "progress": 0})

    try:
        await asyncio.sleep(0)
        await set_task(task_id, {"progress": 10, "message": "开始查询数据库"})
        result = await calculate_total_delta()
        await set_task(task_id, {"progress": 100, "status": "succeeded", "result": result})
        log_info(f"task=calculate_total_delta ok task_id={task_id}", request_id)
    except asyncio.CancelledError:
        await set_task(
            task_id,
            {
                "status": "canceled",
                "progress": 0,
                "error": {"code": "CANCELED", "message": "任务已取消"},
            },
        )
        log_error(f"task=calculate_total_delta canceled task_id={task_id}", request_id)
    except Exception as e:  # pylint: disable=broad-except
        await set_task(
            task_id,
            {
                "status": "failed",
                "progress": 0,
                "error": {"code": "INTERNAL_ERROR", "message": f"任务执行出错: {str(e)}"},
            },
        )
        log_error(f"task=calculate_total_delta error task_id={task_id} err={str(e)}", request_id)


async def start_calculate_total_delta_task() -> dict:
    task_id = new_task_id()
    await set_task(task_id, {"status": "queued", "progress": 0, "created_at": datetime.utcnow().isoformat()})

    background = asyncio.create_task(_run_task_calculate_total_delta(task_id))
    await set_task(task_id, {"_asyncio_task": background})
    return {"task_id": task_id, "status": "queued", "progress": 0}


async def get_task_status(task_id: str) -> dict:
    item = await get_task(task_id)
    if item is None:
        return {"task_id": task_id, **error_payload("NOT_FOUND", "未找到任务", new_request_id())}

    public_item = {k: v for k, v in item.items() if not k.startswith("_")}
    public_item["task_id"] = task_id
    return public_item


async def cancel_task(task_id: str) -> dict:
    item = await get_task(task_id)
    if item is None:
        return {"task_id": task_id, **error_payload("NOT_FOUND", "未找到任务", new_request_id())}

    background = item.get("_asyncio_task")
    if background is not None and hasattr(background, "cancel"):
        background.cancel()
        await asyncio.sleep(0)

    await set_task(task_id, {"status": "cancel_requested"})
    return {"task_id": task_id, "status": "cancel_requested"}
