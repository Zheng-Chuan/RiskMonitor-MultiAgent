"""企业微信适配器.

将企业微信回调消息转为统一 GatewayMessage, 并提供告警推送能力.
当前为 mock 实现, 不真正调用企业微信 API.
"""

from __future__ import annotations

import logging
from typing import Any

from riskmonitor_multiagent.gateway.adapter import GatewayAdapter, GatewayMessage

logger = logging.getLogger(__name__)

# 企业微信消息类型映射
_WECHAT_MSG_TYPE_MAP: dict[str, str] = {
    "text": "user_task",
    "event": "system_event",
    "alert": "alert",
    "approval": "approval",
    "query": "query",
    "status": "status",
}


class WeChatWorkAdapter(GatewayAdapter):
    """企业微信适配器.

    解析企业微信回调消息格式, 将其转换为统一 GatewayMessage.
    支持文本消息收发和告警卡片推送.
    """

    @property
    def platform_name(self) -> str:
        return "wechat_work"

    async def receive_message(self, raw_input: dict[str, Any]) -> GatewayMessage:
        """解析企业微信回调消息格式.

        支持的 raw_input 格式:
            - msg_type: 消息类型 (text/event 等)
            - content: 消息文本
            - from_user: 发送者 ID
            - agent_id: 企业应用 ID
            - chat_id: 群聊 ID
            - msg_id: 消息 ID (可选)
            - message_type: 显式指定统一消息类型 (可选, 优先于 msg_type 映射)

        Args:
            raw_input: 企业微信回调消息字典.

        Returns:
            统一格式的 GatewayMessage.
        """
        wechat_msg_type = str(raw_input.get("msg_type", "text"))
        content = str(raw_input.get("content", ""))
        from_user = raw_input.get("from_user")
        agent_id = raw_input.get("agent_id")
        chat_id = raw_input.get("chat_id")
        msg_id = raw_input.get("msg_id")

        # 显式 message_type 优先, 否则从 msg_type 映射
        explicit_type = raw_input.get("message_type")
        if isinstance(explicit_type, str) and explicit_type:
            message_type = explicit_type
        else:
            message_type = _WECHAT_MSG_TYPE_MAP.get(wechat_msg_type, "user_task")

        metadata: dict[str, Any] = {}
        if agent_id is not None:
            metadata["agent_id"] = agent_id
        if chat_id is not None:
            metadata["chat_id"] = chat_id
        if wechat_msg_type:
            metadata["wechat_msg_type"] = wechat_msg_type

        return GatewayMessage(
            platform=self.platform_name,
            message_type=message_type,
            content=content,
            user_id=str(from_user) if from_user is not None else None,
            channel_id=str(chat_id) if chat_id is not None else None,
            metadata=metadata,
            reply_to=str(msg_id) if msg_id else None,
        )

    async def send_response(self, message: GatewayMessage, response: dict[str, Any]) -> bool:
        """发送文本响应.

        企业微信限制 2048 字符, 超出部分将被截断.

        Args:
            message: 原始 GatewayMessage.
            response: 响应内容字典, 支持 "text" 或 "content" 字段.

        Returns:
            是否发送成功.
        """
        text = str(response.get("text") or response.get("content") or "")
        max_len = self.platform_hints()["max_text_length"]
        if len(text) > max_len:
            text = text[:max_len]
            logger.warning(
                "WeChatWork response truncated to %d chars for message %s",
                max_len,
                message.message_id,
            )
        logger.info(
            "WeChatWork send_response: user=%s, channel=%s, text_len=%d",
            message.user_id,
            message.channel_id,
            len(text),
        )
        return True

    async def send_alert(self, alert: dict[str, Any], channel_id: str | None = None) -> bool:
        """推送告警卡片消息.

        将告警内容封装为企业微信卡片格式并推送.

        Args:
            alert: 告警内容字典, 包含 title、description、level 等字段.
            channel_id: 目标频道 ID, 为 None 时使用默认频道.

        Returns:
            是否推送成功.
        """
        title = str(alert.get("title", "风险告警"))
        description = str(alert.get("description", ""))
        level = str(alert.get("level", "normal"))
        logger.info(
            "WeChatWork send_alert: channel=%s, title=%s, level=%s",
            channel_id,
            title,
            level,
        )
        return True

    def platform_hints(self) -> dict[str, Any]:
        """返回企业微信平台特性提示."""
        return {
            "max_text_length": 2048,
            "supports_markdown": True,
            "supports_card": True,
            "supports_buttons": False,
        }
