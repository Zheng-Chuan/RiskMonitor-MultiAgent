"""
ReAct + CoT 与现有系统的适配器.

将 ReAct 循环集成到现有的 Orchestrator 工作流中.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from riskmonitor_multiagent.agents.roles import (
    IntentAgent,
    OrchestratorAgent,
    CriticAgent,
    SystemEngineerAgent,
    RiskAnalystAgent,
)
from riskmonitor_multiagent.orchestration.react_loop import (
    ReActStep,
    ReActResult,
    ReActLoop,
    CoTEnhancedReActLoop,
    format_react_trace,
)
from riskmonitor_multiagent.utils import truncate_context

logger = logging.getLogger(__name__)


class RiskMonitorReActAdapter:
    """
    RiskMonitor 系统的 ReAct 适配器.
    
    将 ReAct 循环与现有的 Agent 和工具集成.
    """
    
    def __init__(self) -> None:
        """初始化适配器."""
        self.intent_agent = IntentAgent()
        self.orchestrator_agent = OrchestratorAgent()
        self.critic_agent = CriticAgent()
        self.system_engineer_agent = SystemEngineerAgent()
        self.risk_analyst_agent = RiskAnalystAgent()
    
    def _thought_generator(
        self,
        task: dict[str, Any],
        history: list[ReActStep],
    ) -> str:
        """
        生成思考.
        
        Args:
            task: 任务
            history: 历史步骤
            
        Returns:
            思考内容
        """
        if not history:
            return "我需要先理解这个任务的意图，然后制定执行计划。"
        
        last_step = history[-1]
        if last_step.observation and "error" in last_step.observation:
            return f"上一步执行失败了：{last_step.observation['error']}。我需要重新考虑下一步。"
        
        return "基于之前的结果，我需要决定下一步做什么。"
    
    def _reasoning_generator(
        self,
        task: dict[str, Any],
        history: list[ReActStep],
        thought: str,
    ) -> str:
        """
        生成推理理由 (CoT).
        
        Args:
            task: 任务
            history: 历史步骤
            thought: 当前思考
            
        Returns:
            推理理由
        """
        step_count = len(history)
        
        if step_count == 0:
            return "第一步应该先理解任务意图，因为意图识别是所有后续步骤的基础。"
        elif step_count == 1:
            return "有了意图之后，我需要让 Orchestrator 制定执行计划，这样可以确保任务按合理的顺序执行。"
        elif step_count == 2:
            return "计划制定后，需要让 Critic 审查，这样可以发现潜在的风险和问题。"
        elif step_count == 3:
            return "计划通过审查后，需要 System Engineer 和 Risk Analyst 从不同角度分析，这样可以得到全面的结果。"
        
        return "现在已经收集了足够的信息，可以总结最终结果了。"
    
    def _evidence_generator(
        self,
        task: dict[str, Any],
        history: list[ReActStep],
        thought: str,
    ) -> dict[str, Any]:
        """
        生成证据 (CoT).
        
        Args:
            task: 任务
            history: 历史步骤
            thought: 当前思考
            
        Returns:
            证据字典
        """
        evidence = {
            "fields": ["task.payload.content"],
        }
        
        if history:
            last_step = history[-1]
            evidence["last_step_id"] = last_step.step_id
            if last_step.observation:
                evidence["has_observation"] = True
        
        return evidence
    
    def _action_decider(
        self,
        task: dict[str, Any],
        history: list[ReActStep],
        thought: str,
    ) -> tuple[str, dict[str, Any]]:
        """
        决定下一步行动.
        
        Args:
            task: 任务
            history: 历史步骤
            thought: 思考
            
        Returns:
            (action_type, action)
        """
        step_count = len(history)
        
        if step_count == 0:
            return "call_intent_agent", {"task": task}
        elif step_count == 1:
            return "call_orchestrator_agent", {"task": task}
        elif step_count == 2:
            last_step = history[-1]
            return "call_critic_agent", {
                "task": task,
                "orchestrator": last_step.observation,
            }
        elif step_count == 3:
            return "call_engineer_and_analyst", {"task": task}
        else:
            return "finalize", {"task": task}
    
    def _action_executor(
        self,
        action_type: str,
        action: dict[str, Any],
    ) -> dict[str, Any]:
        """
        执行行动.
        
        Args:
            action_type: 行动类型
            action: 行动参数
            
        Returns:
            观察结果
        """
        import asyncio
        
        if action_type == "call_intent_agent":
            task = action.get("task", {})
            result = asyncio.run(self.intent_agent.recognize(task=task))
            return {
                "ok": result.ok,
                "output": result.output,
                "usage": result.usage,
            }
        
        elif action_type == "call_orchestrator_agent":
            task = action.get("task", {})
            result = asyncio.run(self.orchestrator_agent.orchestrate(task=task))
            return {
                "ok": result.ok,
                "output": result.output,
                "usage": result.usage,
            }
        
        elif action_type == "call_critic_agent":
            task = action.get("task", {})
            orchestrator = action.get("orchestrator", {})
            result = asyncio.run(self.critic_agent.review(
                task=task,
                orchestrator=orchestrator.get("output", {}),
            ))
            return {
                "ok": result.ok,
                "output": result.output,
                "usage": result.usage,
            }
        
        elif action_type == "call_engineer_and_analyst":
            task = action.get("task", {})
            engineer_result = asyncio.run(self.system_engineer_agent.analyze_task(task=task))
            analyst_result = asyncio.run(self.risk_analyst_agent.analyze_task(task=task))
            return {
                "engineer": {
                    "ok": engineer_result.ok,
                    "output": engineer_result.output,
                },
                "analyst": {
                    "ok": analyst_result.ok,
                    "output": analyst_result.output,
                },
            }
        
        elif action_type == "finalize":
            return {"status": "completed", "message": "任务完成"}
        
        else:
            return {"error": f"Unknown action type: {action_type}"}
    
    def _termination_checker(
        self,
        task: dict[str, Any],
        history: list[ReActStep],
    ) -> bool:
        """
        检查是否应该终止循环.
        
        Args:
            task: 任务
            history: 历史步骤
            
        Returns:
            是否终止
        """
        if len(history) >= 5:
            return True
        
        if history and history[-1].action_type == "finalize":
            return True
        
        return False
    
    def _final_answer_generator(
        self,
        task: dict[str, Any],
        history: list[ReActStep],
    ) -> dict[str, Any]:
        """
        生成最终答案.
        
        Args:
            task: 任务
            history: 历史步骤
            
        Returns:
            最终答案
        """
        result = {
            "task": task,
            "steps": [
                {
                    "step_id": step.step_id,
                    "thought": step.thought,
                    "reasoning": step.reasoning,
                    "evidence": step.evidence,
                    "action_type": step.action_type,
                    "observation": step.observation,
                }
                for step in history
            ],
        }
        
        for step in history:
            if step.action_type == "call_intent_agent" and step.observation:
                result["intent"] = step.observation.get("output")
            elif step.action_type == "call_orchestrator_agent" and step.observation:
                result["orchestrator_plan"] = step.observation.get("output")
            elif step.action_type == "call_critic_agent" and step.observation:
                result["critic_review"] = step.observation.get("output")
            elif step.action_type == "call_engineer_and_analyst" and step.observation:
                result["engineer"] = step.observation.get("engineer", {}).get("output")
                result["analyst"] = step.observation.get("analyst", {}).get("output")
        
        return result
    
    async def run_react_loop(
        self,
        *,
        task: dict[str, Any],
        max_steps: int = 10,
    ) -> ReActResult:
        """
        运行 ReAct 循环.
        
        Args:
            task: 任务
            max_steps: 最大步数
            
        Returns:
            ReActResult
        """
        loop = CoTEnhancedReActLoop(
            max_steps=max_steps,
            thought_generator=self._thought_generator,
            reasoning_generator=self._reasoning_generator,
            evidence_generator=self._evidence_generator,
            action_decider=self._action_decider,
            action_executor=self._action_executor,
            termination_checker=self._termination_checker,
            final_answer_generator=self._final_answer_generator,
        )
        
        result = await loop.run(task=task)
        
        logger.info(f"ReAct loop completed: {result.run_id}, success={result.success}")
        
        return result


# 全局适配器实例
_adapter: Optional[RiskMonitorReActAdapter] = None


def get_react_adapter() -> RiskMonitorReActAdapter:
    """获取全局 ReAct 适配器实例."""
    global _adapter
    if _adapter is None:
        _adapter = RiskMonitorReActAdapter()
    return _adapter


def reset_react_adapter() -> None:
    """重置适配器（用于测试）."""
    global _adapter
    _adapter = None


__all__ = [
    "RiskMonitorReActAdapter",
    "get_react_adapter",
    "reset_react_adapter",
]
