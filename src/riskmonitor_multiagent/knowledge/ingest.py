from __future__ import annotations

import time
from typing import Any

from riskmonitor_multiagent.data_access import alerts_repository
from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore


def _alert_to_doc(alert: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    alert_id = str(alert.get("alert_id") or "")
    desk = str(alert.get("desk") or "")
    severity = str(alert.get("severity") or "")
    alert_type = str(alert.get("alert_type") or "")
    metric_name = str(alert.get("metric_name") or "")
    message = str(alert.get("message") or "")

    content = " ".join(
        [
            "alert",
            f"desk {desk}",
            f"severity {severity}",
            f"type {alert_type}",
            f"metric {metric_name}",
            message,
        ]
    ).strip()

    metadata = {
        "alert_id": alert_id,
        "desk": desk,
        "severity": severity,
        "alert_type": alert_type,
        "metric_name": metric_name,
        "request_id": alert.get("request_id"),
        "created_at": str(alert.get("created_at") or ""),
    }

    return alert_id, content, metadata


def ingest_recent_alerts(
    *,
    limit: int = 500,
    severity: str | None = None,
    desk: str | None = None,
) -> dict[str, Any]:
    store = ChromaVectorStore()

    alerts = alerts_repository.get_recent_alerts(limit=limit, severity=severity, desk=desk)
    now_ms = int(time.time() * 1000)

    ingested = 0
    skipped = 0
    for alert in alerts:
        doc_id, content, metadata = _alert_to_doc(alert)
        if not doc_id:
            skipped += 1
            continue
        metadata["updated_at_ms"] = now_ms
        store.upsert_alert(alert_id=doc_id, document=content, metadata=metadata)
        ingested += 1

    return {
        "vector_db": "chroma",
        "collection": "alerts",
        "ingested": ingested,
        "skipped": skipped,
    }
