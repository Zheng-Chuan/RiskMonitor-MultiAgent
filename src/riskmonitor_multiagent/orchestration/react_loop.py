from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ReActStep:
    """单个 ReAct 步骤."""

    step_id: str
    thought: str
    action_type: str
    action: dict[str, Any]
    observation: dict[str, Any] | None = None
    reasoning: str | None = None
    evidence: dict[str, Any] | None = None


@dataclass
class ReActResult:
    """ReAct 执行结果."""

    run_id: str
    success: bool
    steps: list[ReActStep] = field(default_factory=list)
    final_answer: dict[str, Any] | None = None
    total_latency_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


class ReActLoop:
    """最小可测的 ReAct 循环实现."""

    def __init__(
        self,
        *,
        max_steps: int = 5,
        thought_generator: Callable[[dict[str, Any], list[ReActStep]], str],
        action_decider: Callable[[dict[str, Any], list[ReActStep], str], tuple[str, dict[str, Any]]],
        action_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
        termination_checker: Callable[[dict[str, Any], list[ReActStep]], bool],
        final_answer_generator: Callable[[dict[str, Any], list[ReActStep]], dict[str, Any]] | None = None,
    ) -> None:
        self._max_steps = max_steps
        self._thought_generator = thought_generator
        self._action_decider = action_decider
        self._action_executor = action_executor
        self._termination_checker = termination_checker
        self._final_answer_generator = final_answer_generator

    async def run(self, *, task: dict[str, Any]) -> ReActResult:
        start = time.perf_counter()
        steps: list[ReActStep] = []
        errors: list[str] = []

        try:
            for index in range(self._max_steps):
                thought = self._thought_generator(task, steps)
                action_type, action = self._action_decider(task, steps, thought)
                step = ReActStep(
                    step_id=f"step_{index + 1}",
                    thought=thought,
                    action_type=action_type,
                    action=action,
                )
                step.observation = self._action_executor(action_type, action)
                steps.append(step)
                if self._termination_checker(task, steps):
                    break

            final_answer = None
            if self._final_answer_generator is not None:
                final_answer = self._final_answer_generator(task, steps)
            elif steps:
                final_answer = steps[-1].observation

            return ReActResult(
                run_id=f"react_{uuid.uuid4().hex[:8]}",
                success=True,
                steps=steps,
                final_answer=final_answer,
                total_latency_ms=(time.perf_counter() - start) * 1000,
                errors=errors,
            )
        except Exception as exc:
            errors.append(str(exc))
            return ReActResult(
                run_id=f"react_{uuid.uuid4().hex[:8]}",
                success=False,
                steps=steps,
                final_answer=None,
                total_latency_ms=(time.perf_counter() - start) * 1000,
                errors=errors,
            )


class CoTEnhancedReActLoop(ReActLoop):
    """带 reasoning 和 evidence 的 ReAct 循环."""

    def __init__(
        self,
        *,
        reasoning_generator: Callable[[dict[str, Any], list[ReActStep], str], str],
        evidence_generator: Callable[[dict[str, Any], list[ReActStep], str], dict[str, Any]],
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._reasoning_generator = reasoning_generator
        self._evidence_generator = evidence_generator

    async def run(self, *, task: dict[str, Any]) -> ReActResult:
        start = time.perf_counter()
        steps: list[ReActStep] = []
        errors: list[str] = []

        try:
            for index in range(self._max_steps):
                thought = self._thought_generator(task, steps)
                action_type, action = self._action_decider(task, steps, thought)
                step = ReActStep(
                    step_id=f"step_{index + 1}",
                    thought=thought,
                    reasoning=self._reasoning_generator(task, steps, thought),
                    evidence=self._evidence_generator(task, steps, thought),
                    action_type=action_type,
                    action=action,
                )
                step.observation = self._action_executor(action_type, action)
                steps.append(step)
                if self._termination_checker(task, steps):
                    break

            return ReActResult(
                run_id=f"react_{uuid.uuid4().hex[:8]}",
                success=True,
                steps=steps,
                final_answer=steps[-1].observation if steps else None,
                total_latency_ms=(time.perf_counter() - start) * 1000,
                errors=errors,
            )
        except Exception as exc:
            errors.append(str(exc))
            return ReActResult(
                run_id=f"react_{uuid.uuid4().hex[:8]}",
                success=False,
                steps=steps,
                final_answer=None,
                total_latency_ms=(time.perf_counter() - start) * 1000,
                errors=errors,
            )


def format_react_trace(result: ReActResult) -> str:
    """格式化 ReAct 追踪 兼容旧测试断言."""
    lines = [
        f"Run ID: {result.run_id}",
        f"Success: {result.success}",
        f"Total Steps: {len(result.steps)}",
        f"Total Latency: {result.total_latency_ms:.1f}ms",
    ]
    for step in result.steps:
        lines.append(f"Step: {step.step_id}")
        lines.append(f"Thought: {step.thought}")
        if step.reasoning is not None:
            lines.append(f"Reasoning: {step.reasoning}")
        lines.append(f"Action: {step.action_type}")
        lines.append(f"Observation: {step.observation}")
    if result.errors:
        lines.append("Errors:")
        lines.extend(result.errors)
    return "\n".join(lines)


__all__ = [
    "ReActStep",
    "ReActResult",
    "ReActLoop",
    "CoTEnhancedReActLoop",
    "format_react_trace",
]
