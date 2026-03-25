"""
详细执行轨迹模块.

用于完整记录每个 Agent 的执行过程, 包括:
- LLM 交互记录 (输入/输出/tokens/cost)
- ReAct 步骤详情
- BDI 状态变化
- 时间戳信息
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def get_timestamp_ms() -> int:
    """获取当前时间戳 (毫秒)."""
    return int(time.time() * 1000)


def get_iso_timestamp() -> str:
    """获取 ISO 8601 格式的时间戳."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LLMInteraction:
    """单次 LLM 交互记录."""
    
    timestamp_ms: int
    agent_name: str
    interaction_type: str
    
    system_prompt: str = ""
    user_prompt: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 1024
    
    raw_response: str = ""
    parsed_output: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    
    success: bool = True
    error: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return {
            "timestamp_ms": self.timestamp_ms,
            "agent_name": self.agent_name,
            "interaction_type": self.interaction_type,
            "system_prompt": self.system_prompt[:500] if self.system_prompt else "",
            "user_prompt": self.user_prompt[:1000] if self.user_prompt else "",
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "raw_response": self.raw_response[:2000] if self.raw_response else "",
            "parsed_output": self.parsed_output,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class AgentExecution:
    """单个 Agent 的完整执行记录."""
    
    agent_name: str
    agent_role: str
    
    start_time_ms: int = 0
    end_time_ms: int = 0
    duration_ms: int = 0
    
    initial_bdi_state: dict[str, Any] = field(default_factory=dict)
    final_bdi_state: dict[str, Any] = field(default_factory=dict)
    
    react_steps: list[dict[str, Any]] = field(default_factory=list)
    llm_interactions: list[LLMInteraction] = field(default_factory=list)
    
    output: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "start_time_ms": self.start_time_ms,
            "end_time_ms": self.end_time_ms,
            "duration_ms": self.duration_ms,
            "initial_bdi_state": self.initial_bdi_state,
            "final_bdi_state": self.final_bdi_state,
            "react_steps": self.react_steps,
            "llm_interactions": [i.to_dict() for i in self.llm_interactions],
            "output": self.output,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class DetailedTrace:
    """完整的执行轨迹 (用于调试和分析)."""
    
    run_id: str
    case_id: str
    timestamp_start: str = ""
    timestamp_end: str = ""
    
    task: dict[str, Any] = field(default_factory=dict)
    ground_truth: dict[str, Any] = field(default_factory=dict)
    
    overall_success: bool = False
    error: str | None = None
    
    agent_executions: dict[str, AgentExecution] = field(default_factory=dict)
    
    total_llm_calls: int = 0
    total_tokens_used: int = 0
    total_cost_usd: float = 0.0
    
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "task": self.task,
            "ground_truth": self.ground_truth,
            "overall_success": self.overall_success,
            "error": self.error,
            "agent_executions": {
                name: exec.to_dict() for name, exec in self.agent_executions.items()
            },
            "total_llm_calls": self.total_llm_calls,
            "total_tokens_used": self.total_tokens_used,
            "total_cost_usd": self.total_cost_usd,
            "tool_calls": self.tool_calls,
            "messages": self.messages,
        }
    
    def add_agent_execution(self, execution: AgentExecution) -> None:
        """添加 Agent 执行记录."""
        self.agent_executions[execution.agent_name] = execution
        self.total_llm_calls += len(execution.llm_interactions)
        self.total_tokens_used += sum(i.tokens_used for i in execution.llm_interactions)
        self.total_cost_usd += sum(i.cost_usd for i in execution.llm_interactions)


__all__ = [
    "LLMInteraction",
    "AgentExecution",
    "DetailedTrace",
    "get_timestamp_ms",
    "get_iso_timestamp",
]
