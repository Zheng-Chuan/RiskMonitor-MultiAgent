"""
BDI 模型和 Proactive Agent 测试.
"""

from __future__ import annotations

import pytest

from riskmonitor_multiagent.proactive_agents.base import (
    Belief,
    Desire,
    Intention,
    BaseProactiveAgent,
)


class TestBelief:
    """测试 Belief."""

    def test_create_belief(self) -> None:
        """测试创建信念."""
        belief = Belief(
            content="the sky is blue",
            source="observation",
            confidence=0.9,
        )
        assert belief.belief_id is not None
        assert belief.content == "the sky is blue"
        assert belief.source == "observation"
        assert belief.confidence == 0.9


class TestDesire:
    """测试 Desire."""

    def test_create_desire(self) -> None:
        """测试创建愿望."""
        desire = Desire(
            description="solve the problem",
            priority=100,
        )
        assert desire.desire_id is not None
        assert desire.description == "solve the problem"
        assert desire.priority == 100
        assert desire.active is True


class TestIntention:
    """测试 Intention."""

    def test_create_intention(self) -> None:
        """测试创建意图."""
        intention = Intention(
            description="call the query tool",
            tool_name="query_positions",
            tool_params={"desk": "Equities"},
        )
        assert intention.intention_id is not None
        assert intention.description == "call the query tool"
        assert intention.tool_name == "query_positions"
        assert intention.tool_params == {"desk": "Equities"}
        assert intention.status == "pending"


class TestBaseProactiveAgent:
    """测试 BaseProactiveAgent."""

    def test_add_belief(self) -> None:
        """测试添加信念."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        belief = agent.add_belief(
            content="task received",
            source="user_input",
            confidence=1.0,
        )
        
        assert belief is not None
        assert len(agent._beliefs) == 1
        assert agent._beliefs[0].content == "task received"

    def test_get_beliefs(self) -> None:
        """测试获取信念."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        agent.add_belief(content="belief1", source="source1")
        agent.add_belief(content="belief2", source="source2")
        
        all_beliefs = agent.get_beliefs()
        assert len(all_beliefs) == 2
        
        source1_beliefs = agent.get_beliefs(source="source1")
        assert len(source1_beliefs) == 1
        assert source1_beliefs[0].content == "belief1"

    def test_add_desire(self) -> None:
        """测试添加愿望."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        desire = agent.add_desire(
            description="complete the task",
            priority=100,
        )
        
        assert desire is not None
        assert len(agent._desires) == 1

    def test_get_active_desires(self) -> None:
        """测试获取活跃愿望."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        agent.add_desire(description="low priority", priority=10)
        agent.add_desire(description="high priority", priority=100)
        
        active = agent.get_active_desires()
        assert len(active) == 2
        assert active[0].priority == 100
        assert active[1].priority == 10

    def test_add_intention(self) -> None:
        """测试添加意图."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        intention = agent.add_intention(
            description="do something",
            tool_name="tool_a",
            tool_params={"param": "value"},
        )
        
        assert intention is not None
        assert len(agent._intentions) == 1

    def test_get_pending_intentions(self) -> None:
        """测试获取待处理意图."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        agent.add_intention(description="pending1")
        agent.add_intention(description="pending2")
        
        pending = agent.get_pending_intentions()
        assert len(pending) == 2

    def test_update_intention_status(self) -> None:
        """测试更新意图状态."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        intention = agent.add_intention(description="test")
        
        updated = agent.update_intention_status(
            intention_id=intention.intention_id,
            status="in_progress",
        )
        assert updated is True
        assert intention.status == "in_progress"

    def test_get_bdi_state(self) -> None:
        """测试获取 BDI 状态."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        agent.add_belief(content="test belief", source="test")
        agent.add_desire(description="test desire")
        agent.add_intention(description="test intention")
        
        state = agent.get_bdi_state()
        
        assert "agent_name" in state
        assert "beliefs" in state
        assert "desires" in state
        assert "intentions" in state
        assert len(state["beliefs"]) == 1
        assert len(state["desires"]) == 1
        assert len(state["intentions"]) == 1

    def test_record_llm_interaction(self) -> None:
        """测试记录 LLM 交互."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        agent.record_llm_interaction(
            interaction_type="thought",
            system_prompt="test system",
            user_prompt="test user",
            raw_response="test response",
            parsed_output={"thought": "test"},
            latency_ms=100,
            model="test-model",
            success=True,
        )
        
        interactions = agent.get_llm_interactions()
        assert len(interactions) == 1
        assert interactions[0]["interaction_type"] == "thought"
        assert interactions[0]["latency_ms"] == 100
