"""
消息化 Agent 基类.

提供支持消息总线的 Agent 基类，包括:
- 订阅和处理消息
- 发送响应消息
- 主动发送消息
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from riskmonitor_multiagent.agents.base import AgentResult, BaseAgent
from riskmonitor_multiagent.contracts.message import MessageType
from riskmonitor_multiagent.orchestration.message_bus import MessageBus, get_message_bus

logger = logging.getLogger(__name__)


class MessageEnabledAgent:
    """
    消息化 Agent 基类.

    支持通过 Message Bus 与其他 Agent 通信.
    """

    def __init__(
        self,
        *,
        agent_id: str,
        base_agent: Optional[BaseAgent] = None,
        message_bus: Optional[MessageBus] = None,
    ) -> None:
        """
        初始化消息化 Agent.

        Args:
            agent_id: Agent ID
            base_agent: 可选的 BaseAgent 实例
            message_bus: 可选的 MessageBus 实例
        """
        self._agent_id = agent_id
        self._base_agent = base_agent
        self._message_bus = message_bus or get_message_bus()

        # 订阅消息
        self._message_bus.subscribe(self._agent_id, self._on_message)

    async def _on_message(self, message: dict[str, Any]) -> None:
        """
        处理收到的消息.

        Args:
            message: 收到的消息
        """
        message_type = message.get("message_type")
        from_agent = message.get("from_agent")
        content = message.get("content", {})

        logger.debug(f"Agent {self._agent_id} received message: {message_type} from {from_agent}")

        if message_type == MessageType.REQUEST.value:
            await self._handle_request(message, content)
        elif message_type == MessageType.RESPONSE.value:
            await self._handle_response(message, content)
        elif message_type == MessageType.BROADCAST.value:
            await self._handle_broadcast(message, content)
        elif message_type == MessageType.INTERRUPT.value:
            await self._handle_interrupt(message, content)
        elif message_type == MessageType.FEEDBACK.value:
            await self._handle_feedback(message, content)

    async def _handle_request(self, message: dict[str, Any], content: dict[str, Any]) -> None:
        """
        处理请求消息.

        子类应该重写这个方法来处理请求.

        Args:
            message: 收到的消息
            content: 消息内容
        """
        logger.warning(f"Agent {self._agent_id} received request but _handle_request not implemented")

        # 默认响应
        await self._send_response(
            message=message,
            content={"ok": False, "error": "not_implemented"},
        )

    async def _handle_response(self, message: dict[str, Any], content: dict[str, Any]) -> None:
        """
        处理响应消息.

        子类可以重写这个方法来处理响应.

        Args:
            message: 收到的消息
            content: 消息内容
        """
        pass

    async def _handle_broadcast(self, message: dict[str, Any], content: dict[str, Any]) -> None:
        """
        处理广播消息.

        子类可以重写这个方法来处理广播.

        Args:
            message: 收到的消息
            content: 消息内容
        """
        pass

    async def _handle_interrupt(self, message: dict[str, Any], content: dict[str, Any]) -> None:
        """
        处理中断消息.

        子类可以重写这个方法来处理中断.

        Args:
            message: 收到的消息
            content: 消息内容
        """
        pass

    async def _handle_feedback(self, message: dict[str, Any], content: dict[str, Any]) -> None:
        """
        处理反馈消息.

        子类可以重写这个方法来处理反馈.

        Args:
            message: 收到的消息
            content: 消息内容
        """
        pass

    async def _send_response(
        self,
        message: dict[str, Any],
        content: dict[str, Any],
    ) -> None:
        """
        发送响应消息.

        Args:
            message: 收到的请求消息
            content: 响应内容
        """
        in_reply_to = message.get("message_id")
        to_agent = message.get("from_agent")

        if not in_reply_to or not to_agent:
            logger.warning(f"Cannot send response: missing in_reply_to or from_agent")
            return

        await self._message_bus.send_response(
            from_agent=self._agent_id,
            to_agent=to_agent,
            content=content,
            in_reply_to=in_reply_to,
        )

    async def send_request(
        self,
        to_agent: str,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        """
        发送请求消息.

        Args:
            to_agent: 目标 Agent ID
            content: 请求内容

        Returns:
            发送的消息
        """
        return await self._message_bus.send_request(
            from_agent=self._agent_id,
            to_agent=to_agent,
            content=content,
        )

    async def send_broadcast(
        self,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        """
        发送广播消息.

        Args:
            content: 广播内容

        Returns:
            发送的消息
        """
        return await self._message_bus.broadcast(
            from_agent=self._agent_id,
            content=content,
        )

    async def send_interrupt(
        self,
        reason: str,
        to_agent: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        发送中断消息.

        Args:
            reason: 中断原因
            to_agent: 目标 Agent ID（None 表示广播）

        Returns:
            发送的消息
        """
        return await self._message_bus.send_interrupt(
            from_agent=self._agent_id,
            reason=reason,
            to_agent=to_agent,
        )

    async def send_feedback(
        self,
        to_agent: str,
        feedback: str,
        in_reply_to: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        发送反馈消息.

        Args:
            to_agent: 目标 Agent ID
            feedback: 反馈内容
            in_reply_to: 回复的消息 ID

        Returns:
            发送的消息
        """
        return await self._message_bus.send_feedback(
            from_agent=self._agent_id,
            to_agent=to_agent,
            feedback=feedback,
            in_reply_to=in_reply_to,
        )

    @property
    def agent_id(self) -> str:
        """获取 Agent ID."""
        return self._agent_id

    @property
    def message_bus(self) -> MessageBus:
        """获取 Message Bus."""
        return self._message_bus

    @property
    def base_agent(self) -> Optional[BaseAgent]:
        """获取 BaseAgent 实例."""
        return self._base_agent
