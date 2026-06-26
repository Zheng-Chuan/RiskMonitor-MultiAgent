"""Cron workflow integration tests."""

from __future__ import annotations

import time
from typing import Any

import pytest

from riskmonitor_multiagent.governance.proactive_budget import (
    ProactiveBudgetManager,
    reset_proactive_budget_manager,
)
from riskmonitor_multiagent.observability.run_trace import reset_run_trace_store
from riskmonitor_multiagent.orchestration.proactive_workflow import (
    ProactiveMultiAgentWorkflow,
    reset_proactive_workflow,
)
from riskmonitor_multiagent.scheduling.cron_manager import CronManager, CronTask
from riskmonitor_multiagent.scheduling.cron_templates import FINANCIAL_CRON_TEMPLATES


def _make_cron_task(
    *,
    name: str = "test-cron-task",
    cron_expression: str = "0 18 * * 1-5",
    natural_language: str = "every-weekday-after-close",
    task_template: dict[str, Any] | None = None,
    trigger_config: dict[str, Any] | None = None,
) -> CronTask:
    return CronTask(
        task_id=f"cron_test_{int(time.time() * 1000)}",
        name=name,
        cron_expression=cron_expression,
        natural_language=natural_language,
        task_template=task_template or {"intent": "test_intent", "content": {"scope": "test"}},
        trigger_config=trigger_config or {"entry_type": "system_event", "priority": "normal"},
        enabled=True,
        created_at=int(time.time() * 1000),
        last_triggered=None,
        trigger_count=0,
        max_recursion_depth=3,
    )


