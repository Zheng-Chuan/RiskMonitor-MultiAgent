"""
支持消息模式的 Agent 角色定义.

基于现有 Agent，添加消息总线支持.
"""

from __future__ import annotations

from typing import Any, Optional

from riskmonitor_multiagent.agents.base import AgentResult, BaseAgent
from riskmonitor_multiagent.agents.message_agent import MessageEnabledAgent
from riskmonitor_multiagent.agents.roles import (
    CriticAgent as OriginalCriticAgent,
    IntentAgent as OriginalIntentAgent,
    OrchestratorAgent as OriginalOrchestratorAgent,
    RiskAnalystAgent as OriginalRiskAnalystAgent,
    SystemEngineerAgent as OriginalSystemEngineerAgent,
)
from riskmonitor_multiagent.contracts import (
    INTENT_OUTPUT_SCHEMA_VERSION,
    RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
    SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
    normalize_critic_review,
    normalize_intent_output,
    normalize_orchestrator_output,
    normalize_risk_analyst_output,
    normalize_system_engineer_output,
    validate_critic_review,
    validate_intent_output,
    validate_orchestrator_output,
    validate_risk_analyst_output,
    validate_system_engineer_output,
)
from riskmonitor_multiagent.governance.versions import (
    PROMPT_VERSION_CRITIC,
    PROMPT_VERSION_INTENT,
    PROMPT_VERSION_ORCHESTRATOR,
    PROMPT_VERSION_RISK_ANALYST,
    PROMPT_VERSION_SYSTEM_ENGINEER,
    get_policy_version,
)
from riskmonitor_multiagent.orchestration.intent_heuristics import (
    guess_risk_level,
    guess_side_effects,
)
from riskmonitor_multiagent.orchestration.message_bus import MessageBus, get_message_bus
from riskmonitor_multiagent.utils import truncate_context

import logging

logger = logging.getLogger(__name__)


class MessageEnabledIntentAgent(MessageEnabledAgent):
    """支持消息模式的 Intent Agent."""

    def __init__(
        self,
        *,
        message_bus: Optional[MessageBus] = None,
    ) -> None:
        self._original_agent = OriginalIntentAgent()
        super().__init__(
            agent_id="intent",
            base_agent=self._original_agent._agent,
            message_bus=message_bus,
        )

    async def _handle_request(self, message: dict[str, Any], content: dict[str, Any]) -> None:
        """处理请求消息."""
        task = content.get("task")
        metadata = content.get("metadata")
        max_tokens = content.get("max_tokens")

        if not task:
            await self._send_response(
                message=message,
                content={"ok": False, "error": "missing_task"},
            )
            return

        try:
            result = await self._original_agent.recognize(
                task=task,
                metadata=metadata,
                max_tokens=max_tokens,
            )
            await self._send_response(
                message=message,
                content={"ok": result.ok, "output": result.output, "usage": result.usage, "meta": result.meta},
            )
        except Exception as e:
            logger.error(f"IntentAgent error: {e}")
            await self._send_response(
                message=message,
                content={"ok": False, "error": str(e)},
            )


class MessageEnabledOrchestratorAgent(MessageEnabledAgent):
    """支持消息模式的 Orchestrator Agent."""

    def __init__(
        self,
        *,
        message_bus: Optional[MessageBus] = None,
    ) -> None:
        self._original_agent = OriginalOrchestratorAgent()
        super().__init__(
            agent_id="orchestrator",
            base_agent=self._original_agent._agent,
            message_bus=message_bus,
        )

    async def _handle_request(self, message: dict[str, Any], content: dict[str, Any]) -> None:
        """处理请求消息."""
        task = content.get("task")
        context = content.get("conversation_history")
        max_tokens = content.get("max_tokens")

        if not task:
            await self._send_response(
                message=message,
                content={"ok": False, "error": "missing_task"},
            )
            return

        try:
            result = await self._original_agent.orchestrate(
                task=task,
                context=context,
                max_tokens=max_tokens,
            )
            await self._send_response(
                message=message,
                content={"ok": result.ok, "output": result.output, "usage": result.usage, "meta": result.meta},
            )
        except Exception as e:
            logger.error(f"OrchestratorAgent error: {e}")
            await self._send_response(
                message=message,
                content={"ok": False, "error": str(e)},
            )


