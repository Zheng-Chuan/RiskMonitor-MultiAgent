"""
迭代优化(Iterative Refinement)测试.
"""

from __future__ import annotations

import pytest

from riskmonitor_multiagent.proactive_agents.moderator import ModeratorAgent
from riskmonitor_multiagent.orchestration.iterative_refinement import (
    ArbitrationDecision,
    Conflict,
    IterativeRefinementEngine,
    RefinementStep,
    get_refinement_engine,
    reset_refinement_engine,
)


class TestRefinementStep:
    """RefinementStep 测试."""

    def test_create_refinement_step(self) -> None:
        """测试创建优化步骤."""
        step = RefinementStep(
            step_id="step_001",
            step_type="refine",
            agent="engineer",
            input_content={"data": "input"},
            output_content={"data": "output"},
        )
        
        assert step.step_id == "step_001"
        assert step.step_type == "refine"
        assert step.agent == "engineer"
        assert step.feedback is None
        assert step.revision_count == 0


class TestConflict:
    """Conflict 测试."""

    def test_create_conflict(self) -> None:
        """测试创建冲突."""
        conflict = Conflict(
            conflict_id="conflict_001",
            agent_a="engineer",
            agent_b="analyst",
            description="对风险等级有不同意见",
        )
        
        assert conflict.conflict_id == "conflict_001"
        assert conflict.agent_a == "engineer"
        assert conflict.agent_b == "analyst"
        assert conflict.description == "对风险等级有不同意见"
        assert conflict.resolved is False
        assert conflict.resolution is None

    def test_detect_conflict(self) -> None:
        """测试从 proposal 检测冲突."""
        engine = IterativeRefinementEngine()
        conflict = engine.detect_conflict(
            proposals=[
                {"agent": "engineer", "value": "tool_a"},
                {"agent": "analyst", "value": "tool_b"},
            ],
            conflict_type="tool_selection_conflict",
            description="工具选择不一致",
        )

        assert conflict is not None
        assert conflict.conflict_type == "tool_selection_conflict"
        assert conflict.candidates == ["analyst", "engineer"]


