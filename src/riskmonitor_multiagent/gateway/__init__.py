"""
多平台网关模块.

提供统一的消息收发接口, 支持企业微信、Slack 等多平台接入.
新增平台只需实现 GatewayAdapter 即可.
"""

from __future__ import annotations

from riskmonitor_multiagent.gateway.adapter import GatewayAdapter, GatewayMessage
from riskmonitor_multiagent.gateway.router import GatewayRouter
from riskmonitor_multiagent.gateway.slack_adapter import SlackAdapter
from riskmonitor_multiagent.gateway.wechat_work_adapter import WeChatWorkAdapter

__all__ = [
    "GatewayAdapter",
    "GatewayMessage",
    "GatewayRouter",
    "SlackAdapter",
    "WeChatWorkAdapter",
]
