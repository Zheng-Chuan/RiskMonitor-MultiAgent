import asyncio
import json
from http.server import HTTPServer
from pathlib import Path
import sys
import threading
import time
from typing import Any

import pytest


project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

import mcp  # noqa: F401

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


def test_monitor_desk_exposure_acceptance_flow() -> None:
    # 端到端验收: 覆盖监控工具的主链输出 contract.
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
        print("monitor_desk_exposure_acceptance ok")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
