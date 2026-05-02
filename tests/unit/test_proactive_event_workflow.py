from __future__ import annotations

import pytest

from riskmonitor_multiagent.contracts.event import EventType, new_event
from riskmonitor_multiagent.orchestration.proactive_workflow import (
    ProactiveMultiAgentWorkflow,
    reset_proactive_workflow,
)


@pytest.mark.asyncio
async def test_start_from_event_builds_system_event_run_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_proactive_workflow()
    workflow = ProactiveMultiAgentWorkflow()
    captured: dict[str, object] = {}

    async def fake_run_internal(
        self,
        *,
        task: dict,
        run_context: dict,
        route_decision: dict | None = None,
        source_event: dict | None = None,
    ) -> dict:
        captured["task"] = task
        captured["run_context"] = run_context
        captured["route_decision"] = route_decision
        captured["source_event"] = source_event
        return {
            "status": "completed",
            "run_id": run_context.get("run_id"),
            "entry_type": run_context.get("entry_type"),
            "run_context": run_context,
        }

    monkeypatch.setattr(
        ProactiveMultiAgentWorkflow,
        "_run_internal",
        fake_run_internal,
        raising=True,
    )
    event = new_event(
        event_type=EventType.TASK_CREATED,
        source_agent="monitor",
        payload={"content": "请处理告警事件", "task_id": "evt_task_001"},
    )

    result = await workflow.start_from_event(event=event, candidate_agents=["orchestrator"])

    assert result.get("entry_type") == "system_event"
    run_context = captured["run_context"]
    assert isinstance(run_context, dict)
    assert run_context.get("entry_type") == "system_event"
    assert run_context.get("trigger_event_id") == event.get("event_id")
    task = captured["task"]
    assert isinstance(task, dict)
    assert task.get("trigger_event_id") == event.get("event_id")
    assert isinstance(task.get("trigger_reason"), str) and task.get("trigger_reason")
    assert isinstance(task.get("trigger_evidence"), dict)
    assert task.get("payload", {}).get("content") == "请处理告警事件"
    assert task.get("payload", {}).get("trigger_event_id") == event.get("event_id")


@pytest.mark.asyncio
async def test_start_from_event_rejects_invalid_event() -> None:
    reset_proactive_workflow()
    workflow = ProactiveMultiAgentWorkflow()

    result = await workflow.start_from_event(
        event={
            "event_id": "evt_invalid_001",
            "event_type": "not_supported",
            "source_agent": "monitor",
            "payload": {},
        }
    )

    assert result.get("status") == "failed"
    assert result.get("entry_type") == "system_event"
    assert "invalid_event:" in (result.get("errors") or [""])[0]
