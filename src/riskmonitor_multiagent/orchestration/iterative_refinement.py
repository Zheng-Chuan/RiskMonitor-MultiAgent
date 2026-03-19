"""
Iterative Refinement（迭代优化）模式和 Review-and-Revise（评审-修订）模式.

实现多轮对话优化、Critic 评审反馈和冲突解决机制.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class RefinementStep:
    """迭代优化的单步."""
    
    step_id: str
    step_type: str
    agent: str
    input_content: Any
    output_content: Any
    feedback: Optional[str] = None
    revision_count: int = 0
    timestamp_ms: int = field(default_factory=lambda: __import__('time').time_ns() // 1000000)


@dataclass
class Conflict:
    """冲突记录."""
    
    conflict_id: str
    agent_a: str
    agent_b: str
    description: str
    resolution: Optional[str] = None
    resolved: bool = False
    timestamp_ms: int = field(default_factory=lambda: __import__('time').time_ns() // 1000000)


class IterativeRefinementEngine:
    """
    迭代优化引擎.
    
    实现：
    1. Iterative Refinement - 多轮对话优化
    2. Review-and-Revise - Critic 评审反馈
    3. Conflict Resolution - 冲突解决机制
    """
    
    def __init__(
        self,
        max_iterations: int = 3,
        max_conflicts: int = 5,
    ) -> None:
        """
        初始化迭代优化引擎.
        
        Args:
            max_iterations: 最大迭代次数
            max_conflicts: 最大冲突记录数
        """
        self.max_iterations = max_iterations
        self.max_conflicts = max_conflicts
        self._steps: list[RefinementStep] = []
        self._conflicts: list[Conflict] = []
        self._current_iteration = 0

    async def run_iterative_refinement(
        self,
        *,
        initial_input: Any,
        agent_fn: Callable[[Any], Any],
        critic_fn: Optional[Callable[[Any], tuple[bool, str]]] = None,
        max_iterations: Optional[int] = None,
    ) -> tuple[Any, list[RefinementStep]]:
        """
        运行迭代优化.
        
        Args:
            initial_input: 初始输入
            agent_fn: Agent 执行函数，接收输入返回输出
            critic_fn: Critic 评审函数，接收输出返回 (ok, feedback)
            max_iterations: 最大迭代次数（覆盖默认值）
            
        Returns:
            (final_output, steps)
        """
        max_iters = max_iterations or self.max_iterations
        current_input = initial_input
        steps: list[RefinementStep] = []
        
        logger.info(f"Starting iterative refinement, max iterations: {max_iters}")
        
        for iteration in range(max_iters):
            self._current_iteration = iteration + 1
            logger.info(f"Iteration {self._current_iteration}/{max_iters}")
            
            step_id = f"refine_{iteration + 1}"
            
            step = RefinementStep(
                step_id=step_id,
                step_type="refine",
                agent="refinement_agent",
                input_content=current_input,
                output_content=None,
                revision_count=iteration,
            )
            
            output = agent_fn(current_input)
            step.output_content = output
            steps.append(step)
            self._steps.append(step)
            
            if critic_fn is None:
                logger.info("No critic function, finishing early")
                break
            
            ok, feedback = critic_fn(output)
            step.feedback = feedback
            
            if ok:
                logger.info("Critic approved, finishing")
                break
            
            logger.info(f"Critic feedback: {feedback[:100]}...")
            current_input = {
                "previous_output": output,
                "feedback": feedback,
            }
        
        final_output = steps[-1].output_content if steps else initial_input
        return final_output, steps

    async def run_review_and_revise(
        self,
        *,
        initial_output: Any,
        reviewer_fn: Callable[[Any], tuple[bool, str, list[str]]],
        reviser_fn: Callable[[Any, list[str]], Any],
        max_revisions: int = 3,
    ) -> tuple[Any, list[RefinementStep]]:
        """
        运行 Review-and-Revise（评审-修订）模式.
        
        Args:
            initial_output: 初始输出
            reviewer_fn: 评审函数，返回 (ok, summary, issues)
            reviser_fn: 修订函数，接收输出和问题列表返回修订后的输出
            max_revisions: 最大修订次数
            
        Returns:
            (final_output, steps)
        """
        current_output = initial_output
        steps: list[RefinementStep] = []
        
        logger.info(f"Starting review-and-revise, max revisions: {max_revisions}")
        
        for revision in range(max_revisions):
            self._current_iteration = revision + 1
            logger.info(f"Revision {self._current_iteration}/{max_revisions}")
            
            step_id = f"review_{revision + 1}"
            
            ok, summary, issues = reviewer_fn(current_output)
            
            step = RefinementStep(
                step_id=step_id,
                step_type="review",
                agent="critic",
                input_content=current_output,
                output_content=current_output,
                feedback=summary,
                revision_count=revision,
            )
            steps.append(step)
            self._steps.append(step)
            
            if ok or not issues:
                logger.info("No more issues to fix, finishing")
                break
            
            logger.info(f"Found {len(issues)} issues, revising...")
            current_output = reviser_fn(current_output, issues)
        
        final_output = current_output
        return final_output, steps

    def record_conflict(
        self,
        agent_a: str,
        agent_b: str,
        description: str,
    ) -> Conflict:
        """
        记录一个冲突.
        
        Args:
            agent_a: Agent A
            agent_b: Agent B
            description: 冲突描述
            
        Returns:
            Conflict 对象
        """
        import uuid
        conflict = Conflict(
            conflict_id=str(uuid.uuid4())[:8],
            agent_a=agent_a,
            agent_b=agent_b,
            description=description,
        )
        
        self._conflicts.append(conflict)
        
        if len(self._conflicts) > self.max_conflicts:
            self._conflicts.pop(0)
        
        logger.warning(f"Conflict recorded: {agent_a} vs {agent_b} - {description}")
        return conflict

    async def resolve_conflict(
        self,
        conflict_id: str,
        resolution: str,
    ) -> bool:
        """
        解决一个冲突.
        
        Args:
            conflict_id: 冲突 ID
            resolution: 解决方案
            
        Returns:
            是否成功解决
        """
        for conflict in self._conflicts:
            if conflict.conflict_id == conflict_id:
                conflict.resolution = resolution
                conflict.resolved = True
                logger.info(f"Conflict resolved: {conflict_id} - {resolution}")
                return True
        
        logger.warning(f"Conflict not found: {conflict_id}")
        return False

    def get_unresolved_conflicts(self) -> list[Conflict]:
        """
        获取未解决的冲突.
        
        Returns:
            未解决的冲突列表
        """
        return [c for c in self._conflicts if not c.resolved]

    def get_refinement_trace(self) -> str:
        """
        获取迭代优化的追踪信息.
        
        Returns:
            格式化的追踪字符串
        """
        lines = [
            f"Iterative Refinement Trace",
            f"Total steps: {len(self._steps)}",
            f"Total conflicts: {len(self._conflicts)}",
            f"Unresolved conflicts: {len(self.get_unresolved_conflicts())}",
            "=" * 60,
        ]
        
        for step in self._steps:
            lines.append(f"\nStep {step.step_id}:")
            lines.append(f"  Type: {step.step_type}")
            lines.append(f"  Agent: {step.agent}")
            if step.feedback:
                lines.append(f"  Feedback: {step.feedback}")
            lines.append(f"  Revisions: {step.revision_count}")
        
        if self._conflicts:
            lines.append("\n" + "=" * 60)
            lines.append("Conflicts:")
            for conflict in self._conflicts:
                status = "RESOLVED" if conflict.resolved else "UNRESOLVED"
                lines.append(f"  [{status}] {conflict.agent_a} vs {conflict.agent_b}")
                lines.append(f"    {conflict.description}")
                if conflict.resolution:
                    lines.append(f"    Resolution: {conflict.resolution}")
        
        return "\n".join(lines)

    def get_state_summary(self) -> dict[str, Any]:
        """
        获取状态摘要.
        
        Returns:
            状态字典
        """
        return {
            "current_iteration": self._current_iteration,
            "total_steps": len(self._steps),
            "total_conflicts": len(self._conflicts),
            "unresolved_conflicts": len(self.get_unresolved_conflicts()),
            "steps": [
                {
                    "step_id": s.step_id,
                    "step_type": s.step_type,
                    "agent": s.agent,
                    "revision_count": s.revision_count,
                }
                for s in self._steps
            ],
        }


_refinement_engine: Optional[IterativeRefinementEngine] = None


def get_refinement_engine() -> IterativeRefinementEngine:
    """获取全局迭代优化引擎实例."""
    global _refinement_engine
    if _refinement_engine is None:
        _refinement_engine = IterativeRefinementEngine()
    return _refinement_engine


def reset_refinement_engine() -> None:
    """重置迭代优化引擎（用于测试）."""
    global _refinement_engine
    _refinement_engine = None


__all__ = [
    "RefinementStep",
    "Conflict",
    "IterativeRefinementEngine",
    "get_refinement_engine",
    "reset_refinement_engine",
]
