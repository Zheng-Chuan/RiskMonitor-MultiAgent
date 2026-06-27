"""统一消息路由.

根据消息类型决定入口（user_task 或 system_event）,
并根据平台特性适配响应格式.
网关只是入口适配, 不改变执行内核.
"""

from __future__ import annotations

import logging
from typing import Any

from riskmonitor_multiagent.gateway.adapter import GatewayAdapter, GatewayMessage

logger = logging.getLogger(__name__)

# 映射到 system_event 入口的消息类型
_SYSTEM_EVENT_TYPES = frozenset({"alert", "approval", "query", "status", "system_event"})
_SYSTEM_EVENT_TYPE_MAP = {
    "alert": "risk_breach_detected",
    "approval": "approval_required",
    "query": "task_created",
    "status": "task_created",
    "system_event": "task_created",
}


class GatewayRouter:
    """统一消息路由.

    根据消息类型决定入口:
        - "user_task" → user_task 入口
        - "alert" / "approval" / "query" / "status" → system_event 入口

    新增平台只需注册对应适配器, 路由逻辑无需修改.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, GatewayAdapter] = {}

    def register_adapter(self, adapter: GatewayAdapter) -> None:
        """注册平台适配器.

        Args:
            adapter: 实现 GatewayAdapter 的适配器实例.
        """
        self._adapters[adapter.platform_name] = adapter
        logger.info("Registered gateway adapter: %s", adapter.platform_name)

    def get_adapter(self, platform: str) -> GatewayAdapter | None:
        """获取已注册的平台适配器.

        Args:
            platform: 平台名称.

        Returns:
            适配器实例, 未注册时返回 None.
        """
        return self._adapters.get(platform)

    async def route_message(
        self,
        raw_input: dict[str, Any],
        platform: str,
    ) -> dict[str, Any]:
        """路由消息到统一执行内核.

        流程:
            1. 获取适配器
            2. receive_message → GatewayMessage
            3. 根据 message_type 决定入口:
               - "user_task" → user_task 入口
               - "alert" / "approval" / "query" / "status" → system_event 入口
            4. 返回路由决策

        Args:
            raw_input: 平台特定的原始消息字典.
            platform: 来源平台名称.

        Returns:
            路由决策字典, 包含:
                - entry_type: "user_task" 或 "system_event"
                - message: GatewayMessage 对象
                - platform: 平台名称
                - adapter: 适配器实例
            若平台未注册, 返回 error 信息.
        """
        adapter = self._adapters.get(platform)
        if adapter is None:
            logger.warning("No adapter registered for platform: %s", platform)
            return {
                "entry_type": None,
                "message": None,
                "platform": platform,
                "adapter": None,
                "error": f"platform_not_registered:{platform}",
            }

        message = await adapter.receive_message(raw_input)

        if message.message_type in _SYSTEM_EVENT_TYPES:
            entry_type = "system_event"
        else:
            entry_type = "user_task"

        logger.info(
            "Routed message %s from %s: type=%s → entry=%s",
            message.message_id,
            platform,
            message.message_type,
            entry_type,
        )

        return {
            "entry_type": entry_type,
            "message": message,
            "platform": platform,
            "adapter": adapter,
        }

    async def route_and_execute(
        self,
        raw_input: dict[str, Any],
        platform: str,
        *,
        user_task_executor: Any | None = None,
        system_event_executor: Any | None = None,
    ) -> dict[str, Any]:
        """路由后直接调用统一执行入口.

        说明:
            - 保持 route_message 的纯路由语义不变
            - 新增 route_and_execute 用于真正接到统一 workflow
            - 测试可通过传入自定义 executor 隔离外部依赖
        """
        route_result = await self.route_message(raw_input=raw_input, platform=platform)
        if route_result.get("error"):
            route_result["execution_result"] = None
            return route_result

        execution_result = await self.execute_route(
            route_result=route_result,
            user_task_executor=user_task_executor,
            system_event_executor=system_event_executor,
        )
        out = dict(route_result)
        out["execution_result"] = execution_result
        return out

    async def execute_route(
        self,
        *,
        route_result: dict[str, Any],
        user_task_executor: Any | None = None,
        system_event_executor: Any | None = None,
    ) -> dict[str, Any]:
        """执行已完成路由的消息."""
        entry_type = route_result.get("entry_type")
        message = route_result.get("message")
        if not isinstance(message, GatewayMessage) or entry_type not in {"user_task", "system_event"}:
            raise ValueError("route_result 缺少有效的 entry_type 或 message")

        if entry_type == "system_event":
            executor = system_event_executor or self._default_system_event_executor
            return await executor(self._build_system_event(message))

        executor = user_task_executor or self._default_user_task_executor
        return await executor(self._build_user_task(message))

    @staticmethod
    async def _default_user_task_executor(task: dict[str, Any]) -> dict[str, Any]:
        """默认 user_task 执行器, 接入统一主动工作流."""
        from riskmonitor_multiagent.orchestration import run_proactive_workflow

        return await run_proactive_workflow(task=task)

    @staticmethod
    async def _default_system_event_executor(event: dict[str, Any]) -> dict[str, Any]:
        """默认 system_event 执行器, 接入统一事件入口."""
        from riskmonitor_multiagent.orchestration.proactive_workflow import get_proactive_workflow

        workflow = get_proactive_workflow()
        return await workflow.start_from_event(event=event)

    @staticmethod
    def _build_user_task(message: GatewayMessage) -> dict[str, Any]:
        """将平台消息转换为统一 user_task 结构."""
        session_key = message.channel_id or message.user_id or "gateway"
        return {
            "task_id": message.message_id,
            "session_id": f"gateway:{message.platform}:{session_key}",
            "source": f"gateway:{message.platform}",
            "payload": {
                "content": message.content,
                "gateway_message": GatewayRouter._serialize_message(message),
            },
        }

    @staticmethod
    def _build_system_event(message: GatewayMessage) -> dict[str, Any]:
        """将平台消息转换为统一 system_event 结构."""
        from riskmonitor_multiagent.contracts.event import new_event

        event_type = _SYSTEM_EVENT_TYPE_MAP.get(message.message_type, "task_created")
        return new_event(
            event_type=event_type,
            source_agent=f"gateway:{message.platform}",
            payload={
                "task_id": message.message_id,
                "content": message.content,
                "gateway_message": GatewayRouter._serialize_message(message),
                "task": GatewayRouter._build_user_task(message),
            },
        )

    @staticmethod
    def _serialize_message(message: GatewayMessage) -> dict[str, Any]:
        """序列化 GatewayMessage, 便于透传到执行内核."""
        return {
            "message_id": message.message_id,
            "platform": message.platform,
            "message_type": message.message_type,
            "content": message.content,
            "user_id": message.user_id,
            "channel_id": message.channel_id,
            "timestamp": message.timestamp,
            "metadata": dict(message.metadata),
            "reply_to": message.reply_to,
        }

    async def format_response(
        self,
        platform: str,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """根据 platform_hints 适配响应格式.

        若响应文本超过平台最大长度, 将进行截断处理.

        Args:
            platform: 目标平台名称.
            response: 原始响应字典.

        Returns:
            适配后的响应字典, 可能包含 "truncated" 标记.
        """
        adapter = self._adapters.get(platform)
        if adapter is None:
            logger.warning("No adapter for platform: %s, returning raw response", platform)
            return dict(response)

        hints = adapter.platform_hints()
        max_len = hints.get("max_text_length", 0)

        formatted = dict(response)
        text = str(formatted.get("text") or formatted.get("content") or "")

        if max_len and len(text) > max_len:
            truncated_text = text[:max_len]
            if "text" in formatted:
                formatted["text"] = truncated_text
            elif "content" in formatted:
                formatted["content"] = truncated_text
            else:
                formatted["text"] = truncated_text
            formatted["truncated"] = True
            formatted["original_length"] = len(text)
            logger.info(
                "Response truncated for platform %s: %d → %d chars",
                platform,
                len(text),
                max_len,
            )

        formatted.setdefault("platform", platform)
        formatted.setdefault("platform_hints", hints)
        return formatted
