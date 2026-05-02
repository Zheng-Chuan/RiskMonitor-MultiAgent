"""
ModeratorAgent.

规则优先做调度和仲裁, 只有规则无法唯一决定时才调用 LLM tie breaker.
"""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

from riskmonitor_multiagent.contracts.event import EventType
from riskmonitor_multiagent.orchestration.message_bus import MessageBus
from riskmonitor_multiagent.utils.time import now_ms

TieBreaker = Callable[[dict[str, Any], list[str], dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


class ModeratorAgent:
    """规则优先的 moderator."""

    def __init__(
        self,
        *,
        llm_tie_breaker: TieBreaker | None = None,
        message_bus: MessageBus | None = None,
    ) -> None:
        self._llm_tie_breaker = llm_tie_breaker
        self._message_bus = message_bus
        self._decision_history: list[dict[str, Any]] = []

    async def moderate(
        self,
        *,
        event: dict[str, Any],
        candidate_agents: list[str],
        conflict: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """根据事件和冲突上下文决定下一跳 agent."""
        decision = self._apply_rules(
            event=event,
            candidate_agents=candidate_agents,
            conflict=conflict or {},
            context=context or {},
        )
        if decision is None:
            decision = await self._break_tie(
                event=event,
                candidate_agents=candidate_agents,
                conflict=conflict or {},
                context=context or {},
            )

        self._decision_history.append(decision)
        if self._message_bus is not None:
            await self._message_bus.emit_event(
                event_type=EventType.MODERATOR_DECISION,
                source_agent="moderator",
                target_agent=decision.get("selected_agent"),
                payload=decision,
                correlation_id=event.get("correlation_id") or event.get("event_id"),
                causation_id=event.get("event_id"),
                priority="high" if decision.get("selected_agent") == "human" else "normal",
            )
            if decision.get("conflict_id") or decision.get("conflict_type"):
                await self._message_bus.emit_event(
                    event_type=EventType.ARBITRATION_RESOLVED,
                    source_agent="moderator",
                    target_agent=decision.get("selected_agent"),
                    payload=decision,
                    correlation_id=event.get("correlation_id") or event.get("event_id"),
                    causation_id=event.get("event_id"),
                    priority="high" if decision.get("selected_agent") == "human" else "normal",
                )
        return dict(decision)

    def get_decision_history(self) -> list[dict[str, Any]]:
        """返回 moderator 决策历史."""
        return list(self._decision_history)

    def _apply_rules(
        self,
        *,
        event: dict[str, Any],
        candidate_agents: list[str],
        conflict: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not candidate_agents:
            return self._build_decision(
                selected_agent="human",
                reason="没有可用 agent, 升级到人工处理",
                decision_source="rule",
                rule_name="empty_candidates_escalate",
                event=event,
                candidate_agents=candidate_agents,
                conflict=conflict,
                context=context,
            )

        unique_candidates = sorted(set(candidate_agents))
        if len(unique_candidates) == 1:
            return self._build_decision(
                selected_agent=unique_candidates[0],
                reason="只有一个候选 agent",
                decision_source="rule",
                rule_name="single_candidate",
                event=event,
                candidate_agents=unique_candidates,
                conflict=conflict,
                context=context,
            )

        event_type = str(event.get("event_type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        conflict_type = str(conflict.get("conflict_type") or "")

        if event_type == EventType.APPROVAL_REQUIRED.value or conflict_type == "approval_priority_conflict":
            return self._prefer_agent(
                preferred_agents=["human", "critic"],
                fallback_agents=unique_candidates,
                reason="审批事件优先升级人工或评审",
                rule_name="approval_priority",
                event=event,
                conflict=conflict,
                context=context,
            )

        if event_type == EventType.RISK_BREACH_DETECTED.value:
            return self._prefer_agent(
                preferred_agents=["risk_analyst", "critic"],
                fallback_agents=unique_candidates,
                reason="风险 breach 优先交给风险分析和评审",
                rule_name="risk_breach_priority",
                event=event,
                conflict=conflict,
                context=context,
            )

        if event_type == EventType.TOOL_FINISHED.value and payload.get("success") is False:
            return self._prefer_agent(
                preferred_agents=["system_engineer", "critic"],
                fallback_agents=unique_candidates,
                reason="工具失败优先交给系统工程师排障",
                rule_name="tool_failure_priority",
                event=event,
                conflict=conflict,
                context=context,
            )

        if event_type == EventType.TASK_CREATED.value:
            return self._prefer_agent(
                preferred_agents=["orchestrator"],
                fallback_agents=unique_candidates,
                reason="新任务先交给 orchestrator 规划",
                rule_name="task_created_priority",
                event=event,
                conflict=conflict,
                context=context,
            )

        if event_type == EventType.HUMAN_FEEDBACK_RECEIVED.value:
            return self._prefer_agent(
                preferred_agents=["critic", "orchestrator"],
                fallback_agents=unique_candidates,
                reason="人工反馈优先触发评审或重规划",
                rule_name="human_feedback_priority",
                event=event,
                conflict=conflict,
                context=context,
            )

        if conflict_type == "tool_selection_conflict":
            return self._prefer_agent(
                preferred_agents=["system_engineer"],
                fallback_agents=unique_candidates,
                reason="工具选择冲突优先交给系统工程师",
                rule_name="tool_selection_conflict",
                event=event,
                conflict=conflict,
                context=context,
            )

        if conflict_type == "conclusion_conflict":
            return self._prefer_agent(
                preferred_agents=["critic"],
                fallback_agents=unique_candidates,
                reason="结论冲突优先交给 critic 仲裁",
                rule_name="conclusion_conflict",
                event=event,
                conflict=conflict,
                context=context,
            )
        return None

    async def _break_tie(
        self,
        *,
        event: dict[str, Any],
        candidate_agents: list[str],
        conflict: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        unique_candidates = sorted(set(candidate_agents))
        if self._llm_tie_breaker is not None:
            result = self._llm_tie_breaker(event, unique_candidates, {"conflict": conflict, "context": context})
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, dict) and result.get("selected_agent") in unique_candidates:
                return self._build_decision(
                    selected_agent=str(result.get("selected_agent")),
                    reason=str(result.get("reason") or "LLM tie breaker 选择下一跳"),
                    decision_source="llm_tie_breaker",
                    rule_name="llm_tie_breaker",
                    event=event,
                    candidate_agents=unique_candidates,
                    conflict=conflict,
                    context=context,
                    extra={
                        "tie_breaker_output": dict(result),
                    },
                )

        return self._build_decision(
            selected_agent=unique_candidates[0],
            reason="规则无法唯一决定, 使用稳定降级策略选择首个候选",
            decision_source="fallback",
            rule_name="stable_fallback",
            event=event,
            candidate_agents=unique_candidates,
            conflict=conflict,
            context=context,
            extra={"degraded": True},
        )

    def _prefer_agent(
        self,
        *,
        preferred_agents: list[str],
        fallback_agents: list[str],
        reason: str,
        rule_name: str,
        event: dict[str, Any],
        conflict: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        for agent in preferred_agents:
            if agent in fallback_agents:
                return self._build_decision(
                    selected_agent=agent,
                    reason=reason,
                    decision_source="rule",
                    rule_name=rule_name,
                    event=event,
                    candidate_agents=fallback_agents,
                    conflict=conflict,
                    context=context,
                )
        return self._build_decision(
            selected_agent=fallback_agents[0],
            reason=f"{reason}, 但首选角色不可用, 选择首个候选",
            decision_source="rule",
            rule_name=f"{rule_name}_fallback",
            event=event,
            candidate_agents=fallback_agents,
            conflict=conflict,
            context=context,
        )

    def _build_decision(
        self,
        *,
        selected_agent: str,
        reason: str,
        decision_source: str,
        rule_name: str,
        event: dict[str, Any],
        candidate_agents: list[str],
        conflict: dict[str, Any],
        context: dict[str, Any],
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        decision = {
            "decision_id": f"moderator_{now_ms()}",
            "selected_agent": selected_agent,
            "reason": reason,
            "decision_source": decision_source,
            "rule_name": rule_name,
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "candidate_agents": list(candidate_agents),
            "discarded_candidates": [
                {
                    "agent": agent,
                    "reason": f"未被选中, 由 {rule_name} 放弃",
                }
                for agent in candidate_agents
                if agent != selected_agent
            ],
            "discarded_path_reason": f"{rule_name}:{reason}",
            "conflict_id": conflict.get("conflict_id"),
            "conflict_type": conflict.get("conflict_type"),
            "context_summary": self._build_context_summary(context),
            "timestamp_ms": now_ms(),
        }
        if extra:
            decision.update(extra)
        return decision

    def _build_context_summary(self, context: dict[str, Any]) -> dict[str, Any]:
        """压缩上下文, 便于 trace 与 replay."""
        summary: dict[str, Any] = {}
        for key in ("run_id", "entry_type"):
            if isinstance(context.get(key), str) and context.get(key):
                summary[key] = context.get(key)
        if isinstance(context.get("task"), dict):
            task = context.get("task", {})
            summary["task_id"] = task.get("task_id")
        return summary


__all__ = ["ModeratorAgent"]
