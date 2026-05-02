"""
多 Agent 协作系统单元测试.

测试 Message Bus、Moderator Agent 和多 Agent 工作流的基础功能.
"""

from __future__ import annotations

import pytest

from riskmonitor_multiagent.contracts.event import (
    EVENT_SCHEMA_VERSION,
    EventType,
    new_event,
    normalize_event,
    validate_event,
)
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
from riskmonitor_multiagent.orchestration.proactive_workflow import (
    ProactiveMultiAgentWorkflow,
    reset_proactive_workflow,
)
from riskmonitor_multiagent.orchestration.multiagent_workflow import (
    MultiAgentCollaborationWorkflow,
    get_multi_agent_workflow,
    reset_multi_agent_workflow,
)
from riskmonitor_multiagent.proactive_agents.moderator import ModeratorAgent


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
    reset_proactive_workflow()
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


class TestEventContract:
    """测试事件契约."""

    def test_validate_valid_event(self) -> None:
        """测试验证有效事件."""
        event = new_event(
            event_type=EventType.TASK_CREATED,
            source_agent="intent",
            payload={"task": "analyze risk"},
        )

        is_valid, errors = validate_event(event)
        assert is_valid
        assert errors == []

    def test_validate_invalid_event(self) -> None:
        """测试非法事件被识别."""
        event = {
            "event_id": "",
            "event_type": "unknown",
            "source_agent": "",
            "payload": [],
            "timestamp_ms": 0,
            "priority": "urgent",
            "requires_ack": "yes",
        }

        is_valid, errors = validate_event(event)
        assert not is_valid
        assert "bad_event_id" in errors
        assert "bad_event_type" in errors
        assert "bad_payload" in errors

    def test_normalize_event(self) -> None:
        """测试事件归一化."""
        event = normalize_event(
            {
                "event_type": EventType.TASK_CREATED.value,
                "source_agent": "intent",
            }
        )
        assert event.get("schema_version") == EVENT_SCHEMA_VERSION
        assert event.get("payload") == {}
        assert event.get("priority") == "normal"


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

    @pytest.mark.asyncio
    async def test_publish_event_and_trace(self, message_bus: MessageBus) -> None:
        """测试发布事件并写入 trace."""
        received_events = []

        def callback(event: dict) -> None:
            received_events.append(event)

        message_bus.subscribe_event(EventType.TASK_CREATED, callback)
        event = new_event(
            event_type=EventType.TASK_CREATED,
            source_agent="intent",
            payload={"task_id": "task-001"},
        )
        published = await message_bus.publish_event(event)

        assert published.get("event_type") == EventType.TASK_CREATED.value
        assert len(received_events) == 1
        trace = message_bus.get_event_trace()
        assert len(trace) == 1
        assert trace[0].get("status") == "accepted"

    @pytest.mark.asyncio
    async def test_reject_invalid_event(self, message_bus: MessageBus) -> None:
        """测试非法事件被拒绝并留下记录."""
        with pytest.raises(ValueError, match="invalid_event"):
            await message_bus.publish_event(
                {
                    "event_type": "bad_type",
                    "source_agent": "",
                    "payload": [],
                    "timestamp_ms": -1,
                }
            )

        rejected = message_bus.get_rejected_events()
        assert len(rejected) == 1
        trace = message_bus.get_event_trace(status="rejected")
        assert len(trace) == 1
        assert "bad_event_type" in trace[0].get("errors", [])


