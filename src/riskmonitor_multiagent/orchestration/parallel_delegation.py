"""
Parallel Delegation 模式.

实现多 Agent 并行协作，让 System Engineer 和 Risk Analyst 可以同时工作.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from riskmonitor_multiagent.agents.base import AgentResult
from riskmonitor_multiagent.agents.message_roles import (
    MessageEnabledRiskAnalystAgent,
    MessageEnabledSystemEngineerAgent,
)
from riskmonitor_multiagent.contracts.message import MessageType
from riskmonitor_multiagent.orchestration.message_bus import MessageBus, get_message_bus
from riskmonitor_multiagent.services.logging_service import new_request_id
from riskmonitor_multiagent.utils.time import now_ms

import logging

logger = logging.getLogger(__name__)


class ParallelDelegationResult:
    """
    并行委派结果.

    包含 System Engineer 和 Risk Analyst 的输出.
    """

    def __init__(
        self,
        *,
        engineer_result: Optional[AgentResult] = None,
        analyst_result: Optional[AgentResult] = None,
        engineer_error: Optional[str] = None,
        analyst_error: Optional[str] = None,
        started_ms: Optional[int] = None,
        completed_ms: Optional[int] = None,
    ) -> None:
        self.engineer_result = engineer_result
        self.analyst_result = analyst_result
        self.engineer_error = engineer_error
        self.analyst_error = analyst_error
        self.started_ms = started_ms
        self.completed_ms = completed_ms

    @property
    def ok(self) -> bool:
        """是否成功."""
        return (
            self.engineer_result is not None and self.engineer_result.ok and
            self.analyst_result is not None and self.analyst_result.ok
        )

    @property
    def both_completed(self) -> bool:
        """两个 Agent 都完成了."""
        return (
            self.engineer_result is not None and
            self.analyst_result is not None
        )

    @property
    def latency_ms(self) -> Optional[int]:
        """延迟（毫秒）."""
        if self.started_ms and self.completed_ms:
            return self.completed_ms - self.started_ms
        return None


class ParallelDelegationExecutor:
    """
    并行委派执行器.

    实现 System Engineer 和 Risk Analyst 的并行执行.
    """

    def __init__(
        self,
        *,
        message_bus: Optional[MessageBus] = None,
        engineer_agent: Optional[MessageEnabledSystemEngineerAgent] = None,
        analyst_agent: Optional[MessageEnabledRiskAnalystAgent] = None,
    ) -> None:
        """
        初始化并行委派执行器.

        Args:
            message_bus: 可选的 MessageBus 实例
            engineer_agent: 可选的 System Engineer Agent 实例
            analyst_agent: 可选的 Risk Analyst Agent 实例
        """
        self._message_bus = message_bus or get_message_bus()
        self._engineer_agent = engineer_agent or MessageEnabledSystemEngineerAgent(message_bus=self._message_bus)
        self._analyst_agent = analyst_agent or MessageEnabledRiskAnalystAgent(message_bus=self._message_bus)

    async def execute(
        self,
        *,
        task: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
    ) -> ParallelDelegationResult:
        """
        并行执行 System Engineer 和 Risk Analyst.

        Args:
            task: 任务
            context: 上下文
            max_tokens: 最大 Token 数

        Returns:
            并行委派结果
        """
        request_id = new_request_id()
        logger.info(f"Starting parallel delegation: {request_id}")

        started_ms = now_ms()
        result = ParallelDelegationResult(started_ms=started_ms)

        # 准备两个 Agent 的参数
        engineer_task = task
        analyst_task = task
        shared_context = context or {}

        try:
            # 并行执行两个 Agent
            engineer_task_future = self._run_engineer(
                task=engineer_task,
                context=shared_context,
                max_tokens=max_tokens,
            )
            analyst_task_future = self._run_analyst(
                task=analyst_task,
                context=shared_context,
                max_tokens=max_tokens,
            )

            # 等待两个任务完成
            engineer_result, analyst_result = await asyncio.gather(
                engineer_task_future,
                analyst_task_future,
                return_exceptions=True,
            )

            # 处理结果
            if isinstance(engineer_result, Exception):
                result.engineer_error = str(engineer_result)
                logger.error(f"Engineer error: {engineer_result}")
            else:
                result.engineer_result = engineer_result

            if isinstance(analyst_result, Exception):
                result.analyst_error = str(analyst_result)
                logger.error(f"Analyst error: {analyst_result}")
            else:
                result.analyst_result = analyst_result

        except Exception as e:
            logger.error(f"Parallel delegation error: {e}")
            result.engineer_error = str(e)
            result.analyst_error = str(e)

        finally:
            result.completed_ms = now_ms()

        logger.info(
            f"Parallel delegation completed: {request_id}, "
            f"ok={result.ok}, latency={result.latency_ms}ms"
        )

        return result

    async def _run_engineer(
        self,
        *,
        task: dict[str, Any],
        context: Optional[dict[str, Any]],
        max_tokens: Optional[int],
    ) -> AgentResult:
        """运行 System Engineer Agent."""
        # 注意：这里我们直接调用 original_agent，不走消息总线
        # 因为 MessageEnabledAgent 的 _handle_request 是处理收到的消息，不是主动调用
        return await self._engineer_agent._original_agent.analyze_task(
            task=task,
            context=context,
            max_tokens=max_tokens,
        )

    async def _run_analyst(
        self,
        *,
        task: dict[str, Any],
        context: Optional[dict[str, Any]],
        max_tokens: Optional[int],
    ) -> AgentResult:
        """运行 Risk Analyst Agent."""
        # 注意：这里我们直接调用 original_agent，不走消息总线
        return await self._analyst_agent._original_agent.analyze_task(
            task=task,
            context=context,
            max_tokens=max_tokens,
        )


# 全局并行委派执行器实例
_executor: Optional[ParallelDelegationExecutor] = None


def get_parallel_delegation_executor(
    message_bus: Optional[MessageBus] = None,
) -> ParallelDelegationExecutor:
    """
    获取全局并行委派执行器实例.

    Args:
        message_bus: 可选的 MessageBus 实例

    Returns:
        并行委派执行器
    """
    global _executor
    if _executor is None:
        _executor = ParallelDelegationExecutor(message_bus=message_bus)
    return _executor


def reset_parallel_delegation_executor() -> None:
    """重置并行委派执行器（用于测试）."""
    global _executor
    _executor = None
