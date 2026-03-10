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

# 向后兼容的旧名称（测试依赖这些名称）
CRITIC_REVIEW_SCHEMA_VERSION = CRITIC_VERSION
ORCHESTRATOR_OUTPUT_SCHEMA_VERSION = ORCHESTRATOR_VERSION
RISK_ANALYST_OUTPUT_SCHEMA_VERSION = RISK_ANALYST_VERSION
SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION = SYSTEM_ENGINEER_VERSION

__all__ = [
    # Agent 输出 - 版本常量（旧名称）
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
    # 意图输出
    "INTENT_OUTPUT_SCHEMA_VERSION",
    "validate_intent_output",
    "normalize_intent_output",
    # 记忆条目
    "MEMORY_ENTRY_SCHEMA_VERSION",
    "validate_memory_entry",
    "normalize_memory_entry",
]
