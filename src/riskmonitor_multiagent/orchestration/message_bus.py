"""
消息总线实现.

实现多 Agent 之间的通信基础设施，支持发送、接收、订阅消息.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from typing import Any, Callable, Optional

from riskmonitor_multiagent.contracts.message import (
    MessageType,
    normalize_message,
    validate_message,
)
from riskmonitor_multiagent.services.logging_service import get_logger
from riskmonitor_multiagent.utils.time import now_ms

logger = get_logger(__name__)


class MessageBus:
    """
    消息总线.

    负责 Agent 之间的消息传递，支持：
    - 发送消息（点对点、广播）
    - 订阅消息
    - 查询消息历史
    """

    def __init__(self):
        self._messages: list[dict[str, Any]] = []
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._broadcast_subscribers: list[Callable] = []
        self._lock = asyncio.Lock()

    async def send(
        self,
        message_type: MessageType,
        from_agent: str,
        content: dict[str, Any],
        to_agent: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        发送消息.

        Args:
            message_type: 消息类型
            from_agent: 发送者 Agent ID
            content: 消息内容
            to_agent: 接收者 Agent ID（None 表示广播）
            in_reply_to: 回复的消息 ID

        Returns:
            发送的消息
        """
        message = {
            "message_id": str(uuid.uuid4()),
            "message_type": message_type.value,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "content": content,
            "timestamp_ms": now_ms(),
            "in_reply_to": in_reply_to,
        }

        # 归一化和验证
        message = normalize_message(message)
        is_valid, errors = validate_message(message)
        if not is_valid:
            logger.error(f"Message validation failed: {errors}")
            message["degraded"] = True
            message["degraded_reason"] = f"validation_failed: {errors}"

        async with self._lock:
            self._messages.append(message)

        # 通知订阅者
        await self._notify_subscribers(message)

        logger.debug(f"Message sent: {message['message_id']} from {from_agent} to {to_agent or 'broadcast'}")
        return message

    async def send_request(
        self,
        from_agent: str,
        to_agent: str,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        """发送请求消息."""
        return await self.send(
            message_type=MessageType.REQUEST,
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
        )

    async def send_response(
        self,
        from_agent: str,
        to_agent: str,
        content: dict[str, Any],
        in_reply_to: str,
    ) -> dict[str, Any]:
        """发送响应消息."""
        return await self.send(
            message_type=MessageType.RESPONSE,
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            in_reply_to=in_reply_to,
        )

    async def broadcast(
        self,
        from_agent: str,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        """发送广播消息."""
        return await self.send(
            message_type=MessageType.BROADCAST,
            from_agent=from_agent,
            to_agent=None,
            content=content,
        )

    async def send_interrupt(
        self,
        from_agent: str,
        reason: str,
        to_agent: Optional[str] = None,
    ) -> dict[str, Any]:
        """发送中断消息."""
        return await self.send(
            message_type=MessageType.INTERRUPT,
            from_agent=from_agent,
            to_agent=to_agent,
            content={"reason": reason},
        )

    async def send_feedback(
        self,
        from_agent: str,
        to_agent: str,
        feedback: str,
        in_reply_to: Optional[str] = None,
    ) -> dict[str, Any]:
        """发送反馈消息."""
        return await self.send(
            message_type=MessageType.FEEDBACK,
            from_agent=from_agent,
            to_agent=to_agent,
            content={"feedback": feedback},
            in_reply_to=in_reply_to,
        )

    async def send_tool_call(
        self,
        from_agent: str,
        tool_name: str,
        tool_params: dict[str, Any],
        to_agent: Optional[str] = None,
    ) -> dict[str, Any]:
        """发送工具调用请求."""
        return await self.send(
            message_type=MessageType.TOOL_CALL,
            from_agent=from_agent,
            to_agent=to_agent,
            content={"tool_name": tool_name, "tool_params": tool_params},
        )

    async def send_tool_result(
        self,
        from_agent: str,
        to_agent: str,
        tool_name: str,
        result: Any,
        success: bool = True,
        error: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> dict[str, Any]:
        """发送工具调用结果."""
        return await self.send(
            message_type=MessageType.TOOL_RESULT,
            from_agent=from_agent,
            to_agent=to_agent,
            content={
                "tool_name": tool_name,
                "result": result,
                "success": success,
                "error": error,
            },
            in_reply_to=in_reply_to,
        )

    def subscribe(
        self,
        agent_id: str,
        callback: Callable[[dict[str, Any]], Any],
    ) -> None:
        """
        订阅发给特定 Agent 的消息.

        Args:
            agent_id: Agent ID
            callback: 消息到达时的回调函数
        """
        self._subscribers[agent_id].append(callback)
        logger.debug(f"Subscribed: {agent_id}")

    def subscribe_broadcast(
        self,
        callback: Callable[[dict[str, Any]], Any],
    ) -> None:
        """
        订阅广播消息.

        Args:
            callback: 消息到达时的回调函数
        """
        self._broadcast_subscribers.append(callback)
        logger.debug("Subscribed to broadcast")

    def get_messages_for_agent(
        self,
        agent_id: str,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """
        获取发给特定 Agent 的消息历史.

        Args:
            agent_id: Agent ID
            limit: 最大返回数量

        Returns:
            消息列表
        """
        messages = [
            m for m in self._messages
            if m.get("to_agent") == agent_id or m.get("to_agent") is None
        ]
        if limit:
            messages = messages[-limit:]
        return messages

    def get_message_history(
        self,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """
        获取所有消息历史.

        Args:
            limit: 最大返回数量

        Returns:
            消息列表
        """
        messages = list(self._messages)
        if limit:
            messages = messages[-limit:]
        return messages

    def get_message_by_id(
        self,
        message_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        根据 ID 获取消息.

        Args:
            message_id: 消息 ID

        Returns:
            消息，如果找不到返回 None
        """
        for m in self._messages:
            if m.get("message_id") == message_id:
                return m
        return None

    async def _notify_subscribers(self, message: dict[str, Any]) -> None:
        """通知订阅者."""
        to_agent = message.get("to_agent")

        # 通知广播订阅者
        for callback in self._broadcast_subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"Broadcast subscriber error: {e}")

        # 通知特定 Agent 的订阅者
        if to_agent and to_agent in self._subscribers:
            for callback in self._subscribers[to_agent]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(message)
                    else:
                        callback(message)
                except Exception as e:
                    logger.error(f"Subscriber error for {to_agent}: {e}")


# 全局消息总线实例
_message_bus: Optional[MessageBus] = None


def get_message_bus() -> MessageBus:
    """获取全局消息总线实例."""
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus


def reset_message_bus() -> None:
    """重置消息总线（用于测试）."""
    global _message_bus
    _message_bus = None
