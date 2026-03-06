"""
集成测试: MCP 工具
测试 MCP 服务端的工具函数
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
import mcp  # noqa: F401

from main import (  
    query_all_positions,
    query_positions_by_trader,
    query_positions_by_desk,
    calculate_total_delta,
    monitor_desk_exposure,
)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"missing env var: {name}")
    return value.strip()


@pytest.fixture(autouse=True)
def _require_db_env() -> None:
    # 所有 MCP 工具都会连接数据库, 缺失环境变量时直接跳过.
    _require_env("MYSQL_HOST")
    _require_env("MYSQL_PORT")
    _require_env("MYSQL_DATABASE")
    _require_env("MYSQL_USER")
    _require_env("MYSQL_PASSWORD")


class _SnapshotHandler(BaseHTTPRequestHandler):
    def _write_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802  pylint: disable=invalid-name
        if self.path in {"/snapshot", "/snapshot/"}:
            self._write_json(
                200,
                {
                    "as_of": "2026-01-07T00:00:00Z",
                    "prices": {"AAPL-CALL-175-20250331": 12.34},
                    "fx_rates": {"USD": 1.0},
                },
            )
            return
        self._write_json(404, {"error": {"code": "NOT_FOUND", "message": "not found"}})

    def log_message(self, format: str, *args: Any) -> None:  
        return


def _start_snapshot_server() -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), _SnapshotHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    return server, f"http://{host}:{port}/snapshot"


def test_query_all_positions_schema():
    """测试查询所有头寸(结构化 JSON)"""
    result = query_all_positions()
    assert isinstance(result, dict)
    assert "request_id" in result
    assert "position_count" in result
    assert "positions" in result
    assert isinstance(result["positions"], list)


def test_query_positions_by_trader():
    """测试按交易员查询"""
    result = query_positions_by_trader("TRADER-001")
    assert isinstance(result, dict)
    assert result.get("trader_id") == "TRADER-001"
    assert "request_id" in result
    assert "error" not in result
    assert "positions" in result
    assert isinstance(result["positions"], list)


def test_query_positions_by_trader_not_found():
    """测试查询不存在的交易员"""
    result = query_positions_by_trader("TRADER-999")
    assert isinstance(result, dict)
    assert result.get("trader_id") == "TRADER-999"
    assert result.get("position_count") == 0
    assert "message" in result
    assert "未找到" in str(result.get("message"))


@pytest.mark.asyncio
async def test_query_positions_by_desk_schema():
    """测试按交易台查询(结构化 JSON, async)"""
    result = await query_positions_by_desk("Equity Derivatives")
    assert isinstance(result, dict)
    assert result.get("desk") == "Equity Derivatives"
    assert "request_id" in result
    assert "positions" in result
    assert "total_delta" in result


@pytest.mark.asyncio
async def test_query_positions_by_desk_not_found():
    """测试查询不存在的交易台"""
    result = await query_positions_by_desk("NonExistent Desk")
    assert isinstance(result, dict)
    assert result.get("position_count") == 0


@pytest.mark.asyncio
async def test_calculate_total_delta_schema():
    """测试计算总Delta(结构化 JSON, async)"""
    result = await calculate_total_delta()
    assert isinstance(result, dict)
    assert "request_id" in result
    assert "total_delta" in result
    assert "by_desk" in result
    assert isinstance(result["by_desk"], list)


@pytest.mark.asyncio
async def test_monitor_desk_exposure_schema():
    """测试 desk exposure monitoring 的输出 schema"""
    server, url = _start_snapshot_server()
    try:
        result = await monitor_desk_exposure(
            desk="Equity Derivatives",
            market_snapshot_url=url,
            abs_delta_limit=500.0,
        )
    finally:
        server.shutdown()
        server.server_close()
    assert isinstance(result, dict)
    assert "request_id" in result
    assert result.get("desk") == "Equity Derivatives"
    assert "exposure" in result
    assert "breaches" in result
    assert "alerts" in result
    assert "latency_ms" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
