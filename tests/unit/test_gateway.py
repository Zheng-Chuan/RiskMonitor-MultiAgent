"""多平台网关单元测试."""

from __future__ import annotations

import pytest

from riskmonitor_multiagent.gateway import (
    GatewayAdapter,
    GatewayMessage,
    GatewayRouter,
    SlackAdapter,
    WeChatWorkAdapter,
)


# ---------------------------------------------------------------------------
# 1. GatewayMessage 构造和字段验证
# ---------------------------------------------------------------------------


class TestGatewayMessage:
    """GatewayMessage 数据类测试."""

    def test_default_fields_auto_generated(self) -> None:
        """不传参时 message_id 和 timestamp 自动生成."""
        msg = GatewayMessage(platform="slack")
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
            platform="wechat_work",
            message_type="alert",
            content="系统异常",
            user_id="user_001",
            channel_id="ch_001",
            timestamp=1700000000000,
            metadata={"agent_id": "1000002"},
            reply_to="gw_orig_001",
        )
        assert msg.message_id == "gw_custom_001"
        assert msg.platform == "wechat_work"
        assert msg.message_type == "alert"
        assert msg.content == "系统异常"
        assert msg.user_id == "user_001"
        assert msg.channel_id == "ch_001"
        assert msg.timestamp == 1700000000000
        assert msg.metadata == {"agent_id": "1000002"}
        assert msg.reply_to == "gw_orig_001"

    def test_message_id_uniqueness(self) -> None:
        """连续构造的两个消息 ID 不同."""
        msg1 = GatewayMessage(platform="slack")
        msg2 = GatewayMessage(platform="slack")
        assert msg1.message_id != msg2.message_id


# ---------------------------------------------------------------------------
# 2 & 3. 适配器 receive_message → GatewayMessage 正确转换
# ---------------------------------------------------------------------------


class TestWeChatWorkAdapterReceive:
    """企业微信适配器 receive_message 测试."""

    @pytest.mark.asyncio
    async def test_receive_text_message(self) -> None:
        """文本消息正确转换为 GatewayMessage."""
        adapter = WeChatWorkAdapter()
        raw = {
            "msg_type": "text",
            "content": "请检查系统状态",
            "from_user": "zhangsan",
            "chat_id": "group_001",
            "agent_id": "1000002",
            "msg_id": "msg_abc123",
        }
        msg = await adapter.receive_message(raw)
        assert msg.platform == "wechat_work"
        assert msg.message_type == "user_task"
        assert msg.content == "请检查系统状态"
        assert msg.user_id == "zhangsan"
        assert msg.channel_id == "group_001"
        assert msg.metadata.get("agent_id") == "1000002"
        assert msg.metadata.get("wechat_msg_type") == "text"
        assert msg.reply_to == "msg_abc123"
        assert msg.timestamp > 0

    @pytest.mark.asyncio
    async def test_receive_explicit_message_type(self) -> None:
        """显式 message_type 优先于 msg_type 映射."""
        adapter = WeChatWorkAdapter()
        raw = {
            "msg_type": "text",
            "content": "告警确认",
            "from_user": "lisi",
            "message_type": "approval",
        }
        msg = await adapter.receive_message(raw)
        assert msg.message_type == "approval"

    @pytest.mark.asyncio
    async def test_receive_minimal_input(self) -> None:
        """最小输入也能正常转换."""
        adapter = WeChatWorkAdapter()
        raw = {"content": "hello"}
        msg = await adapter.receive_message(raw)
        assert msg.platform == "wechat_work"
        assert msg.content == "hello"
        assert msg.message_type == "user_task"
        assert msg.user_id is None


class TestSlackAdapterReceive:
    """Slack 适配器 receive_message 测试."""

    @pytest.mark.asyncio
    async def test_receive_message_event(self) -> None:
        """Slack message 事件正确转换为 GatewayMessage."""
        adapter = SlackAdapter()
        raw = {
            "type": "message",
            "event": {
                "text": "check system health",
                "user": "U12345",
                "channel": "C67890",
                "ts": "1700000000.123456",
            },
            "team_id": "T00001",
            "api_app_id": "A00001",
        }
        msg = await adapter.receive_message(raw)
        assert msg.platform == "slack"
        assert msg.message_type == "user_task"
        assert msg.content == "check system health"
        assert msg.user_id == "U12345"
        assert msg.channel_id == "C67890"
        assert msg.timestamp == 1700000000123
        assert msg.metadata.get("team_id") == "T00001"
        assert msg.metadata.get("api_app_id") == "A00001"
        assert msg.metadata.get("slack_event_type") == "message"

    @pytest.mark.asyncio
    async def test_receive_app_mention_with_thread(self) -> None:
        """app_mention 事件含 thread_ts 时正确设置 reply_to."""
        adapter = SlackAdapter()
        raw = {
            "type": "app_mention",
            "event": {
                "text": "<@U BOT> analyze risk",
                "user": "U99999",
                "channel": "C11111",
                "ts": "1700000001.000000",
                "thread_ts": "1699999999.000000",
            },
        }
        msg = await adapter.receive_message(raw)
        assert msg.message_type == "user_task"
        assert msg.reply_to == "1699999999.000000"

    @pytest.mark.asyncio
    async def test_receive_explicit_message_type(self) -> None:
        """显式 message_type 优先."""
        adapter = SlackAdapter()
        raw = {
            "type": "message",
            "event": {"text": "status query", "user": "U1", "channel": "C1"},
            "message_type": "status",
        }
        msg = await adapter.receive_message(raw)
        assert msg.message_type == "status"

    @pytest.mark.asyncio
    async def test_receive_invalid_ts_defaults_to_zero(self) -> None:
        """无效时间戳时 timestamp 保持为 0, 由 dataclass 补默认值."""
        adapter = SlackAdapter()
        raw = {
            "type": "message",
            "event": {
                "text": "test",
                "user": "U1",
                "channel": "C1",
                "ts": "not_a_number",
            },
        }
        msg = await adapter.receive_message(raw)
        # 无效 ts 解析为 0, __post_init__ 会补当前时间戳
        assert msg.timestamp > 0


