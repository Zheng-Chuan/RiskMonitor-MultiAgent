#!/usr/bin/env python3
"""
RiskMonitor-MCP 服务端
用于金融衍生品风险管理的 MCP 服务
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server import FastMCP

from riskmonitor_mcp.services.logging_service import configure_logging
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


if __name__ == "__main__":
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
