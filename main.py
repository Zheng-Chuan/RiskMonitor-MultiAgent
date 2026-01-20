#!/usr/bin/env python3
"""RiskMonitor-MultiAgent 入口.

此文件保持为薄入口, 便于:
- 兼容历史 import: tests 仍可从 main import 工具函数
- docker 与本地运行统一入口

业务实现位于 src/riskmonitor_multiagent/server.py.
"""

from __future__ import annotations

import os
import sys

# 确保 src 在 Python 路径中
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from riskmonitor_multiagent import server as _server  # pylint: disable=wrong-import-position

# 对外暴露工具函数, 便于 tests 继续从 main import.
mcp = _server.mcp
query_all_positions = _server.query_all_positions
query_positions_by_trader = _server.query_positions_by_trader
query_positions_by_desk = _server.query_positions_by_desk
calculate_total_delta = _server.calculate_total_delta
monitor_desk_exposure = _server.monitor_desk_exposure
get_service_metrics = _server.get_service_metrics


def main() -> None:
    """
    主入口函数
    根据环境变量配置并启动 MCP 服务.

    支持的传输模式 (MCP_TRANSPORT):
    - stdio: 标准输入输出 (默认开发环境)
    - streamable-http: SSE over HTTP (生产环境推荐)
    - sse: 标准 SSE (需要指定挂载路径)
    """
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


if __name__ == "__main__":
    main()
