"""
ReAct + CoT 增强的 Agent.

将 ReAct 循环和 CoT 思维链集成到实际的 Agent 中.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from riskmonitor_multiagent.agents.bdi import BDIAgentMixin
from riskmonitor_multiagent.orchestration.react_loop import (
    ReActStep,
    ReActResult,
    ReActLoop,
    CoTEnhancedReActLoop,
    format_react_trace,
)

logger = logging.getLogger(__name__)


class ReActAgentMixin(BDIAgentMixin):
    """
    ReAct Agent 混入类.
    
    为 Agent 添加 ReAct 循环和 CoT 思维链能力.
    """

    def __init__(self, agent_name: str = "agent") -> None:
        """
        初始化 ReAct Agent.
        
        Args:
            agent_name: Agent 名称
        """
        super().__init__()
        self._agent_name = agent_name
        self._react_loop: Optional[CoTEnhancedReActLoop] = None
        self._last_react_result: Optional[ReActResult] = None

    def _setup_react_loop(
        self,
        *,
        thought_generator: Any,
        reasoning_generator: Any,
        evidence_generator: Any,
        action_decider: Any,
        action_executor: Any,
        termination_checker: Any,
        final_answer_generator: Optional[Any] = None,
        max_steps: int = 10,
    ) -> None:
        """
        设置 ReAct 循环.
        
        Args:
            thought_generator: 思考生成器
            reasoning_generator: 推理生成器
            evidence_generator: 证据生成器
            action_decider: 行动决定器
            action_executor: 行动执行器
            termination_checker: 终止检查器
            final_answer_generator: 最终答案生成器（可选）
            max_steps: 最大步数
        """
        self._react_loop = CoTEnhancedReActLoop(
            max_steps=max_steps,
            thought_generator=thought_generator,
            reasoning_generator=reasoning_generator,
            evidence_generator=evidence_generator,
            action_decider=action_decider,
            action_executor=action_executor,
            termination_checker=termination_checker,
            final_answer_generator=final_answer_generator,
        )

    async def run_react(
        self,
        *,
        task: dict[str, Any],
    ) -> ReActResult:
        """
        运行 ReAct 循环.
        
        Args:
            task: 任务
            
        Returns:
            ReActResult
        """
        if self._react_loop is None:
            raise ValueError("ReAct loop not set up. Call _setup_react_loop() first.")
        
        logger.info(f"[{self._agent_name}] Starting ReAct loop")
        
        result = await self._react_loop.run(task=task)
        self._last_react_result = result
        
        if result.success:
            logger.info(f"[{self._agent_name}] ReAct loop completed successfully in {len(result.steps)} steps")
        else:
            logger.error(f"[{self._agent_name}] ReAct loop failed: {result.errors}")
        
        return result

    def get_last_react_trace(self) -> Optional[str]:
        """
        获取最后一次 ReAct 循环的追踪信息.
        
        Returns:
            格式化的追踪字符串，或 None
        """
        if self._last_react_result is None:
            return None
        return format_react_trace(self._last_react_result)

    def add_task_belief(self, task: dict[str, Any]) -> None:
        """
        添加关于任务的信念.
        
        Args:
            task: 任务
        """
        self.add_belief(
            content=task,
            source=f"{self._agent_name}_task_input",
            confidence=1.0,
        )

    def add_observation_belief(
        self,
        observation: Any,
        source: str = "observation",
    ) -> None:
        """
        添加观察到的信念.
        
        Args:
            observation: 观察结果
            source: 来源
        """
        self.add_belief(
            content=observation,
            source=source,
            confidence=0.9,
        )

    def add_goal_desire(
        self,
        description: str,
        priority: int = 100,
    ) -> None:
        """
        添加目标愿望.
        
        Args:
            description: 目标描述
            priority: 优先级
        """
        self.add_desire(
            description=description,
            priority=priority,
        )

    def add_action_intention(
        self,
        description: str,
        tool_name: Optional[str] = None,
        tool_params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """
        添加行动意图.
        
        Args:
            description: 描述
            tool_name: 工具名称
            tool_params: 工具参数
            
        Returns:
            Intention 对象
        """
        return self.add_intention(
            description=description,
            tool_name=tool_name,
            tool_params=tool_params,
        )

    def get_react_state_summary(self) -> dict[str, Any]:
        """
        获取 ReAct 状态摘要.
        
        Returns:
            状态字典
        """
        summary = {
            "agent_name": self._agent_name,
            "bdi": self.get_bdi_state(),
        }
        
        if self._last_react_result:
            summary["last_react"] = {
                "run_id": self._last_react_result.run_id,
                "success": self._last_react_result.success,
                "steps": len(self._last_react_result.steps),
                "latency_ms": self._last_react_result.total_latency_ms,
            }
        
        return summary


__all__ = [
    "ReActAgentMixin",
]
