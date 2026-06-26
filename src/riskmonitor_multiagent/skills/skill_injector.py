"""
Skill 注入器.

在规划阶段检索匹配的 Skill, 以结构化 few-shot 形式注入规划 prompt.

设计约束:
- 多Agent架构不变量: Skill 注入是增强 OrchestratorAgent 的规划能力, 不替代多 Agent 协作.
- prompt 膨胀控制: max_skills 限制注入数量.
- 异常隔离: Skill 注入失败不影响主流程.
- 遵循现有代码风格: async/await, 类型标注.
"""

from __future__ import annotations

import logging
from typing import Any

from riskmonitor_multiagent.skills.skill_governor import SkillGovernor
from riskmonitor_multiagent.skills.skill_store import SkillStore

logger = logging.getLogger(__name__)


class SkillInjector:
    """在规划阶段检索匹配的 Skill, 以结构化 few-shot 形式注入规划 prompt."""

    def __init__(
        self,
        skill_store: SkillStore,
        *,
        min_confidence: float = 0.3,
        max_skills: int = 3,
        governor: SkillGovernor | None = None,
    ) -> None:
        self._store = skill_store
        self._min_confidence = min_confidence
        self._max_skills = max_skills
        self._governor = governor
        self._last_injected_skill_ids: list[str] = []

    @property
    def last_injected_skill_ids(self) -> list[str]:
        """返回最近一次注入的 skill_id 列表 (只读副本)."""
        return list(self._last_injected_skill_ids)

    async def retrieve_applicable_skills(
        self,
        *,
        task: dict[str, Any],
        intent: str | None = None,
        skill_enabled: bool = True,
    ) -> dict[str, Any]:
        """检索匹配当前任务的 Skill, 返回注入结构.

        流程:
        1. 如果 skill_enabled=False, 返回空结构
        2. 从 task/intent 提取查询关键词
        3. 调用 skill_store.search(query, limit=max_skills, min_confidence=min_confidence)
        4. 过滤 status != "active" 的结果 (SkillStore.search 已内置过滤)
        5. 构建 few-shot 注入结构
        """
        if not skill_enabled:
            self._last_injected_skill_ids = []
            return {
                "skill_enabled": False,
                "skills": [],
                "skill_count": 0,
                "injected_skill_ids": [],
                "injection_summary": "Skill injection disabled",
            }

        query = self._build_query(task=task, intent=intent)
        if not query.strip():
            self._last_injected_skill_ids = []
            return {
                "skill_enabled": True,
                "skills": [],
                "skill_count": 0,
                "injected_skill_ids": [],
                "injection_summary": "No query keywords extracted for skill retrieval",
            }

        try:
            hits = await self._store.search(
                query,
                limit=self._max_skills,
                min_confidence=self._min_confidence,
            )
        except Exception as exc:
            logger.warning("Skill search failed: %s", exc)
            self._last_injected_skill_ids = []
            return {
                "skill_enabled": True,
                "skills": [],
                "skill_count": 0,
                "injected_skill_ids": [],
                "injection_summary": f"Skill search error: {exc}",
            }

        skills = [self._build_injection_item(hit) for hit in hits]

        # 治理过滤: 置信度/状态/数量/token 预算控制
        if self._governor and skills:
            try:
                skills = await self._governor.enforce_injection_limits(skills)
            except Exception as exc:
                logger.warning("Skill governance failed: %s", exc)
        count = len(skills)
        self._last_injected_skill_ids = [str(s.get("skill_id", "")) for s in skills if s.get("skill_id")]
        return {
            "skill_enabled": True,
            "skills": skills,
            "skill_count": count,
            "injected_skill_ids": list(self._last_injected_skill_ids),
            "injection_summary": (
                f"Found {count} applicable skill{'s' if count != 1 else ''} "
                f"for this task"
            ),
        }

    # ==================== 内部工具 ====================

    def _build_query(
        self,
        *,
        task: dict[str, Any],
        intent: str | None,
    ) -> str:
        """从 task/intent 提取查询关键词.

        兼容多种 task 结构:
        - intent 参数 (字符串)
        - task["intent"]: 字符串或 dict (含 type / primary_intent_type)
        - task["payload"]["content"]: 字符串
        - task["content"]: dict (含 description) 或字符串
        - task["description"]: 字符串
        """
        parts: list[str] = []

        # 外部传入的 intent 字符串
        if isinstance(intent, str) and intent.strip():
            parts.append(intent.strip())

        # task.intent
        task_intent = task.get("intent")
        if isinstance(task_intent, str) and task_intent.strip():
            parts.append(task_intent.strip())
        elif isinstance(task_intent, dict):
            intent_type = (
                task_intent.get("primary_intent_type")
                or task_intent.get("type")
            )
            if isinstance(intent_type, str) and intent_type.strip():
                parts.append(intent_type.strip())

        # task.payload.content
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        content = payload.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())

        # task.content
        task_content = task.get("content")
        if isinstance(task_content, dict):
            desc = task_content.get("description")
            if isinstance(desc, str) and desc.strip():
                parts.append(desc.strip())
        elif isinstance(task_content, str) and task_content.strip():
            parts.append(task_content.strip())

        # task.description
        desc = task.get("description")
        if isinstance(desc, str) and desc.strip():
            parts.append(desc.strip())

        return " ".join(parts)

    @staticmethod
    def _build_injection_item(skill: dict[str, Any]) -> dict[str, Any]:
        """构建单个 Skill 的 few-shot 注入结构."""
        steps = skill.get("steps")
        if not isinstance(steps, list):
            steps = []
        else:
            steps = [dict(s) if isinstance(s, dict) else {} for s in steps]

        conds = skill.get("applicable_conditions")
        if not isinstance(conds, list):
            conds = []
        else:
            conds = [str(c) for c in conds]

        return {
            "skill_id": str(skill.get("skill_id") or ""),
            "name": str(skill.get("name") or ""),
            "applicable_conditions": conds,
            "steps": steps,
            "failure_boundary": str(skill.get("failure_boundary") or ""),
            "confidence": float(skill.get("confidence", 0.0)),
        }
