from __future__ import annotations

import pytest

from riskmonitor_multiagent.proactive_agents.roles import ProactiveSystemEngineerAgent


@pytest.mark.asyncio
async def test_proactive_agent_emits_event_and_runs_followup_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = ProactiveSystemEngineerAgent()
    emitted: dict[str, object] = {}

    class FakeWorkflow:
        async def start_from_event(
            self,
            *,
            event: dict,
            candidate_agents: list[str] | None = None,
        ) -> dict:
            emitted["event"] = event
            emitted["candidate_agents"] = candidate_agents
            return {
                "status": "completed",
                "entry_type": "system_event",
                "run_context": {"entry_type": "system_event", "run_id": "run_001"},
            }

    import riskmonitor_multiagent.orchestration.proactive_workflow as workflow_module

    monkeypatch.setattr(workflow_module, "get_proactive_workflow", lambda: FakeWorkflow(), raising=True)

    agent.add_intention(
        description="主动告警:系统错误率异常",
        target_agent="orchestrator",
        tool_name="submit_alerts",
        tool_params={
            "metric_name": "error_rate",
            "metric_value": 0.34,
            "severity": "high",
        },
    )

    await agent._act()

    event = emitted["event"]
    assert isinstance(event, dict)
    assert event.get("event_type") == "risk_breach_detected"
    payload = event.get("payload") or {}
    assert payload.get("trigger_reason") == "主动告警:系统错误率异常"
    task = payload.get("task") or {}
    assert task.get("payload", {}).get("proactive_intention_id")
    assert emitted["candidate_agents"] == ["orchestrator", "critic"]
