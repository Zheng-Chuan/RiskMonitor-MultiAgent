#!/usr/bin/env python3

import asyncio
import pytest
import json
import threading
import time
from typing import Any

from http.server import HTTPServer

from pathlib import Path
import sys


# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

pytest.importorskip("mcp")

from tests.fixtures.market_snapshot_server import Handler

from main import monitor_desk_exposure  # noqa: E402


def start_snapshot_server(host: str, port: int) -> HTTPServer:
    server = HTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    return server


def assert_schema(result: dict[str, Any]) -> None:
    assert isinstance(result, dict)
    assert "request_id" in result
    assert "desk" in result
    assert "as_of" in result
    assert "exposure" in result
    assert "breaches" in result
    assert "alerts" in result
    assert "latency_ms" in result

    exposure = result["exposure"]
    assert isinstance(exposure, dict)
    assert "pv_usd" in exposure
    assert "total_delta" in exposure
    assert "position_count" in exposure


async def run_smoke(snapshot_url: str) -> dict[str, Any]:
    return await monitor_desk_exposure(
        desk="Equity Derivatives",
        market_snapshot_url=snapshot_url,
        abs_delta_limit=500.0,
    )


def test_week1_smoke() -> None:
    # Week 1 验收: 端到端 smoke test 覆盖 monitoring 链路.
    server = start_snapshot_server("127.0.0.1", 9010)
    try:
        snapshot_url = "http://127.0.0.1:9010/snapshot"
        result = asyncio.run(run_smoke(snapshot_url))
        assert_schema(result)
    finally:
        server.shutdown()
        server.server_close()


def main() -> None:
    server = start_snapshot_server("127.0.0.1", 9010)
    try:
        snapshot_url = "http://127.0.0.1:9010/snapshot"
        result = asyncio.run(run_smoke(snapshot_url))
        assert_schema(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("smoke_test_week1 ok")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
