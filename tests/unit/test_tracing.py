"""
分布式追踪(Tracing)测试.
"""

from __future__ import annotations

import pytest

from riskmonitor_multiagent.observability.tracing import (
    Span,
    Trace,
    TraceStore,
    get_trace_store,
    reset_trace_store,
    generate_trace_id,
    generate_span_id,
    get_current_trace_id,
    get_current_span_id,
    trace,
    add_trace_attributes,
    get_trace_summary,
)


class TestSpan:
    """Span 测试."""

    def test_create_span(self) -> None:
        """测试创建 Span."""
        span = Span(
            span_id="span_001",
            parent_span_id=None,
            name="test_operation",
            start_timestamp_ms=1000,
        )
        
        assert span.span_id == "span_001"
        assert span.name == "test_operation"
        assert span.status == "pending"
        assert span.duration_ms is None


class TestTraceStore:
    """TraceStore 测试."""

    def setup_method(self) -> None:
        """测试前重置."""
        reset_trace_store()
    
    def test_create_trace(self) -> None:
        """测试创建 Trace."""
        store = TraceStore()
        trace_id = store.create_trace()
        
        assert trace_id is not None
        assert len(trace_id) > 0
        
        trace = store.get_trace(trace_id)
        assert trace is not None
        assert trace.trace_id == trace_id
    
    def test_add_span(self) -> None:
        """测试添加 Span."""
        store = TraceStore()
        trace_id = store.create_trace()
        
        span = Span(
            span_id="span_001",
            parent_span_id=None,
            name="test_operation",
            start_timestamp_ms=1000,
        )
        
        store.add_span(trace_id, span)
        
        trace = store.get_trace(trace_id)
        assert len(trace.spans) == 1
        assert trace.spans[0].span_id == "span_001"
    
    def test_get_all_traces(self) -> None:
        """测试获取所有 Trace."""
        store = TraceStore()
        store.create_trace()
        store.create_trace()
        
        traces = store.get_all_traces()
        assert len(traces) == 2
    
    def test_max_traces_limit(self) -> None:
        """测试最大 Trace 数量限制."""
        store = TraceStore(max_traces=3)
        ids = []
        for i in range(5):
            ids.append(store.create_trace())
        
        traces = store.get_all_traces()
        assert len(traces) == 3


class TestTraceContext:
    """Trace 上下文测试."""

    def setup_method(self) -> None:
        """测试前重置."""
        reset_trace_store()
    
    def test_trace_decorator(self) -> None:
        """测试 @trace 装饰器."""
        import asyncio
        
        @trace("test_operation")
        async def test_func():
            return "done"
        
        result = asyncio.run(test_func())
        assert result == "done"
    
    def test_trace_summary(self) -> None:
        """测试获取 Trace 摘要."""
        import asyncio
        
        store = get_trace_store()
        trace_id = store.create_trace()
        
        span = Span(
            span_id="span_001",
            parent_span_id=None,
            name="test_operation",
            start_timestamp_ms=1000,
            end_timestamp_ms=2000,
            duration_ms=1000,
            status="completed",
        )
        store.add_span(trace_id, span)
        
        summary = get_trace_summary(trace_id)
        assert summary is not None
        assert summary["trace_id"] == trace_id
        assert summary["span_count"] == 1


class TestGenerateIds:
    """ID 生成测试."""

    def test_generate_trace_id(self) -> None:
        """测试生成 Trace ID."""
        trace_id1 = generate_trace_id()
        trace_id2 = generate_trace_id()
        
        assert trace_id1 is not None
        assert trace_id2 is not None
        assert trace_id1 != trace_id2
    
    def test_generate_span_id(self) -> None:
        """测试生成 Span ID."""
        span_id1 = generate_span_id()
        span_id2 = generate_span_id()
        
        assert span_id1 is not None
        assert span_id2 is not None
        assert span_id1 != span_id2
        assert len(span_id1) == 16


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
