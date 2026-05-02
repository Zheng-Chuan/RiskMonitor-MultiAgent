from __future__ import annotations

from typing import Any

from riskmonitor_multiagent.contracts.event import EventType
from riskmonitor_multiagent.orchestration.message_bus import get_message_bus
from riskmonitor_multiagent.orchestration.proactive_workflow import get_proactive_workflow
from riskmonitor_multiagent.proactive_agents import ModeratorAgent


class MultiAgentCollaborationWorkflow:
    """旧测试兼容的多 Agent 工作流骨架."""

    def __init__(self) -> None:
        self._message_bus = get_message_bus()
        self._workflow = get_proactive_workflow()
        self._moderator = ModeratorAgent(message_bus=self._message_bus)
        self._intent_agent = object()
        self._orchestrator_agent = object()
        self._critic_agent = object()
        self._system_engineer_agent = object()
        self._risk_analyst_agent = object()

    async def route_event(
        self,
        *,
        event: dict[str, Any],
        candidate_agents: list[str],
        conflict: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """让 moderator 基于事件做下一跳决策."""
        return await self._moderator.moderate(
            event=event,
            candidate_agents=candidate_agents,
            conflict=conflict,
        )

    async def create_task(self, *, source_agent: str, payload: dict[str, Any]) -> dict[str, Any]:
        """创建任务事件, 供集成测试和最小工作流使用."""
        return await self._message_bus.emit_event(
            event_type=EventType.TASK_CREATED,
            source_agent=source_agent,
            payload=payload,
        )

    async def run_user_task(self, *, task: dict[str, Any]) -> dict[str, Any]:
        """通过统一 workflow 运行用户显式任务."""
        return await self._workflow.run(task)

    async def run_system_event(
        self,
        *,
        event: dict[str, Any],
        candidate_agents: list[str] | None = None,
    ) -> dict[str, Any]:
        """通过统一 workflow 运行系统事件."""
        return await self._workflow.start_from_event(
            event=event,
            candidate_agents=candidate_agents,
        )


_MULTI_AGENT_WORKFLOW: MultiAgentCollaborationWorkflow | None = None


def get_multi_agent_workflow() -> MultiAgentCollaborationWorkflow:
    global _MULTI_AGENT_WORKFLOW
    if _MULTI_AGENT_WORKFLOW is None:
        _MULTI_AGENT_WORKFLOW = MultiAgentCollaborationWorkflow()
    return _MULTI_AGENT_WORKFLOW


def reset_multi_agent_workflow() -> None:
    global _MULTI_AGENT_WORKFLOW
    _MULTI_AGENT_WORKFLOW = None


__all__ = [
    "MultiAgentCollaborationWorkflow",
    "get_multi_agent_workflow",
    "reset_multi_agent_workflow",
]
