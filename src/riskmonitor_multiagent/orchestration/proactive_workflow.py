"""
主动多 Agent 协作工作流.

使用具备 BDI + ReAct + 后台监控的主动 Agent.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from riskmonitor_multiagent.proactive_agents import (
    ProactiveIntentAgent,
    ProactiveOrchestratorAgent,
    ProactiveCriticAgent,
    ProactiveSystemEngineerAgent,
    ProactiveRiskAnalystAgent,
)
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms
from riskmonitor_multiagent.utils.ids import new_run_id

logger = logging.getLogger(__name__)


class ProactiveMultiAgentWorkflow:
    """
    主动多 Agent 协作工作流.
    
    核心特点：
    1. 每个 Agent 都具备 BDI 模型
    2. 每个 Agent 都使用 ReAct 循环
    3. 每个 Agent 都有后台监控线程
    4. 动态协作，非固定流程
    """
    
    def __init__(self) -> None:
        self._intent_agent = ProactiveIntentAgent()
        self._orchestrator_agent = ProactiveOrchestratorAgent()
        self._critic_agent = ProactiveCriticAgent()
        self._engineer_agent = ProactiveSystemEngineerAgent()
        self._analyst_agent = ProactiveRiskAnalystAgent()
        
        self._agents_started = False
    
    async def start_agents(self) -> None:
        """启动所有 Agent 的后台监控."""
        if self._agents_started:
            return
        
        await asyncio.gather(
            self._intent_agent.start_background_monitor(),
            self._orchestrator_agent.start_background_monitor(),
            self._critic_agent.start_background_monitor(),
            self._engineer_agent.start_background_monitor(),
            self._analyst_agent.start_background_monitor(),
        )
        
        self._agents_started = True
        logger.info("All proactive agents started with background monitoring")
    
    async def stop_agents(self) -> None:
        """停止所有 Agent 的后台监控."""
        if not self._agents_started:
            return
        
        await asyncio.gather(
            self._intent_agent.stop_background_monitor(),
            self._orchestrator_agent.stop_background_monitor(),
            self._critic_agent.stop_background_monitor(),
            self._engineer_agent.stop_background_monitor(),
            self._analyst_agent.stop_background_monitor(),
        )
        
        self._agents_started = False
        logger.info("All proactive agents stopped")
    
    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """
        运行主动多 Agent 协作.
        
        流程：
        1. Intent Agent 识别意图（使用 ReAct）
        2. Orchestrator Agent 制定计划（使用 ReAct）
        3. Critic Agent 评审计划（使用 ReAct）
        4. Engineer 和 Analyst 并行执行（使用 ReAct）
        5. 汇总结果
        
        Args:
            task: 任务定义
            
        Returns:
            协作结果
        """
        start_time = time.time()
        run_id = new_run_id("proactive_workflow")
        
        logger.info(f"[ProactiveWorkflow] Starting for task: {task.get('task_id') or run_id}")
        
        try:
            await self.start_agents()
            
            intent_result = await self._intent_agent.recognize(task=task)
            logger.info(f"[ProactiveWorkflow] Intent recognized: {intent_result.output.get('primary_intent_type')}")
            
            orchestrator_result = await self._orchestrator_agent.orchestrate(
                task=task,
                context={"intent": intent_result.output},
            )
            logger.info(f"[ProactiveWorkflow] Plan created with {len(orchestrator_result.output.get('plan_steps', []))} steps")
            
            critic_result = await self._critic_agent.review(
                task=task,
                orchestrator=orchestrator_result.output,
            )
            logger.info(f"[ProactiveWorkflow] Review completed: ok={critic_result.output.get('ok')}")
            
            engineer_task = self._engineer_agent.analyze_task(task=task)
            analyst_task = self._analyst_agent.analyze_task(task=task)
            
            engineer_result, analyst_result = await asyncio.gather(
                engineer_task,
                analyst_task,
            )
            logger.info(f"[ProactiveWorkflow] Specialist analysis completed")
            
            result = self._build_result(
                run_id=run_id,
                task=task,
                intent_result=intent_result,
                orchestrator_result=orchestrator_result,
                critic_result=critic_result,
                engineer_result=engineer_result,
                analyst_result=analyst_result,
                start_time=start_time,
            )
            
            return result
            
        except Exception as e:
            logger.exception(f"[ProactiveWorkflow] Failed: {e}")
            return {
                "status": "failed",
                "run_id": run_id,
                "task_id": task.get("task_id"),
                "errors": [str(e)],
            }
    
    def _build_result(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        intent_result: Any,
        orchestrator_result: Any,
        critic_result: Any,
        engineer_result: Any,
        analyst_result: Any,
        start_time: float,
    ) -> dict[str, Any]:
        """构建结果."""
        latency_ms = (time.time() - start_time) * 1000
        
        all_react_steps = []
        all_react_steps.extend(intent_result.react_steps)
        all_react_steps.extend(orchestrator_result.react_steps)
        all_react_steps.extend(critic_result.react_steps)
        all_react_steps.extend(engineer_result.react_steps)
        all_react_steps.extend(analyst_result.react_steps)
        
        return {
            "status": "completed",
            "run_id": run_id,
            "task_id": task.get("task_id"),
            "task": task,
            "intent": intent_result.output,
            "orchestrator_plan": orchestrator_result.output,
            "critic_plan": critic_result.output,
            "engineer": engineer_result.output,
            "analyst": analyst_result.output,
            "react_steps": [
                {
                    "step_id": s.step_id,
                    "thought": s.thought,
                    "reasoning": s.reasoning,
                    "evidence": s.evidence,
                    "action_type": s.action_type,
                    "observation": s.observation,
                }
                for s in all_react_steps
            ],
            "bdi_states": {
                "intent": intent_result.bdi_state,
                "orchestrator": orchestrator_result.bdi_state,
                "critic": critic_result.bdi_state,
                "engineer": engineer_result.bdi_state,
                "analyst": analyst_result.bdi_state,
            },
            "latency_ms": latency_ms,
            "errors": [],
        }


_proactive_workflow: Optional[ProactiveMultiAgentWorkflow] = None


def get_proactive_workflow() -> ProactiveMultiAgentWorkflow:
    """获取主动工作流单例."""
    global _proactive_workflow
    if _proactive_workflow is None:
        _proactive_workflow = ProactiveMultiAgentWorkflow()
    return _proactive_workflow


def reset_proactive_workflow() -> None:
    """重置主动工作流."""
    global _proactive_workflow
    _proactive_workflow = None


__all__ = [
    "ProactiveMultiAgentWorkflow",
    "get_proactive_workflow",
    "reset_proactive_workflow",
]
