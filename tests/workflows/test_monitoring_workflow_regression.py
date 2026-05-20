import asyncio
import sys
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from main import get_service_metrics, monitor_desk_exposure  # noqa: E402
from tests.fixtures.market_snapshot_server import Handler  # noqa: E402


def _start_snapshot_server() -> HTTPServer:
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    return server


async def _run_monitoring_workflow(snapshot_url: str) -> dict[str, Any]:
    result = await monitor_desk_exposure(
        desk="Equity Derivatives",
        market_snapshot_url=snapshot_url,
        abs_delta_limit=500.0,
    )
    metrics = await get_service_metrics()
    return {"result": result, "metrics": metrics}


def test_monitoring_workflow_returns_exposure_and_service_metrics() -> None:
    server = _start_snapshot_server()
    host, port = server.server_address
    snapshot_url = f"http://{host}:{port}/snapshot"
    try:
        payload = asyncio.run(_run_monitoring_workflow(snapshot_url))
    finally:
        server.shutdown()
        server.server_close()

    result = payload["result"]
    metrics = payload["metrics"]

    assert result["desk"] == "Equity Derivatives"
    assert isinstance(result.get("exposure"), dict)
    assert isinstance(result.get("breaches"), list)
    assert isinstance(result.get("alerts"), list)
    assert "request_id" in result

    assert metrics.get("ok") is True
    assert "request_id" in metrics
    assert isinstance(metrics.get("summary"), dict)
    assert "uptime_seconds" in metrics["summary"]