class MessageEnabledCriticAgent(MessageEnabledAgent):
    """支持消息模式的 Critic Agent."""

    def __init__(
        self,
        *,
        message_bus: Optional[MessageBus] = None,
    ) -> None:
        self._original_agent = OriginalCriticAgent()
        super().__init__(
            agent_id="critic",
            base_agent=self._original_agent._agent,
            message_bus=message_bus,
        )

    async def _handle_request(self, message: dict[str, Any], content: dict[str, Any]) -> None:
        """处理请求消息."""
        task = content.get("task")
        orchestrator = content.get("orchestrator")
        engineer = content.get("engineer")
        analyst = content.get("analyst")
        receipts = content.get("receipts")
        max_tokens = content.get("max_tokens")

        if not task:
            await self._send_response(
                message=message,
                content={"ok": False, "error": "missing_task"},
            )
            return

        try:
            result = await self._original_agent.review(
                task=task,
                orchestrator=orchestrator,
                engineer=engineer,
                analyst=analyst,
                receipts=receipts,
                max_tokens=max_tokens,
            )
            await self._send_response(
                message=message,
                content={"ok": result.ok, "output": result.output, "usage": result.usage, "meta": result.meta},
            )
        except Exception as e:
            logger.error(f"CriticAgent error: {e}")
            await self._send_response(
                message=message,
                content={"ok": False, "error": str(e)},
            )


class MessageEnabledSystemEngineerAgent(MessageEnabledAgent):
    """支持消息模式的 System Engineer Agent."""

    def __init__(
        self,
        *,
        message_bus: Optional[MessageBus] = None,
    ) -> None:
        self._original_agent = OriginalSystemEngineerAgent()
        super().__init__(
            agent_id="system_engineer",
            base_agent=self._original_agent._agent,
            message_bus=message_bus,
        )

    async def _handle_request(self, message: dict[str, Any], content: dict[str, Any]) -> None:
        """处理请求消息."""
        task = content.get("task")
        context = content.get("conversation_history")
        max_tokens = content.get("max_tokens")

        if not task:
            await self._send_response(
                message=message,
                content={"ok": False, "error": "missing_task"},
            )
            return

        try:
            result = await self._original_agent.analyze_task(
                task=task,
                context=context,
                max_tokens=max_tokens,
            )
            await self._send_response(
                message=message,
                content={"ok": result.ok, "output": result.output, "usage": result.usage, "meta": result.meta},
            )
        except Exception as e:
            logger.error(f"SystemEngineerAgent error: {e}")
            await self._send_response(
                message=message,
                content={"ok": False, "error": str(e)},
            )


class MessageEnabledRiskAnalystAgent(MessageEnabledAgent):
    """支持消息模式的 Risk Analyst Agent."""

    def __init__(
        self,
        *,
        message_bus: Optional[MessageBus] = None,
    ) -> None:
        self._original_agent = OriginalRiskAnalystAgent()
        super().__init__(
            agent_id="risk_analyst",
            base_agent=self._original_agent._agent,
            message_bus=message_bus,
        )

    async def _handle_request(self, message: dict[str, Any], content: dict[str, Any]) -> None:
        """处理请求消息."""
        task = content.get("task")
        context = content.get("conversation_history")
        max_tokens = content.get("max_tokens")

        if not task:
            await self._send_response(
                message=message,
                content={"ok": False, "error": "missing_task"},
            )
            return

        try:
            result = await self._original_agent.analyze_task(
                task=task,
                context=context,
                max_tokens=max_tokens,
            )
            await self._send_response(
                message=message,
                content={"ok": result.ok, "output": result.output, "usage": result.usage, "meta": result.meta},
            )
        except Exception as e:
            logger.error(f"RiskAnalystAgent error: {e}")
            await self._send_response(
                message=message,
                content={"ok": False, "error": str(e)},
            )


def create_all_message_enabled_agents(
    message_bus: Optional[MessageBus] = None,
) -> dict[str, MessageEnabledAgent]:
    """
    创建所有支持消息模式的 Agent.

    Args:
        message_bus: 可选的 MessageBus 实例

    Returns:
        Agent ID 到 Agent 实例的映射
    """
    bus = message_bus or get_message_bus()
    return {
        "intent": MessageEnabledIntentAgent(message_bus=bus),
        "orchestrator": MessageEnabledOrchestratorAgent(message_bus=bus),
        "critic": MessageEnabledCriticAgent(message_bus=bus),
        "system_engineer": MessageEnabledSystemEngineerAgent(message_bus=bus),
        "risk_analyst": MessageEnabledRiskAnalystAgent(message_bus=bus),
    }
