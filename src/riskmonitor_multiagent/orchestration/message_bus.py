"""
消息总线实现.

实现多 Agent 之间的通信基础设施,支持发送、接收、订阅消息.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from typing import Any, Callable, Optional

from riskmonitor_multiagent.contracts.event import (
    EventType,
    new_event,
    validate_event,
)
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

    负责 Agent 之间的消息传递,支持:
    - 发送消息(点对点、广播)
    - 订阅消息
    - 查询消息历史
    """

    def __init__(self):
        self._messages: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._event_trace: list[dict[str, Any]] = []
        self._rejected_events: list[dict[str, Any]] = []
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._broadcast_subscribers: list[Callable] = []
        self._event_subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._event_any_subscribers: list[Callable] = []
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
            to_agent: 接收者 Agent ID(None 表示广播)
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

    async def emit_event(
        self,
        *,
        event_type: EventType,
        source_agent: str,
        payload: dict[str, Any] | None = None,
        target_agent: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        priority: str = "normal",
        requires_ack: bool = False,
    ) -> dict[str, Any]:
        """构造并发布事件."""
        event = new_event(
            event_type=event_type,
            source_agent=source_agent,
            payload=payload,
            target_agent=target_agent,
            correlation_id=correlation_id,
            causation_id=causation_id,
            priority=priority,
            requires_ack=requires_ack,
        )
        return await self.publish_event(event)

    async def publish_event(
        self,
        event: dict[str, Any],
        *,
        raise_on_error: bool = True,
    ) -> dict[str, Any]:
        """发布统一事件. 非法事件默认直接拒绝."""
        is_valid, errors = validate_event(event)
        if not is_valid:
            rejection = {
                "status": "rejected",
                "errors": list(errors),
                "event": dict(event) if isinstance(event, dict) else event,
                "timestamp_ms": now_ms(),
            }
            async with self._lock:
                self._rejected_events.append(rejection)
                self._event_trace.append(
                    {
                        "trace_id": f"trace_{uuid.uuid4().hex[:12]}",
                        "status": "rejected",
                        "event_id": event.get("event_id") if isinstance(event, dict) else None,
                        "event_type": event.get("event_type") if isinstance(event, dict) else None,
                        "source_agent": event.get("source_agent") if isinstance(event, dict) else None,
                        "target_agent": event.get("target_agent") if isinstance(event, dict) else None,
                        "errors": list(errors),
                        "timestamp_ms": now_ms(),
                    }
                )
            logger.warning("Event validation failed: %s", errors)
            if raise_on_error:
                raise ValueError(f"invalid_event:{','.join(errors)}")
            return rejection

        normalized_event = dict(event)
        delivery = await self._notify_event_subscribers(normalized_event)
        trace_entry = {
            "trace_id": f"trace_{uuid.uuid4().hex[:12]}",
            "status": "accepted",
            "event_id": normalized_event.get("event_id"),
            "event_type": normalized_event.get("event_type"),
            "source_agent": normalized_event.get("source_agent"),
            "target_agent": normalized_event.get("target_agent"),
            "subscriber_count": delivery.get("subscriber_count", 0),
            "delivery_errors": delivery.get("delivery_errors", []),
            "timestamp_ms": now_ms(),
        }

        async with self._lock:
            self._events.append(normalized_event)
            self._event_trace.append(trace_entry)

        logger.debug(
            "Event published: %s type=%s subscribers=%s",
            normalized_event.get("event_id"),
            normalized_event.get("event_type"),
            delivery.get("subscriber_count", 0),
        )
        return normalized_event

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

    def subscribe_event(
        self,
        event_type: EventType | str | None,
        callback: Callable[[dict[str, Any]], Any],
    ) -> None:
        """订阅统一事件. event_type 为 None 表示订阅全部事件."""
        if event_type is None:
            self._event_any_subscribers.append(callback)
            logger.debug("Subscribed to all events")
            return
        key = event_type.value if isinstance(event_type, EventType) else str(event_type)
        self._event_subscribers[key].append(callback)
        logger.debug("Subscribed to event type: %s", key)

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

    def get_event_history(
        self,
        *,
        limit: Optional[int] = None,
        event_type: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取事件历史."""
        events = list(self._events)
        if event_type:
            events = [event for event in events if event.get("event_type") == event_type]
        if status is not None:
            accepted_ids = {
                trace.get("event_id")
                for trace in self._event_trace
                if trace.get("status") == status
            }
            events = [event for event in events if event.get("event_id") in accepted_ids]
        if limit:
            events = events[-limit:]
        return events

    def get_event_trace(
        self,
        *,
        limit: Optional[int] = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取事件 trace sink 记录."""
        trace = list(self._event_trace)
        if status:
            trace = [item for item in trace if item.get("status") == status]
        if limit:
            trace = trace[-limit:]
        return trace

    def get_rejected_events(
        self,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """获取被拒绝的非法事件."""
        rejected = list(self._rejected_events)
        if limit:
            rejected = rejected[-limit:]
        return rejected

    def get_related_event_history(
        self,
        *,
        root_event_id: str | None = None,
        run_id: str | None = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """获取与某个 run 或根事件相关的事件历史."""
        events = [
            event
            for event in self._events
            if self._is_related_event(event=event, root_event_id=root_event_id, run_id=run_id)
        ]
        if limit:
            events = events[-limit:]
        return events

    def get_related_event_trace(
        self,
        *,
        root_event_id: str | None = None,
        run_id: str | None = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """获取与某个 run 或根事件相关的 event trace."""
        related_event_ids = {
            event.get("event_id")
            for event in self.get_related_event_history(
                root_event_id=root_event_id,
                run_id=run_id,
            )
            if isinstance(event, dict)
        }
        trace = [
            item
            for item in self._event_trace
            if item.get("event_id") in related_event_ids
        ]
        if limit:
            trace = trace[-limit:]
        return trace

    def get_message_by_id(
        self,
        message_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        根据 ID 获取消息.

        Args:
            message_id: 消息 ID

        Returns:
            消息,如果找不到返回 None
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

    async def _notify_event_subscribers(self, event: dict[str, Any]) -> dict[str, Any]:
        """通知事件订阅者,并返回投递摘要."""
        callbacks = list(self._event_any_subscribers)
        callbacks.extend(self._event_subscribers.get(str(event.get("event_type")), []))

        delivery_errors: list[str] = []
        subscriber_count = 0
        for callback in callbacks:
            subscriber_count += 1
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as exc:
                delivery_errors.append(str(exc))
                logger.error("Event subscriber error: %s", exc)

        return {
            "subscriber_count": subscriber_count,
            "delivery_errors": delivery_errors,
        }

    def _is_related_event(
        self,
        *,
        event: dict[str, Any],
        root_event_id: str | None,
        run_id: str | None,
    ) -> bool:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        context_summary = payload.get("context_summary") if isinstance(payload.get("context_summary"), dict) else {}
        if isinstance(run_id, str) and run_id:
            if context_summary.get("run_id") == run_id:
                return True
        if isinstance(root_event_id, str) and root_event_id:
            if event.get("event_id") == root_event_id:
                return True
            if event.get("correlation_id") == root_event_id:
                return True
            if event.get("causation_id") == root_event_id:
                return True
            if payload.get("event_id") == root_event_id:
                return True
        return False


# 全局消息总线实例
_message_bus: Optional[MessageBus] = None


def get_message_bus() -> MessageBus:
    """获取全局消息总线实例."""
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus


def reset_message_bus() -> None:
    """重置消息总线(用于测试)."""
    global _message_bus
    _message_bus = None
