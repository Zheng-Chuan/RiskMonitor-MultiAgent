"""
主动 Agent 模块.

提供具备 BDI 模型、ReAct 循环和后台监控能力的 Agent.

核心特性：
1. BDI 模型：信念、愿望、意图
2. ReAct 循环：Thought → Reasoning → Action → Observation
3. CoT 思维链：每个步骤都有动态生成的 reason 和 evidence
4. 后台监控：主动感知环境变化并发起行为
"""

from riskmonitor_multiagent.proactive_agents.base import (
    BaseProactiveAgent,
    Belief,
    Desire,
    Intention,
    ReActStep,
    ProactiveAgentResult,
)
from riskmonitor_multiagent.proactive_agents.roles import (
    ProactiveIntentAgent,
    ProactiveOrchestratorAgent,
    ProactiveCriticAgent,
    ProactiveSystemEngineerAgent,
    ProactiveRiskAnalystAgent,
)

__all__ = [
    "BaseProactiveAgent",
    "Belief",
    "Desire",
    "Intention",
    "ReActStep",
    "ProactiveAgentResult",
    "ProactiveIntentAgent",
    "ProactiveOrchestratorAgent",
    "ProactiveCriticAgent",
    "ProactiveSystemEngineerAgent",
    "ProactiveRiskAnalystAgent",
]
