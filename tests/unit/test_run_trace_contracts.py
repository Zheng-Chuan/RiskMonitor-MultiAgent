from __future__ import annotations

from riskmonitor_multiagent.contracts.run_trace import (
    RUN_TRACE_SCHEMA_VERSION,
    normalize_run_trace,
    validate_run_trace,
)


def test_run_trace_contract_accepts_valid_v2_snapshot() -> None:
    snapshot = normalize_run_trace(
        {
            "run_id": "run-v2-1",
            "entry_type": "user_task",
            "status": "completed",
            "task_id": "task-1",
            "version_snapshot": {"model": "demo-model"},
            "failure_summary": {},
            "summary": {"entry_count": 2},
            "entries": [
                {
                    "category": "task",
                    "trace_type": "task",
                    "timestamp_ms": 1,
                    "status": "recorded",
                    "summary": {"task_id": "task-1"},
                    "payload": {"task_id": "task-1"},
                },
                {
                    "category": "final",
                    "trace_type": "run_finished",
                    "timestamp_ms": 2,
                    "status": "completed",
                    "summary": {"status": "completed"},
                    "payload": {"final_output": {"summary": "ok"}},
                },
            ],
        }
    )

    ok, errors = validate_run_trace(snapshot)

    assert snapshot["schema_version"] == RUN_TRACE_SCHEMA_VERSION
    assert ok is True, errors


def test_run_trace_contract_rejects_invalid_category() -> None:
    ok, errors = validate_run_trace(
        {
            "schema_version": RUN_TRACE_SCHEMA_VERSION,
            "run_id": "run-v2-2",
            "entry_type": "user_task",
            "status": "completed",
            "task_id": "task-2",
            "version_snapshot": {},
            "failure_summary": {},
            "summary": {},
            "entries": [
                {
                    "category": "bad_category",
                    "trace_type": "task",
                    "timestamp_ms": 1,
                    "status": "recorded",
                    "summary": {},
                    "payload": {},
                }
            ],
        }
    )

    assert ok is False
    assert "bad_run_trace_entry_category" in errors
