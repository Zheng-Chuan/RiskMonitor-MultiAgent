"""
真正的动态协作工作流.

不是固定顺序的工作流，而是由 Moderator 动态协调.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from riskmonitor_multiagent.agents.roles import (
    CriticAgent,
    IntentAgent,
    OrchestratorAgent,
    RiskAnalystAgent,
    SystemEngineerAgent,
)
from riskmonitor_multiagent.agents.moderator import ModeratorAgent
from riskmonitor_multiagent.orchestration.message_bus import get_message_bus
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms
from riskmonitor_multiagent.services.logging_service import new_request_id
from riskmonitor_multiagent.utils.ids import new_run_id

import logging

logger = logging.getLogger(__name__)


class DynamicCollaborationWorkflow:
    """
    真正的动态协作工作流.

    由 Moderator 动态决定下一步做什么，不是固定顺序.
    """

    def __init__(self):
        self._message_bus = get_message_bus()
        self._moderator = ModeratorAgent()
        self._intent_agent = IntentAgent()
        self._orchestrator_agent = OrchestratorAgent()
        self._critic_agent = CriticAgent()
        self._system_engineer_agent = SystemEngineerAgent()
        self._risk_analyst_agent = RiskAnalystAgent()
        self._conversation_history: list[dict[str, Any]] = []
        self._task: Optional[dict[str, Any]] = None
        self._completed_agents: set[str] = set()
        self._state = "initial"

    async def run(
        self,
        task: dict[str, Any],
        max_iterations: int = 10,
    ) -> dict[str, Any]:
        """
        运行动态协作工作流.

        Args:
            task: 任务
            max_iterations: 最大迭代次数

        Returns:
            协作结果
        """
        inc_counter("dynamic_workflow_runs_total")
        start_time = time.time()

        self._task = task
        self._conversation_history = []
        self._completed_agents = set()
        self._state = "initial"
        request_id = task.get("task_id") or new_request_id()
        run_id = new_run_id("dynamic_workflow")

        logger.info(f"Starting dynamic collaboration for task: {request_id}")

        try:
            await self._message_bus.broadcast(
                from_agent="workflow",
                content={"status": "started", "task_id": request_id, "mode": "dynamic"},
            )

            iteration = 0
            while iteration < max_iterations:
                iteration += 1
                logger.info(f"Dynamic iteration {iteration}/{max_iterations}, state: {self._state}")

                next_action = await self._decide_next_action()
                logger.info(f"Moderator decided: {next_action}")

                if next_action == "done":
                    logger.info("Moderator decided we're done")
                    break

                await self._execute_action(next_action)

                if self._state == "done":
                    break

            result = await self._finalize_result(
                request_id=request_id,
                run_id=run_id,
                start_time=start_time,
            )

            await self._message_bus.broadcast(
                from_agent="workflow",
                content={"status": "completed", "task_id": request_id},
            )

            logger.info(f"Dynamic collaboration completed for task: {request_id}")
            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            observe_ms("dynamic_workflow_latency_ms", latency_ms)
            inc_counter("dynamic_workflow_runs_error")
            logger.exception(f"Dynamic collaboration failed for task {request_id}")

            await self._message_bus.broadcast(
                from_agent="workflow",
                content={"status": "error", "task_id": request_id, "error": str(e)},
            )

            return {
                "status": "error",
                "run_id": run_id,
                "task_id": request_id,
                "conversation_history": self._conversation_history,
                "message_history": self._message_bus.get_message_history(),
                "latency_ms": latency_ms,
                "errors": [str(e)],
            }

    async def _decide_next_action(self) -> str:
        """
        让 Moderator 决定下一步做什么.

        Returns:
            下一步行动
        """
        if self._state == "initial":
            return "call_intent"

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

    async def _execute_action(self, action: str) -> None:
        """
        执行动作.

        Args:
            action: 动作类型
        """
        if action == "call_intent":
            await self._call_intent_agent()
        elif action == "call_orchestrator":
            await self._call_orchestrator_agent()
        elif action == "call_critic":
            await self._call_critic_agent()
        elif action == "call_engineer":
            await self._call_engineer_agent()
        elif action == "call_analyst":
            await self._call_analyst_agent()
        elif action == "call_both_parallel":
            await self._call_both_parallel()
        elif action == "done":
            self._state = "done"

    async def _call_intent_agent(self) -> None:
        """调用 Intent Agent."""
        request_msg = await self._message_bus.send_request(
            from_agent="moderator",
            to_agent="intent",
            content={"task": self._task},
        )

        intent_result = await self._intent_agent.recognize(task=self._task)

        response_msg = await self._message_bus.send_response(
            from_agent="intent",
            to_agent="moderator",
            content={"output": intent_result.output, "ok": intent_result.ok},
            in_reply_to=request_msg["message_id"],
        )

        self._conversation_history.append({
            "from_agent": "intent",
            "type": "response",
            "content": {"output": intent_result.output, "ok": intent_result.ok},
            "message_id": response_msg["message_id"],
        })
        self._completed_agents.add("intent")
        self._state = "intent_done"

    async def _call_orchestrator_agent(self) -> None:
        """调用 Orchestrator Agent."""
        request_msg = await self._message_bus.send_request(
            from_agent="moderator",
            to_agent="orchestrator",
            content={"task": self._task},
        )

        orchestrator_result = await self._orchestrator_agent.orchestrate(task=self._task)

        response_msg = await self._message_bus.send_response(
            from_agent="orchestrator",
            to_agent="moderator",
            content={"output": orchestrator_result.output, "ok": orchestrator_result.ok},
            in_reply_to=request_msg["message_id"],
        )

        self._conversation_history.append({
            "from_agent": "orchestrator",
            "type": "response",
            "content": {"output": orchestrator_result.output, "ok": orchestrator_result.ok},
            "message_id": response_msg["message_id"],
        })
        self._completed_agents.add("orchestrator")
        self._state = "orchestrator_done"

    async def _call_critic_agent(self) -> None:
        """调用 Critic Agent."""
        orchestrator_output = self._get_agent_output("orchestrator")

        request_msg = await self._message_bus.send_request(
            from_agent="moderator",
            to_agent="critic",
            content={"task": self._task, "orchestrator": orchestrator_output},
        )

        critic_result = await self._critic_agent.review(
            task=self._task,
            orchestrator=orchestrator_output,
        )

        response_msg = await self._message_bus.send_response(
            from_agent="critic",
            to_agent="moderator",
            content={"output": critic_result.output, "ok": critic_result.ok},
            in_reply_to=request_msg["message_id"],
        )

        self._conversation_history.append({
            "from_agent": "critic",
            "type": "response",
            "content": {"output": critic_result.output, "ok": critic_result.ok},
            "message_id": response_msg["message_id"],
        })
        self._completed_agents.add("critic")
        self._state = "critic_done"

    async def _call_engineer_agent(self) -> None:
        """调用 System Engineer Agent."""
        request_msg = await self._message_bus.send_request(
            from_agent="moderator",
            to_agent="system_engineer",
            content={"task": self._task},
        )

        engineer_result = await self._system_engineer_agent.analyze_task(task=self._task)

        response_msg = await self._message_bus.send_response(
            from_agent="system_engineer",
            to_agent="moderator",
            content={"output": engineer_result.output, "ok": engineer_result.ok},
            in_reply_to=request_msg["message_id"],
        )

        self._conversation_history.append({
            "from_agent": "system_engineer",
            "type": "response",
            "content": {"output": engineer_result.output, "ok": engineer_result.ok},
            "message_id": response_msg["message_id"],
        })
        self._completed_agents.add("engineer")

    async def _call_analyst_agent(self) -> None:
        """调用 Risk Analyst Agent."""
        request_msg = await self._message_bus.send_request(
            from_agent="moderator",
            to_agent="risk_analyst",
            content={"task": self._task},
        )

        analyst_result = await self._risk_analyst_agent.analyze_task(task=self._task)

        response_msg = await self._message_bus.send_response(
            from_agent="risk_analyst",
            to_agent="moderator",
            content={"output": analyst_result.output, "ok": analyst_result.ok},
            in_reply_to=request_msg["message_id"],
        )

        self._conversation_history.append({
            "from_agent": "risk_analyst",
            "type": "response",
            "content": {"output": analyst_result.output, "ok": analyst_result.ok},
            "message_id": response_msg["message_id"],
        })
        self._completed_agents.add("analyst")

    async def _call_both_parallel(self) -> None:
        """并行调用 Engineer 和 Analyst."""
        engineer_request_msg = await self._message_bus.send_request(
            from_agent="moderator",
            to_agent="system_engineer",
            content={"task": self._task},
        )
        analyst_request_msg = await self._message_bus.send_request(
            from_agent="moderator",
            to_agent="risk_analyst",
            content={"task": self._task},
        )

        engineer_task = asyncio.create_task(
            self._system_engineer_agent.analyze_task(task=self._task)
        )
        analyst_task = asyncio.create_task(
            self._risk_analyst_agent.analyze_task(task=self._task)
        )

        engineer_result, analyst_result = await asyncio.gather(
            engineer_task,
            analyst_task,
        )

        engineer_response_msg = await self._message_bus.send_response(
            from_agent="system_engineer",
            to_agent="moderator",
            content={"output": engineer_result.output, "ok": engineer_result.ok},
            in_reply_to=engineer_request_msg["message_id"],
        )
        analyst_response_msg = await self._message_bus.send_response(
            from_agent="risk_analyst",
            to_agent="moderator",
            content={"output": analyst_result.output, "ok": analyst_result.ok},
            in_reply_to=analyst_request_msg["message_id"],
        )

        self._conversation_history.append({
            "from_agent": "system_engineer",
            "type": "response",
            "content": {"output": engineer_result.output, "ok": engineer_result.ok},
            "message_id": engineer_response_msg["message_id"],
        })
        self._conversation_history.append({
            "from_agent": "risk_analyst",
            "type": "response",
            "content": {"output": analyst_result.output, "ok": analyst_result.ok},
            "message_id": analyst_response_msg["message_id"],
        })
        self._completed_agents.add("engineer")
        self._completed_agents.add("analyst")
        self._state = "all_done"

    def _get_agent_output(self, agent_id: str) -> dict[str, Any]:
        """从对话历史中获取 Agent 的输出."""
        for msg in reversed(self._conversation_history):
            if msg.get("from_agent") == agent_id:
                return msg.get("content", {}).get("output", {})
        return {}

    async def _finalize_result(
        self,
        request_id: str,
        run_id: str,
        start_time: float,
    ) -> dict[str, Any]:
        """构建最终结果."""
        latency_ms = (time.time() - start_time) * 1000
        observe_ms("dynamic_workflow_latency_ms", latency_ms)
        inc_counter("dynamic_workflow_runs_success")

        message_history = self._message_bus.get_message_history()

        result = {
            "status": "completed",
            "run_id": run_id,
            "task_id": request_id,
            "mode": "dynamic",
            "conversation_history": self._conversation_history,
            "message_history": message_history,
            "completed_agents": list(self._completed_agents),
            "final_state": self._state,
            "latency_ms": latency_ms,
            "intent": self._get_agent_output("intent"),
            "orchestrator": self._get_agent_output("orchestrator"),
            "critic": self._get_agent_output("critic"),
            "engineer": self._get_agent_output("system_engineer"),
            "analyst": self._get_agent_output("risk_analyst"),
        }

        return result


_dynamic_workflow: Optional[DynamicCollaborationWorkflow] = None


def get_dynamic_workflow() -> DynamicCollaborationWorkflow:
    """获取动态协作工作流实例."""
    global _dynamic_workflow
    if _dynamic_workflow is None:
        _dynamic_workflow = DynamicCollaborationWorkflow()
    return _dynamic_workflow


def reset_dynamic_workflow() -> None:
    """重置工作流（用于测试）."""
    global _dynamic_workflow
    _dynamic_workflow = None


__all__ = [
    "DynamicCollaborationWorkflow",
    "get_dynamic_workflow",
    "reset_dynamic_workflow",
]
