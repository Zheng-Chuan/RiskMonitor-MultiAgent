"""
完整的多 Agent 协作工作流.

让系统真正能跑起来的完整实现，集成消息总线.
真正集成 ReAct + CoT 推理范式.
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
from riskmonitor_multiagent.orchestration.react_loop import (
    ReActStep,
    format_react_trace,
)
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms
from riskmonitor_multiagent.services.logging_service import new_request_id
from riskmonitor_multiagent.utils.ids import new_run_id

import logging

logger = logging.getLogger(__name__)


class MultiAgentCollaborationWorkflow:
    """
    完整的多 Agent 协作工作流.

    整合所有 Agent，让系统真正能跑起来，使用消息总线通信.
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
        self._react_steps: list[ReActStep] = []
        self._task: Optional[dict[str, Any]] = None

    async def run(
        self,
        task: dict[str, Any],
    ) -> dict[str, Any]:
        """
        运行多 Agent 协作工作流，使用消息总线.

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
            # 发送广播消息：任务开始
            await self._message_bus.broadcast(
                from_agent="workflow",
                content={"status": "started", "task_id": request_id},
            )

            # ============================================
            # ReAct Step 1: Intent Agent
            # ============================================
            logger.info("ReAct Step 1: Intent Agent")
            
            # Thought + Reasoning + Evidence (CoT)
            thought1 = "我需要先理解用户的意图"
            reasoning1 = "意图识别是所有后续步骤的基础"
            evidence1 = {"fields": ["task.payload.content"]}
            
            action_type1 = "call_intent"
            action1 = {"task": task}
            
            # 发送请求到 Intent Agent
            request_msg = await self._message_bus.send_request(
                from_agent="workflow",
                to_agent="intent",
                content={"task": task},
            )
            
            # 执行 Intent Agent
            intent_result = await self._intent_agent.recognize(task=task)
            
            # 发送响应消息
            response_msg = await self._message_bus.send_response(
                from_agent="intent",
                to_agent="workflow",
                content={"output": intent_result.output, "ok": intent_result.ok},
                in_reply_to=request_msg["message_id"],
            )
            
            # Observation
            observation1 = {
                "output": intent_result.output,
                "ok": intent_result.ok,
            }
            
            # 记录 ReAct Step
            step1 = ReActStep(
                step_id="step_1_intent",
                thought=thought1,
                reasoning=reasoning1,
                evidence=evidence1,
                action_type=action_type1,
                action=action1,
                observation=observation1,
            )
            self._react_steps.append(step1)
            
            # 记录到对话历史
            self._conversation_history.append({
                "from_agent": "intent",
                "type": "response",
                "content": {"output": intent_result.output, "ok": intent_result.ok},
                "message_id": response_msg["message_id"],
            })

            # ============================================
            # ReAct Step 2: Orchestrator Agent
            # ============================================
            logger.info("ReAct Step 2: Orchestrator Agent")
            
            # Thought + Reasoning + Evidence (CoT)
            thought2 = "有了意图，我需要制定执行计划"
            reasoning2 = "计划确保任务按合理顺序执行"
            evidence2 = {"previous_output": intent_result.output}
            
            action_type2 = "call_orchestrator"
            action2 = {"task": task, "intent": intent_result.output}
            
            request_msg = await self._message_bus.send_request(
                from_agent="workflow",
                to_agent="orchestrator",
                content={"task": task, "intent": intent_result.output},
            )
            
            orchestrator_result = await self._orchestrator_agent.orchestrate(task=task)
            
            response_msg = await self._message_bus.send_response(
                from_agent="orchestrator",
                to_agent="workflow",
                content={"output": orchestrator_result.output, "ok": orchestrator_result.ok},
                in_reply_to=request_msg["message_id"],
            )
            
            observation2 = {
                "output": orchestrator_result.output,
                "ok": orchestrator_result.ok,
            }
            
            step2 = ReActStep(
                step_id="step_2_orchestrator",
                thought=thought2,
                reasoning=reasoning2,
                evidence=evidence2,
                action_type=action_type2,
                action=action2,
                observation=observation2,
            )
            self._react_steps.append(step2)
            
            self._conversation_history.append({
                "from_agent": "orchestrator",
                "type": "response",
                "content": {"output": orchestrator_result.output, "ok": orchestrator_result.ok},
                "message_id": response_msg["message_id"],
            })

            # ============================================
            # ReAct Step 3: Critic Agent
            # ============================================
            logger.info("ReAct Step 3: Critic Agent")
            
            # Thought + Reasoning + Evidence (CoT)
            thought3 = "计划制定后，需要让 Critic 审查"
            reasoning3 = "评审可以发现潜在风险和问题"
            evidence3 = {"previous_plan": orchestrator_result.output}
            
            action_type3 = "call_critic"
            action3 = {"task": task, "orchestrator": orchestrator_result.output}
            
            request_msg = await self._message_bus.send_request(
                from_agent="workflow",
                to_agent="critic",
                content={"task": task, "orchestrator": orchestrator_result.output},
            )
            
            critic_result = await self._critic_agent.review(
                task=task,
                orchestrator=orchestrator_result.output,
            )
            
            response_msg = await self._message_bus.send_response(
                from_agent="critic",
                to_agent="workflow",
                content={"output": critic_result.output, "ok": critic_result.ok},
                in_reply_to=request_msg["message_id"],
            )
            
            observation3 = {
                "output": critic_result.output,
                "ok": critic_result.ok,
            }
            
            step3 = ReActStep(
                step_id="step_3_critic",
                thought=thought3,
                reasoning=reasoning3,
                evidence=evidence3,
                action_type=action_type3,
                action=action3,
                observation=observation3,
            )
            self._react_steps.append(step3)
            
            self._conversation_history.append({
                "from_agent": "critic",
                "type": "response",
                "content": {"output": critic_result.output, "ok": critic_result.ok},
                "message_id": response_msg["message_id"],
            })

            # ============================================
            # ReAct Step 4: Parallel Delegation - Engineer and Analyst
            # ============================================
            logger.info("ReAct Step 4: Parallel Delegation")
            
            # Thought + Reasoning + Evidence (CoT)
            thought4 = "计划通过审查，需要 Engineer 和 Analyst 从不同角度分析"
            reasoning4 = "双视角分析可以得到全面的结果"
            evidence4 = {"critique": critic_result.output}
            
            action_type4 = "call_both_parallel"
            action4 = {"task": task}
            
            # 发送请求给 Engineer
            engineer_request_msg = await self._message_bus.send_request(
                from_agent="workflow",
                to_agent="system_engineer",
                content={"task": task},
            )
            # 发送请求给 Analyst
            analyst_request_msg = await self._message_bus.send_request(
                from_agent="workflow",
                to_agent="risk_analyst",
                content={"task": task},
            )
            
            # 并行执行
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
            
            # 发送响应消息
            engineer_response_msg = await self._message_bus.send_response(
                from_agent="system_engineer",
                to_agent="workflow",
                content={"output": engineer_result.output, "ok": engineer_result.ok},
                in_reply_to=engineer_request_msg["message_id"],
            )
            analyst_response_msg = await self._message_bus.send_response(
                from_agent="risk_analyst",
                to_agent="workflow",
                content={"output": analyst_result.output, "ok": analyst_result.ok},
                in_reply_to=analyst_request_msg["message_id"],
            )
            
            observation4 = {
                "engineer": {"output": engineer_result.output, "ok": engineer_result.ok},
                "analyst": {"output": analyst_result.output, "ok": analyst_result.ok},
            }
            
            step4 = ReActStep(
                step_id="step_4_parallel",
                thought=thought4,
                reasoning=reasoning4,
                evidence=evidence4,
                action_type=action_type4,
                action=action4,
                observation=observation4,
            )
            self._react_steps.append(step4)
            
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

            # ============================================
            # 构建结果
            # ============================================
            latency_ms = (time.time() - start_time) * 1000
            observe_ms("orchestrator_latency_ms", latency_ms)
            inc_counter("orchestrator_runs_success")

            # 打印 ReAct Trace（用于调试）
            from riskmonitor_multiagent.orchestration.react_loop import ReActResult
            react_result = ReActResult(
                run_id=run_id,
                success=True,
                steps=self._react_steps,
                total_latency_ms=latency_ms,
            )
            logger.info(f"ReAct Trace:\n{format_react_trace(react_result)}")

            # 获取消息总线的历史
            message_history = self._message_bus.get_message_history()

            result = {
                "status": "completed",
                "run_id": run_id,
                "task_id": request_id,
                "conversation_history": self._conversation_history,
                "message_history": message_history,
                "latency_ms": latency_ms,
                "intent": intent_result.output,
                "orchestrator": orchestrator_result.output,
                "critic": critic_result.output,
                "engineer": engineer_result.output,
                "analyst": analyst_result.output,
            }

            # 发送广播消息：任务完成
            await self._message_bus.broadcast(
                from_agent="workflow",
                content={"status": "completed", "task_id": request_id},
            )

            logger.info(f"Multi-agent collaboration completed for task: {request_id}")
            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            observe_ms("orchestrator_latency_ms", latency_ms)
            inc_counter("orchestrator_runs_error")
            logger.exception(f"Orchestration failed for task {request_id}")
            
            # 发送广播消息：任务失败
            await self._message_bus.broadcast(
                from_agent="workflow",
                content={"status": "error", "task_id": request_id, "error": str(e)},
            )
            
            message_history = self._message_bus.get_message_history()
            
            return {
                "status": "error",
                "run_id": run_id,
                "task_id": request_id,
                "conversation_history": self._conversation_history,
                "message_history": message_history,
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