@pytest.mark.asyncio
async def test_cron_triggered_workflow_has_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_proactive_workflow()
    reset_proactive_budget_manager()
    reset_run_trace_store()
    workflow = ProactiveMultiAgentWorkflow()

    captured: dict[str, Any] = {}

    async def fake_run_internal(
        self,
        *,
        task: dict[str, Any],
        run_context: dict[str, Any],
        route_decision: dict[str, Any] | None = None,
        source_event: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        captured["task"] = task
        captured["run_context"] = run_context
        captured["source_event"] = source_event
        captured["route_decision"] = route_decision
        return {
            "status": "completed",
            "run_id": run_context.get("run_id"),
            "entry_type": run_context.get("entry_type"),
            "run_context": run_context,
            "task_id": task.get("task_id"),
            "task_graph_execution": {"status": "completed", "trace": [], "receipts": []},
            "orchestrator_plan": {"plan_steps": [], "nodes": []},
            "critic_plan": {"ok": True, "issues": []},
            "receipts": [],
            "final_output": {"result": "done"},
            "errors": [],
            "latency_ms": 1.0,
        }

    monkeypatch.setattr(
        ProactiveMultiAgentWorkflow,
        "_run_internal",
        fake_run_internal,
        raising=True,
    )

    cron_task = _make_cron_task(name="post-market-risk-summary")
    result = await workflow.run_cron_triggered_workflow(cron_task)

    assert result["status"] == "completed"
    assert result["entry_type"] == "system_event"
    assert result["cron_task_id"] == cron_task.task_id
    assert result["cron_task_name"] == "post-market-risk-summary"

    source_event = captured.get("source_event")
    assert source_event is not None
    assert source_event["event_type"] == "cron_triggered"
    assert source_event["source_agent"] == "cron_manager"
    assert source_event["event_id"].startswith(f"cron_{cron_task.task_id}_")

    payload = source_event["payload"]
    assert payload["intent"] == "test_intent"
    assert payload["task_id"] == cron_task.task_id

    assert "run_trace" in result
    trace = result["run_trace"]
    assert trace["entry_type"] == "system_event"
    assert trace["status"] == "completed"

    source_event_entries = [
        e for e in trace["entries"] if e.get("trace_type") == "source_event"
    ]
    assert len(source_event_entries) >= 1
    assert source_event_entries[0]["payload"]["event_type"] == "cron_triggered"


@pytest.mark.asyncio
async def test_cron_storm_budget_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_proactive_workflow()
    reset_proactive_budget_manager()
    reset_run_trace_store()
    workflow = ProactiveMultiAgentWorkflow()

    blocked_count = {"value": 0}

    async def fake_run_internal(
        self,
        *,
        task: dict[str, Any],
        run_context: dict[str, Any],
        route_decision: dict[str, Any] | None = None,
        source_event: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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

    budget = workflow._proactive_budget
    budget._event_burst_limit = 3
    budget._max_concurrent_runs = 2

    results: list[dict[str, Any]] = []
    for i in range(6):
        cron_task = _make_cron_task(name=f"storm-task-{i}")
        result = await workflow.run_cron_triggered_workflow(cron_task)
        results.append(result)
        if result.get("status") == "blocked":
            blocked_count["value"] += 1
        if result.get("status") == "completed":
            budget.release_run(
                run_id=str(result.get("run_context", {}).get("run_id", "")),
                status="completed",
            )

    assert blocked_count["value"] > 0, "Expected some cron tasks to be blocked by budget"

    blocked_result = next(r for r in results if r.get("status") == "blocked")
    budget_info = blocked_result.get("governance", {}).get("proactive_budget", {})
    assert budget_info.get("reason") in {
        "event_burst_limit_exceeded",
        "concurrent_proactive_runs_exceeded",
        "proactive_token_budget_exceeded",
        "circuit_breaker_open",
    }


@pytest.mark.asyncio
async def test_financial_templates_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_proactive_workflow()
    reset_proactive_budget_manager()
    reset_run_trace_store()
    workflow = ProactiveMultiAgentWorkflow()

    captured_events: list[dict[str, Any]] = []

    async def fake_run_internal(
        self,
        *,
        task: dict[str, Any],
        run_context: dict[str, Any],
        route_decision: dict[str, Any] | None = None,
        source_event: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        captured_events.append(source_event or {})
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

    for template in FINANCIAL_CRON_TEMPLATES:
        cron_task = CronTask(
            task_id=f"cron_tmpl_{template['name']}",
            name=template["name"],
            cron_expression=template["cron_expression"],
            natural_language=template["natural_language"],
            task_template=template["task_template"],
            trigger_config=template["trigger_config"],
            enabled=True,
            created_at=int(time.time() * 1000),
            last_triggered=None,
            trigger_count=0,
            max_recursion_depth=3,
        )
        result = await workflow.run_cron_triggered_workflow(cron_task)

        assert result["status"] == "completed"
        assert result["cron_task_name"] == template["name"]
        assert result["cron_expression"] == template["cron_expression"]

        budget = workflow._proactive_budget
        budget.release_run(
            run_id=str(result.get("run_context", {}).get("run_id", "")),
            status="completed",
        )

    assert len(captured_events) == 3

    intents = [evt.get("payload", {}).get("intent") for evt in captured_events]
    assert "daily_post_market_risk_summary" in intents
    assert "threshold_patrol_check" in intents
    assert "weekly_compliance_report" in intents

    for evt in captured_events:
        priority = evt.get("priority", "normal")
        assert priority in {"normal", "high"}


@pytest.mark.asyncio
async def test_natural_language_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_proactive_workflow()
    reset_proactive_budget_manager()
    reset_run_trace_store()
    workflow = ProactiveMultiAgentWorkflow()

    manager = CronManager()

    task = await manager.create_task({
        "name": "nl-only-test",
        "natural_language": "每小时",
        "task_template": {"intent": "hourly"},
        "trigger_config": {"priority": "high"},
    })

    assert task.cron_expression == "0 * * * *"

    task2 = await manager.create_task({
        "name": "override-test",
        "natural_language": "每个工作日收盘后",
        "cron_expression": "30 17 * * 1-5",
        "task_template": {"intent": "custom"},
        "trigger_config": {},
    })

    assert task2.cron_expression == "30 17 * * 1-5"
    assert task2.natural_language == "每个工作日收盘后"

    parsed = manager.parse_natural_language("每个工作日收盘后")
    assert parsed == "0 18 * * 1-5"
    assert task2.cron_expression != parsed

    captured: dict[str, Any] = {}

    async def fake_run_internal(
        self,
        *,
        task: dict[str, Any],
        run_context: dict[str, Any],
        route_decision: dict[str, Any] | None = None,
        source_event: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        captured["source_event"] = source_event
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

    result = await workflow.run_cron_triggered_workflow(task2)
    assert result["status"] == "completed"
    assert result["cron_expression"] == "30 17 * * 1-5"

    source_event = captured.get("source_event")
    assert source_event is not None
    assert source_event["event_type"] == "cron_triggered"
    assert source_event["payload"]["intent"] == "custom"


@pytest.mark.asyncio
async def test_paused_cron_does_not_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_proactive_workflow()
    reset_proactive_budget_manager()
    reset_run_trace_store()

    manager = CronManager()
    task = await manager.create_task({
        "name": "pause-test",
        "cron_expression": "0 * * * *",
        "task_template": {"intent": "paused"},
        "trigger_config": {},
    })

    await manager.pause_task(task.task_id)

    due = await manager.get_due_tasks()
    assert all(t.task_id != task.task_id for t in due)

    await manager.resume_task(task.task_id)
    due = await manager.get_due_tasks()
    assert any(t.task_id == task.task_id for t in due)


@pytest.mark.asyncio
async def test_cron_failure_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_proactive_workflow()
    reset_proactive_budget_manager()
    reset_run_trace_store()
    workflow = ProactiveMultiAgentWorkflow()

    call_count = {"value": 0}

    async def fake_run_internal(
        self,
        *,
        task: dict[str, Any],
        run_context: dict[str, Any],
        route_decision: dict[str, Any] | None = None,
        source_event: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise RuntimeError("simulated first task failure")
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

    cron_task_1 = _make_cron_task(name="will-fail")
    result_1 = await workflow.run_cron_triggered_workflow(cron_task_1)
    assert result_1["status"] == "failed"
    assert result_1["cron_task_id"] == cron_task_1.task_id

    budget = workflow._proactive_budget
    budget.release_run(
        run_id=str(result_1.get("run_context", {}).get("run_id", "")),
        status="failed",
    )

    cron_task_2 = _make_cron_task(name="should-succeed")
    result_2 = await workflow.run_cron_triggered_workflow(cron_task_2)
    assert result_2["status"] == "completed"
    assert result_2["cron_task_id"] == cron_task_2.task_id


@pytest.mark.asyncio
async def test_cron_manager_with_budget_integration() -> None:
    reset_proactive_workflow()
    reset_proactive_budget_manager()
    reset_run_trace_store()

    manager = CronManager()
    budget = ProactiveBudgetManager()
    budget._event_burst_limit = 2

    tasks = []
    for i in range(3):
        task = await manager.create_task({
            "name": f"budget-task-{i}",
            "cron_expression": "0 * * * *",
            "task_template": {"intent": f"task_{i}"},
            "trigger_config": {},
        })
        tasks.append(task)

    allowed = 0
    blocked = 0
    for task in tasks:
        event = {
            "event_type": "cron_triggered",
            "source_agent": "cron_manager",
            "payload": task.task_template,
        }
        decision = budget.evaluate_and_reserve(
            run_id=f"run_{task.task_id}",
            event=event,
        )
        if decision.allowed:
            allowed += 1
        else:
            blocked += 1

    assert allowed == 2
    assert blocked == 1


@pytest.mark.asyncio
async def test_recursion_guard_integration() -> None:
    manager = CronManager()
    task = await manager.create_task({
        "name": "recursion-guard",
        "cron_expression": "0 0 * * *",
        "task_template": {"intent": "recursive"},
        "trigger_config": {},
        "max_recursion_depth": 2,
    })

    assert manager.check_recursion(task.task_id, 0) is True
    assert manager.check_recursion(task.task_id, 1) is True
    assert manager.check_recursion(task.task_id, 2) is True
    assert manager.check_recursion(task.task_id, 3) is False

    manager.reset_recursion(task.task_id)
    assert manager.check_recursion(task.task_id, 1) is True
