from __future__ import annotations

import time
from typing import Any

from riskmonitor_multiagent.data_access.health_checks import check_mysql_ready
from riskmonitor_multiagent.services.prometheus_metrics_service import get_metrics_summary


def observe_service_metrics() -> dict[str, Any]:
    start = time.monotonic()
    summary = get_metrics_summary()
    latency_ms = (time.monotonic() - start) * 1000.0
    return {"ok": True, "latency_ms": float(latency_ms), "summary": summary}


def observe_mysql_health() -> dict[str, Any]:
    start = time.monotonic()
    ok, message, err = check_mysql_ready()
    latency_ms = (time.monotonic() - start) * 1000.0
    return {
        "ok": bool(ok),
        "latency_ms": float(latency_ms),
        "message": message,
        "error_code": err.code if err is not None else None,
    }


def observe_chroma_health() -> dict[str, Any]:
    start = time.monotonic()
    try:
        from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore

        store = ChromaVectorStore()
        _ = store.query_alerts(query_text="health_check", top_k=1)
        ok = True
        message = "ok"
        error = None
    except Exception as e:  # pylint: disable=broad-except
        ok = False
        message = "chroma_unavailable"
        error = str(e)
    latency_ms = (time.monotonic() - start) * 1000.0
    return {"ok": bool(ok), "latency_ms": float(latency_ms), "message": message, "error": error}


def observe_kafka_lag_estimate(*, message_ts_ms: int | None) -> dict[str, Any]:
    start = time.monotonic()
    now_ms = int(time.time() * 1000)
    if not isinstance(message_ts_ms, int):
        ok = False
        lag_ms = None
        message = "missing_message_ts_ms"
    else:
        ok = True
        lag_ms = max(0, now_ms - int(message_ts_ms))
        message = "ok"
    latency_ms = (time.monotonic() - start) * 1000.0
    return {"ok": bool(ok), "latency_ms": float(latency_ms), "message": message, "lag_ms": lag_ms}
