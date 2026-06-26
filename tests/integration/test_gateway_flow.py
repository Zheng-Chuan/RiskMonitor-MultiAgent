"""多平台网关集成测试.

验证从平台消息接收到响应格式适配的完整流程,
以及告警推送到多平台的能力.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.gateway import (
    GatewayMessage,
    GatewayRouter,
    SlackAdapter,
    WeChatWorkAdapter,
)


def _build_router() -> GatewayRouter:
    """构造注册了所有平台适配器的路由器."""
    router = GatewayRouter()
    router.register_adapter(WeChatWorkAdapter())
    router.register_adapter(SlackAdapter())
    return router


async def _mock_execute(
    *,
    entry_type: str,
    message: GatewayMessage,
) -> dict[str, Any]:
    """模拟统一执行内核.

    实际项目中此处会调用 ProactiveMultiAgentWorkflow.run() 或 start_from_event().
    此处使用 mock 确保测试不依赖 LLM/数据库等外部资源.
    """
    return {
        "status": "completed",
        "entry_type": entry_type,
        "task_id": message.message_id,
        "text": f"已处理来自 {message.platform} 的请求: {message.content[:50]}",
        "raw_content": message.content,
    }


# ---------------------------------------------------------------------------
# 1. 企业微信消息 → 路由 → 执行 → 响应格式适配
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wechat_work_full_flow() -> None:
    """企业微信消息完整流程: 接收 → 路由 → 执行 → 格式化 → 发送."""
    router = _build_router()

    # 1. 模拟企业微信回调
    wechat_raw = {
        "msg_type": "text",
        "content": "请分析订单系统延迟异常",
        "from_user": "zhangsan",
        "chat_id": "group_dev",
        "agent_id": "1000002",
        "msg_id": "msg_001",
    }

    # 2. 路由消息
    route_result = await router.route_message(wechat_raw, platform="wechat_work")
    assert route_result["entry_type"] == "user_task"
    assert "error" not in route_result

    message: GatewayMessage = route_result["message"]
    assert message.platform == "wechat_work"
    assert message.content == "请分析订单系统延迟异常"
    assert message.user_id == "zhangsan"

    # 3. 模拟执行内核
    exec_result = await _mock_execute(
        entry_type=route_result["entry_type"],
        message=message,
    )
    assert exec_result["status"] == "completed"

    # 4. 格式化响应（适配企业微信限制）
    formatted = await router.format_response("wechat_work", exec_result)
    assert formatted["platform"] == "wechat_work"
    assert "platform_hints" in formatted
    assert len(formatted["text"]) <= 2048

    # 5. 发送响应
    adapter = route_result["adapter"]
    sent = await adapter.send_response(message, formatted)
    assert sent is True


# ---------------------------------------------------------------------------
# 2. Slack 消息 → 路由 → 执行 → 响应格式适配
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_full_flow() -> None:
    """Slack 消息完整流程: 接收 → 路由 → 执行 → 格式化 → 发送."""
    router = _build_router()

    # 1. 模拟 Slack Events API 回调
    slack_raw = {
        "type": "message",
        "event": {
            "text": "analyze payment gateway timeout",
            "user": "U12345",
            "channel": "C_devops",
            "ts": "1700000000.500000",
        },
        "team_id": "T00001",
    }

    # 2. 路由消息
    route_result = await router.route_message(slack_raw, platform="slack")
    assert route_result["entry_type"] == "user_task"

    message: GatewayMessage = route_result["message"]
    assert message.platform == "slack"
    assert message.content == "analyze payment gateway timeout"
    assert message.user_id == "U12345"
    assert message.channel_id == "C_devops"
    assert message.timestamp == 1700000000500

    # 3. 模拟执行内核
    exec_result = await _mock_execute(
        entry_type=route_result["entry_type"],
        message=message,
    )
    assert exec_result["status"] == "completed"

    # 4. 格式化响应
    formatted = await router.format_response("slack", exec_result)
    assert formatted["platform"] == "slack"
    assert "platform_hints" in formatted

    # 5. 发送响应
    adapter = route_result["adapter"]
    sent = await adapter.send_response(message, formatted)
    assert sent is True


# ---------------------------------------------------------------------------
# 3. 告警推送到两个平台
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_push_to_both_platforms() -> None:
    """告警同时推送到企业微信和 Slack 两个平台."""
    router = _build_router()

    alert = {
        "title": "CPU 使用率告警",
        "description": "server-01 CPU 使用率持续 5 分钟超过 90%",
        "level": "high",
        "source": "prometheus",
        "timestamp": "2026-06-26T10:00:00Z",
    }

    # 推送到企业微信
    wechat_adapter = router.get_adapter("wechat_work")
    assert wechat_adapter is not None
    wechat_result = await wechat_adapter.send_alert(alert, channel_id="wechat_alert_group")
    assert wechat_result is True

    # 推送到 Slack
    slack_adapter = router.get_adapter("slack")
    assert slack_adapter is not None
    slack_result = await slack_adapter.send_alert(alert, channel_id="slack_alert_channel")
    assert slack_result is True

    # 两平台都应推送成功
    assert wechat_result and slack_result


# ---------------------------------------------------------------------------
# 额外: 跨平台一致性验证
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_platform_same_request_same_result() -> None:
    """不同平台的同一请求产生相同的执行结果.

    验证多Agent架构不变量: 网关只是入口适配, 不改变执行内核.
    """
    router = _build_router()

    wechat_raw = {
        "msg_type": "text",
        "content": "检查数据库连接池状态",
        "from_user": "user_a",
    }
    slack_raw = {
        "type": "message",
        "event": {
            "text": "检查数据库连接池状态",
            "user": "U_user_a",
            "channel": "C_test",
            "ts": "1700000000.000000",
        },
    }

    wechat_route = await router.route_message(wechat_raw, platform="wechat_work")
    slack_route = await router.route_message(slack_raw, platform="slack")

    # 两个平台的路由入口应相同
    assert wechat_route["entry_type"] == slack_route["entry_type"]

    # 执行内核结果应相同（内容一致）
    wechat_exec = await _mock_execute(
        entry_type=wechat_route["entry_type"],
        message=wechat_route["message"],
    )
    slack_exec = await _mock_execute(
        entry_type=slack_route["entry_type"],
        message=slack_route["message"],
    )

    assert wechat_exec["status"] == slack_exec["status"]
    assert wechat_exec["entry_type"] == slack_exec["entry_type"]
    assert wechat_exec["raw_content"] == slack_exec["raw_content"]


@pytest.mark.asyncio
async def test_alert_message_routes_to_system_event() -> None:
    """告警类型消息从两个平台都路由到 system_event 入口."""
    router = _build_router()

    wechat_alert_raw = {
        "msg_type": "text",
        "content": "内存告警: > 95%",
        "from_user": "monitor_system",
        "message_type": "alert",
    }
    slack_alert_raw = {
        "type": "message",
        "event": {
            "text": "内存告警: > 95%",
            "user": "U_monitor",
            "channel": "C_alerts",
        },
        "message_type": "alert",
    }

    wechat_result = await router.route_message(wechat_alert_raw, platform="wechat_work")
    slack_result = await router.route_message(slack_alert_raw, platform="slack")

    assert wechat_result["entry_type"] == "system_event"
    assert slack_result["entry_type"] == "system_event"
    assert wechat_result["message"].message_type == "alert"
    assert slack_result["message"].message_type == "alert"


@pytest.mark.asyncio
async def test_long_response_truncated_for_wechat_not_slack() -> None:
    """同一长响应在企业微信被截断, 在 Slack 不被截断."""
    router = _build_router()

    long_text = "X" * 5000
    exec_result = {"text": long_text, "status": "completed"}

    wechat_formatted = await router.format_response("wechat_work", exec_result)
    slack_formatted = await router.format_response("slack", exec_result)

    # 企业微信截断到 2048
    assert wechat_formatted.get("truncated") is True
    assert len(wechat_formatted["text"]) == 2048

    # Slack 不截断 (5000 < 40000)
    assert slack_formatted.get("truncated") is not True
    assert slack_formatted["text"] == long_text
