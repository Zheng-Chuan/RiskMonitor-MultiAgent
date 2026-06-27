"""Slack 网关适配器."""

from __future__ import annotations

from typing import Any

from riskmonitor_multiagent.gateway.adapter import GatewayAdapter, GatewayMessage


class SlackAdapter(GatewayAdapter):
    """把 Slack 原始事件转换为统一 GatewayMessage."""

    @property
    def platform_name(self) -> str:
        return "slack"

    async def receive_message(self, raw_input: dict[str, Any]) -> GatewayMessage:
        event = raw_input.get("event") if isinstance(raw_input.get("event"), dict) else {}
        raw_type = str(raw_input.get("type") or "message").strip().lower()
        message_type = raw_type if raw_type in {"alert", "approval", "query", "status", "system_event"} else "user_task"
        ts = str(event.get("ts") or "").strip()
        return GatewayMessage(
            message_id=f"gw_slack_{ts.replace('.', '_')}" if ts else "",
            platform=self.platform_name,
            message_type=message_type,
            content=str(event.get("text") or raw_input.get("text") or "").strip(),
            user_id=str(event.get("user") or raw_input.get("user") or "").strip() or None,
            channel_id=str(event.get("channel") or raw_input.get("channel") or "").strip() or None,
            metadata={"raw_input": dict(raw_input)},
            reply_to=ts or None,
        )

    async def send_response(self, message: GatewayMessage, response: dict[str, Any]) -> bool:
        _ = (message, response)
        return True

    async def send_alert(self, alert: dict[str, Any], channel_id: str | None = None) -> bool:
        _ = (alert, channel_id)
        return True

    def platform_hints(self) -> dict[str, Any]:
        return {
            "max_text_length": 40000,
            "supports_markdown": True,
            "supports_rich_text": True,
            "supports_buttons": True,
        }


__all__ = ["SlackAdapter"]
