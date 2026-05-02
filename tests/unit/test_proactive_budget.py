from __future__ import annotations

import pytest

from riskmonitor_multiagent.contracts.event import EventType, new_event
from riskmonitor_multiagent.governance.proactive_budget import (
    ProactiveBudgetManager,
    reset_proactive_budget_manager,
)
from riskmonitor_multiagent.orchestration.proactive_workflow import (
    ProactiveMultiAgentWorkflow,
    reset_proactive_workflow,
)
from riskmonitor_multiagent.observability.run_trace import reset_run_trace_store


def test_proactive_budget_blocks_event_burst() -> None:
    manager = ProactiveBudgetManager()
    manager._event_burst_limit = 1

    first = manager.evaluate_and_reserve(
        run_id="run_001",
        event=new_event(event_type=EventType.TASK_CREATED, source_agent="monitor", payload={"content": "a"}),
    )
    second = manager.evaluate_and_reserve(
        run_id="run_002",
        event=new_event(event_type=EventType.TASK_CREATED, source_agent="monitor", payload={"content": "b"}),
    )

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "event_burst_limit_exceeded"


def test_proactive_budget_opens_circuit_after_failures() -> None:
    manager = ProactiveBudgetManager()
    manager._failure_threshold = 2
    manager.release_run(run_id="run_001", status="failed")
    manager.release_run(run_id="run_002", status="failed")

    decision = manager.evaluate_and_reserve(
        run_id="run_003",
        event=new_event(event_type=EventType.RISK_BREACH_DETECTED, source_agent="monitor", payload={"content": "risk"}),
    )

    assert decision.allowed is False
    assert decision.reason == "circuit_breaker_open"


@pytest.mark.asyncio
async def test_start_from_event_returns_blocked_when_budget_denies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_proactive_workflow()
    reset_proactive_budget_manager()
    reset_run_trace_store()
    workflow = ProactiveMultiAgentWorkflow()

    class FakeBudget:
        def evaluate_and_reserve(self, *, run_id: str, event: dict) -> object:
            return type("Decision", (), {"allowed": False, "reason": "event_burst_limit_exceeded", "evidence": {"events_in_window": 9}})()

        def release_run(self, *, run_id: str, status: str) -> None:
            return None

    monkeypatch.setattr(workflow, "_proactive_budget", FakeBudget(), raising=False)

    result = await workflow.start_from_event(
        event=new_event(
            event_type=EventType.TASK_CREATED,
            source_agent="monitor",
            payload={"content": "请处理"},
        )
    )

    assert result.get("status") == "blocked"
    assert result.get("entry_type") == "system_event"
    assert result.get("governance", {}).get("proactive_budget", {}).get("reason") == "event_burst_limit_exceeded"


@pytest.mark.asyncio
async def test_user_task_run_not_guarded_by_proactive_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_proactive_workflow()
    reset_run_trace_store()
    workflow = ProactiveMultiAgentWorkflow()

    async def fake_run_internal(self, *, task: dict, run_context: dict, route_decision=None, source_event=None) -> dict:
        return {
            "status": "completed",
            "run_id": run_context.get("run_id"),
            "entry_type": run_context.get("entry_type"),
            "run_context": run_context,
            "task_id": task.get("task_id"),
            "task_graph_execution": {},
            "orchestrator_plan": {},
            "critic_plan": {},
            "receipts": [],
            "final_output": {},
            "errors": [],
            "latency_ms": 1.0,
        }

    monkeypatch.setattr(
        ProactiveMultiAgentWorkflow,
        "_run_internal",
        fake_run_internal,
        raising=True,
    )

    result = await workflow.run(
        {"task_id": "task_user_001", "payload": {"content": "用户任务"}}
    )

    assert result.get("status") == "completed"
    assert result.get("entry_type") == "user_task"
