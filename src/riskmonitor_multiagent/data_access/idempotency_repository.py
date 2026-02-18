from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import text

from riskmonitor_multiagent.data_access.errors import map_mysql_error
from riskmonitor_multiagent.data_access.mysql_engine import get_engine


@dataclass(frozen=True)
class ProcessingDecision:
    decision: str
    attempts: int
    status: str
    last_error: Optional[str]


def try_begin_processing(*, topic: str, partition: int, offset: int, event_id: str) -> ProcessingDecision:
    engine = get_engine()
    sql_select = text(
        """
        SELECT status, attempts, last_error
        FROM processed_cdc_events
        WHERE topic = :topic AND partition_id = :partition_id AND offset_id = :offset_id
        FOR UPDATE
        """
    )
    sql_insert = text(
        """
        INSERT INTO processed_cdc_events (topic, partition_id, offset_id, event_id, status, attempts, last_error)
        VALUES (:topic, :partition_id, :offset_id, :event_id, 'processing', 1, NULL)
        """
    )
    sql_update_retry = text(
        """
        UPDATE processed_cdc_events
        SET status = 'processing',
            attempts = attempts + 1,
            event_id = :event_id,
            last_error = NULL
        WHERE topic = :topic AND partition_id = :partition_id AND offset_id = :offset_id
        """
    )

    params = {"topic": topic, "partition_id": int(partition), "offset_id": int(offset), "event_id": event_id}

    try:
        with engine.connect() as conn:
            with conn.begin():
                row = conn.execute(sql_select, params).mappings().fetchone()
                if row is None:
                    conn.execute(sql_insert, params)
                    return ProcessingDecision(decision="process", attempts=1, status="processing", last_error=None)
                status = str(row.get("status") or "")
                attempts = int(row.get("attempts") or 0)
                last_error = row.get("last_error")
                if status == "done":
                    return ProcessingDecision(decision="skip_done", attempts=attempts, status=status, last_error=str(last_error) if last_error is not None else None)
                if status == "processing":
                    return ProcessingDecision(decision="skip_inflight", attempts=attempts, status=status, last_error=str(last_error) if last_error is not None else None)
                conn.execute(sql_update_retry, params)
                return ProcessingDecision(decision="process", attempts=attempts + 1, status="processing", last_error=None)
    except Exception as e:
        raise map_mysql_error(e, operation="try_begin_processing") from e


def mark_done(*, topic: str, partition: int, offset: int) -> None:
    engine = get_engine()
    sql = text(
        """
        UPDATE processed_cdc_events
        SET status = 'done', last_error = NULL
        WHERE topic = :topic AND partition_id = :partition_id AND offset_id = :offset_id
        """
    )
    try:
        with engine.connect() as conn:
            conn.execute(sql, {"topic": topic, "partition_id": int(partition), "offset_id": int(offset)})
            conn.commit()
    except Exception as e:
        raise map_mysql_error(e, operation="mark_done") from e


def mark_failed(*, topic: str, partition: int, offset: int, error_message: str) -> None:
    engine = get_engine()
    sql = text(
        """
        UPDATE processed_cdc_events
        SET status = 'failed', last_error = :last_error
        WHERE topic = :topic AND partition_id = :partition_id AND offset_id = :offset_id
        """
    )
    try:
        with engine.connect() as conn:
            conn.execute(
                sql,
                {
                    "topic": topic,
                    "partition_id": int(partition),
                    "offset_id": int(offset),
                    "last_error": (error_message or "")[:2000],
                },
            )
            conn.commit()
    except Exception as e:
        raise map_mysql_error(e, operation="mark_failed") from e


def get_status(*, topic: str, partition: int, offset: int) -> Optional[dict[str, Any]]:
    engine = get_engine()
    sql = text(
        """
        SELECT topic, partition_id, offset_id, event_id, status, attempts, last_error, created_at, updated_at
        FROM processed_cdc_events
        WHERE topic = :topic AND partition_id = :partition_id AND offset_id = :offset_id
        """
    )
    try:
        with engine.connect() as conn:
            row = conn.execute(sql, {"topic": topic, "partition_id": int(partition), "offset_id": int(offset)}).mappings().fetchone()
            return dict(row) if row else None
    except Exception as e:
        raise map_mysql_error(e, operation="get_status") from e

