"""Integration tests for streamable-http extra endpoints."""

from __future__ import annotations



import sys
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def test_health_and_ready_endpoints() -> None:
    from starlette.testclient import TestClient

    from riskmonitor_multiagent.server import mcp
    from riskmonitor_multiagent.services import readiness_service

    readiness_service._reset_for_tests()

    app = mcp.streamable_http_app()
    client = TestClient(app)

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"

    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ready"


def test_ready_returns_503_when_shutting_down() -> None:
    from starlette.testclient import TestClient

    from riskmonitor_multiagent.server import mcp
    from riskmonitor_multiagent.services import readiness_service

    readiness_service._reset_for_tests()
    readiness_service.mark_shutting_down("test")

    app = mcp.streamable_http_app()
    client = TestClient(app)

    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json().get("status") == "not_ready"
