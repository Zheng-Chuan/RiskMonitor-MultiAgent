"""
ReAct (Reasoning + Acting) 循环实现.

实现 Thought -> Action -> Observation 动态循环.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from riskmonitor_multiagent.utils.ids import new_run_id

logger = logging.getLogger(__name__)


@dataclass
class ReActStep:
    """ReAct 循环的单个步骤."""
    
    step_id: str
    thought: str
    action_type: str
    action: dict[str, Any]
    observation: Optional[dict[str, Any]] = None
    reasoning: Optional[str] = None
    evidence: Optional[dict[str, Any]] = None
    timestamp_ms: int = field(default_factory=lambda: __import__('time').time_ns() // 1000000)


@dataclass
class ReActResult:
    """ReAct 循环的最终结果."""
    
    run_id: str
    success: bool
    final_answer: Optional[Any] = None
    steps: list[ReActStep] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_latency_ms: float = 0.0


class ReActLoop:
    """
    ReAct 循环引擎.
    
    实现 Thought -> Action -> Observation 动态循环.
    """
    
    def __init__(
        self,
        *,
        max_steps: int = 10,
        thought_generator: Callable[[dict[str, Any], list[ReActStep]], str],
        action_decider: Callable[[dict[str, Any], list[ReActStep], str], tuple[str, dict[str, Any]]],
        action_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
        termination_checker: Callable[[dict[str, Any], list[ReActStep]], bool],
        final_answer_generator: Optional[Callable[[dict[str, Any], list[ReActStep]], Any]] = None,
    ) -> None:
        """
        初始化 ReAct 循环引擎.
        
        Args:
            max_steps: 最大步数
            thought_generator: 生成思考的函数 (task, history) -> thought
            action_decider: 决定行动的函数 (task, history, thought) -> (action_type, action)
            action_executor: 执行行动的函数 (action_type, action) -> observation
            termination_checker: 检查是否终止的函数 (task, history) -> bool
            final_answer_generator: 生成最终答案的函数 (可选)
        """
        self.max_steps = max_steps
        self.thought_generator = thought_generator
        self.action_decider = action_decider
        self.action_executor = action_executor
        self.termination_checker = termination_checker
        self.final_answer_generator = final_answer_generator
    
    async def run(
        self,
        *,
        task: dict[str, Any],
    ) -> ReActResult:
        """
        运行 ReAct 循环.
        
        Args:
            task: 任务定义
            
        Returns:
            ReActResult 包含循环结果
        """
        import time
        start_time = time.time()
        run_id = new_run_id("react")
        
        logger.info(f"Starting ReAct loop: {run_id}")
        
        result = ReActResult(run_id=run_id, success=False)
        steps: list[ReActStep] = []
        
        try:
            for step_idx in range(self.max_steps):
                logger.debug(f"ReAct step {step_idx + 1}/{self.max_steps}")
                
                # 1. Thought: 思考下一步做什么
                thought = self.thought_generator(task, steps)
                logger.debug(f"Thought: {thought[:100]}...")
                
                # 2. Action: 决定并执行行动
                action_type, action = self.action_decider(task, steps, thought)
                logger.debug(f"Action: {action_type} - {action}")
                
                # 创建步骤记录
                step = ReActStep(
                    step_id=f"step_{step_idx + 1}",
                    thought=thought,
                    action_type=action_type,
                    action=action,
                )
                steps.append(step)
                
                # 3. Observation: 执行行动并观察结果
                try:
                    observation = self.action_executor(action_type, action)
                    step.observation = observation
                    logger.debug(f"Observation: {str(observation)[:100]}...")
                except Exception as e:
                    error_msg = f"Action execution failed: {str(e)}"
                    logger.error(error_msg)
                    step.observation = {"error": error_msg}
                    result.errors.append(error_msg)
                
                # 4. 检查是否终止
                if self.termination_checker(task, steps):
                    logger.info(f"ReAct loop terminated at step {step_idx + 1}")
                    break
            
            # 生成最终答案
            result.success = True
            result.steps = steps
            
            if self.final_answer_generator:
                result.final_answer = self.final_answer_generator(task, steps)
            
            logger.info(f"ReAct loop completed: {run_id}, success={result.success}")
            
        except Exception as e:
            error_msg = f"ReAct loop failed: {str(e)}"
            logger.exception(error_msg)
            result.errors.append(error_msg)
            result.success = False
        
        finally:
            result.total_latency_ms = (time.time() - start_time) * 1000
        
        return result


class CoTEnhancedReActLoop(ReActLoop):
    """
    带有 CoT (Chain-of-Thought) 增强的 ReAct 循环.
    
    每个步骤都有明确的 reasoning 和 evidence.
    """
    
    def __init__(
        self,
        *,
        max_steps: int = 10,
        thought_generator: Callable[[dict[str, Any], list[ReActStep]], str],
        reasoning_generator: Callable[[dict[str, Any], list[ReActStep], str], str],
        evidence_generator: Callable[[dict[str, Any], list[ReActStep], str], dict[str, Any]],
        action_decider: Callable[[dict[str, Any], list[ReActStep], str], tuple[str, dict[str, Any]]],
        action_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
        termination_checker: Callable[[dict[str, Any], list[ReActStep]], bool],
        final_answer_generator: Optional[Callable[[dict[str, Any], list[ReActStep]], Any]] = None,
    ) -> None:
        """
        初始化 CoT 增强的 ReAct 循环.
        
        Args:
            reasoning_generator: 生成推理理由的函数
            evidence_generator: 生成证据的函数
            其他参数同 ReActLoop
        """
        super().__init__(
            max_steps=max_steps,
            thought_generator=thought_generator,
            action_decider=action_decider,
            action_executor=action_executor,
            termination_checker=termination_checker,
            final_answer_generator=final_answer_generator,
        )
        self.reasoning_generator = reasoning_generator
        self.evidence_generator = evidence_generator
    
    async def run(
        self,
        *,
        task: dict[str, Any],
    ) -> ReActResult:
        """运行 CoT 增强的 ReAct 循环."""
        import time
        start_time = time.time()
        run_id = new_run_id("react_cot")
        
        logger.info(f"Starting CoT-enhanced ReAct loop: {run_id}")
        
        result = ReActResult(run_id=run_id, success=False)
        steps: list[ReActStep] = []
        
        try:
            for step_idx in range(self.max_steps):
                logger.debug(f"CoT-ReAct step {step_idx + 1}/{self.max_steps}")
                
                # 1. Thought
                thought = self.thought_generator(task, steps)
                
                # 2. Reasoning (CoT)
                reasoning = self.reasoning_generator(task, steps, thought)
                
                # 3. Evidence (CoT)
                evidence = self.evidence_generator(task, steps, thought)
                
                # 4. Action
                action_type, action = self.action_decider(task, steps, thought)
                
                # 创建步骤记录（包含 CoT）
                step = ReActStep(
                    step_id=f"step_{step_idx + 1}",
                    thought=thought,
                    reasoning=reasoning,
                    evidence=evidence,
                    action_type=action_type,
                    action=action,
                )
                steps.append(step)
                
                # 5. Observation
                try:
                    observation = self.action_executor(action_type, action)
                    step.observation = observation
                except Exception as e:
                    error_msg = f"Action execution failed: {str(e)}"
                    logger.error(error_msg)
                    step.observation = {"error": error_msg}
                    result.errors.append(error_msg)
                
                # 6. Check termination
                if self.termination_checker(task, steps):
                    logger.info(f"CoT-ReAct loop terminated at step {step_idx + 1}")
                    break
            
            result.success = True
            result.steps = steps
            
            if self.final_answer_generator:
                result.final_answer = self.final_answer_generator(task, steps)
            
        except Exception as e:
            error_msg = f"CoT-ReAct loop failed: {str(e)}"
            logger.exception(error_msg)
            result.errors.append(error_msg)
        
        finally:
            result.total_latency_ms = (time.time() - start_time) * 1000
        
        return result


def format_react_trace(result: ReActResult) -> str:
    """
    格式化 ReAct 循环的追踪信息.
    
    Args:
        result: ReActResult
        
    Returns:
        格式化的字符串
    """
    lines = [
        f"ReAct Trace (run_id: {result.run_id})",
        f"Success: {result.success}",
        f"Total Steps: {len(result.steps)}",
        f"Latency: {result.total_latency_ms:.2f}ms",
        "=" * 60,
    ]
    
    for step in result.steps:
        lines.append(f"\nStep {step.step_id}:")
        lines.append(f"  Thought: {step.thought}")
        if step.reasoning:
            lines.append(f"  Reasoning: {step.reasoning}")
        if step.evidence:
            lines.append(f"  Evidence: {step.evidence}")
        lines.append(f"  Action: {step.action_type} - {step.action}")
        if step.observation:
            lines.append(f"  Observation: {step.observation}")
    
    if result.final_answer:
        lines.append("\n" + "=" * 60)
        lines.append(f"Final Answer: {result.final_answer}")
    
    if result.errors:
        lines.append("\n" + "=" * 60)
        lines.append("Errors:")
        for error in result.errors:
            lines.append(f"  - {error}")
    
    return "\n".join(lines)


__all__ = [
    "ReActStep",
    "ReActResult",
    "ReActLoop",
    "CoTEnhancedReActLoop",
    "format_react_trace",
]
