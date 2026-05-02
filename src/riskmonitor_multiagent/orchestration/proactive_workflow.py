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
    ProactiveAgentResult,
    ProactiveIntentAgent,
    ProactiveOrchestratorAgent,
    ProactiveCriticAgent,
    ProactiveSystemEngineerAgent,
    ProactiveRiskAnalystAgent,
)
from riskmonitor_multiagent.contracts.task_graph import append_replan_subgraph
from riskmonitor_multiagent.orchestration.task_graph_executor import TaskGraphExecutor
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms
from riskmonitor_multiagent.utils.ids import new_run_id

logger = logging.getLogger(__name__)


class ProactiveMultiAgentWorkflow:
    """
    主动多 Agent 协作工作流.
    
    核心特点:
    1. 每个 Agent 都具备 BDI 模型
    2. 每个 Agent 都使用 ReAct 循环
    3. 每个 Agent 都有后台监控线程
    4. 动态协作,非固定流程
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
        
        流程:
        1. Intent Agent 识别意图(使用 ReAct)
        2. Orchestrator Agent 制定计划(使用 ReAct)
        3. Critic Agent 评审计划(使用 ReAct)
        4. Engineer 和 Analyst 并行执行(使用 ReAct)
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
            resume_request = task.get("resume") if isinstance(task.get("resume"), dict) else {}
            is_resume = bool(resume_request)

            replan_details: dict[str, Any] | None = None
            execution_state = resume_request.get("execution_state") if is_resume else None
            resume_from_step_id = (
                resume_request.get("resume_from_step_id")
                or (execution_state.get("failed_step_id") if isinstance(execution_state, dict) else None)
            ) if is_resume else None

            if is_resume:
                orchestrator_result = self._new_placeholder_result(
                    output=resume_request.get("task_graph") if isinstance(resume_request.get("task_graph"), dict) else {},
                    agent_name="orchestrator",
                )
                critic_result = self._new_placeholder_result(
                    output={"ok": True, "resumed": True},
                    agent_name="critic",
                )
                active_task_graph = resume_request.get("task_graph") if isinstance(resume_request.get("task_graph"), dict) else {}
                replan_details = {
                    "trigger": "manual_resume",
                    "reason": f"resume_from_step:{resume_from_step_id or 'unknown'}",
                }
            else:
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

                active_task_graph = orchestrator_result.output
                if self._should_replan(critic_result.output):
                    logger.info("[ProactiveWorkflow] Critic rejected plan. Starting replan")
                    replan_result = await self._orchestrator_agent.orchestrate(
                        task=task,
                        context={
                            "phase": "replan",
                            "intent": intent_result.output,
                            "critic": critic_result.output,
                            "prior_orchestrator_plan": orchestrator_result.output,
                            "prior_task_graph": active_task_graph,
                        },
                    )
                    active_task_graph = append_replan_subgraph(
                        active_task_graph,
                        replan_result.output,
                        reason=self._build_replan_reason(critic_result.output),
                    )
                    replan_details = {
                        "trigger": "critic_rejected",
                        "reason": self._build_replan_reason(critic_result.output),
                        "orchestrator_plan": replan_result.output,
                    }
                    logger.info(
                        "[ProactiveWorkflow] Replan completed with %s nodes",
                        len(active_task_graph.get("nodes", [])) if isinstance(active_task_graph, dict) else 0,
                    )
            
            executor = TaskGraphExecutor(
                delegate_handlers={
                    "system_engineer": self._engineer_agent.analyze_task,
                    "engineer": self._engineer_agent.analyze_task,
                    "risk_analyst": self._analyst_agent.analyze_task,
                    "analyst": self._analyst_agent.analyze_task,
                }
            )
            execution_result = await executor.execute(
                task=task,
                task_graph=active_task_graph,
                execution_state=execution_state,
                resume_from_step_id=resume_from_step_id if isinstance(resume_from_step_id, str) else None,
            )
            logger.info(
                "[ProactiveWorkflow] TaskGraph execution completed with status=%s",
                execution_result.get("status"),
            )

            delegate_results = execution_result.get("delegate_results", {})
            engineer_result = delegate_results.get("system_engineer") or delegate_results.get("engineer") or ProactiveAgentResult(
                ok=True,
                output={},
            )
            analyst_result = delegate_results.get("risk_analyst") or delegate_results.get("analyst") or ProactiveAgentResult(
                ok=True,
                output={},
            )
            
            result = self._build_result(
                run_id=run_id,
                task=task,
                intent_result=intent_result,
                orchestrator_result=orchestrator_result,
                critic_result=critic_result,
                engineer_result=engineer_result,
                analyst_result=analyst_result,
                execution_result=execution_result,
                replan_details=replan_details,
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
        execution_result: dict[str, Any],
        replan_details: dict[str, Any] | None,
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
        
        all_llm_interactions = []
        all_llm_interactions.extend(intent_result.llm_interactions)
        all_llm_interactions.extend(orchestrator_result.llm_interactions)
        all_llm_interactions.extend(critic_result.llm_interactions)
        all_llm_interactions.extend(engineer_result.llm_interactions)
        all_llm_interactions.extend(analyst_result.llm_interactions)
        
        return {
            "status": execution_result.get("status", "completed"),
            "run_id": run_id,
            "task_id": task.get("task_id"),
            "task": task,
            "intent": intent_result.output,
            "task_graph": execution_result.get("task_graph", orchestrator_result.output.get("task_graph", {})),
            "task_graph_execution": execution_result.get("task_graph_execution", {}),
            "orchestrator_plan": orchestrator_result.output,
            "critic_plan": critic_result.output,
            "replan": replan_details or {},
            "receipts": execution_result.get("receipts", []),
            "engineer": engineer_result.output,
            "analyst": analyst_result.output,
            "final_output": execution_result.get("final_output", {}),
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
            "llm_interactions": all_llm_interactions,
            "latency_ms": latency_ms,
            "errors": execution_result.get("task_graph_execution", {}).get("errors", []),
        }

    def _new_placeholder_result(self, *, output: dict[str, Any], agent_name: str) -> ProactiveAgentResult:
        """构造恢复执行时的占位结果."""
        return ProactiveAgentResult(
            ok=True,
            output=output if isinstance(output, dict) else {},
            meta={"agent_name": agent_name, "placeholder": True},
        )

    def _should_replan(self, critic_output: dict[str, Any]) -> bool:
        """判断是否需要重规划."""
        if not isinstance(critic_output, dict):
            return False
        if critic_output.get("ok") is False:
            return True
        return False

    def _build_replan_reason(self, critic_output: dict[str, Any]) -> str:
        """构造重规划原因."""
        if not isinstance(critic_output, dict):
            return "critic rejected previous plan"

        issues = critic_output.get("issues")
        if isinstance(issues, list) and issues:
            first_issue = issues[0]
            if isinstance(first_issue, str) and first_issue.strip():
                return first_issue.strip()

        fixes = critic_output.get("suggested_fixes")
        if isinstance(fixes, list) and fixes:
            first_fix = fixes[0]
            if isinstance(first_fix, str) and first_fix.strip():
                return first_fix.strip()

        return "critic rejected previous plan"


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
