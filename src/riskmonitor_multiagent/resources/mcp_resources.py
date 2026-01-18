"""MCP resource registrations."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from mcp.server import FastMCP


def register_resources(mcp: FastMCP) -> None:
    """注册 MCP Resources."""
    @mcp.resource(
        "risk://metadata/desks",
        name="desks",
        title="Desk Metadata",
        description="交易台列表与元数据",
        mime_type="application/json",
    )
    def resource_desks() -> str:
        payload = {
            "desks": [
                {"desk": "Equity Derivatives"},
                {"desk": "Fixed Income"},
                {"desk": "FX Options"},
            ]
        }
        return json.dumps(payload, ensure_ascii=False)

    @mcp.resource(
        "risk://limits/global",
        name="global_limits",
        title="Global Risk Limits",
        description="全局风控限额(当前为最小演示版本)",
        mime_type="application/json",
    )
    def resource_global_limits() -> str:
        payload = {"abs_delta_limit": 1000000.0}
        return json.dumps(payload, ensure_ascii=False)

    @mcp.resource(
        "market://snapshot/latest",
        name="market_snapshot_latest",
        title="Latest Market Snapshot",
        description="最新行情快照(当前为最小演示版本)",
        mime_type="application/json",
    )
    def resource_market_snapshot_latest() -> str:
        payload = {
            "as_of": (
                datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            ),
            "prices": {},
            "fx_rates": {"USD": 1.0},
        }
        return json.dumps(payload, ensure_ascii=False)
