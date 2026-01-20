#!/usr/bin/env python3
"""
RiskMonitor-MultiAgent 服务端
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

from riskmonitor_multiagent.data_access.health_checks import check_mysql_ready
from riskmonitor_multiagent.services import readiness_service
from riskmonitor_multiagent.services.logging_service import configure_logging
from riskmonitor_multiagent.services.prometheus_metrics_service import (
    generate_prometheus_metrics,
)
from riskmonitor_multiagent.services.auth_service import is_authorized
from riskmonitor_multiagent.resources.mcp_resources import register_resources
from riskmonitor_multiagent.prompts.mcp_prompts import register_prompts
from riskmonitor_multiagent.tools import mcp_tools as tools

query_all_positions = tools.query_all_positions
query_positions_by_trader = tools.query_positions_by_trader
query_positions_by_desk = tools.query_positions_by_desk
calculate_total_delta = tools.calculate_total_delta
monitor_desk_exposure = tools.monitor_desk_exposure
get_service_metrics = tools.get_service_metrics


# 加载环境变量
# 从项目目录加载 .env, 不依赖当前工作目录
_repo_root = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=_repo_root / ".env")

configure_logging()

_server_name = os.getenv("MCP_SERVER_NAME", "RiskMonitor MultiAgent").strip()
mcp = FastMCP(_server_name or "RiskMonitor MultiAgent")
tools.register_tools(mcp)
register_resources(mcp)
register_prompts(mcp)


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health_check(request: Request) -> Response:
    """
    健康检查端点(存活探针).
    Kubernetes 用此端点判断容器是否存活.
    """
    del request
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/ready", methods=["GET"], include_in_schema=False)
async def readiness_check(request: Request) -> Response:
    """
    就绪检查端点(就绪探针).
    Kubernetes 用此端点判断服务是否准备好接收流量.
    检查项:
    - 是否正在关闭(优雅退出)
    - 数据库连接是否正常
    """
    if not is_authorized(request.headers):
        return JSONResponse(
            {"error": {"code": "UNAUTHORIZED", "message": "unauthorized"}},
            status_code=401,
        )

    if readiness_service.is_shutting_down():
        return JSONResponse(
            {
                "status": "not_ready",
                "reason": readiness_service.shutdown_reason() or "shutting_down",
            },
            status_code=503,
        )

    # 本地演示场景下, 数据库就绪检查是可选的.
    # 如果环境变量不完整, 则跳过 MySQL 检查.
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
    """第 4 周: Prometheus 指标端点"""
    if not is_authorized(request.headers):
        return JSONResponse(
            {"error": {"code": "UNAUTHORIZED", "message": "unauthorized"}},
            status_code=401,
        )
    metrics_text = generate_prometheus_metrics()
    return Response(content=metrics_text, media_type="text/plain; version=0.0.4")


def _install_signal_handlers() -> None:
    # 在收到退出信号时, 先将就绪状态置为 not_ready.
    def _handler(signum: int, frame: object) -> None:
        del frame
        readiness_service.mark_shutting_down(f"signal={signum}")

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)

_install_signal_handlers()
