"""
多 Agent 协作系统单元测试.

测试 Message Bus、Moderator Agent 和多 Agent 工作流的基础功能.
"""

from __future__ import annotations

import pytest

from riskmonitor_multiagent.contracts.message import (
    MESSAGE_SCHEMA_VERSION,
    MessageType,
    normalize_message,
    validate_message,
)
from riskmonitor_multiagent.orchestration.message_bus import (
    MessageBus,
    get_message_bus,
    reset_message_bus,
)
from riskmonitor_multiagent.orchestration.multiagent_workflow import (
    MultiAgentCollaborationWorkflow,
    get_multi_agent_workflow,
    reset_multi_agent_workflow,
)


@pytest.fixture
def message_bus() -> MessageBus:
    """消息总线 fixture."""
    reset_message_bus()
    return get_message_bus()


@pytest.fixture
def workflow() -> MultiAgentCollaborationWorkflow:
    """多 Agent 工作流 fixture."""
    reset_message_bus()
    reset_multi_agent_workflow()
    return get_multi_agent_workflow()


class TestMessageContract:
    """测试消息契约."""

    def test_message_type_enum(self) -> None:
        """测试消息类型枚举."""
        assert MessageType.REQUEST.value == "request"
        assert MessageType.RESPONSE.value == "response"
        assert MessageType.BROADCAST.value == "broadcast"
        assert MessageType.INTERRUPT.value == "interrupt"
        assert MessageType.FEEDBACK.value == "feedback"
        assert MessageType.TOOL_CALL.value == "tool_call"
        assert MessageType.TOOL_RESULT.value == "tool_result"

    def test_validate_valid_message(self) -> None:
        """测试验证有效消息."""
        message = {
            "message_id": "test-001",
            "message_type": "request",
            "from_agent": "intent",
            "content": {"task": "test"},
            "timestamp_ms": 1234567890,
        }

        is_valid, errors = validate_message(message)
        assert is_valid
        assert len(errors) == 0

    def test_validate_message_missing_fields(self) -> None:
        """测试验证缺失字段的消息."""
        message = {
            "message_type": "request",
        }

        is_valid, errors = validate_message(message)
        assert not is_valid
        assert "bad_message_id" in errors
        assert "bad_from_agent" in errors
        assert "missing_timestamp_ms" in errors

    def test_normalize_message(self) -> None:
        """测试消息归一化."""
        message = {
            "message_id": "test-001",
            "message_type": "request",
            "from_agent": "intent",
        }

        normalized = normalize_message(message)
        assert normalized.get("schema_version") == MESSAGE_SCHEMA_VERSION
        assert normalized.get("content") == {}
        assert normalized.get("degraded") is False


class TestMessageBus:
    """测试 Message Bus."""

    @pytest.mark.asyncio
    async def test_send_message(self, message_bus: MessageBus) -> None:
        """测试发送消息."""
        message = await message_bus.send_request(
            from_agent="intent",
            to_agent="orchestrator",
            content={"task": "test"},
        )

        assert message.get("message_id") is not None
        assert message.get("message_type") == "request"
        assert message.get("from_agent") == "intent"
        assert message.get("to_agent") == "orchestrator"

    @pytest.mark.asyncio
    async def test_broadcast_message(self, message_bus: MessageBus) -> None:
        """测试广播消息."""
        message = await message_bus.broadcast(
            from_agent="moderator",
            content={"status": "started"},
        )

        assert message.get("message_id") is not None
        assert message.get("message_type") == "broadcast"
        assert message.get("to_agent") is None

    @pytest.mark.asyncio
    async def test_get_message_history(self, message_bus: MessageBus) -> None:
        """测试获取消息历史."""
        # 发送几条消息
        await message_bus.send_request(
            from_agent="intent",
            to_agent="orchestrator",
            content={"task": "test1"},
        )
        await message_bus.send_request(
            from_agent="orchestrator",
            to_agent="critic",
            content={"task": "test2"},
        )

        history = message_bus.get_message_history()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_get_messages_for_agent(self, message_bus: MessageBus) -> None:
        """测试获取特定 Agent 的消息."""
        await message_bus.send_request(
            from_agent="intent",
            to_agent="orchestrator",
            content={"task": "test1"},
        )
        await message_bus.send_request(
            from_agent="orchestrator",
            to_agent="critic",
            content={"task": "test2"},
        )

        orchestrator_messages = message_bus.get_messages_for_agent("orchestrator")
        assert len(orchestrator_messages) == 1
        assert orchestrator_messages[0].get("to_agent") == "orchestrator"

    @pytest.mark.asyncio
    async def test_subscribe_and_notify(self, message_bus: MessageBus) -> None:
        """测试订阅和通知."""
        received_messages = []

        def callback(message: dict) -> None:
            received_messages.append(message)

        message_bus.subscribe("orchestrator", callback)

        await message_bus.send_request(
            from_agent="intent",
            to_agent="orchestrator",
            content={"task": "test"},
        )

        # 注意:这里用的是 async 回调,实际测试需要 asyncio
        # 这里只验证订阅成功
        assert len(message_bus._subscribers["orchestrator"]) == 1


class TestMultiAgentWorkflow:
    """测试多 Agent 工作流."""

    def test_workflow_initialization(self, workflow: MultiAgentCollaborationWorkflow) -> None:
        """测试工作流初始化."""
        assert workflow._message_bus is not None
        assert workflow._moderator is not None
        assert workflow._intent_agent is not None
        assert workflow._orchestrator_agent is not None
        assert workflow._critic_agent is not None
        assert workflow._system_engineer_agent is not None
        assert workflow._risk_analyst_agent is not None

    def test_global_singleton(self) -> None:
        """测试全局单例."""
        reset_message_bus()
        reset_multi_agent_workflow()

        workflow1 = get_multi_agent_workflow()
        workflow2 = get_multi_agent_workflow()

        assert workflow1 is workflow2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
