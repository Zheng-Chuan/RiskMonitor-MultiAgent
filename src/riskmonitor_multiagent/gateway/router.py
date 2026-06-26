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
_SYSTEM_EVENT_TYPES = frozenset({"alert", "approval", "query", "status"})


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
