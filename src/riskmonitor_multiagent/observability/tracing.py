"""
分布式追踪（Distributed Tracing）.

实现请求追踪、Span 管理和 Trace ID 传播.
"""

from __future__ import annotations

import contextvars
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)


_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id",
    default="",
)

_span_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "span_id",
    default="",
)


@dataclass
class Span:
    """追踪 Span."""
    
    span_id: str
    parent_span_id: Optional[str]
    name: str
    start_timestamp_ms: int
    end_timestamp_ms: Optional[int] = None
    duration_ms: Optional[float] = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    error_message: Optional[str] = None


@dataclass
class Trace:
    """完整的 Trace."""
    
    trace_id: str
    spans: list[Span] = field(default_factory=list)
    start_timestamp_ms: int = field(default_factory=lambda: __import__('time').time_ns() // 1000000)
    end_timestamp_ms: Optional[int] = None


class TraceStore:
    """Trace 存储."""
    
    def __init__(self, max_traces: int = 1000) -> None:
        """
        初始化 Trace 存储.
        
        Args:
            max_traces: 最大 Trace 数量
        """
        self._traces: dict[str, Trace] = {}
        self._max_traces = max_traces
        self._lock = threading.Lock()
    
    def create_trace(self) -> str:
        """
        创建一个新的 Trace.
        
        Returns:
            Trace ID
        """
        trace_id = str(uuid.uuid4())
        with self._lock:
            if len(self._traces) >= self._max_traces:
                oldest = min(self._traces.keys(), key=lambda k: self._traces[k].start_timestamp_ms)
                del self._traces[oldest]
            self._traces[trace_id] = Trace(trace_id=trace_id)
        return trace_id
    
    def add_span(self, trace_id: str, span: Span) -> None:
        """
        添加 Span 到 Trace.
        
        Args:
            trace_id: Trace ID
            span: Span 对象
        """
        with self._lock:
            if trace_id in self._traces:
                self._traces[trace_id].spans.append(span)
    
    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """
        获取 Trace.
        
        Args:
            trace_id: Trace ID
            
        Returns:
            Trace 对象或 None
        """
        with self._lock:
            return self._traces.get(trace_id)
    
    def get_all_traces(self) -> list[Trace]:
        """
        获取所有 Trace.
        
        Returns:
            Trace 列表
        """
        with self._lock:
            return list(self._traces.values())


_trace_store: Optional[TraceStore] = None


def get_trace_store() -> TraceStore:
    """获取全局 TraceStore 实例."""
    global _trace_store
    if _trace_store is None:
        _trace_store = TraceStore()
    return _trace_store


def reset_trace_store() -> None:
    """重置 TraceStore（用于测试）."""
    global _trace_store
    _trace_store = None


def generate_trace_id() -> str:
    """生成新的 Trace ID."""
    return str(uuid.uuid4())


def generate_span_id() -> str:
    """生成新的 Span ID."""
    return str(uuid.uuid4())[:16]


def get_current_trace_id() -> str:
    """获取当前 Trace ID."""
    return _trace_id_var.get()


def get_current_span_id() -> str:
    """获取当前 Span ID."""
    return _span_id_var.get()


@contextmanager
def trace(
    name: str,
    trace_id: Optional[str] = None,
    attributes: Optional[dict[str, Any]] = None,
) -> Generator[Span, None, None]:
    """
    追踪上下文管理器.
    
    Args:
        name: Span 名称
        trace_id: 可选的 Trace ID（如果不提供则使用当前上下文或创建新的）
        attributes: 可选的属性字典
        
    Yields:
        Span 对象
    """
    import time
    
    if trace_id is None:
        current_trace_id = get_current_trace_id()
        if current_trace_id:
            trace_id = current_trace_id
        else:
            trace_id = get_trace_store().create_trace()
    
    parent_span_id = get_current_span_id() or None
    
    span_id = generate_span_id()
    span = Span(
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        start_timestamp_ms=int(time.time_ns() // 1000000),
        attributes=attributes or {},
        status="in_progress",
    )
    
    get_trace_store().add_span(trace_id, span)
    
    trace_token = _trace_id_var.set(trace_id)
    span_token = _span_id_var.set(span_id)
    
    try:
        logger.debug(f"Span started: {name} (trace={trace_id}, span={span_id})")
        yield span
        span.status = "completed"
    except Exception as e:
        span.status = "error"
        span.error_message = str(e)
        logger.error(f"Span error: {name} - {e}")
        raise
    finally:
        import time
        span.end_timestamp_ms = int(time.time_ns() // 1000000)
        span.duration_ms = span.end_timestamp_ms - span.start_timestamp_ms
        _trace_id_var.reset(trace_token)
        _span_id_var.reset(span_token)
        logger.debug(f"Span ended: {name}, duration={span.duration_ms:.2f}ms")


def add_trace_attributes(attributes: dict[str, Any]) -> None:
    """
    添加 Trace 属性.
    
    Args:
        attributes: 属性字典
    """
    trace_id = get_current_trace_id()
    if not trace_id:
        return
    
    trace_store = get_trace_store()
    trace = trace_store.get_trace(trace_id)
    if trace and trace.spans:
        last_span = trace.spans[-1]
        last_span.attributes.update(attributes)


def get_trace_summary(trace_id: str) -> Optional[dict[str, Any]]:
    """
    获取 Trace 摘要.
    
    Args:
        trace_id: Trace ID
        
    Returns:
        Trace 摘要字典或 None
    """
    trace = get_trace_store().get_trace(trace_id)
    if not trace:
        return None
    
    total_duration_ms = 0.0
    if trace.end_timestamp_ms:
        total_duration_ms = trace.end_timestamp_ms - trace.start_timestamp_ms
    elif trace.spans:
        total_duration_ms = sum(
            (s.duration_ms or 0)
            for s in trace.spans
        )
    
    return {
        "trace_id": trace.trace_id,
        "span_count": len(trace.spans),
        "start_timestamp_ms": trace.start_timestamp_ms,
        "end_timestamp_ms": trace.end_timestamp_ms,
        "total_duration_ms": total_duration_ms,
        "spans": [
            {
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "name": s.name,
                "status": s.status,
                "duration_ms": s.duration_ms,
            }
            for s in trace.spans
        ],
    }


__all__ = [
    "Span",
    "Trace",
    "TraceStore",
    "get_trace_store",
    "reset_trace_store",
    "generate_trace_id",
    "generate_span_id",
    "get_current_trace_id",
    "get_current_span_id",
    "trace",
    "add_trace_attributes",
    "get_trace_summary",
]
