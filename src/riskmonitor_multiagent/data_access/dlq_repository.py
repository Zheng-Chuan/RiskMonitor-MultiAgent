from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import text

from riskmonitor_multiagent.data_access.errors import map_mysql_error
from riskmonitor_multiagent.data_access.mysql_engine import get_engine


def save_dlq_event(
    *,
    topic: str,
    partition: int,
    offset: int,
    event_id: Optional[str],
    error_code: Optional[str],
    error_message: str,
    payload: Any,
    attempts: int,
) -> None:
    engine = get_engine()
    sql = text(
        """
        INSERT INTO dlq_events (
            topic, partition_id, offset_id, event_id, error_code, error_message, payload_json, attempts
        ) VALUES (
            :topic, :partition_id, :offset_id, :event_id, :error_code, :error_message, CAST(:payload_json AS JSON), :attempts
        )
        ON DUPLICATE KEY UPDATE
            event_id = VALUES(event_id),
            error_code = VALUES(error_code),
            error_message = VALUES(error_message),
            payload_json = VALUES(payload_json),
            attempts = GREATEST(attempts, VALUES(attempts))
        """
    )
    payload_json = None
    try:
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except Exception:
        payload_json = json.dumps({"unserializable": True}, ensure_ascii=False)

    params = {
        "topic": topic,
        "partition_id": int(partition),
        "offset_id": int(offset),
        "event_id": event_id,
        "error_code": error_code,
        "error_message": (error_message or "")[:2000],
        "payload_json": payload_json,
        "attempts": int(attempts),
    }
    try:
        with engine.connect() as conn:
            conn.execute(sql, params)
            conn.commit()
    except Exception as e:
        raise map_mysql_error(e, operation="save_dlq_event") from e


def get_dlq_event(*, topic: str, partition: int, offset: int) -> Optional[dict[str, Any]]:
    engine = get_engine()
    sql = text(
        """
        SELECT dlq_id, topic, partition_id, offset_id, event_id, error_code, error_message, payload_json, attempts, created_at
        FROM dlq_events
        WHERE topic = :topic AND partition_id = :partition_id AND offset_id = :offset_id
        """
    )
    try:
        with engine.connect() as conn:
            row = conn.execute(sql, {"topic": topic, "partition_id": int(partition), "offset_id": int(offset)}).mappings().fetchone()
            return dict(row) if row else None
    except Exception as e:
        raise map_mysql_error(e, operation="get_dlq_event") from e

