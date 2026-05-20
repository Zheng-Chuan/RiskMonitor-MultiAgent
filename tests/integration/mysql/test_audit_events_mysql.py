import sys
import time
import uuid
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


@pytest.mark.asyncio
async def test_audit_event_persistence_and_retrieval():
    from riskmonitor_multiagent.data_access import audit_repository
    from riskmonitor_multiagent.data_access.mysql_engine import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_id VARCHAR(36) PRIMARY KEY,
                    ts_ms BIGINT NOT NULL,
                    event_id VARCHAR(128) NOT NULL,
                    correlation_id VARCHAR(128) DEFAULT NULL,
                    run_id VARCHAR(128) NOT NULL,
                    command_id VARCHAR(128) DEFAULT NULL,
                    target_agent VARCHAR(64) NOT NULL,
                    action VARCHAR(128) NOT NULL,
                    actor VARCHAR(128) NOT NULL,
                    approved BOOLEAN NOT NULL DEFAULT FALSE,
                    approved_by VARCHAR(128) DEFAULT NULL,
                    approval_reason VARCHAR(128) DEFAULT NULL,
                    ok BOOLEAN NOT NULL DEFAULT FALSE,
                    error TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_audit_event_id (event_id),
                    INDEX idx_audit_correlation_id (correlation_id),
                    INDEX idx_audit_run_id (run_id),
                    INDEX idx_audit_ts_ms (ts_ms)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )

    event_id = f"test-audit-{int(time.time() * 1000)}"
    record = {
        "audit_id": str(uuid.uuid4()),
        "ts_ms": int(time.time() * 1000),
        "event_id": event_id,
        "correlation_id": "corr-1",
        "run_id": "run-1",
        "command_id": "cmd-1",
        "target_agent": "orchestrator",
        "action": "write_alert",
        "actor": "proactive_workflow",
        "approved": True,
        "approved_by": "auto",
        "approval_reason": "side_effect_required",
        "ok": True,
        "error": None,
    }
    audit_repository.save_audit_record(record)
    rows = audit_repository.get_audit_records_by_event_id(event_id, limit=10)
    assert len(rows) >= 1
    assert rows[0]["event_id"] == event_id
    by_id = audit_repository.get_audit_record_by_id(record["audit_id"])
    assert by_id is not None
    assert by_id["audit_id"] == record["audit_id"]
