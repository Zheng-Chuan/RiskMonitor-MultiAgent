#!/usr/bin/env python3
"""
RiskMonitor-MCP 服务端
用于金融衍生品风险管理的 MCP 服务
"""

from __future__ import annotations

import os
import signal
from pathlib import Path

from dotenv import load_dotenv
from mcp.server import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from riskmonitor_mcp.data_access.health_checks import check_mysql_ready
from riskmonitor_mcp.services import readiness_service
from riskmonitor_mcp.services.logging_service import configure_logging
from riskmonitor_mcp.services.prometheus_metrics_service import generate_prometheus_metrics
from riskmonitor_mcp.tools.mcp_tools import (
    calculate_total_delta,
    cancel_task,
    get_service_metrics,
    get_task_status,
    monitor_desk_exposure,
    query_all_positions,
    query_positions_by_desk,
    query_positions_by_trader,
    register_tools,
    start_calculate_total_delta_task,
)


# 加载环境变量
# 从项目目录加载 .env, 不依赖当前工作目录
_repo_root = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=_repo_root / ".env")

configure_logging()

mcp = FastMCP("RiskMonitor")
register_tools(mcp)


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health_check(request: Request) -> Response:
    del request
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/ready", methods=["GET"], include_in_schema=False)
async def readiness_check(request: Request) -> Response:
    del request

    if readiness_service.is_shutting_down():
        return JSONResponse(
            {
                "status": "not_ready",
                "reason": readiness_service.shutdown_reason() or "shutting_down",
            },
            status_code=503,
        )

    # DB readiness is optional for local demo.
    # If env is incomplete, skip MySQL check.
    mysql_password = os.getenv("MYSQL_PASSWORD")
    if mysql_password is None or not mysql_password.strip():
        return JSONResponse({"status": "ready", "checks": {"mysql": "skipped"}})

    ok, message, err = check_mysql_ready()
    if ok:
        return JSONResponse({"status": "ready", "checks": {"mysql": "ok"}})

    return JSONResponse(
        {
            "status": "not_ready",
            "checks": {
                "mysql": {
                    "status": "not_ready",
                    "message": message,
                    "code": getattr(err, "code", "DB_ERROR"),
                }
            },
        },
        status_code=503,
    )


@mcp.custom_route("/metrics", methods=["GET"], include_in_schema=False)
async def metrics_endpoint(request: Request) -> Response:
    """Week4: Prometheus 指标端点"""
    del request
    metrics_text = generate_prometheus_metrics()
    return Response(content=metrics_text, media_type="text/plain; version=0.0.4")


def _install_signal_handlers() -> None:
    # 在收到退出信号时, 先将 readiness 置为 not ready.
    def _handler(signum: int, frame: object) -> None:
        del frame
        readiness_service.mark_shutting_down(f"signal={signum}")

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


if __name__ == "__main__":
    _install_signal_handlers()
    transport = os.getenv("MCP_TRANSPORT")
    if transport is None or not transport.strip():
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        if app_env == "production":
            transport = "streamable-http"
        else:
            transport = "stdio"
    transport = transport.strip().lower()

    mount_path = os.getenv("MCP_MOUNT_PATH")
    if mount_path is not None:
        mount_path = mount_path.strip() or None

    if transport == "sse":
        mcp.run(transport="sse", mount_path=mount_path)
    elif transport in {"streamable-http", "http"}:
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
