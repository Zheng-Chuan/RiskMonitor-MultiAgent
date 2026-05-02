from __future__ import annotations

from riskmonitor_multiagent.contracts.run_context import (
    RUN_CONTEXT_SCHEMA_VERSION,
    new_run_context,
    normalize_run_context,
    validate_run_context,
)


def test_normalize_run_context() -> None:
    run_context = normalize_run_context(
        {
            "entry_type": "user_task",
            "task_id": "task-001",
        }
    )

    assert run_context.get("schema_version") == RUN_CONTEXT_SCHEMA_VERSION
    assert isinstance(run_context.get("run_id"), str) and run_context.get("run_id")
    assert run_context.get("entry_type") == "user_task"
    assert run_context.get("trigger_evidence") == {}
    assert run_context.get("route_decision") == {}


def test_validate_run_context_rejects_bad_fields() -> None:
    is_valid, errors = validate_run_context(
        {
            "schema_version": RUN_CONTEXT_SCHEMA_VERSION,
            "run_id": "",
            "entry_type": "bad",
            "trigger_evidence": [],
            "route_decision": [],
            "metadata": [],
        }
    )

    assert is_valid is False
    assert "bad_run_id" in errors
    assert "bad_entry_type" in errors
    assert "bad_trigger_evidence" in errors
    assert "bad_route_decision" in errors
    assert "bad_metadata" in errors


def test_new_run_context_for_system_event() -> None:
    run_context = new_run_context(
        entry_type="system_event",
        task_id="event-task",
        trigger_event_id="evt_001",
        trigger_reason="风险 breach 优先交给 orchestrator",
        trigger_evidence={"event_type": "risk_breach_detected"},
    )

    is_valid, errors = validate_run_context(run_context)
    assert is_valid is True
    assert errors == []
    assert run_context.get("entry_type") == "system_event"
    assert run_context.get("trigger_event_id") == "evt_001"
