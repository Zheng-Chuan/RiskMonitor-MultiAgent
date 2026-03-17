"""Agent 间消息总线.

实现 Agent 之间的异步消息传递，使用纯内存存储。

功能：
- 发布/订阅模式
- 点对点消息
- 消息回溯
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型."""
    OBSERVATION = "observation"
    QUESTION = "question"
    ANSWER = "answer"
    PROPOSAL = "proposal"
    CRITIQUE = "critique"
    REVISION = "revision"
    SUMMARY = "summary"
    COMMAND = "command"
    RECEIPT = "receipt"


@dataclass
class AgentMessage:
    """Agent 消息."""
    message_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    from_agent: str
    to_agent: Optional[str] = None
    message_type: MessageType
    content: dict[str, Any] = field(default_factory=dict)
    in_reply_to: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": self.message_type.value,
            "content": self.content,
            "in_reply_to": self.in_reply_to,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":
        return cls(
            message_id=data["message_id"],
            timestamp=data["timestamp"],
            from_agent=data["from_agent"],
            to_agent=data.get("to_agent"),
            message_type=MessageType(data["message_type"]),
            content=data.get("content", {}),
            in_reply_to=data.get("in_reply_to"),
            metadata=data.get("metadata", {}),
        )


class MessageBus:
    """Agent 消息总线（纯内存实现）."""

    def __init__(self) -> None:
        self._messages: list[AgentMessage] = []
        self._subscribers: dict[str, list[Callable[[AgentMessage], None]]] = {}
        self._lock = asyncio.Lock()

    async def publish(
        self,
        from_agent: str,
        message_type: MessageType,
        content: dict[str, Any],
        to_agent: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AgentMessage:
        """发布消息."""
        msg = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            in_reply_to=in_reply_to,
            metadata=metadata or {},
        )

        async with self._lock:
            self._messages.append(msg)

        await self._notify_subscribers(msg)
        logger.debug(f"Message published: {msg.message_id} from={from_agent} type={message_type.value}")
        return msg

    async def _notify_subscribers(self, msg: AgentMessage) -> None:
        """通知订阅者."""
        subscribers = []
        async with self._lock:
            if msg.to_agent and msg.to_agent in self._subscribers:
                subscribers.extend(self._subscribers[msg.to_agent])
            if "*" in self._subscribers:
                subscribers.extend(self._subscribers["*"])

        for callback in subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(msg)
                else:
                    callback(msg)
            except Exception as e:
                logger.error(f"Subscriber callback failed: {e}")

    def subscribe(self, agent_id: str, callback: Callable[[AgentMessage], None]) -> None:
        """订阅消息."""
        if agent_id not in self._subscribers:
            self._subscribers[agent_id] = []
        self._subscribers[agent_id].append(callback)

    def unsubscribe(self, agent_id: str, callback: Callable[[AgentMessage], None]) -> None:
        """取消订阅."""
        if agent_id in self._subscribers:
            self._subscribers[agent_id] = [
                cb for cb in self._subscribers[agent_id] if cb != callback
            ]

    async def get_messages(
        self,
        from_agent: Optional[str] = None,
        to_agent: Optional[str] = None,
        message_type: Optional[MessageType] = None,
        since_timestamp: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> list[AgentMessage]:
        """获取消息历史."""
        async with self._lock:
            messages = list(self._messages)

        if since_timestamp is not None:
            messages = [m for m in messages if m.timestamp >= since_timestamp]
        if from_agent is not None:
            messages = [m for m in messages if m.from_agent == from_agent]
        if to_agent is not None:
            messages = [m for m in messages if m.to_agent in (to_agent, None)]
        if message_type is not None:
            messages = [m for m in messages if m.message_type == message_type]

        if limit is not None:
            messages = messages[-limit:]

        return messages

    async def get_conversation(self, message_id: str) -> list[AgentMessage]:
        """获取对话线程（消息及其回复）."""
        async with self._lock:
            messages = list(self._messages)

        result: list[AgentMessage] = []
        queue = [message_id]

        while queue:
            current_id = queue.pop(0)
            msg = next((m for m in messages if m.message_id == current_id), None)
            if msg and msg not in result:
                result.append(msg)
                replies = [m.message_id for m in messages if m.in_reply_to == current_id]
                queue.extend(replies)

        return sorted(result, key=lambda m: m.timestamp)

    async def clear(self) -> None:
        """清空消息总线."""
        async with self._lock:
            self._messages.clear()


# 全局消息总线实例
_message_bus: Optional[MessageBus] = None


def get_message_bus() -> MessageBus:
    """
    获取全局消息总线实例.

    Returns:
        MessageBus 实例
    """
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus


def reset_message_bus() -> None:
    """重置消息总线（用于测试）."""
    global _message_bus
    _message_bus = None
