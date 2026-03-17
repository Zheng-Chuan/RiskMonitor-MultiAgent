"""
完整的多 Agent 协作工作流.

让系统真正能跑起来的完整实现.
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
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms
from riskmonitor_multiagent.services.logging_service import new_request_id
from riskmonitor_multiagent.utils.ids import new_run_id

import logging

logger = logging.getLogger(__name__)


class MultiAgentCollaborationWorkflow:
    """
    完整的多 Agent 协作工作流.

    整合所有 Agent，让系统真正能跑起来.
    """

    def __init__(self):
        self._intent_agent = IntentAgent()
        self._orchestrator_agent = OrchestratorAgent()
        self._critic_agent = CriticAgent()
        self._system_engineer_agent = SystemEngineerAgent()
        self._risk_analyst_agent = RiskAnalystAgent()
        self._conversation_history: list[dict[str, Any]] = []
        self._task: Optional[dict[str, Any]] = None

    async def run(
        self,
        task: dict[str, Any],
    ) -> dict[str, Any]:
        """
        运行多 Agent 协作工作流.

        Args:
            task: 任务

        Returns:
            协作结果
        """
        inc_counter("orchestrator_runs_total")
        start_time = time.time()

        self._task = task
        self._conversation_history = []
        request_id = task.get("task_id") or new_request_id()
        run_id = new_run_id("workflow")

        logger.info(f"Starting multi-agent collaboration for task: {request_id}")

        try:
            # Step 1: Intent Agent
            logger.info("Step 1: Intent Agent")
            intent_result = await self._intent_agent.recognize(task=task)
            self._conversation_history.append({
                "from_agent": "intent",
                "type": "response",
                "content": {"output": intent_result.output, "ok": intent_result.ok},
            })

            # Step 2: Orchestrator Agent
            logger.info("Step 2: Orchestrator Agent")
            orchestrator_result = await self._orchestrator_agent.orchestrate(task=task)
            self._conversation_history.append({
                "from_agent": "orchestrator",
                "type": "response",
                "content": {"output": orchestrator_result.output, "ok": orchestrator_result.ok},
            })

            # Step 3: Critic Agent
            logger.info("Step 3: Critic Agent")
            critic_result = await self._critic_agent.review(
                task=task,
                orchestrator=orchestrator_result.output,
            )
            self._conversation_history.append({
                "from_agent": "critic",
                "type": "response",
                "content": {"output": critic_result.output, "ok": critic_result.ok},
            })

            # Step 4: Parallel Delegation - Engineer and Analyst
            logger.info("Step 4: Parallel Delegation")
            engineer_task = asyncio.create_task(
                self._system_engineer_agent.analyze_task(task=task)
            )
            analyst_task = asyncio.create_task(
                self._risk_analyst_agent.analyze_task(task=task)
            )

            engineer_result, analyst_result = await asyncio.gather(
                engineer_task,
                analyst_task,
            )

            self._conversation_history.append({
                "from_agent": "system_engineer",
                "type": "response",
                "content": {"output": engineer_result.output, "ok": engineer_result.ok},
            })
            self._conversation_history.append({
                "from_agent": "risk_analyst",
                "type": "response",
                "content": {"output": analyst_result.output, "ok": analyst_result.ok},
            })

            # 构建结果
            latency_ms = (time.time() - start_time) * 1000
            observe_ms("orchestrator_latency_ms", latency_ms)
            inc_counter("orchestrator_runs_success")

            result = {
                "status": "completed",
                "run_id": run_id,
                "task_id": request_id,
                "conversation_history": self._conversation_history,
                "latency_ms": latency_ms,
                "intent": intent_result.output,
                "orchestrator": orchestrator_result.output,
                "critic": critic_result.output,
                "engineer": engineer_result.output,
                "analyst": analyst_result.output,
            }

            logger.info(f"Multi-agent collaboration completed for task: {request_id}")
            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            observe_ms("orchestrator_latency_ms", latency_ms)
            inc_counter("orchestrator_runs_error")
            logger.exception(f"Orchestration failed for task {request_id}")
            return {
                "status": "error",
                "run_id": run_id,
                "task_id": request_id,
                "conversation_history": self._conversation_history,
                "latency_ms": latency_ms,
                "errors": [str(e)],
            }


# 全局工作流实例
_workflow: Optional[MultiAgentCollaborationWorkflow] = None


def get_multi_agent_workflow() -> MultiAgentCollaborationWorkflow:
    """获取全局多 Agent 协作工作流实例."""
    global _workflow
    if _workflow is None:
        _workflow = MultiAgentCollaborationWorkflow()
    return _workflow


def reset_multi_agent_workflow() -> None:
    """重置工作流（用于测试）."""
    global _workflow
    _workflow = None