# ---------------------------------------------------------------------------
# 4 & 5. send_response 和 send_alert 返回 True
# ---------------------------------------------------------------------------


class TestSendResponseAndAlert:
    """send_response 和 send_alert 测试."""

    @pytest.mark.asyncio
    async def test_wechat_work_send_response_returns_true(self) -> None:
        adapter = WeChatWorkAdapter()
        msg = GatewayMessage(platform="wechat_work", user_id="u1", channel_id="c1")
        result = await adapter.send_response(msg, {"text": "处理完成"})
        assert result is True

    @pytest.mark.asyncio
    async def test_wechat_work_send_alert_returns_true(self) -> None:
        adapter = WeChatWorkAdapter()
        result = await adapter.send_alert(
            {"title": "CPU 告警", "description": "CPU 超过 90%", "level": "high"},
            channel_id="ch_alert",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_slack_send_response_returns_true(self) -> None:
        adapter = SlackAdapter()
        msg = GatewayMessage(platform="slack", user_id="U1", channel_id="C1")
        result = await adapter.send_response(msg, {"text": "analysis done"})
        assert result is True

    @pytest.mark.asyncio
    async def test_slack_send_alert_returns_true(self) -> None:
        adapter = SlackAdapter()
        result = await adapter.send_alert(
            {"title": "Memory Alert", "description": "Memory > 95%", "level": "critical"},
            channel_id="C_alerts",
        )
        assert result is True


# ---------------------------------------------------------------------------
# 6. platform_hints 返回正确特性
# ---------------------------------------------------------------------------


class TestPlatformHints:
    """platform_hints 测试."""

    def test_wechat_work_hints(self) -> None:
        hints = WeChatWorkAdapter().platform_hints()
        assert hints["max_text_length"] == 2048
        assert hints["supports_markdown"] is True
        assert hints["supports_card"] is True
        assert hints["supports_buttons"] is False

    def test_slack_hints(self) -> None:
        hints = SlackAdapter().platform_hints()
        assert hints["max_text_length"] == 40000
        assert hints["supports_markdown"] is True
        assert hints["supports_card"] is True
        assert hints["supports_buttons"] is True


# ---------------------------------------------------------------------------
# 7. GatewayRouter 注册和获取适配器
# ---------------------------------------------------------------------------


class TestGatewayRouterRegister:
    """GatewayRouter 注册和获取适配器测试."""

    def test_register_and_get_adapter(self) -> None:
        router = GatewayRouter()
        wechat = WeChatWorkAdapter()
        slack = SlackAdapter()
        router.register_adapter(wechat)
        router.register_adapter(slack)

        assert router.get_adapter("wechat_work") is wechat
        assert router.get_adapter("slack") is slack

    def test_get_unregistered_platform_returns_none(self) -> None:
        router = GatewayRouter()
        assert router.get_adapter("nonexistent") is None

    def test_register_overwrites_same_platform(self) -> None:
        router = GatewayRouter()
        adapter1 = WeChatWorkAdapter()
        adapter2 = WeChatWorkAdapter()
        router.register_adapter(adapter1)
        router.register_adapter(adapter2)
        assert router.get_adapter("wechat_work") is adapter2


# ---------------------------------------------------------------------------
# 8 & 9. route_message 路由决策
# ---------------------------------------------------------------------------


class TestGatewayRouterRoute:
    """GatewayRouter route_message 测试."""

    @pytest.mark.asyncio
    async def test_route_user_task(self) -> None:
        """user_task 消息类型路由到 user_task 入口."""
        router = GatewayRouter()
        router.register_adapter(WeChatWorkAdapter())
        raw = {"msg_type": "text", "content": "分析风险", "from_user": "u1"}
        result = await router.route_message(raw, platform="wechat_work")
        assert result["entry_type"] == "user_task"
        assert result["platform"] == "wechat_work"
        assert isinstance(result["message"], GatewayMessage)
        assert result["adapter"] is not None

    @pytest.mark.asyncio
    async def test_route_alert_to_system_event(self) -> None:
        """alert 消息类型路由到 system_event 入口."""
        router = GatewayRouter()
        router.register_adapter(WeChatWorkAdapter())
        raw = {
            "msg_type": "text",
            "content": "告警: CPU > 90%",
            "from_user": "monitor",
            "message_type": "alert",
        }
        result = await router.route_message(raw, platform="wechat_work")
        assert result["entry_type"] == "system_event"
        assert result["message"].message_type == "alert"

    @pytest.mark.asyncio
    async def test_route_approval_to_system_event(self) -> None:
        """approval 消息类型路由到 system_event 入口."""
        router = GatewayRouter()
        router.register_adapter(SlackAdapter())
        raw = {
            "type": "message",
            "event": {"text": "approve", "user": "U1", "channel": "C1"},
            "message_type": "approval",
        }
        result = await router.route_message(raw, platform="slack")
        assert result["entry_type"] == "system_event"

    @pytest.mark.asyncio
    async def test_route_status_to_system_event(self) -> None:
        """status 消息类型路由到 system_event 入口."""
        router = GatewayRouter()
        router.register_adapter(SlackAdapter())
        raw = {
            "type": "message",
            "event": {"text": "status?", "user": "U1", "channel": "C1"},
            "message_type": "status",
        }
        result = await router.route_message(raw, platform="slack")
        assert result["entry_type"] == "system_event"

    @pytest.mark.asyncio
    async def test_route_unregistered_platform(self) -> None:
        """未注册平台返回错误."""
        router = GatewayRouter()
        result = await router.route_message({"content": "test"}, platform="unknown")
        assert result["entry_type"] is None
        assert "error" in result
        assert "platform_not_registered" in result["error"]

    @pytest.mark.asyncio
    async def test_route_same_content_different_platforms_same_entry(self) -> None:
        """不同平台相同请求产生相同路由决策."""
        router = GatewayRouter()
        router.register_adapter(WeChatWorkAdapter())
        router.register_adapter(SlackAdapter())

        wechat_raw = {"msg_type": "text", "content": "分析风险", "from_user": "u1"}
        slack_raw = {
            "type": "message",
            "event": {"text": "分析风险", "user": "U1", "channel": "C1"},
        }

        wechat_result = await router.route_message(wechat_raw, platform="wechat_work")
        slack_result = await router.route_message(slack_raw, platform="slack")

        assert wechat_result["entry_type"] == slack_result["entry_type"]
        assert wechat_result["message"].content == slack_result["message"].content


# ---------------------------------------------------------------------------
# 10. format_response 根据 platform_hints 截断
# ---------------------------------------------------------------------------


class TestGatewayRouterFormatResponse:
    """GatewayRouter format_response 测试."""

    @pytest.mark.asyncio
    async def test_format_response_wechat_truncation(self) -> None:
        """企业微信平台响应超长时被截断."""
        router = GatewayRouter()
        router.register_adapter(WeChatWorkAdapter())
        long_text = "A" * 3000
        result = await router.format_response("wechat_work", {"text": long_text})
        assert result["truncated"] is True
        assert result["original_length"] == 3000
        assert len(result["text"]) == 2048

    @pytest.mark.asyncio
    async def test_format_response_slack_no_truncation(self) -> None:
        """Slack 平台 3000 字符不触发截断."""
        router = GatewayRouter()
        router.register_adapter(SlackAdapter())
        text = "B" * 3000
        result = await router.format_response("slack", {"text": text})
        assert result.get("truncated") is not True
        assert result["text"] == text

    @pytest.mark.asyncio
    async def test_format_response_slack_truncation_at_limit(self) -> None:
        """Slack 平台超 40000 字符时截断."""
        router = GatewayRouter()
        router.register_adapter(SlackAdapter())
        long_text = "C" * 40001
        result = await router.format_response("slack", {"text": long_text})
        assert result["truncated"] is True
        assert result["original_length"] == 40001
        assert len(result["text"]) == 40000

    @pytest.mark.asyncio
    async def test_format_response_adds_platform_hints(self) -> None:
        """格式化后的响应包含平台特性提示."""
        router = GatewayRouter()
        router.register_adapter(WeChatWorkAdapter())
        result = await router.format_response("wechat_work", {"text": "ok"})
        assert result["platform"] == "wechat_work"
        assert "platform_hints" in result
        assert result["platform_hints"]["max_text_length"] == 2048

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
        router.register_adapter(WeChatWorkAdapter())
        long_text = "D" * 3000
        result = await router.format_response("wechat_work", {"content": long_text})
        assert result["truncated"] is True
        assert len(result["content"]) == 2048


# ---------------------------------------------------------------------------
# 额外: GatewayAdapter 抽象基类不可实例化
# ---------------------------------------------------------------------------


def test_gateway_adapter_is_abstract() -> None:
    """GatewayAdapter 是抽象基类, 不能直接实例化."""
    with pytest.raises(TypeError):
        GatewayAdapter()  # type: ignore[abstract]
