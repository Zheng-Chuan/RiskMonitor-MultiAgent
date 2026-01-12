"""In process metrics.

This module provides minimal metrics for demo and tests.
"""

from __future__ import annotations

import asyncio
from typing import Any


_metrics_lock = asyncio.Lock()
_metrics: dict[str, Any] = {
    "monitor_desk_exposure": {
        "request_count": 0,
        "latency_ms": [],
        "max_samples": 200,
    }
}


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = int(round(0.95 * (len(sorted_values) - 1)))
    idx = max(0, min(idx, len(sorted_values) - 1))
    return float(sorted_values[idx])


async def record_latency(tool_name: str, latency_ms: float) -> None:
    async with _metrics_lock:
        item = _metrics.get(tool_name)
        if item is None:
            return
        item["request_count"] = int(item.get("request_count", 0)) + 1
        samples = list(item.get("latency_ms", []))
        samples.append(float(latency_ms))
        max_samples = int(item.get("max_samples", 200))
        if len(samples) > max_samples:
            samples = samples[-max_samples:]
        item["latency_ms"] = samples


async def get_service_metrics_snapshot() -> dict[str, Any]:
    async with _metrics_lock:
        monitor = dict(_metrics.get("monitor_desk_exposure", {}))
        latencies = list(monitor.get("latency_ms", []))
        return {
            "monitor_desk_exposure": {
                "request_count": int(monitor.get("request_count", 0)),
                "p95_latency_ms": p95(latencies),
                "sample_size": len(latencies),
            }
        }
