"""
Agent 的 BDI（信念、愿望、意图）模型.

实现 Agent 的主动性和目标导向行为.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from riskmonitor_multiagent.utils.ids import new_run_id


@dataclass
class Belief:
    """Agent 的信念：Agent 认为世界的状态."""
    
    content: Any
    source: str
    confidence: float = 1.0
    belief_id: str = field(default_factory=lambda: f"belief_{uuid.uuid4().hex[:8]}")
    timestamp_ms: int = field(default_factory=lambda: __import__('time').time_ns() // 1000000)


@dataclass
class Desire:
    """Agent 的愿望：Agent 想要达到的状态."""
    
    description: str
    priority: int = 0
    active: bool = True
    desire_id: str = field(default_factory=lambda: f"desire_{uuid.uuid4().hex[:8]}")


@dataclass
class Intention:
    """Agent 的意图：Agent 承诺要执行的行动."""
    
    description: str
    target_agent: Optional[str] = None
    tool_name: Optional[str] = None
    tool_params: Optional[dict[str, Any]] = None
    status: str = "pending"
    intention_id: str = field(default_factory=lambda: f"intention_{uuid.uuid4().hex[:8]}")
    created_timestamp_ms: int = field(default_factory=lambda: __import__('time').time_ns() // 1000000)


class BDIAgentMixin:
    """
    BDI Agent 混入类.
    
    为 Agent 添加信念、愿望、意图能力.
    """

    def __init__(self) -> None:
        """初始化 BDI Agent."""
        self._beliefs: list[Belief] = []
        self._desires: list[Desire] = []
        self._intentions: list[Intention] = []

    def add_belief(
        self,
        content: Any,
        source: str,
        confidence: float = 1.0,
    ) -> Belief:
        """
        添加一个信念.

        Args:
            content: 信念内容
            source: 来源
            confidence: 置信度

        Returns:
            Belief 对象
        """
        belief = Belief(
            content=content,
            source=source,
            confidence=confidence,
        )
        self._beliefs.append(belief)
        return belief

    def get_beliefs(self, source: Optional[str] = None) -> list[Belief]:
        """
        获取信念.

        Args:
            source: 可选来源过滤

        Returns:
            信念列表
        """
        if source:
            return [b for b in self._beliefs if b.source == source]
        return list(self._beliefs)

    def add_desire(
        self,
        description: str,
        priority: int = 0,
    ) -> Desire:
        """
        添加一个愿望.

        Args:
            description: 愿望描述
            priority: 优先级

        Returns:
            Desire 对象
        """
        desire = Desire(
            description=description,
            priority=priority,
        )
        self._desires.append(desire)
        return desire

    def get_active_desires(self) -> list[Desire]:
        """
        获取活跃的愿望，按优先级排序.

        Returns:
            活跃愿望列表
        """
        active = [d for d in self._desires if d.active]
        return sorted(active, key=lambda x: -x.priority)

    def add_intention(
        self,
        description: str,
        target_agent: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_params: Optional[dict[str, Any]] = None,
    ) -> Intention:
        """
        添加一个意图.

        Args:
            description: 意图描述
            target_agent: 目标 Agent
            tool_name: 工具名称
            tool_params: 工具参数

        Returns:
            Intention 对象
        """
        intention = Intention(
            description=description,
            target_agent=target_agent,
            tool_name=tool_name,
            tool_params=tool_params,
            status="pending",
        )
        self._intentions.append(intention)
        return intention

    def get_pending_intentions(self) -> list[Intention]:
        """
        获取待处理的意图.

        Returns:
            待处理意图列表
        """
        return [i for i in self._intentions if i.status == "pending"]

    def update_intention_status(
        self,
        intention_id: str,
        status: str,
    ) -> bool:
        """
        更新意图状态.

        Args:
            intention_id: 意图 ID
            status: 新状态

        Returns:
            是否找到并更新
        """
        for intention in self._intentions:
            if intention.intention_id == intention_id:
                intention.status = status
                return True
        return False

    def get_bdi_state(self) -> dict[str, Any]:
        """
        获取 BDI 状态摘要.

        Returns:
            BDI 状态字典
        """
        return {
            "beliefs": [
                {
                    "belief_id": b.belief_id,
                    "source": b.source,
                    "confidence": b.confidence,
                }
                for b in self._beliefs
            ],
            "desires": [
                {
                    "desire_id": d.desire_id,
                    "description": d.description,
                    "priority": d.priority,
                    "active": d.active,
                }
                for d in self._desires
            ],
            "intentions": [
                {
                    "intention_id": i.intention_id,
                    "description": i.description,
                    "target_agent": i.target_agent,
                    "status": i.status,
                }
                for i in self._intentions
            ],
        }


__all__ = [
    "Belief",
    "Desire",
    "Intention",
    "BDIAgentMixin",
]
