"""MCP 工具函数.

说明:
- 本模块只包含工具入口函数
- 数据库访问下沉到 data_access
- 业务逻辑下沉到 services
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from mcp.server import FastMCP
from mcp.server.fastmcp import Context

from riskmonitor_multiagent.data_access import positions_repository
from riskmonitor_multiagent.data_access.errors import DataAccessError
from riskmonitor_multiagent.data_access import alerts_repository
from riskmonitor_multiagent.services.exposure_service import compute_exposure
from riskmonitor_multiagent.services.breach_service import build_abs_delta_breaches
from riskmonitor_multiagent.services import alert_rules_service
from riskmonitor_multiagent.services.logging_service import (
    new_request_id,
    log_info,
    log_error,
    log_exception,
)
from riskmonitor_multiagent.services.prometheus_metrics_service import (
    record_request,
    get_metrics_summary,
)
from riskmonitor_multiagent.services.auth_service import get_headers_from_ctx, is_authorized
from riskmonitor_multiagent.tools.errors import error_payload
from riskmonitor_multiagent.tools.tool_helpers import (
    normalize_as_of,
    normalize_limit_offset,
    normalize_positions,
    normalize_str,
    validate_optional_yyyy_mm_dd,
)


def register_tools(mcp: FastMCP) -> None:
    """注册所有 MCP 工具."""
    # 将工具注册到 MCP 实例. 服务端只需要调用一次.
    mcp.tool()(query_all_positions)
    mcp.tool()(query_positions_by_trader)
    mcp.tool()(query_positions_by_desk)
    mcp.tool()(calculate_total_delta)
    mcp.tool()(monitor_desk_exposure)
    mcp.tool()(submit_alerts)
    mcp.tool()(get_service_metrics)


def query_all_positions(ctx: Context = None) -> dict:
    """
    查询所有头寸.
    此工具通常仅用于调试或数据量极小的场景.

    返回:
        包含所有头寸的字典
    """
    try:
        request_id = new_request_id()
        if ctx is not None and not is_authorized(get_headers_from_ctx(ctx)):
            return {"request_id": request_id, **error_payload("UNAUTHORIZED", "未授权", request_id)}
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

        log_info(
            f"tool=query_all_positions ok count={len(positions)}", request_id
        )
        return {
            "position_count": len(positions),
            "positions": normalized_positions,
            "request_id": request_id,
        }

    except DataAccessError as e:
        request_id = locals().get("request_id") or new_request_id()
        log_exception(
            f"tool=query_all_positions data_access_error code={e.code} err={str(e)}",
            request_id
        )
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


def query_positions_by_trader(  # pylint: disable=too-many-arguments, too-many-positional-arguments
    trader_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    ctx: Context = None,
) -> dict:
    """
    按 Trader ID 查询头寸.
    支持日期范围过滤和分页.

    参数:
        trader_id: 交易员ID
        start_date: 开始日期 (YYYY-MM-DD), 可选
        end_date: 结束日期 (YYYY-MM-DD), 可选
        limit: 返回记录数限制, 默认 100
        offset: 偏移量, 默认 0

    返回:
        包含头寸列表和汇总信息的字典
    """
    try:
        request_id = new_request_id()
        if ctx is not None and not is_authorized(get_headers_from_ctx(ctx)):
            return {
                "request_id": request_id,
                "trader_id": trader_id,
                **error_payload("UNAUTHORIZED", "未授权", request_id),
            }
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
            **error_payload(
                "INTERNAL_ERROR",
                f"查询交易员 {trader_id} 头寸出错: {str(e)}",
                request_id,
            ),
        }


async def query_positions_by_desk(  # pylint: disable=too-many-arguments, too-many-positional-arguments, too-many-return-statements
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

    参数:
        desk_name: 交易台名称
        start_date: 开始日期 (YYYY-MM-DD), 可选
        end_date: 结束日期 (YYYY-MM-DD), 可选
        limit: 返回记录数限制, 默认 100
        offset: 偏移量, 默认 0
        ctx: MCP 上下文 (用于进度报告)

    返回:
        包含头寸列表和汇总信息的字典
    """
    try:
        request_id = new_request_id()
        if ctx is not None and not is_authorized(get_headers_from_ctx(ctx)):
            return {
                "request_id": request_id,
                "desk": desk_name,
                **error_payload("UNAUTHORIZED", "未授权", request_id),
            }
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
        log_exception(
            f"tool=query_positions_by_desk data_access_error code={e.code} err={str(e)}",
            request_id,
        )
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

    参数:
        ctx: MCP 上下文 (用于进度报告)

    返回:
        包含总 Delta 和按 Desk 分组详情的字典
    """
    try:
        request_id = new_request_id()
        if ctx is not None and not is_authorized(get_headers_from_ctx(ctx)):
            return {"request_id": request_id, **error_payload("UNAUTHORIZED", "未授权", request_id)}
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
            desk_delta = (
                float(desk["desk_delta"]) if desk.get("desk_delta") is not None else 0.0
            )
            position_count = (
                int(desk["position_count"]) if desk.get("position_count") is not None else 0
            )
            normalized_desks.append(
                {
                    "desk": desk.get("desk"),
                    "desk_delta": desk_delta,
                    "position_count": position_count,
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
        log_exception(
            f"tool=calculate_total_delta data_access_error code={e.code} err={str(e)}",
            request_id
        )
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


async def monitor_desk_exposure(  # pylint: disable=too-many-locals, too-many-arguments, too-many-positional-arguments
    desk: str,
    as_of: Optional[str] = None,
    market_snapshot_url: Optional[str] = None,
    market_snapshot: Optional[dict[str, Any]] = None,
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

    参数:
        desk: 交易台名称
        as_of: 计算基准时间 (ISO8601), 可选
        market_snapshot_url: 市场快照来源标识(仅用于回显), 可选
        market_snapshot: 市场快照(建议由上游 Agent 获取并传入), 可选
        abs_delta_limit: Delta 绝对值限额, 默认 1,000,000
        ctx: MCP 上下文 (用于进度报告)

    返回:
        包含风险指标、违规记录和告警信息的字典
    """
    request_id = new_request_id()
    start = time.monotonic()

    try:
        if ctx is not None and not is_authorized(get_headers_from_ctx(ctx)):
            latency_ms = (time.monotonic() - start) * 1000.0
            record_request("monitor_desk_exposure", latency_ms, is_error=True)
            return {
                "desk": desk,
                "as_of": as_of,
                "latency_ms": float(latency_ms),
                "request_id": request_id,
                **error_payload("UNAUTHORIZED", "未授权", request_id),
            }
        as_of = normalize_as_of(as_of)
        market_snapshot_url = normalize_str(market_snapshot_url, "embedded")
        snapshot = (
            market_snapshot
            if isinstance(market_snapshot, dict)
            else {"as_of": as_of, "prices": {}, "fx_rates": {"USD": 1.0}}
        )

        if ctx is not None:
            await ctx.report_progress(0, 100, "开始处理请求")

        log_info(
            f"tool=monitor_desk_exposure start desk={desk} as_of={as_of}",
            request_id,
        )

        if ctx is not None:
            await ctx.report_progress(20, 100, "market snapshot 已就绪")

        positions = (
            await positions_repository.fetch_positions_by_desk_for_monitoring_with_retry(
                desk
            )
        )
        if ctx is not None:
            await ctx.report_progress(60, 100, "positions 已获取")

        total_delta, total_pv_usd, by_currency = compute_exposure(
            positions, snapshot
        )

        breaches = build_abs_delta_breaches(
            total_delta=total_delta, abs_delta_limit=abs_delta_limit
        )

        # 第 4 周: 告警闭环 - 评估告警规则 (不在此处持久化; 由 submit_alerts 负责写入)
        abs_delta = abs(total_delta)
        alert_records = alert_rules_service.evaluate_desk_delta_breach(
            desk=desk,
            abs_delta=abs_delta,
            threshold=abs_delta_limit,
            request_id=request_id
        )

        if ctx is not None:
            await ctx.report_progress(95, 100, "结果整理完成")

        latency_ms = (time.monotonic() - start) * 1000.0
        record_request("monitor_desk_exposure", latency_ms)
        log_info(
            f"tool=monitor_desk_exposure ok desk={desk} latency_ms={latency_ms:.2f}",
            request_id
        )

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
            f"tool=monitor_desk_exposure data_access_error code={e.code} err={str(e)} latency_ms={latency_ms:.2f}",  # pylint: disable=line-too-long
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
        log_exception(
            f"tool=monitor_desk_exposure error={str(e)} latency_ms={latency_ms:.2f}",
            request_id
        )
        return {
            "desk": desk,
            "as_of": as_of,
            "latency_ms": float(latency_ms),
            "request_id": request_id,
            **error_payload(
                "INTERNAL_ERROR",
                f"monitor desk exposure 出错: {str(e)}",
                request_id
            ),
        }