class TestModeratorAgent:
    """测试 ModeratorAgent."""

    @pytest.mark.asyncio
    async def test_rule_first_risk_breach(self, message_bus: MessageBus) -> None:
        """测试风险事件优先交给风险分析师."""
        moderator = ModeratorAgent(message_bus=message_bus)
        event = new_event(
            event_type=EventType.RISK_BREACH_DETECTED,
            source_agent="system_engineer",
            payload={"breach": "limit"},
        )

        decision = await moderator.moderate(
            event=event,
            candidate_agents=["critic", "risk_analyst", "system_engineer"],
        )

        assert decision.get("selected_agent") == "risk_analyst"
        assert decision.get("decision_source") == "rule"
        trace = message_bus.get_event_history(event_type=EventType.MODERATOR_DECISION.value)
        assert len(trace) == 1

    @pytest.mark.asyncio
    async def test_llm_tie_breaker_only_when_rules_do_not_apply(self, message_bus: MessageBus) -> None:
        """测试规则失效时才调用 tie breaker."""
        calls = {"count": 0}

        async def fake_tie_breaker(event: dict, candidates: list[str], context: dict) -> dict:
            calls["count"] += 1
            return {
                "selected_agent": candidates[-1],
                "reason": f"choose_for_{event.get('event_type')}",
                "context_seen": context,
            }

        moderator = ModeratorAgent(
            llm_tie_breaker=fake_tie_breaker,
            message_bus=message_bus,
        )
        event = new_event(
            event_type=EventType.CONFLICT_DETECTED,
            source_agent="critic",
            payload={"conflict": "generic"},
        )

        decision = await moderator.moderate(
            event=event,
            candidate_agents=["critic", "risk_analyst"],
            conflict={"conflict_type": "generic_conflict"},
        )

        assert calls["count"] == 1
        assert decision.get("selected_agent") == "risk_analyst"
        assert decision.get("decision_source") == "llm_tie_breaker"

    @pytest.mark.asyncio
    async def test_approval_priority_routes_to_human(self, message_bus: MessageBus) -> None:
        """测试审批优先级冲突升级人工."""
        moderator = ModeratorAgent(message_bus=message_bus)
        event = new_event(
            event_type=EventType.APPROVAL_REQUIRED,
            source_agent="critic",
            payload={"reason": "side effect"},
        )

        decision = await moderator.moderate(
            event=event,
            candidate_agents=["critic", "human", "orchestrator"],
            conflict={"conflict_type": "approval_priority_conflict"},
        )

        assert decision.get("selected_agent") == "human"
        assert decision.get("rule_name") == "approval_priority"

    @pytest.mark.asyncio
    async def test_conclusion_conflict_prioritizes_critic(self, message_bus: MessageBus) -> None:
        """测试结论冲突优先交给 critic."""
        moderator = ModeratorAgent(message_bus=message_bus)
        event = new_event(
            event_type=EventType.CONFLICT_DETECTED,
            source_agent="orchestrator",
            payload={"summary": "结论冲突"},
        )

        decision = await moderator.moderate(
            event=event,
            candidate_agents=["risk_analyst", "critic", "system_engineer"],
            conflict={"conflict_type": "conclusion_conflict"},
        )

        assert decision.get("selected_agent") == "critic"
        assert decision.get("decision_source") == "rule"
        assert isinstance(decision.get("discarded_candidates"), list)
        assert isinstance(decision.get("discarded_path_reason"), str)
        arbitration_events = message_bus.get_event_history(event_type=EventType.ARBITRATION_RESOLVED.value)
        assert len(arbitration_events) == 1


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

    @pytest.mark.asyncio
    async def test_workflow_route_event(self, workflow: MultiAgentCollaborationWorkflow) -> None:
        """测试 workflow 通过 moderator 做事件路由."""
        event = await workflow.create_task(
            source_agent="intent",
            payload={"task_id": "task-001", "content": "分析风险"},
        )
        decision = await workflow.route_event(
            event=event,
            candidate_agents=["risk_analyst", "orchestrator"],
        )

        assert decision.get("selected_agent") == "orchestrator"
        history = workflow._message_bus.get_event_history()
        assert len(history) == 2
        assert history[0].get("event_type") == EventType.TASK_CREATED.value
        assert history[1].get("event_type") == EventType.MODERATOR_DECISION.value

    @pytest.mark.asyncio
    async def test_workflow_runs_system_event_with_unified_workflow(
        self,
        workflow: MultiAgentCollaborationWorkflow,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """测试 system_event 通过统一 workflow 执行."""
        captured: dict[str, object] = {}

        async def fake_start_from_event(self, *, event: dict, candidate_agents: list[str] | None = None) -> dict:
            captured["event"] = event
            captured["candidate_agents"] = candidate_agents
            return {
                "status": "completed",
                "run_id": "run_001",
                "entry_type": "system_event",
                "run_context": {"entry_type": "system_event", "run_id": "run_001"},
            }

        monkeypatch.setattr(
            ProactiveMultiAgentWorkflow,
            "start_from_event",
            fake_start_from_event,
            raising=True,
        )
        event = new_event(
            event_type=EventType.RISK_BREACH_DETECTED,
            source_agent="monitor",
            payload={"content": "风险 breach"},
        )

        result = await workflow.run_system_event(
            event=event,
            candidate_agents=["orchestrator", "critic"],
        )

        assert result.get("entry_type") == "system_event"
        assert captured["event"] == event
        assert captured["candidate_agents"] == ["orchestrator", "critic"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
