from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class HierarchyLevel:
    """层次定义."""

    level_id: str
    level_name: str
    agents: list[str]
    responsibility: str
    parent_level: str | None = None


@dataclass
class TaskAssignment:
    """任务分配记录."""

    assignment_id: str
    task: dict[str, Any]
    from_agent: str
    to_agent: str
    status: str = "pending"
    result: dict[str, Any] | None = None


class HierarchicalCoordinator:
    """最小层级协调器."""

    def __init__(self) -> None:
        self._levels: dict[str, HierarchyLevel] = {}
        self._assignments: list[TaskAssignment] = []

    def add_level(
        self,
        *,
        level_id: str,
        level_name: str,
        agents: list[str],
        responsibility: str,
        parent_level: str | None = None,
    ) -> HierarchyLevel:
        level = HierarchyLevel(
            level_id=level_id,
            level_name=level_name,
            agents=list(agents),
            responsibility=responsibility,
            parent_level=parent_level,
        )
        self._levels[level_id] = level
        return level

    def get_level(self, level_id: str) -> HierarchyLevel | None:
        return self._levels.get(level_id)

    def get_child_levels(self, parent_level: str) -> list[HierarchyLevel]:
        return [level for level in self._levels.values() if level.parent_level == parent_level]

    def assign_task(self, *, task: dict[str, Any], from_agent: str, to_agent: str) -> TaskAssignment:
        assignment = TaskAssignment(
            assignment_id=f"assign_{uuid.uuid4().hex[:8]}",
            task=task,
            from_agent=from_agent,
            to_agent=to_agent,
        )
        self._assignments.append(assignment)
        return assignment

    def get_pending_assignments(self, to_agent: str | None = None) -> list[TaskAssignment]:
        assignments = [assignment for assignment in self._assignments if assignment.status == "pending"]
        if to_agent is not None:
            assignments = [assignment for assignment in assignments if assignment.to_agent == to_agent]
        return assignments

    def get_hierarchy_summary(self) -> dict[str, Any]:
        pending = self.get_pending_assignments()
        return {
            "total_assignments": len(self._assignments),
            "pending_assignments": len(pending),
            "levels": [level.__dict__ for level in self._levels.values()],
        }


_HIERARCHICAL_COORDINATOR: HierarchicalCoordinator | None = None


def get_hierarchical_coordinator() -> HierarchicalCoordinator:
    global _HIERARCHICAL_COORDINATOR
    if _HIERARCHICAL_COORDINATOR is None:
        _HIERARCHICAL_COORDINATOR = HierarchicalCoordinator()
    return _HIERARCHICAL_COORDINATOR


def reset_hierarchical_coordinator() -> None:
    global _HIERARCHICAL_COORDINATOR
    _HIERARCHICAL_COORDINATOR = None


__all__ = [
    "HierarchyLevel",
    "TaskAssignment",
    "HierarchicalCoordinator",
    "get_hierarchical_coordinator",
    "reset_hierarchical_coordinator",
]
