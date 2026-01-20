"""
第 1 周验收: 真实 MCP client 调用.

目标:
- 通过 stdio 传输启动 main.py
- 使用 mcp.client 连接服务端
- 至少调用 2 个工具, 并断言返回 schema

说明:
- 该测试依赖本地 MySQL 可连接
- 服务端会从仓库根目录加载 .env
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp.client.session import ClientSession  
from mcp.client.stdio import (  
    StdioServerParameters,
    stdio_client,
)

from tests.fixtures.market_snapshot_server import Handler  


project_root = Path(__file__).resolve().parents[2]


def _start_snapshot_server() -> tuple[HTTPServer, str]:
    # 在测试进程内启动 mock 行情快照服务, 避免依赖额外进程.
    server = HTTPServer(("127.0.0.1", 0), Handler)
    host_raw, port_raw = server.server_address
    host = (
        host_raw.decode("utf-8")
        if isinstance(host_raw, (bytes, bytearray))
        else str(host_raw)
    )
    port = int(port_raw)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    time.sleep(0.1)
    return server, f"http://{host}:{port}/snapshot"


def _extract_structured(result: Any) -> dict[str, Any]:
    # mcp CallToolResult 可能使用 structuredContent, 也可能使用 content[0].text.
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    content = getattr(result, "content", None) or []
    if content:
        first = content[0]
        text = getattr(first, "text", None)
        if isinstance(text, str) and text.strip():
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

    raise AssertionError("unable to extract structured tool result")


@pytest.mark.asyncio
async def test_week1_mcp_client_calls_two_tools() -> None:
    server, snapshot_url = _start_snapshot_server()
    try:
        # 使用同一 Python 解释器启动服务端, 保证依赖一致.
        params = StdioServerParameters(
            command=sys.executable,
            args=["main.py"],
            cwd=project_root,
        )

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                tools = await session.list_tools()
                names = {t.name for t in tools.tools}

                assert "monitor_desk_exposure" in names
                assert "get_service_metrics" in names

                call1 = await session.call_tool(
                    "monitor_desk_exposure",
                    {
                        "desk": "Equity Derivatives",
                        "market_snapshot_url": snapshot_url,
                        "abs_delta_limit": 500.0,
                    },
                )
                payload1 = _extract_structured(call1)
                assert "request_id" in payload1
                assert payload1.get("desk") == "Equity Derivatives"
                assert "exposure" in payload1
                assert "breaches" in payload1
                assert "alerts" in payload1

                call2 = await session.call_tool("get_service_metrics", {})
                payload2 = _extract_structured(call2)
                assert "monitor_desk_exposure" in payload2

    finally:
        server.shutdown()
        server.server_close()
