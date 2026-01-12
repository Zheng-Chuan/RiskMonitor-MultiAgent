#!/usr/bin/env python3
"""Benchmark script for monitor_desk_exposure.

说明:
- 固化请求集, 输出 p50 与 p95
- 直接调用 tool 函数, 避免引入额外 client 开销
- 使用本地 HTTP server 提供 market snapshot
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

# 加载 .env, 避免 benchmark 运行前需要手动 export 环境变量.
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")


def _configure_logging() -> None:
    # 复用服务端结构化日志配置.
    from riskmonitor_mcp.services.logging_service import (  # pylint: disable=import-outside-toplevel
        configure_logging,
    )

    configure_logging()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"missing env var: {name}")
    return value.strip()


class _SnapshotHandler(BaseHTTPRequestHandler):
    def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
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

    def log_message(self, format: str, *args: Any) -> None:  # pylint: disable=redefined-builtin,unused-argument
        return


def _start_snapshot_server() -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), _SnapshotHandler)
    host, port = server.server_address
    # 某些类型定义里 host 可能被标注为 bytes, 这里统一转换为 str.
    if isinstance(host, (bytes, bytearray)):
        host = host.decode("utf-8")
    else:
        host = str(host)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    return server, f"http://{host}:{port}/snapshot"


def _percentile(values_ms: list[float], q: float) -> float:
    if not values_ms:
        return 0.0
    if q <= 0:
        return float(min(values_ms))
    if q >= 1:
        return float(max(values_ms))
    sorted_values = sorted(values_ms)
    idx = int(round(q * (len(sorted_values) - 1)))
    idx = max(0, min(idx, len(sorted_values) - 1))
    return float(sorted_values[idx])


@dataclass(frozen=True)
class _BenchConfig:
    iterations: int
    concurrency: int
    warmup: int
    desk: str
    abs_delta_limit: float
    p95_target_ms: float


async def _run_once(snapshot_url: str, desk: str, abs_delta_limit: float) -> float:
    from riskmonitor_mcp.tools.mcp_tools import (  # pylint: disable=import-outside-toplevel
        monitor_desk_exposure,
    )

    start = time.perf_counter()
    result = await monitor_desk_exposure(
        desk=desk,
        market_snapshot_url=snapshot_url,
        abs_delta_limit=abs_delta_limit,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    if not isinstance(result, dict) or "error" in result:
        raise RuntimeError(f"tool returned error: {result}")

    return float(elapsed_ms)


async def _run_benchmark(config: _BenchConfig) -> None:
    _configure_logging()
    _require_env("MYSQL_HOST")
    _require_env("MYSQL_PORT")
    _require_env("MYSQL_DATABASE")
    _require_env("MYSQL_USER")
    _require_env("MYSQL_PASSWORD")

    server, snapshot_url = _start_snapshot_server()
    try:
        sem = asyncio.Semaphore(max(1, int(config.concurrency)))

        async def one() -> float:
            async with sem:
                return await _run_once(snapshot_url, config.desk, config.abs_delta_limit)

        # warmup
        for _ in range(max(0, int(config.warmup))):
            await one()

        latencies: list[float] = []
        pending = [asyncio.create_task(one()) for _ in range(int(config.iterations))]
        for task in asyncio.as_completed(pending):
            latencies.append(await task)

        p50 = _percentile(latencies, 0.50)
        p95 = _percentile(latencies, 0.95)

        print("benchmark=monitor_desk_exposure")
        print(f"iterations={len(latencies)}")
        print(f"concurrency={config.concurrency}")
        print(f"p50_ms={p50:.2f}")
        print(f"p95_ms={p95:.2f}")

        if float(p95) > float(config.p95_target_ms):
            print(f"result=fail p95_target_ms={config.p95_target_ms:.2f}")
            raise SystemExit(1)
        print(f"result=pass p95_target_ms={config.p95_target_ms:.2f}")
    finally:
        server.shutdown()
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark monitor_desk_exposure")
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--desk", default="Equity Derivatives")
    parser.add_argument("--abs-delta-limit", type=float, default=500.0)
    parser.add_argument("--p95-target-ms", type=float, default=500.0)
    args = parser.parse_args()

    config = _BenchConfig(
        iterations=int(args.iterations),
        concurrency=int(args.concurrency),
        warmup=int(args.warmup),
        desk=str(args.desk),
        abs_delta_limit=float(args.abs_delta_limit),
        p95_target_ms=float(args.p95_target_ms),
    )

    asyncio.run(_run_benchmark(config))


if __name__ == "__main__":
    main()
