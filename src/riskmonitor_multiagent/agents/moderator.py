"""
Moderator Agent（协调者）.

负责多 Agent 协作的协调工作，包括：
- 决定下一步该谁说话
- 处理冲突（仲裁）
- 管理协作流程
- 决定什么时候结束
"""

from __future__ import annotations

from typing import Any, Optional

import logging

from riskmonitor_multiagent.contracts.message import MessageType
from riskmonitor_multiagent.orchestration.message_bus import MessageBus, get_message_bus

logger = logging.getLogger(__name__)


class ModeratorAgent:
    """
    协调者 Agent.

    负责多 Agent 协作的协调工作.
    """

    # Agent ID
    AGENT_ID = "moderator"

    # 可用的 Agent 列表
    AVAILABLE_AGENTS = [
        "intent",
        "orchestrator",
        "critic",
        "system_engineer",
        "risk_analyst",
    ]

    def __init__(self, message_bus: Optional[MessageBus] = None):
        self._message_bus = message_bus or get_message_bus()
        self._task: Optional[dict[str, Any]] = None
        self._conversation_history: list[dict[str, Any]] = []
        self._current_speaker: Optional[str] = None
        self._is_running: bool = False

    async def start_collaboration(
        self,
        task: dict[str, Any],
    ) -> dict[str, Any]:
        """
        开始协作流程.

        Args:
            task: 任务

        Returns:
            协作结果
        """
        self._task = task
        self._conversation_history = []
        self._is_running = True

        logger.info(f"Starting collaboration for task: {task.get('task_id')}")

        # 第一步：先让 Intent Agent 识别意图
        self._current_speaker = "intent"
        await self._message_bus.send_request(
            from_agent=self.AGENT_ID,
            to_agent="intent",
            content={"task": task},
        )

        # 等待协作完成
        result = await self._wait_for_completion()
        return result

    async def on_message(self, message: dict[str, Any]) -> None:
        """
        处理收到的消息.

        Args:
            message: 消息
        """
        message_type = message.get("message_type")
        from_agent = message.get("from_agent")

        logger.debug(f"Moderator received message: {message_type} from {from_agent}")

        # 记录消息历史
        self._conversation_history.append(message)

        # 根据消息类型处理
        if message_type == MessageType.RESPONSE.value:
            await self._on_response(message)
        elif message_type == MessageType.BROADCAST.value:
            await self._on_broadcast(message)
        elif message_type == MessageType.INTERRUPT.value:
            await self._on_interrupt(message)
        elif message_type == MessageType.FEEDBACK.value:
            await self._on_feedback(message)

    async def _on_response(self, message: dict[str, Any]) -> None:
        """处理响应消息."""
        from_agent = message.get("from_agent")

        # 决定下一步该谁说话
        next_speaker = self._decide_next_speaker(from_agent)

        if next_speaker:
            self._current_speaker = next_speaker
            await self._message_bus.send_request(
                from_agent=self.AGENT_ID,
                to_agent=next_speaker,
                content={
                    "task": self._task,
                    "conversation_history": self._conversation_history,
                },
            )
        else:
            # 没有下一步了，结束协作
            await self._finalize()

    async def _on_broadcast(self, message: dict[str, Any]) -> None:
        """处理广播消息."""
        # 广播消息所有 Agent 都能收到，Moderator 不需要特殊处理
        pass

    async def _on_interrupt(self, message: dict[str, Any]) -> None:
        """处理中断消息."""
        from_agent = message.get("from_agent")
        reason = message.get("content", {}).get("reason", "")

        logger.warning(f"Collaboration interrupted by {from_agent}: {reason}")

        # 仲裁：决定是否继续、暂停还是结束
        decision = self._arbitrate_interrupt(from_agent, reason)

        if decision == "continue":
            # 继续当前流程
            pass
        elif decision == "replan":
            # 重新规划
            self._current_speaker = "orchestrator"
            await self._message_bus.send_request(
                from_agent=self.AGENT_ID,
                to_agent="orchestrator",
                content={
                    "task": self._task,
                    "conversation_history": self._conversation_history,
                    "interrupt_reason": reason,
                },
            )
        else:
            # 结束
            await self._finalize()

    async def _on_feedback(self, message: dict[str, Any]) -> None:
        """处理反馈消息."""
        from_agent = message.get("from_agent")
        feedback = message.get("content", {}).get("feedback", "")

        logger.debug(f"Feedback from {from_agent}: {feedback}")

        # 可以根据反馈决定下一步
        # 这里先简单处理，直接继续
        pass

    def _decide_next_speaker(self, last_speaker: str) -> Optional[str]:
        """
        决定下一步该谁说话.

        Args:
            last_speaker: 上一个说话的 Agent

        Returns:
            下一个说话的 Agent，None 表示结束
        """
        # 简单的规则：按顺序来
        # 实际项目中应该用 LLM 来动态决定
        order = [
            "intent",
            "orchestrator",
            "critic",
            "system_engineer",
            "risk_analyst",
            None,  # 结束
        ]

        try:
            current_index = order.index(last_speaker)
            next_index = current_index + 1
            if next_index < len(order):
                return order[next_index]
        except ValueError:
            pass

        return None

    def _arbitrate_interrupt(self, from_agent: str, reason: str) -> str:
        """
        仲裁中断请求.

        Args:
            from_agent: 发起中断的 Agent
            reason: 中断原因

        Returns:
            决定："continue", "replan", "end"
        """
        # 简单规则：如果是 Critic 发起的中断，重新规划
        if from_agent == "critic":
            return "replan"

        # 其他情况继续
        return "continue"

    async def _finalize(self) -> None:
        """结束协作."""
        self._is_running = False

        logger.info("Collaboration finalized")

        # 广播结束消息
        await self._message_bus.broadcast(
            from_agent=self.AGENT_ID,
            content={"status": "completed"},
        )

    async def _wait_for_completion(self) -> dict[str, Any]:
        """等待协作完成."""
        # 简单实现：轮询检查是否完成
        # 实际项目中应该用事件或 future
        import asyncio

        while self._is_running:
            await asyncio.sleep(0.1)

        # 返回结果
        return {
            "status": "completed",
            "conversation_history": self._conversation_history,
        }
