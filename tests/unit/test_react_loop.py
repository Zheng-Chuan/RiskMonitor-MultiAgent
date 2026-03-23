"""
ReAct 循环单元测试.

验证 ReAct 和 CoT 的基本功能.
"""

from __future__ import annotations

import pytest

from riskmonitor_multiagent.orchestration.react_loop import (
    ReActStep,
    ReActResult,
    ReActLoop,
    CoTEnhancedReActLoop,
    format_react_trace,
)


class TestReActStep:
    """ReActStep 测试."""
    
    def test_create_step(self) -> None:
        """测试创建 ReActStep."""
        step = ReActStep(
            step_id="step_1",
            thought="我需要查询数据",
            action_type="tool_call",
            action={"tool": "query", "params": {"desk": "Equities"}},
        )
        
        assert step.step_id == "step_1"
        assert step.thought == "我需要查询数据"
        assert step.action_type == "tool_call"
        assert step.action["tool"] == "query"
        assert step.observation is None
        assert step.reasoning is None
        assert step.evidence is None
    
    def test_create_step_with_cot(self) -> None:
        """测试创建带有 CoT 的 ReActStep."""
        step = ReActStep(
            step_id="step_1",
            thought="我需要查询数据",
            reasoning="因为分析需要基于真实数据",
            evidence={"source": "user_query"},
            action_type="tool_call",
            action={"tool": "query", "params": {"desk": "Equities"}},
        )
        
        assert step.reasoning == "因为分析需要基于真实数据"
        assert step.evidence == {"source": "user_query"}


class TestReActLoop:
    """ReActLoop 测试."""
    
    def test_simple_react_loop(self) -> None:
        """测试简单的 ReAct 循环."""
        
        def thought_generator(task: dict, history: list[ReActStep]) -> str:
            if not history:
                return "开始处理任务"
            return "继续处理"
        
        def action_decider(
            task: dict,
            history: list[ReActStep],
            thought: str,
        ) -> tuple[str, dict]:
            if len(history) < 2:
                return "mock_action", {"step": len(history) + 1}
            return "finalize", {}
        
        def action_executor(action_type: str, action: dict) -> dict:
            return {"result": f"executed {action_type}", "data": action}
        
        def termination_checker(task: dict, history: list[ReActStep]) -> bool:
            return len(history) >= 2
        
        def final_answer_generator(task: dict, history: list[ReActStep]) -> dict:
            return {"steps": len(history), "task": task}
        
        loop = ReActLoop(
            max_steps=5,
            thought_generator=thought_generator,
            action_decider=action_decider,
            action_executor=action_executor,
            termination_checker=termination_checker,
            final_answer_generator=final_answer_generator,
        )
        
        import asyncio
        result = asyncio.run(loop.run(task={"id": "test_task"}))
        
        assert result.success is True
        assert len(result.steps) == 2
        assert result.final_answer is not None
        assert result.final_answer["steps"] == 2
        assert result.total_latency_ms > 0


class TestCoTEnhancedReActLoop:
    """CoTEnhancedReActLoop 测试."""
    
    def test_cot_react_loop(self) -> None:
        """测试 CoT 增强的 ReAct 循环."""
        
        def thought_generator(task: dict, history: list[ReActStep]) -> str:
            return f"思考步骤 {len(history) + 1}"
        
        def reasoning_generator(
            task: dict,
            history: list[ReActStep],
            thought: str,
        ) -> str:
            return f"理由:{thought} 是必要的"
        
        def evidence_generator(
            task: dict,
            history: list[ReActStep],
            thought: str,
        ) -> dict:
            return {"step": len(history) + 1, "source": "test"}
        
        def action_decider(
            task: dict,
            history: list[ReActStep],
            thought: str,
        ) -> tuple[str, dict]:
            if len(history) < 2:
                return "mock_action", {"step": len(history) + 1}
            return "finalize", {}
        
        def action_executor(action_type: str, action: dict) -> dict:
            return {"result": f"executed {action_type}"}
        
        def termination_checker(task: dict, history: list[ReActStep]) -> bool:
            return len(history) >= 2
        
        loop = CoTEnhancedReActLoop(
            max_steps=5,
            thought_generator=thought_generator,
            reasoning_generator=reasoning_generator,
            evidence_generator=evidence_generator,
            action_decider=action_decider,
            action_executor=action_executor,
            termination_checker=termination_checker,
        )
        
        import asyncio
        result = asyncio.run(loop.run(task={"id": "test_cot_task"}))
        
        assert result.success is True
        assert len(result.steps) == 2
        
        for step in result.steps:
            assert step.reasoning is not None
            assert step.evidence is not None
            assert "理由" in step.reasoning


class TestFormatReactTrace:
    """format_react_trace 测试."""
    
    def test_format_trace(self) -> None:
        """测试格式化 ReAct 追踪."""
        step1 = ReActStep(
            step_id="step_1",
            thought="查询数据",
            reasoning="因为需要数据",
            evidence={"source": "user"},
            action_type="query",
            action={"desk": "Equities"},
            observation={"data": "result1"},
        )
        step2 = ReActStep(
            step_id="step_2",
            thought="分析数据",
            action_type="analyze",
            action={"data": "result1"},
            observation={"analysis": "done"},
        )
        
        result = ReActResult(
            run_id="test_trace_001",
            success=True,
            steps=[step1, step2],
            final_answer={"summary": "完成"},
            total_latency_ms=1234.5,
        )
        
        trace = format_react_trace(result)
        
        assert "test_trace_001" in trace
        assert "Success: True" in trace
        assert "Total Steps: 2" in trace
        assert "step_1" in trace
        assert "step_2" in trace
        assert "查询数据" in trace
        # reasoning 字段现在会被展示
        assert "Reasoning: 因为需要数据" in trace
    
    def test_format_trace_with_errors(self) -> None:
        """测试带有错误的追踪格式化."""
        result = ReActResult(
            run_id="test_error_001",
            success=False,
            steps=[],
            errors=["错误1", "错误2"],
        )
        
        trace = format_react_trace(result)
        
        assert "Success: False" in trace
        assert "错误1" in trace
        assert "错误2" in trace


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
