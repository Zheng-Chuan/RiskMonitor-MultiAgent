"""多平台网关单元测试.

注意: Slack 和企业微信适配器已于 2026-06-27 移除.
      以下仅保留 GatewayAdapter / GatewayMessage / GatewayRouter 核心契约测试.
      适配器相关测试已注释移除, 后续新平台适配器需配套新增测试.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from riskmonitor_multiagent.gateway import (
    GatewayAdapter,
    GatewayMessage,
    GatewayRouter,
)

# [REMOVED - 2026-06-27] Slack 和企业微信适配器已删除
# from riskmonitor_multiagent.gateway.slack_adapter import SlackAdapter
# from riskmonitor_multiagent.gateway.wechat_work_adapter import WeChatWorkAdapter


# ---------------------------------------------------------------------------
# 1. GatewayMessage 构造和字段验证
# ---------------------------------------------------------------------------


class TestGatewayMessage:
    """GatewayMessage 数据类测试."""

    def test_default_fields_auto_generated(self) -> None:
        """不传参时 message_id 和 timestamp 自动生成."""
        msg = GatewayMessage(platform="test_platform")
        assert msg.message_id.startswith("gw_")
        assert len(msg.message_id) > 3
        assert msg.timestamp > 0
        assert msg.message_type == "user_task"
        assert msg.content == ""
        assert msg.user_id is None
        assert msg.channel_id is None
        assert msg.metadata == {}
        assert msg.reply_to is None

    def test_explicit_fields_preserved(self) -> None:
        """显式传参时字段值被保留."""
        msg = GatewayMessage(
            message_id="gw_custom_001",
            platform="test_platform",
            message_type="alert",
            content="系统异常",
            user_id="user_001",
            channel_id="ch_001",
            timestamp=1700000000000,
            metadata={"agent_id": "1000002"},
            reply_to="gw_orig_001",
        )
        assert msg.message_id == "gw_custom_001"
        assert msg.platform == "test_platform"
        assert msg.message_type == "alert"
        assert msg.content == "系统异常"
        assert msg.user_id == "user_001"
        assert msg.channel_id == "ch_001"
        assert msg.timestamp == 1700000000000
        assert msg.metadata == {"agent_id": "1000002"}
        assert msg.reply_to == "gw_orig_001"

    def test_message_id_uniqueness(self) -> None:
        """连续构造的两个消息 ID 不同."""
        msg1 = GatewayMessage(platform="test_platform")
        msg2 = GatewayMessage(platform="test_platform")
        assert msg1.message_id != msg2.message_id


# ---------------------------------------------------------------------------
# [REMOVED - 2026-06-27] 适配器 receive_message 测试
# 以下测试类依赖已删除的 SlackAdapter / WeChatWorkAdapter, 已移除:
#   - TestWeChatWorkAdapterReceive
#   - TestSlackAdapterReceive
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# [REMOVED - 2026-06-27] send_response / send_alert 测试
# 以下测试类依赖已删除的 SlackAdapter / WeChatWorkAdapter, 已移除:
#   - TestSendResponseAndAlert
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# [REMOVED - 2026-06-27] platform_hints 测试
# 以下测试类依赖已删除的 SlackAdapter / WeChatWorkAdapter, 已移除:
#   - TestPlatformHints
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 7. GatewayRouter 注册和获取适配器 (核心契约测试, 使用 mock 适配器)
# ---------------------------------------------------------------------------


class _FakeAdapter(GatewayAdapter):
    """用于测试的 fake 适配器."""

    def __init__(self, platform: str = "fake") -> None:
        self._platform = platform

    @property
    def platform_name(self) -> str:
        return self._platform

    async def receive_message(self, raw_input: dict) -> GatewayMessage:
        return GatewayMessage(
            platform=self.platform_name,
            content=str(raw_input.get("content", "")),
        )

    async def send_response(self, message: GatewayMessage, response: dict) -> bool:
        return True

    async def send_alert(self, alert: dict, channel_id: str | None = None) -> bool:
        return True

    def platform_hints(self) -> dict:
        return {"max_text_length": 1024}


class TestGatewayRouterRegister:
    """GatewayRouter 注册和获取适配器测试."""

    def test_register_and_get_adapter(self) -> None:
        router = GatewayRouter()
        fake = _FakeAdapter("fake")
        router.register_adapter(fake)
        assert router.get_adapter("fake") is fake

    def test_get_unregistered_platform_returns_none(self) -> None:
        router = GatewayRouter()
        assert router.get_adapter("nonexistent") is None

    def test_register_overwrites_same_platform(self) -> None:
        router = GatewayRouter()
        adapter1 = _FakeAdapter("fake")
        adapter2 = _FakeAdapter("fake")
        router.register_adapter(adapter1)
        router.register_adapter(adapter2)
        assert router.get_adapter("fake") is adapter2


# ---------------------------------------------------------------------------
# 8 & 9. route_message 路由决策 (核心契约测试)
# ---------------------------------------------------------------------------


class TestGatewayRouterRoute:
    """GatewayRouter route_message 测试."""

    @pytest.mark.asyncio
    async def test_route_user_task(self) -> None:
        """user_task 消息类型路由到 user_task 入口."""
        router = GatewayRouter()
        router.register_adapter(_FakeAdapter("test"))
        raw = {"content": "分析风险"}
        result = await router.route_message(raw, platform="test")
        assert result["entry_type"] == "user_task"
        assert result["platform"] == "test"
        assert isinstance(result["message"], GatewayMessage)
        assert result["adapter"] is not None

    @pytest.mark.asyncio
    async def test_route_alert_to_system_event(self) -> None:
        """alert 消息类型路由到 system_event 入口."""
        router = GatewayRouter()
        router.register_adapter(_FakeAdapter("test"))
        raw = {"content": "告警: CPU > 90%", "message_type": "alert"}
        result = await router.route_message(raw, platform="test")
        assert result["entry_type"] == "system_event"
        assert result["message"].message_type == "alert"

    @pytest.mark.asyncio
    async def test_route_approval_to_system_event(self) -> None:
        """approval 消息类型路由到 system_event 入口."""
        router = GatewayRouter()
        router.register_adapter(_FakeAdapter("test"))
        raw = {"content": "approve", "message_type": "approval"}
        result = await router.route_message(raw, platform="test")
        assert result["entry_type"] == "system_event"

    @pytest.mark.asyncio
    async def test_route_status_to_system_event(self) -> None:
        """status 消息类型路由到 system_event 入口."""
        router = GatewayRouter()
        router.register_adapter(_FakeAdapter("test"))
        raw = {"content": "status?", "message_type": "status"}
        result = await router.route_message(raw, platform="test")
        assert result["entry_type"] == "system_event"

    @pytest.mark.asyncio
    async def test_route_explicit_system_event_to_system_event(self) -> None:
        """显式 system_event 类型也路由到 system_event 入口."""
        router = GatewayRouter()
        router.register_adapter(_FakeAdapter("test"))
        raw = {"content": "收到平台回调事件", "message_type": "system_event"}
        result = await router.route_message(raw, platform="test")
        assert result["entry_type"] == "system_event"
        assert result["message"].message_type == "system_event"

    @pytest.mark.asyncio
    async def test_route_unregistered_platform(self) -> None:
        """未注册平台返回错误."""
        router = GatewayRouter()
        result = await router.route_message({"content": "test"}, platform="unknown")
        assert result["entry_type"] is None
        assert "error" in result
        assert "platform_not_registered" in result["error"]

    @pytest.mark.asyncio
    async def test_route_and_execute_user_task_uses_executor(self) -> None:
        """route_and_execute 会把 user_task 交给统一执行器."""
        router = GatewayRouter()
        router.register_adapter(_FakeAdapter("test"))
        mock_executor = AsyncMock(return_value={"status": "completed", "kind": "task"})

        result = await router.route_and_execute(
            {"content": "分析风险"},
            platform="test",
            user_task_executor=mock_executor,
        )

        assert result["entry_type"] == "user_task"
        assert result["execution_result"]["kind"] == "task"
        mock_executor.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_route_and_execute_system_event_uses_executor(self) -> None:
        """route_and_execute 会把 system_event 交给事件执行器."""
        router = GatewayRouter()
        router.register_adapter(_FakeAdapter("test"))
        mock_executor = AsyncMock(return_value={"status": "completed", "kind": "event"})

        result = await router.route_and_execute(
            {"content": "CPU 告警", "message_type": "alert"},
            platform="test",
            system_event_executor=mock_executor,
        )

        assert result["entry_type"] == "system_event"
        assert result["execution_result"]["kind"] == "event"
        mock_executor.assert_awaited_once()


# ---------------------------------------------------------------------------
# 10. format_response 根据 platform_hints 截断 (核心契约测试)
# ---------------------------------------------------------------------------


class TestGatewayRouterFormatResponse:
    """GatewayRouter format_response 测试."""

    @pytest.mark.asyncio
    async def test_format_response_truncation(self) -> None:
        """响应超长时被截断."""
        router = GatewayRouter()
        router.register_adapter(_FakeAdapter("test"))
        long_text = "A" * 2000
        result = await router.format_response("test", {"text": long_text})
        assert result["truncated"] is True
        assert result["original_length"] == 2000
        assert len(result["text"]) == 1024

    @pytest.mark.asyncio
    async def test_format_response_no_truncation(self) -> None:
        """短文本不触发截断."""
        router = GatewayRouter()
        router.register_adapter(_FakeAdapter("test"))
        text = "B" * 500
        result = await router.format_response("test", {"text": text})
        assert result.get("truncated") is not True
        assert result["text"] == text

    @pytest.mark.asyncio
    async def test_format_response_adds_platform_hints(self) -> None:
        """格式化后的响应包含平台特性提示."""
        router = GatewayRouter()
        router.register_adapter(_FakeAdapter("test"))
        result = await router.format_response("test", {"text": "ok"})
        assert result["platform"] == "test"
        assert "platform_hints" in result
        assert result["platform_hints"]["max_text_length"] == 1024

    @pytest.mark.asyncio
    async def test_format_response_unregistered_platform(self) -> None:
        """未注册平台返回原始响应."""
        router = GatewayRouter()
        result = await router.format_response("unknown", {"text": "hello"})
        assert result == {"text": "hello"}

    @pytest.mark.asyncio
    async def test_format_response_content_key_truncation(self) -> None:
        """使用 content 键的响应也被正确截断."""
        router = GatewayRouter()
        router.register_adapter(_FakeAdapter("test"))
        long_text = "D" * 2000
        result = await router.format_response("test", {"content": long_text})
        assert result["truncated"] is True
        assert len(result["content"]) == 1024


# ---------------------------------------------------------------------------
# 额外: GatewayAdapter 抽象基类不可实例化
# ---------------------------------------------------------------------------


def test_gateway_adapter_is_abstract() -> None:
    """GatewayAdapter 是抽象基类, 不能直接实例化."""
    with pytest.raises(TypeError):
        GatewayAdapter()  # type: ignore[abstract]
