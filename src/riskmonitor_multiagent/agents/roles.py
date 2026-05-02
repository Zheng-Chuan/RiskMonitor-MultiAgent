from __future__ import annotations

from riskmonitor_multiagent.proactive_agents.roles import (
    ProactiveCriticAgent,
    ProactiveIntentAgent,
    ProactiveOrchestratorAgent,
    ProactiveRiskAnalystAgent,
    ProactiveSystemEngineerAgent,
)

# 旧测试仍引用 riskmonitor_multiagent.agents.roles
# 这里直接别名到当前真实使用的主动式 Agent 类
IntentAgent = ProactiveIntentAgent
OrchestratorAgent = ProactiveOrchestratorAgent
CriticAgent = ProactiveCriticAgent
SystemEngineerAgent = ProactiveSystemEngineerAgent
RiskAnalystAgent = ProactiveRiskAnalystAgent


__all__ = [
    "IntentAgent",
    "OrchestratorAgent",
    "CriticAgent",
    "SystemEngineerAgent",
    "RiskAnalystAgent",
]
