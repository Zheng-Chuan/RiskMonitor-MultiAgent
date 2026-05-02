from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from riskmonitor_multiagent.contracts.event import EventType, new_event


@dataclass
class RefinementStep:
    """单次迭代优化记录."""

    step_id: str
    step_type: str
    agent: str
    input_content: dict[str, Any]
    output_content: dict[str, Any]
    feedback: str | None = None
    revision_count: int = 0


@dataclass
class Conflict:
    """冲突记录."""

    conflict_id: str
    agent_a: str
    agent_b: str
    description: str
    conflict_type: str = "conclusion_conflict"
    candidates: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolution: str | None = None


@dataclass
class ArbitrationDecision:
    """仲裁结果."""

    conflict_id: str
    selected_agent: str
    resolution: str
    decision_source: str
    rule_name: str
    event_type: str
    discarded_candidates: list[dict[str, Any]] = field(default_factory=list)
    discarded_path_reason: str | None = None


class IterativeRefinementEngine:
    """最小可测的迭代优化引擎."""

    def __init__(self) -> None:
        self._conflicts: list[Conflict] = []
        self._conflict_trace: list[dict[str, Any]] = []

    async def run_iterative_refinement(
        self,
        *,
        initial_input: dict[str, Any],
        agent_fn: Callable[[dict[str, Any]], dict[str, Any]],
        critic_fn: Callable[[dict[str, Any]], tuple[bool, str, list[str]]],
        max_iterations: int = 3,
    ) -> tuple[dict[str, Any], list[RefinementStep]]:
        steps: list[RefinementStep] = []
        current = initial_input
        for index in range(max_iterations):
            output = agent_fn(current)
            accepted, feedback, _issues = critic_fn(output)
            steps.append(
                RefinementStep(
                    step_id=f"refine_{index + 1}",
                    step_type="refine",
                    agent="refiner",
                    input_content=current,
                    output_content=output,
                    feedback=feedback,
                    revision_count=index,
                )
            )
            current = output
            if accepted:
                break
        return current, steps

    async def run_review_and_revise(
        self,
        *,
        initial_output: dict[str, Any],
        reviewer_fn: Callable[[dict[str, Any]], tuple[bool, str, list[str]]],
        reviser_fn: Callable[[dict[str, Any], list[str]], dict[str, Any]],
        max_revisions: int = 3,
    ) -> tuple[dict[str, Any], list[RefinementStep]]:
        steps: list[RefinementStep] = []
        current = initial_output
        for index in range(max_revisions):
            accepted, feedback, issues = reviewer_fn(current)
            steps.append(
                RefinementStep(
                    step_id=f"review_{index + 1}",
                    step_type="review",
                    agent="reviewer",
                    input_content=current,
                    output_content=current,
                    feedback=feedback,
                    revision_count=index,
                )
            )
            if accepted:
                break
            current = reviser_fn(current, issues)
        return current, steps

    def record_conflict(self, agent_a: str, agent_b: str, description: str) -> Conflict:
        conflict = Conflict(
            conflict_id=f"conflict_{uuid.uuid4().hex[:8]}",
            agent_a=agent_a,
            agent_b=agent_b,
            description=description,
        )
        self._conflicts.append(conflict)
        return conflict

    def detect_conflict(
        self,
        *,
        proposals: list[dict[str, Any]],
        conflict_type: str,
        description: str,
    ) -> Conflict | None:
        """从多个 proposal 中检测冲突."""
        if len(proposals) < 2:
            return None
        normalized = [proposal for proposal in proposals if isinstance(proposal, dict)]
        if len(normalized) < 2:
            return None

        values = {
            str(
                proposal.get("value")
                or proposal.get("tool_name")
                or proposal.get("summary")
                or proposal.get("decision")
            )
            for proposal in normalized
        }
        if len(values) <= 1:
            return None

        conflict = Conflict(
            conflict_id=f"conflict_{uuid.uuid4().hex[:8]}",
            agent_a=str(normalized[0].get("agent") or "unknown"),
            agent_b=str(normalized[1].get("agent") or "unknown"),
            description=description,
            conflict_type=conflict_type,
            candidates=sorted(
                {
                    str(proposal.get("agent"))
                    for proposal in normalized
                    if isinstance(proposal.get("agent"), str) and proposal.get("agent")
                }
            ),
            evidence={"proposals": normalized},
        )
        self._conflicts.append(conflict)
        self._conflict_trace.append(
            {
                "trace_type": "conflict_detected",
                "conflict_id": conflict.conflict_id,
                "conflict_type": conflict.conflict_type,
                "description": conflict.description,
                "candidates": list(conflict.candidates),
                "evidence": dict(conflict.evidence),
            }
        )
        return conflict

    async def arbitrate_conflict(
        self,
        *,
        conflict_id: str,
        moderator: Any,
        context: dict[str, Any] | None = None,
    ) -> ArbitrationDecision:
        """调用 moderator 做显式仲裁."""
        conflict = next((item for item in self._conflicts if item.conflict_id == conflict_id), None)
        if conflict is None:
            raise ValueError(f"unknown_conflict:{conflict_id}")

        event_type = self._map_conflict_event(conflict.conflict_type)
        event = new_event(
            event_type=event_type,
            source_agent="iterative_refinement",
            payload={
                "conflict_id": conflict.conflict_id,
                "description": conflict.description,
                "conflict_type": conflict.conflict_type,
                "evidence": conflict.evidence,
            },
        )
        message_bus = getattr(moderator, "_message_bus", None)
        if message_bus is not None:
            await message_bus.publish_event(event)
        decision = await moderator.moderate(
            event=event,
            candidate_agents=conflict.candidates or [conflict.agent_a, conflict.agent_b],
            conflict={
                "conflict_id": conflict.conflict_id,
                "conflict_type": conflict.conflict_type,
                "description": conflict.description,
            },
            context=context or {},
        )
        conflict.resolved = True
        conflict.resolution = str(decision.get("reason") or "arbitrated")
        arbitration_trace = {
            "trace_type": "arbitration_resolved",
            "conflict_id": conflict.conflict_id,
            "selected_agent": decision.get("selected_agent"),
            "decision_source": decision.get("decision_source"),
            "rule_name": decision.get("rule_name"),
            "discarded_candidates": decision.get("discarded_candidates", []),
            "discarded_path_reason": decision.get("discarded_path_reason"),
        }
        self._conflict_trace.append(arbitration_trace)
        return ArbitrationDecision(
            conflict_id=conflict.conflict_id,
            selected_agent=str(decision.get("selected_agent") or ""),
            resolution=str(decision.get("reason") or ""),
            decision_source=str(decision.get("decision_source") or "unknown"),
            rule_name=str(decision.get("rule_name") or "unknown"),
            event_type=str(event.get("event_type") or ""),
            discarded_candidates=list(decision.get("discarded_candidates", []) or []),
            discarded_path_reason=(
                str(decision.get("discarded_path_reason"))
                if isinstance(decision.get("discarded_path_reason"), str)
                else None
            ),
        )

    def resolve_conflict(self, conflict_id: str, resolution: str) -> bool:
        for conflict in self._conflicts:
            if conflict.conflict_id == conflict_id:
                conflict.resolved = True
                conflict.resolution = resolution
                return True
        return False

    def get_unresolved_conflicts(self) -> list[Conflict]:
        return [conflict for conflict in self._conflicts if not conflict.resolved]

    def get_refinement_trace(self) -> str:
        return (
            f"Total conflicts: {len(self._conflicts)}\n"
            f"Unresolved conflicts: {len(self.get_unresolved_conflicts())}"
        )

    def get_conflict_trace(self) -> list[dict[str, Any]]:
        """返回结构化冲突与仲裁 trace."""
        return list(self._conflict_trace)

    def _map_conflict_event(self, conflict_type: str) -> EventType:
        if conflict_type == "approval_priority_conflict":
            return EventType.APPROVAL_REQUIRED
        if conflict_type == "tool_selection_conflict":
            return EventType.TOOL_FINISHED
        if conflict_type == "conclusion_conflict":
            return EventType.CONFLICT_DETECTED
        return EventType.CONFLICT_DETECTED


_REFINEMENT_ENGINE: IterativeRefinementEngine | None = None


def get_refinement_engine() -> IterativeRefinementEngine:
    global _REFINEMENT_ENGINE
    if _REFINEMENT_ENGINE is None:
        _REFINEMENT_ENGINE = IterativeRefinementEngine()
    return _REFINEMENT_ENGINE


def reset_refinement_engine() -> None:
    global _REFINEMENT_ENGINE
    _REFINEMENT_ENGINE = None


__all__ = [
    "RefinementStep",
    "Conflict",
    "ArbitrationDecision",
    "IterativeRefinementEngine",
    "get_refinement_engine",
    "reset_refinement_engine",
]
