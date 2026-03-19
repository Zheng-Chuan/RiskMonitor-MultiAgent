"""
Hierarchical（层次协作）模式.

实现管理层协调和任务分发的层次协作模式.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class HierarchyLevel:
    """协作层次."""
    
    level_id: str
    level_name: str
    agents: list[str]
    responsibility: str
    parent_level: Optional[str] = None


@dataclass
class TaskAssignment:
    """任务分配记录."""
    
    assignment_id: str
    task: Any
    from_agent: str
    to_agent: str
    status: str = "pending"
    result: Optional[Any] = None
    timestamp_ms: int = field(default_factory=lambda: __import__('time').time_ns() // 1000000)


class HierarchicalCoordinator:
    """
    层次协作协调器.
    
    实现：
    - 层次结构定义
    - 任务分发
    - 结果汇总
    - 层级间通信
    """
    
    def __init__(self) -> None:
        """初始化层次协作协调器."""
        self._levels: dict[str, HierarchyLevel] = {}
        self._assignments: list[TaskAssignment] = []
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    def add_level(
        self,
        level_id: str,
        level_name: str,
        agents: list[str],
        responsibility: str,
        parent_level: Optional[str] = None,
    ) -> HierarchyLevel:
        """
        添加一个协作层次.
        
        Args:
            level_id: 层次 ID
            level_name: 层次名称
            agents: 该层次的 Agent 列表
            responsibility: 职责描述
            parent_level: 父层次 ID（可选）
            
        Returns:
            HierarchyLevel 对象
        """
        level = HierarchyLevel(
            level_id=level_id,
            level_name=level_name,
            agents=agents,
            responsibility=responsibility,
            parent_level=parent_level,
        )
        self._levels[level_id] = level
        logger.info(f"Added hierarchy level: {level_name} ({level_id})")
        return level

    def assign_task(
        self,
        task: Any,
        from_agent: str,
        to_agent: str,
    ) -> TaskAssignment:
        """
        分配任务.
        
        Args:
            task: 任务
            from_agent: 分配者 Agent
            to_agent: 接收者 Agent
            
        Returns:
            TaskAssignment 对象
        """
        import uuid
        assignment = TaskAssignment(
            assignment_id=str(uuid.uuid4())[:8],
            task=task,
            from_agent=from_agent,
            to_agent=to_agent,
            status="pending",
        )
        self._assignments.append(assignment)
        logger.info(f"Task assigned: {from_agent} -> {to_agent}")
        return assignment

    async def execute_assignment(
        self,
        assignment_id: str,
        executor_fn: Callable[[Any], Any],
    ) -> bool:
        """
        执行任务分配.
        
        Args:
            assignment_id: 任务分配 ID
            executor_fn: 执行函数
            
        Returns:
            是否成功执行
        """
        assignment = self._get_assignment(assignment_id)
        if not assignment:
            logger.warning(f"Assignment not found: {assignment_id}")
            return False
        
        assignment.status = "in_progress"
        logger.info(f"Executing assignment: {assignment_id}")
        
        try:
            result = executor_fn(assignment.task)
            assignment.result = result
            assignment.status = "completed"
            logger.info(f"Assignment completed: {assignment_id}")
            return True
        except Exception as e:
            assignment.status = "failed"
            logger.error(f"Assignment failed: {assignment_id}, error: {e}")
            return False

    def complete_assignment(
        self,
        assignment_id: str,
        result: Any,
    ) -> bool:
        """
        完成任务分配.
        
        Args:
            assignment_id: 任务分配 ID
            result: 结果
            
        Returns:
            是否成功完成
        """
        assignment = self._get_assignment(assignment_id)
        if not assignment:
            return False
        
        assignment.result = result
        assignment.status = "completed"
        return True

    def _get_assignment(self, assignment_id: str) -> Optional[TaskAssignment]:
        """获取任务分配."""
        for a in self._assignments:
            if a.assignment_id == assignment_id:
                return a
        return None

    def get_pending_assignments(self, agent_id: Optional[str] = None) -> list[TaskAssignment]:
        """
        获取待处理的任务分配.
        
        Args:
            agent_id: 可选 Agent 过滤
            
        Returns:
            待处理任务列表
        """
        pending = [a for a in self._assignments if a.status == "pending"]
        if agent_id:
            pending = [a for a in pending if a.to_agent == agent_id]
        return pending

    def get_level(self, level_id: str) -> Optional[HierarchyLevel]:
        """
        获取层次信息.
        
        Args:
            level_id: 层次 ID
            
        Returns:
            HierarchyLevel 或 None
        """
        return self._levels.get(level_id)

    def get_child_levels(self, parent_level_id: str) -> list[HierarchyLevel]:
        """
        获取子层次列表.
        
        Args:
            parent_level_id: 父层次 ID
            
        Returns:
            子层次列表
        """
        return [
            level for level in self._levels.values()
            if level.parent_level == parent_level_id
        ]

    async def start_monitor(
        self,
        check_interval_ms: int = 1000,
        on_assignment_pending: Optional[Callable[[TaskAssignment], None]] = None,
    ) -> None:
        """
        启动后台监控线程（真正的主动性）.
        
        Args:
            check_interval_ms: 检查间隔（毫秒）
            on_assignment_pending: 待处理任务回调
        """
        if self._running:
            logger.warning("Monitor already running")
            return
        
        self._running = True
        logger.info("Starting hierarchical monitor")
        
        async def monitor_loop() -> None:
            while self._running:
                try:
                    pending = self.get_pending_assignments()
                    if pending and on_assignment_pending:
                        for assignment in pending:
                            on_assignment_pending(assignment)
                except Exception as e:
                    logger.error(f"Monitor error: {e}")
                
                await asyncio.sleep(check_interval_ms / 1000.0)
        
        self._monitor_task = asyncio.create_task(monitor_loop())

    async def stop_monitor(self) -> None:
        """停止后台监控."""
        if not self._running:
            return
        
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Hierarchical monitor stopped")

    def get_hierarchy_summary(self) -> dict[str, Any]:
        """
        获取层次结构摘要.
        
        Returns:
            摘要字典
        """
        return {
            "levels": [
                {
                    "level_id": l.level_id,
                    "level_name": l.level_name,
                    "agents": l.agents,
                    "responsibility": l.responsibility,
                    "parent_level": l.parent_level,
                }
                for l in self._levels.values()
            ],
            "total_assignments": len(self._assignments),
            "pending_assignments": len(self.get_pending_assignments()),
            "monitor_running": self._running,
        }


_hierarchical_coordinator: Optional[HierarchicalCoordinator] = None


def get_hierarchical_coordinator() -> HierarchicalCoordinator:
    """获取全局层次协作协调器实例."""
    global _hierarchical_coordinator
    if _hierarchical_coordinator is None:
        _hierarchical_coordinator = HierarchicalCoordinator()
    return _hierarchical_coordinator


def reset_hierarchical_coordinator() -> None:
    """重置层次协作协调器（用于测试）."""
    global _hierarchical_coordinator
    _hierarchical_coordinator = None


__all__ = [
    "HierarchyLevel",
    "TaskAssignment",
    "HierarchicalCoordinator",
    "get_hierarchical_coordinator",
    "reset_hierarchical_coordinator",
]
