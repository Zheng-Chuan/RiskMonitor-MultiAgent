from __future__ import annotations

import pytest

from riskmonitor_multiagent.contracts.event import EventType, new_event
from riskmonitor_multiagent.orchestration.multiagent_workflow import (
    run_user_task,
    start_from_event,
)
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


@pytest.mark.asyncio
async def test_multiagent_workflow_facade_routes_user_task(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run(*, task: dict) -> dict:
        captured["task"] = task
        return {"status": "completed", "task_id": task.get("task_id")}

    monkeypatch.setattr(
        "riskmonitor_multiagent.orchestration.proactive_workflow.run_proactive_workflow",
        fake_run,
    )
    result = await run_user_task(task={"task_id": "facade-user-1", "payload": {"content": "分析任务"}})

    assert result.get("status") == "completed"
    assert (captured.get("task") or {}).get("task_id") == "facade-user-1"


@pytest.mark.asyncio
async def test_multiagent_workflow_facade_routes_system_event(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeWorkflow:
        async def start_from_event(self, *, event: dict, candidate_agents=None) -> dict:
            return {
                "status": "completed",
                "event_id": event.get("event_id"),
                "candidate_agents": list(candidate_agents or []),
            }

    monkeypatch.setattr(
        "riskmonitor_multiagent.orchestration.proactive_workflow.get_proactive_workflow",
        lambda: _FakeWorkflow(),
    )
    event = new_event(
        event_type=EventType.TASK_CREATED,
        source_agent="monitor",
        payload={"content": "facade event"},
    )

    result = await start_from_event(event=event, candidate_agents=["orchestrator"])

    assert result.get("status") == "completed"
    assert result.get("event_id") == event.get("event_id")
    assert result.get("candidate_agents") == ["orchestrator"]
