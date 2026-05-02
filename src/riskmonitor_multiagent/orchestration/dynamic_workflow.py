from __future__ import annotations

from typing import Any

from riskmonitor_multiagent.orchestration.message_bus import get_message_bus


class DynamicCollaborationWorkflow:
    """旧动态协作测试兼容层."""

    def __init__(self) -> None:
        self._message_bus = get_message_bus()
        self._moderator = object()
        self._intent_agent = object()
        self._orchestrator_agent = object()
        self._critic_agent = object()
        self._system_engineer_agent = object()
        self._risk_analyst_agent = object()
        self._state = "initial"
        self._completed_agents: set[str] = set()
        self._conversation_history: list[dict[str, Any]] = []

    async def _decide_next_action(self) -> str:
        if self._state == "all_done":
            return "done"
        if "intent" not in self._completed_agents:
            return "call_intent"
        if "orchestrator" not in self._completed_agents:
            return "call_orchestrator"
        if "critic" not in self._completed_agents:
            return "call_critic"
        if "engineer" not in self._completed_agents and "analyst" not in self._completed_agents:
            return "call_both_parallel"
        if "engineer" not in self._completed_agents:
            return "call_engineer"
        if "analyst" not in self._completed_agents:
            return "call_analyst"
        return "done"

    def _get_agent_output(self, agent_name: str) -> dict[str, Any]:
        for item in reversed(self._conversation_history):
            if item.get("from_agent") == agent_name:
                content = item.get("content")
                if isinstance(content, dict):
                    output = content.get("output")
                    if isinstance(output, dict):
                        return output
        return {}


_DYNAMIC_WORKFLOW: DynamicCollaborationWorkflow | None = None


def get_dynamic_workflow() -> DynamicCollaborationWorkflow:
    global _DYNAMIC_WORKFLOW
    if _DYNAMIC_WORKFLOW is None:
        _DYNAMIC_WORKFLOW = DynamicCollaborationWorkflow()
    return _DYNAMIC_WORKFLOW


def reset_dynamic_workflow() -> None:
    global _DYNAMIC_WORKFLOW
    _DYNAMIC_WORKFLOW = None


__all__ = [
    "DynamicCollaborationWorkflow",
    "get_dynamic_workflow",
    "reset_dynamic_workflow",
]
