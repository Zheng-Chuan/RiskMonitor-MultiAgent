"""
迭代优化(Iterative Refinement)测试.
"""

from __future__ import annotations

import pytest

from riskmonitor_multiagent.orchestration.iterative_refinement import (
    RefinementStep,
    Conflict,
    IterativeRefinementEngine,
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


class TestGlobalSingleton:
    """全局单例测试."""

    def test_get_refinement_engine(self) -> None:
        """测试获取全局单例."""
        reset_refinement_engine()
        
        engine1 = get_refinement_engine()
        engine2 = get_refinement_engine()
        
        assert engine1 is engine2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
