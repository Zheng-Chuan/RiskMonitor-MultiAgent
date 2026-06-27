"""企业微信网关适配器."""

from __future__ import annotations

from typing import Any

from riskmonitor_multiagent.gateway.adapter import GatewayAdapter, GatewayMessage


class WeChatWorkAdapter(GatewayAdapter):
    """把企业微信原始消息转换为统一 GatewayMessage."""

    @property
    def platform_name(self) -> str:
        return "wechat_work"

    async def receive_message(self, raw_input: dict[str, Any]) -> GatewayMessage:
        raw_type = str(raw_input.get("msg_type") or "text").strip().lower()
        message_type = raw_type if raw_type in {"alert", "approval", "query", "status", "system_event"} else "user_task"
        return GatewayMessage(
            message_id=str(raw_input.get("msg_id") or "").strip(),
            platform=self.platform_name,
            message_type=message_type,
            content=str(raw_input.get("content") or "").strip(),
            user_id=str(raw_input.get("from_user") or "").strip() or None,
            channel_id=str(raw_input.get("chat_id") or "").strip() or None,
            metadata={"raw_input": dict(raw_input)},
            reply_to=str(raw_input.get("msg_id") or "").strip() or None,
        )

    async def send_response(self, message: GatewayMessage, response: dict[str, Any]) -> bool:
        _ = (message, response)
        return True

    async def send_alert(self, alert: dict[str, Any], channel_id: str | None = None) -> bool:
        _ = (alert, channel_id)
        return True

    def platform_hints(self) -> dict[str, Any]:
        return {
            "max_text_length": 4096,
            "supports_markdown": True,
            "supports_rich_text": True,
            "supports_buttons": True,
        }


__all__ = ["WeChatWorkAdapter"]
