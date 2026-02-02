from __future__ import annotations

import time
from typing import Any

from riskmonitor_multiagent import config
from riskmonitor_multiagent.data_access import alerts_repository
from riskmonitor_multiagent.knowledge.store import SqliteVectorStore
from riskmonitor_multiagent.knowledge.store import stable_alert_text


def _alert_to_doc(alert: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    alert_id = str(alert.get("alert_id") or "")
    desk = str(alert.get("desk") or "")
    severity = str(alert.get("severity") or "")
    alert_type = str(alert.get("alert_type") or "")
    metric_name = str(alert.get("metric_name") or "")
    message = str(alert.get("message") or "")

    content = stable_alert_text(
        [
            "alert",
            f"desk {desk}",
            f"severity {severity}",
            f"type {alert_type}",
            f"metric {metric_name}",
            message,
        ]
    )

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
    store = SqliteVectorStore(path=config.get_knowledge_db_path())
    store.init()

    alerts = alerts_repository.get_recent_alerts(limit=limit, severity=severity, desk=desk)
    now_ms = int(time.time() * 1000)

    ingested = 0
    skipped = 0
    for alert in alerts:
        doc_id, content, metadata = _alert_to_doc(alert)
        if not doc_id:
            skipped += 1
            continue
        store.upsert(doc_id=doc_id, doc_type="alert", content=content, metadata=metadata, updated_at_ms=now_ms)
        ingested += 1

    return {
        "knowledge_db_path": store.path,
        "doc_type": "alert",
        "ingested": ingested,
        "skipped": skipped,
        "total_docs": store.count(doc_type="alert"),
    }

