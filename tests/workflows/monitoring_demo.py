import argparse
import asyncio
import json
from pathlib import Path
import sys
import threading
import time
from typing import Any
from http.server import HTTPServer


project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from tests.fixtures.market_snapshot_server import Handler
from main import monitor_desk_exposure, get_service_metrics  # noqa: E402


def start_snapshot_server(host: str, port: int) -> tuple[HTTPServer, threading.Thread]:
    # 在演示脚本里内嵌启动行情快照服务, 避免依赖额外进程, 提升可复现性.
    server = HTTPServer((host, port), Handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


async def run_demo(
    desk: str, abs_delta_limit: float, market_snapshot_url: str
) -> dict[str, Any]:
    result = await monitor_desk_exposure(
        desk=desk,
        market_snapshot_url=market_snapshot_url,
        abs_delta_limit=abs_delta_limit,
    )
    metrics = await get_service_metrics()
    return {"result": result, "metrics": metrics}


def main() -> None:
    parser = argparse.ArgumentParser(description="监控工作流演示: 交易台敞口监控")
    parser.add_argument("--desk", default="Equity Derivatives")
    parser.add_argument("--abs-delta-limit", type=float, default=500.0)
    parser.add_argument("--snapshot-host", default="127.0.0.1")
    parser.add_argument("--snapshot-port", type=int, default=9010)
    args = parser.parse_args()

    server, _thread = start_snapshot_server(args.snapshot_host, args.snapshot_port)

    # 等待服务就绪.
    time.sleep(0.1)

    snapshot_url = f"http://{args.snapshot_host}:{args.snapshot_port}/snapshot"
    payload = asyncio.run(run_demo(args.desk, args.abs_delta_limit, snapshot_url))

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    server.shutdown()
    server.server_close()


if __name__ == "__main__":
    main()
