"""Slack 适配器.

将 Slack Events API 消息转为统一 GatewayMessage, 并提供告警推送能力.
当前为 mock 实现, 不真正调用 Slack API.
"""

from __future__ import annotations

import logging
from typing import Any

from riskmonitor_multiagent.gateway.adapter import GatewayAdapter, GatewayMessage

logger = logging.getLogger(__name__)

# Slack 消息类型映射
_SLACK_MSG_TYPE_MAP: dict[str, str] = {
    "message": "user_task",
    "app_mention": "user_task",
    "alert": "alert",
    "approval": "approval",
    "query": "query",
    "status": "status",
}


class SlackAdapter(GatewayAdapter):
    """Slack 适配器.

    解析 Slack Events API 消息格式, 将其转换为统一 GatewayMessage.
    支持文本消息收发和 Block Kit 告警推送.
    """

    @property
    def platform_name(self) -> str:
        return "slack"

    async def receive_message(self, raw_input: dict[str, Any]) -> GatewayMessage:
        """解析 Slack Events API 消息格式.

        支持的 raw_input 格式:
            - type: 事件类型 (message/app_mention 等)
            - event: 事件数据, 含 text/user/channel/ts/thread_ts 等
            - team_id: Slack 团队 ID
            - api_app_id: 应用 ID
            - message_type: 显式指定统一消息类型 (可选, 优先于 type 映射)

        Args:
            raw_input: Slack Events API 回调消息字典.

        Returns:
            统一格式的 GatewayMessage.
        """
        event_type = str(raw_input.get("type", "message"))
        event_data = raw_input.get("event") if isinstance(raw_input.get("event"), dict) else {}
        content = str(event_data.get("text", ""))
        user_id = event_data.get("user")
        channel_id = event_data.get("channel")
        ts = event_data.get("ts")
        thread_ts = event_data.get("thread_ts")
        team_id = raw_input.get("team_id")
        api_app_id = raw_input.get("api_app_id")

        # 显式 message_type 优先, 否则从 event type 映射
        explicit_type = raw_input.get("message_type") or event_data.get("message_type")
        if isinstance(explicit_type, str) and explicit_type:
            message_type = explicit_type
        else:
            message_type = _SLACK_MSG_TYPE_MAP.get(event_type, "user_task")

        # 解析 Slack 时间戳为毫秒时间戳
        timestamp = 0
        if ts:
            try:
                timestamp = int(float(ts) * 1000)
            except (ValueError, TypeError):
                timestamp = 0

        metadata: dict[str, Any] = {"slack_event_type": event_type}
        if team_id:
            metadata["team_id"] = team_id
        if api_app_id:
            metadata["api_app_id"] = api_app_id
        if ts:
            metadata["ts"] = ts

        return GatewayMessage(
            platform=self.platform_name,
            message_type=message_type,
            content=content,
            user_id=str(user_id) if user_id is not None else None,
            channel_id=str(channel_id) if channel_id is not None else None,
            timestamp=timestamp,
            metadata=metadata,
            reply_to=str(thread_ts) if thread_ts else None,
        )

    async def send_response(self, message: GatewayMessage, response: dict[str, Any]) -> bool:
        """发送响应.

        Slack 限制 40000 字符, 超出部分将被截断.

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
                "Slack response truncated to %d chars for message %s",
                max_len,
                message.message_id,
            )
        logger.info(
            "Slack send_response: user=%s, channel=%s, text_len=%d",
            message.user_id,
            message.channel_id,
            len(text),
        )
        return True

    async def send_alert(self, alert: dict[str, Any], channel_id: str | None = None) -> bool:
        """推送告警 Block Kit 消息.

        将告警内容封装为 Slack Block Kit 格式并推送.

        Args:
            alert: 告警内容字典, 包含 title、description、level 等字段.
            channel_id: 目标频道 ID, 为 None 时使用默认频道.

        Returns:
            是否推送成功.
        """
        title = str(alert.get("title", "Risk Alert"))
        description = str(alert.get("description", ""))
        level = str(alert.get("level", "normal"))
        logger.info(
            "Slack send_alert: channel=%s, title=%s, level=%s",
            channel_id,
            title,
            level,
        )
        return True

    def platform_hints(self) -> dict[str, Any]:
        """返回 Slack 平台特性提示."""
        return {
            "max_text_length": 40000,
            "supports_markdown": True,
            "supports_card": True,
            "supports_buttons": True,
        }