def submit_alerts(
    alerts: list[dict[str, Any]],
    request_id: Optional[str] = None,
    ctx: Context = None,
) -> dict:
    """
    将告警记录批量写入数据库.
    这是一个有副作用的工具, 建议由上游 Agent 在明确需要时调用.

    参数:
        alerts: 告警记录列表 (alert_rules_service.evaluate_* 输出)
        request_id: 可选, 便于日志追踪

    返回:
        写入结果
    """
    effective_request_id = request_id or new_request_id()
    try:
        if ctx is not None and not is_authorized(get_headers_from_ctx(ctx)):
            return {
                "request_id": effective_request_id,
                **error_payload("UNAUTHORIZED", "未授权", effective_request_id),
            }
        if not alerts:
            return {"request_id": effective_request_id, "saved": 0}
        alerts_repository.save_alerts_batch(alerts)
        return {"request_id": effective_request_id, "saved": len(alerts)}
    except DataAccessError as e:
        log_exception(
            f"tool=submit_alerts data_access_error code={e.code} err={str(e)}",
            effective_request_id,
        )
        return {
            "request_id": effective_request_id,
            **error_payload(e.code, e.message, effective_request_id),
        }
    except Exception as e:  # pylint: disable=broad-except
        log_exception(f"tool=submit_alerts error={str(e)}", effective_request_id)
        return {
            "request_id": effective_request_id,
            **error_payload(
                "INTERNAL_ERROR",
                f"写入 alerts 出错: {str(e)}",
                effective_request_id,
            ),
        }


async def get_service_metrics() -> dict:
    """
    获取服务运行指标摘要.
    包括 API 延迟统计、请求计数等.

    返回:
        指标摘要字典
    """
    summary = get_metrics_summary()
    tools = summary.get("tools") if isinstance(summary.get("tools"), dict) else {}
    return {**summary, **tools}
