"""
层次协作(Hierarchical)测试.
"""

from __future__ import annotations

import pytest

from riskmonitor_multiagent.orchestration.hierarchical import (
    HierarchyLevel,
    TaskAssignment,
    HierarchicalCoordinator,
    get_hierarchical_coordinator,
    reset_hierarchical_coordinator,
)


class TestHierarchyLevel:
    """HierarchyLevel 测试."""

    def test_create_hierarchy_level(self) -> None:
        """测试创建层次."""
        level = HierarchyLevel(
            level_id="level_1",
            level_name="管理层",
            agents=["moderator"],
            responsibility="协调和决策",
        )
        
        assert level.level_id == "level_1"
        assert level.level_name == "管理层"
        assert level.agents == ["moderator"]
        assert level.responsibility == "协调和决策"
        assert level.parent_level is None


class TestTaskAssignment:
    """TaskAssignment 测试."""

    def test_create_task_assignment(self) -> None:
        """测试创建任务分配."""
        assignment = TaskAssignment(
            assignment_id="assign_001",
            task={"payload": {"content": "test"}},
            from_agent="moderator",
            to_agent="engineer",
        )
        
        assert assignment.assignment_id == "assign_001"
        assert assignment.from_agent == "moderator"
        assert assignment.to_agent == "engineer"
        assert assignment.status == "pending"
        assert assignment.result is None


class TestHierarchicalCoordinator:
    """HierarchicalCoordinator 测试."""

    def setup_method(self) -> None:
        """测试前重置."""
        reset_hierarchical_coordinator()
    
    def test_add_level(self) -> None:
        """测试添加层次."""
        coordinator = HierarchicalCoordinator()
        
        level = coordinator.add_level(
            level_id="level_1",
            level_name="管理层",
            agents=["moderator"],
            responsibility="协调和决策",
        )
        
        assert level.level_id == "level_1"
        assert coordinator.get_level("level_1") is not None
    
    def test_add_level_with_parent(self) -> None:
        """测试添加有父级的层次."""
        coordinator = HierarchicalCoordinator()
        
        coordinator.add_level(
            level_id="level_1",
            level_name="管理层",
            agents=["moderator"],
            responsibility="协调和决策",
        )
        
        coordinator.add_level(
            level_id="level_2",
            level_name="执行层",
            agents=["engineer", "analyst"],
            responsibility="执行任务",
            parent_level="level_1",
        )
        
        child_levels = coordinator.get_child_levels("level_1")
        assert len(child_levels) == 1
        assert child_levels[0].level_id == "level_2"
    
    def test_assign_task(self) -> None:
        """测试分配任务."""
        coordinator = HierarchicalCoordinator()
        
        assignment = coordinator.assign_task(
            task={"payload": {"content": "test"}},
            from_agent="moderator",
            to_agent="engineer",
        )
        
        assert assignment.assignment_id is not None
        assert len(coordinator._assignments) == 1
        assert assignment.status == "pending"
    
    def test_get_pending_assignments(self) -> None:
        """测试获取待处理任务分配."""
        coordinator = HierarchicalCoordinator()
        
        coordinator.assign_task(
            task={"payload": {"content": "test1"}},
            from_agent="moderator",
            to_agent="engineer",
        )
        
        coordinator.assign_task(
            task={"payload": {"content": "test2"}},
            from_agent="moderator",
            to_agent="analyst",
        )
        
        pending = coordinator.get_pending_assignments()
        assert len(pending) == 2
        
        engineer_pending = coordinator.get_pending_assignments("engineer")
        assert len(engineer_pending) == 1
    
    def test_get_hierarchy_summary(self) -> None:
        """测试获取层次摘要."""
        coordinator = HierarchicalCoordinator()
        
        coordinator.add_level(
            level_id="level_1",
            level_name="管理层",
            agents=["moderator"],
            responsibility="协调和决策",
        )
        
        coordinator.assign_task(
            task={"payload": {"content": "test"}},
            from_agent="moderator",
            to_agent="engineer",
        )
        
        summary = coordinator.get_hierarchy_summary()
        
        assert summary["total_assignments"] == 1
        assert summary["pending_assignments"] == 1
        assert len(summary["levels"]) == 1


class TestGlobalSingleton:
    """全局单例测试."""

    def test_get_hierarchical_coordinator(self) -> None:
        """测试获取全局单例."""
        reset_hierarchical_coordinator()
        
        coordinator1 = get_hierarchical_coordinator()
        coordinator2 = get_hierarchical_coordinator()
        
        assert coordinator1 is coordinator2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
