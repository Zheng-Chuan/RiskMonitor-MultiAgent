"""
Agent 模块.

保留 BaseAgent 和 AgentResult 供其他模块使用.
主动 Agent 请使用 proactive_agents 模块.
"""

from riskmonitor_multiagent.agents.base import AgentResult, BaseAgent

__all__ = ["AgentResult", "BaseAgent"]
