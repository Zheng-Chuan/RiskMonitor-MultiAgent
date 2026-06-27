"""多平台网关集成测试.

注意: Slack 和企业微信适配器已于 2026-06-27 移除.
      以下仅保留网关核心路由契约测试 (使用 mock 适配器).
      原平台消息收发集成测试已移除, 后续新平台适配器需配套新增测试.
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
    GatewayAdapter,
    GatewayMessage,
    GatewayRouter,
)

# [REMOVED - 2026-06-27] Slack 和企业微信适配器已删除
# from riskmonitor_multiagent.gateway.slack_adapter import SlackAdapter
# from riskmonitor_multiagent.gateway.wechat_work_adapter import WeChatWorkAdapter


class _FakeAdapter(GatewayAdapter):
    """用于集成测试的 fake 适配器."""

    def __init__(self, platform: str = "fake", max_len: int = 2048) -> None:
        self._platform = platform
        self._max_len = max_len
        self._sent_messages: list[tuple[GatewayMessage, dict]] = []
        self._sent_alerts: list[dict] = []

    @property
    def platform_name(self) -> str:
        return self._platform

    async def receive_message(self, raw_input: dict) -> GatewayMessage:
        return GatewayMessage(
            platform=self.platform_name,
            content=str(raw_input.get("content", "")),
            user_id=str(raw_input.get("from_user")) if raw_input.get("from_user") else None,
            channel_id=str(raw_input.get("chat_id")) if raw_input.get("chat_id") else None,
            message_type=str(raw_input.get("message_type", "user_task")),
        )

    async def send_response(self, message: GatewayMessage, response: dict) -> bool:
        self._sent_messages.append((message, response))
        return True

    async def send_alert(self, alert: dict, channel_id: str | None = None) -> bool:
        self._sent_alerts.append(alert)
        return True

    def platform_hints(self) -> dict:
        return {"max_text_length": self._max_len}


def _build_router() -> GatewayRouter:
    """构造注册了 fake 适配器的路由器."""
    router = GatewayRouter()
    router.register_adapter(_FakeAdapter("test_a", max_len=2048))
    router.register_adapter(_FakeAdapter("test_b", max_len=40000))
    return router


async def _mock_execute(
    *,
    entry_type: str,
    message: GatewayMessage,
) -> dict[str, Any]:
    """模拟统一执行内核."""
    return {
        "status": "completed",
        "entry_type": entry_type,
        "task_id": message.message_id,
        "text": f"已处理来自 {message.platform} 的请求: {message.content[:50]}",
        "raw_content": message.content,
    }


# ---------------------------------------------------------------------------
# 1. 消息 → 路由 → 执行 → 响应格式适配
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_flow() -> None:
    """消息完整流程: 接收 → 路由 → 执行 → 格式化 → 发送."""
    router = _build_router()

    raw = {
        "content": "请分析订单系统延迟异常",
        "from_user": "zhangsan",
        "chat_id": "group_dev",
    }

    # 路由消息
    route_result = await router.route_message(raw, platform="test_a")
    assert route_result["entry_type"] == "user_task"
    assert "error" not in route_result

    message: GatewayMessage = route_result["message"]
    assert message.platform == "test_a"
    assert message.content == "请分析订单系统延迟异常"

    # 模拟执行内核
    exec_result = await _mock_execute(
        entry_type=route_result["entry_type"],
        message=message,
    )
    assert exec_result["status"] == "completed"

    # 格式化响应
    formatted = await router.format_response("test_a", exec_result)
    assert formatted["platform"] == "test_a"
    assert "platform_hints" in formatted

    # 发送响应
    adapter = route_result["adapter"]
    sent = await adapter.send_response(message, formatted)
    assert sent is True


# ---------------------------------------------------------------------------
# 2. 告警推送
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_push() -> None:
    """告警推送到适配器."""
    router = _build_router()

    alert = {
        "title": "CPU 使用率告警",
        "description": "server-01 CPU 使用率持续 5 分钟超过 90%",
        "level": "high",
        "source": "prometheus",
    }

    adapter = router.get_adapter("test_a")
    assert adapter is not None
    result = await adapter.send_alert(alert, channel_id="alert_group")
    assert result is True


# ---------------------------------------------------------------------------
# 3. 跨平台一致性验证
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_platform_same_request_same_result() -> None:
    """不同平台的同一请求产生相同的执行结果.

    验证多Agent架构不变量: 网关只是入口适配, 不改变执行内核.
    """
    router = _build_router()

    raw_a = {"content": "检查数据库连接池状态", "from_user": "user_a"}
    raw_b = {"content": "检查数据库连接池状态", "from_user": "user_b"}

    route_a = await router.route_message(raw_a, platform="test_a")
    route_b = await router.route_message(raw_b, platform="test_b")

    assert route_a["entry_type"] == route_b["entry_type"]

    exec_a = await _mock_execute(
        entry_type=route_a["entry_type"],
        message=route_a["message"],
    )
    exec_b = await _mock_execute(
        entry_type=route_b["entry_type"],
        message=route_b["message"],
    )

    assert exec_a["status"] == exec_b["status"]
    assert exec_a["entry_type"] == exec_b["entry_type"]
    assert exec_a["raw_content"] == exec_b["raw_content"]


@pytest.mark.asyncio
async def test_alert_message_routes_to_system_event() -> None:
    """告警类型消息路由到 system_event 入口."""
    router = _build_router()

    alert_raw = {
        "content": "内存告警: > 95%",
        "from_user": "monitor_system",
        "message_type": "alert",
    }

    result = await router.route_message(alert_raw, platform="test_a")
    assert result["entry_type"] == "system_event"
    assert result["message"].message_type == "alert"


@pytest.mark.asyncio
async def test_long_response_truncated() -> None:
    """响应超长时被截断."""
    router = _build_router()

    long_text = "X" * 5000
    exec_result = {"text": long_text, "status": "completed"}

    # test_a 限制 2048
    formatted_a = await router.format_response("test_a", exec_result)
    assert formatted_a.get("truncated") is True
    assert len(formatted_a["text"]) == 2048

    # test_b 限制 40000, 不截断
    formatted_b = await router.format_response("test_b", exec_result)
    assert formatted_b.get("truncated") is not True
    assert formatted_b["text"] == long_text