class TestIterativeRefinementEngine:
    """IterativeRefinementEngine 测试."""

    def setup_method(self) -> None:
        """测试前重置."""
        reset_refinement_engine()
    
    def test_run_iterative_refinement(self) -> None:
        """测试运行迭代优化."""
        import asyncio
        
        engine = IterativeRefinementEngine()
        
        def agent_fn(input_data):
            return {"output": input_data, "quality": "good"}
        
        def critic_fn(output):
            return (True, "Looks good", [])
        
        final_output, steps = asyncio.run(
            engine.run_iterative_refinement(
                initial_input={"task": "test"},
                agent_fn=agent_fn,
                critic_fn=critic_fn,
                max_iterations=3,
            )
        )
        
        assert final_output is not None
        assert len(steps) == 1
    
    def test_run_review_and_revise(self) -> None:
        """测试运行评审-修订."""
        import asyncio
        
        engine = IterativeRefinementEngine()
        
        def reviewer_fn(output):
            return (True, "Looks good", [])
        
        def reviser_fn(output, issues):
            return output
        
        final_output, steps = asyncio.run(
            engine.run_review_and_revise(
                initial_output={"data": "initial"},
                reviewer_fn=reviewer_fn,
                reviser_fn=reviser_fn,
                max_revisions=3,
            )
        )
        
        assert final_output is not None
        assert len(steps) == 1
    
    def test_record_conflict(self) -> None:
        """测试记录冲突."""
        engine = IterativeRefinementEngine()
        
        conflict = engine.record_conflict(
            agent_a="engineer",
            agent_b="analyst",
            description="对风险等级有不同意见",
        )
        
        assert conflict.conflict_id is not None
        assert len(engine._conflicts) == 1
        assert conflict.resolved is False
    
    def test_resolve_conflict(self) -> None:
        """测试解决冲突."""
        engine = IterativeRefinementEngine()
        
        conflict = engine.record_conflict(
            agent_a="engineer",
            agent_b="analyst",
            description="对风险等级有不同意见",
        )
        
        success = engine.resolve_conflict(
            conflict_id=conflict.conflict_id,
            resolution="采用风险等级 HIGH",
        )
        
        assert success is True
        assert conflict.resolved is True
        assert conflict.resolution == "采用风险等级 HIGH"
    
    def test_get_unresolved_conflicts(self) -> None:
        """测试获取未解决的冲突."""
        engine = IterativeRefinementEngine()
        
        conflict1 = engine.record_conflict("a", "b", "conflict1")
        conflict2 = engine.record_conflict("c", "d", "conflict2")
        
        engine.resolve_conflict(conflict1.conflict_id, "resolved")
        
        unresolved = engine.get_unresolved_conflicts()
        assert len(unresolved) == 1
        assert unresolved[0].conflict_id == conflict2.conflict_id
    
    def test_get_refinement_trace(self) -> None:
        """测试获取优化追踪."""
        engine = IterativeRefinementEngine()
        
        engine.record_conflict("a", "b", "conflict1")
        
        trace = engine.get_refinement_trace()
        
        assert "Total conflicts" in trace
        assert "Unresolved conflicts" in trace

    @pytest.mark.asyncio
    async def test_arbitrate_conflict_with_moderator(self) -> None:
        """测试通过 moderator 仲裁冲突."""
        from riskmonitor_multiagent.orchestration.message_bus import MessageBus

        engine = IterativeRefinementEngine()
        moderator = ModeratorAgent(message_bus=MessageBus())
        conflict = engine.detect_conflict(
            proposals=[
                {"agent": "system_engineer", "tool_name": "query_positions"},
                {"agent": "risk_analyst", "tool_name": "query_alerts"},
            ],
            conflict_type="tool_selection_conflict",
            description="工具选择冲突",
        )

        assert conflict is not None
        decision = await engine.arbitrate_conflict(
            conflict_id=conflict.conflict_id,
            moderator=moderator,
        )

        assert isinstance(decision, ArbitrationDecision)
        assert decision.selected_agent == "system_engineer"
        assert decision.rule_name == "tool_selection_conflict"
        assert isinstance(decision.discarded_candidates, list)
        assert decision.discarded_path_reason is not None
        assert conflict.resolved is True
        trace = engine.get_conflict_trace()
        assert len(trace) == 2
        assert trace[0]["trace_type"] == "conflict_detected"
        assert trace[1]["trace_type"] == "arbitration_resolved"

    @pytest.mark.asyncio
    async def test_arbitration_publishes_conflict_and_resolution_events(self) -> None:
        """测试仲裁会发布冲突和解决事件."""
        from riskmonitor_multiagent.contracts.event import EventType
        from riskmonitor_multiagent.orchestration.message_bus import MessageBus

        bus = MessageBus()
        engine = IterativeRefinementEngine()
        moderator = ModeratorAgent(message_bus=bus)
        conflict = engine.detect_conflict(
            proposals=[
                {"agent": "critic", "summary": "high risk"},
                {"agent": "risk_analyst", "summary": "medium risk"},
            ],
            conflict_type="conclusion_conflict",
            description="结论冲突",
        )

        assert conflict is not None
        await engine.arbitrate_conflict(
            conflict_id=conflict.conflict_id,
            moderator=moderator,
        )

        events = bus.get_event_history()
        event_types = [event.get("event_type") for event in events]
        assert EventType.CONFLICT_DETECTED.value in event_types
        assert EventType.MODERATOR_DECISION.value in event_types
        assert EventType.ARBITRATION_RESOLVED.value in event_types


class TestGlobalSingleton:
    """全局单例测试."""

    def test_get_refinement_engine(self) -> None:
        """测试获取全局单例."""
        reset_refinement_engine()
        
        engine1 = get_refinement_engine()
        engine2 = get_refinement_engine()
        
        assert engine1 is engine2
