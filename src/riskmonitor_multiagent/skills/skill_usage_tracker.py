"""
Skill 使用跟踪和置信度动态更新.

在 Skill 注入时记录使用, 在执行完成后根据执行结果和 Critic 评审结果更新置信度.

设计约束:
- 多Agent架构不变量: 置信度更新不改变多 Agent 协作流程.
- 异常隔离: 置信度更新失败不影响主流程.
- 跟踪隔离: 每次 run 的 Skill 使用跟踪是独立的.
- 遵循现有代码风格: async/await, 类型标注.
"""

from __future__ import annotations

import logging
from typing import Any

from riskmonitor_multiagent.skills.skill_store import SkillStore

logger = logging.getLogger(__name__)


class SkillUsageTracker:
    """跟踪 Skill 使用情况, 在执行完成后更新置信度."""

    def __init__(
        self,
        skill_store: SkillStore,
        *,
        success_delta: float = 0.05,
        fail_delta: float = 0.05,
    ) -> None:
        """
        初始化 SkillUsageTracker.

        Args:
            skill_store: Skill 存储实例.
            success_delta: 成功时置信度增量.
            fail_delta: 失败时置信度减量.
        """
        self._store = skill_store
        self._success_delta = success_delta
        self._fail_delta = fail_delta
        # run_id -> list[{skill_id, phase}]
        self._tracking: dict[str, list[dict[str, str]]] = {}

    def track_usage(self, skill_id: str, *, run_id: str, phase: str = "planning") -> None:
        """记录 Skill 在某次 run 中被使用. 在注入时调用.

        同一 run 中同一 skill_id 只记录一次 (去重).
        """
        if run_id not in self._tracking:
            self._tracking[run_id] = []
        entries = self._tracking[run_id]
        for entry in entries:
            if entry["skill_id"] == skill_id:
                return
        entries.append({"skill_id": skill_id, "phase": phase})

    async def update_after_execution(
        self,
        *,
        run_id: str,
        execution_success: bool,
        critic_ok: bool,
    ) -> list[dict[str, Any]]:
        """执行完成后, 更新本次 run 中使用的所有 Skill 的置信度.

        判断成功的逻辑:
        - execution_success=True AND critic_ok=True → success=True
        - 否则 → success=False

        对每个被跟踪的 skill_id 调用 skill_store.update_confidence()
        返回更新结果列表:
        [{skill_id, old_confidence, new_confidence, old_status, new_status, success}]
        """
        tracked = self._tracking.get(run_id, [])
        if not tracked:
            return []

        success = execution_success and critic_ok
        delta = self._success_delta if success else self._fail_delta

        results: list[dict[str, Any]] = []
        for entry in tracked:
            skill_id = entry["skill_id"]
            try:
                old_skill = await self._store.get(skill_id)
                if old_skill is None:
                    logger.warning(
                        "Skill not found during confidence update: %s", skill_id
                    )
                    continue
                old_confidence = float(old_skill.get("confidence", 0.5))
                old_status = str(old_skill.get("status", "active"))

                updated = await self._store.update_confidence(
                    skill_id, success, delta=delta
                )

                new_confidence = float(updated.get("confidence", 0.5))
                new_status = str(updated.get("status", "active"))

                results.append(
                    {
                        "skill_id": skill_id,
                        "old_confidence": old_confidence,
                        "new_confidence": new_confidence,
                        "old_status": old_status,
                        "new_status": new_status,
                        "success": success,
                    }
                )
            except Exception as exc:
                logger.warning(
                    "Failed to update confidence for skill %s: %s", skill_id, exc
                )

        return results

    def get_tracked_skills(self, run_id: str) -> list[str]:
        """获取某次 run 中跟踪的所有 skill_id."""
        tracked = self._tracking.get(run_id, [])
        return [entry["skill_id"] for entry in tracked]

    def clear_tracking(self, run_id: str) -> None:
        """清理某次 run 的跟踪记录."""
        self._tracking.pop(run_id, None)
