"""
契约定义包.

定义 Agent 输出、消息、记忆等数据结构的格式规范与验证.
"""

# Agent 输出契约 - 新版本常量
from riskmonitor_multiagent.contracts.agent_outputs import (
    CRITIC_VERSION,
    ORCHESTRATOR_VERSION,
    RISK_ANALYST_VERSION,
    SYSTEM_ENGINEER_VERSION,
    normalize_critic_review,
    normalize_orchestrator_output,
    normalize_risk_analyst_output,
    normalize_system_engineer_output,
    validate_critic_review,
    validate_orchestrator_output,
    validate_risk_analyst_output,
    validate_system_engineer_output,
)
from riskmonitor_multiagent.contracts.agent_messages import (
    AGENT_COMMAND_SCHEMA_VERSION,
    AGENT_RECEIPT_SCHEMA_VERSION,
    validate_agent_command,
    validate_agent_receipt,
)
from riskmonitor_multiagent.contracts.approval import (
    APPROVAL_RECORD_SCHEMA_VERSION,
    APPROVAL_REQUEST_SCHEMA_VERSION,
    build_approval_summary_text,
    ensure_approval_transition,
    normalize_approval_record,
    normalize_approval_request,
    validate_approval_record,
    validate_approval_request,
    validate_approval_transition,
)
from riskmonitor_multiagent.contracts.intent_output import (
    INTENT_OUTPUT_SCHEMA_VERSION,
    normalize_intent_output,
    validate_intent_output,
)
from riskmonitor_multiagent.contracts.memory_entry import (
    MEMORY_ENTRY_SCHEMA_VERSION,
    normalize_memory_entry,
    validate_memory_entry,
)
from riskmonitor_multiagent.contracts.event import (
    EVENT_SCHEMA_VERSION,
    EventType,
    normalize_event,
    validate_event,
    new_event,
)
from riskmonitor_multiagent.contracts.task_graph import (
    TASK_GRAPH_SCHEMA_VERSION,
    append_replan_subgraph,
    build_task_graph_from_plan_steps,
    normalize_task_graph,
    validate_task_graph,
)
from riskmonitor_multiagent.contracts.run_context import (
    RUN_CONTEXT_SCHEMA_VERSION,
    new_run_context,
    normalize_run_context,
    validate_run_context,
)
from riskmonitor_multiagent.contracts.run_trace import (
    RUN_TRACE_SCHEMA_VERSION,
    normalize_run_trace,
    validate_run_trace,
)

# 向后兼容的旧名称(测试依赖这些名称)
CRITIC_REVIEW_SCHEMA_VERSION = CRITIC_VERSION
ORCHESTRATOR_OUTPUT_SCHEMA_VERSION = ORCHESTRATOR_VERSION
RISK_ANALYST_OUTPUT_SCHEMA_VERSION = RISK_ANALYST_VERSION
SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION = SYSTEM_ENGINEER_VERSION

__all__ = [
    # Agent 输出 - 版本常量(旧名称)
    "CRITIC_REVIEW_SCHEMA_VERSION",
    "ORCHESTRATOR_OUTPUT_SCHEMA_VERSION",
    "RISK_ANALYST_OUTPUT_SCHEMA_VERSION",
    "SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION",
    # Agent 输出 - 验证函数
    "validate_system_engineer_output",
    "validate_risk_analyst_output",
    "validate_orchestrator_output",
    "validate_critic_review",
    # Agent 输出 - 归一化函数
    "normalize_system_engineer_output",
    "normalize_risk_analyst_output",
    "normalize_orchestrator_output",
    "normalize_critic_review",
    # Agent 消息
    "AGENT_COMMAND_SCHEMA_VERSION",
    "AGENT_RECEIPT_SCHEMA_VERSION",
    "validate_agent_command",
    "validate_agent_receipt",
    # Approval
    "APPROVAL_REQUEST_SCHEMA_VERSION",
    "APPROVAL_RECORD_SCHEMA_VERSION",
    "validate_approval_transition",
    "ensure_approval_transition",
    "validate_approval_request",
    "normalize_approval_request",
    "validate_approval_record",
    "normalize_approval_record",
    "build_approval_summary_text",
    # 意图输出
    "INTENT_OUTPUT_SCHEMA_VERSION",
    "validate_intent_output",
    "normalize_intent_output",
    # 记忆条目
    "MEMORY_ENTRY_SCHEMA_VERSION",
    "validate_memory_entry",
    "normalize_memory_entry",
    # Event
    "EVENT_SCHEMA_VERSION",
    "EventType",
    "validate_event",
    "normalize_event",
    "new_event",
    # RunContext
    "RUN_CONTEXT_SCHEMA_VERSION",
    "validate_run_context",
    "normalize_run_context",
    "new_run_context",
    # RunTrace
    "RUN_TRACE_SCHEMA_VERSION",
    "validate_run_trace",
    "normalize_run_trace",
    # TaskGraph
    "TASK_GRAPH_SCHEMA_VERSION",
    "append_replan_subgraph",
    "build_task_graph_from_plan_steps",
    "validate_task_graph",
    "normalize_task_graph",
]
