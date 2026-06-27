"""
多平台网关模块.

提供统一的消息收发接口.
新增平台只需实现 GatewayAdapter 即可.

注意: Slack 和企业微信适配器已移除 (2026-06-27).
      核心抽象层 GatewayAdapter / GatewayMessage / GatewayRouter 保留,
      后续可按需实现新的平台适配器.
"""

from __future__ import annotations

from riskmonitor_multiagent.gateway.adapter import GatewayAdapter, GatewayMessage
from riskmonitor_multiagent.gateway.router import GatewayRouter

# [DEPRECATED - 2026-06-27] Slack 和企业微信适配器已移除
# from riskmonitor_multiagent.gateway.slack_adapter import SlackAdapter
# from riskmonitor_multiagent.gateway.wechat_work_adapter import WeChatWorkAdapter

__all__ = [
    "GatewayAdapter",
    "GatewayMessage",
    "GatewayRouter",
]
