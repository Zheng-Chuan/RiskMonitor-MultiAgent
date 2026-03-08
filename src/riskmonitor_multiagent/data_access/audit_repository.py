from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text

from riskmonitor_multiagent.data_access.errors import map_mysql_error
from riskmonitor_multiagent.data_access.mysql_engine import get_engine


def save_audit_record(record: Dict[str, Any]) -> None:
    engine = get_engine()
    sql = text(
        """
        INSERT INTO audit_events (
            audit_id, ts_ms, event_id, correlation_id, run_id, command_id,
            target_agent, action, actor, approved, approved_by, approval_reason,
            ok, error
        ) VALUES (
            :audit_id, :ts_ms, :event_id, :correlation_id, :run_id, :command_id,
            :target_agent, :action, :actor, :approved, :approved_by, :approval_reason,
            :ok, :error
        )
        """
    )
    try:
        with engine.begin() as conn:
            conn.execute(sql, record)
    except Exception as e:
        raise map_mysql_error(e, operation="save_audit_record") from e


def save_audit_records_batch(records: List[Dict[str, Any]]) -> None:
    if not records:
        return
    engine = get_engine()
    sql = text(
        """
        INSERT INTO audit_events (
            audit_id, ts_ms, event_id, correlation_id, run_id, command_id,
            target_agent, action, actor, approved, approved_by, approval_reason,
            ok, error
        ) VALUES (
            :audit_id, :ts_ms, :event_id, :correlation_id, :run_id, :command_id,
            :target_agent, :action, :actor, :approved, :approved_by, :approval_reason,
            :ok, :error
        )
        """
    )
    try:
        with engine.begin() as conn:
            for rec in records:
                conn.execute(sql, rec)
    except Exception as e:
        raise map_mysql_error(e, operation="save_audit_records_batch") from e


def get_audit_records_by_event_id(event_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
    engine = get_engine()
    sql = text(
        """
        SELECT * FROM audit_events
        WHERE event_id = :event_id
        ORDER BY ts_ms DESC
        LIMIT :limit
        """
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, {"event_id": event_id, "limit": int(limit)}).mappings().fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        raise map_mysql_error(e, operation="get_audit_records_by_event_id") from e


def get_audit_record_by_id(audit_id: str) -> Optional[Dict[str, Any]]:
    engine = get_engine()
    sql = text("SELECT * FROM audit_events WHERE audit_id = :audit_id")
    try:
        with engine.connect() as conn:
            row = conn.execute(sql, {"audit_id": audit_id}).mappings().fetchone()
            return dict(row) if row else None
    except Exception as e:
        raise map_mysql_error(e, operation="get_audit_record_by_id") from e

