"""
多平台网关适配器抽象基类.

为不同平台（企业微信、Slack 等）提供统一的消息收发接口.
新增平台只需实现 GatewayAdapter 即可接入统一执行内核.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GatewayMessage:
    """统一消息格式.

    所有平台的消息在进入执行内核前都会被转换为 GatewayMessage,
    确保内核逻辑与平台无关.

    Attributes:
        message_id: 消息唯一 ID, 格式为 "gw_" + uuid.
        platform: 来源平台, 如 "wechat_work" | "slack" | "mcp" | "api".
        message_type: 消息类型, 如 "user_task" | "alert" | "approval" | "query" | "status".
        content: 消息文本内容.
        user_id: 发送者 ID.
        channel_id: 频道 ID.
        timestamp: 毫秒时间戳.
        metadata: 平台特定元数据.
        reply_to: 回复目标消息 ID.
    """

    message_id: str = ""
    platform: str = ""
    message_type: str = "user_task"
    content: str = ""
    user_id: str | None = None
    channel_id: str | None = None
    timestamp: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    reply_to: str | None = None

    def __post_init__(self) -> None:
        if not self.message_id:
            self.message_id = f"gw_{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = int(time.time() * 1000)


class GatewayAdapter(ABC):
    """网关适配器抽象基类.

    每个具体平台需实现此接口以接入统一路由.
    适配器只负责消息格式转换和平台特性适配, 不改变执行内核逻辑.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """返回平台名称, 如 "wechat_work"、"slack"."""

    @abstractmethod
    async def receive_message(self, raw_input: dict[str, Any]) -> GatewayMessage:
        """将平台原始消息转为统一 GatewayMessage.

        Args:
            raw_input: 平台特定的原始消息字典.

        Returns:
            统一格式的 GatewayMessage.
        """

    @abstractmethod
    async def send_response(self, message: GatewayMessage, response: dict[str, Any]) -> bool:
        """向平台发送响应.

        Args:
            message: 原始 GatewayMessage（含回复目标信息）.
            response: 响应内容字典.

        Returns:
            发送是否成功.
        """

    @abstractmethod
    async def send_alert(self, alert: dict[str, Any], channel_id: str | None = None) -> bool:
        """向平台推送告警.

        Args:
            alert: 告警内容字典.
            channel_id: 目标频道 ID, 为 None 时使用默认频道.

        Returns:
            推送是否成功.
        """

    @abstractmethod
    def platform_hints(self) -> dict[str, Any]:
        """返回平台特性提示.

        包含消息长度限制、是否支持富文本、卡片、按钮等.

        Returns:
            平台特性字典.
        """
