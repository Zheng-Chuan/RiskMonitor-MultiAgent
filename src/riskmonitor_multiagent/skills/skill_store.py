"""
Skill 存储系统.

提供 Skill 的 CRUD 和语义检索能力.
参考 memory/memory_store.py 和 memory/semantic_indexer.py 的模式.

设计约束:
- 多Agent架构不变量: Skill 系统是增强每个 Agent 的基础设施, 不替代多 Agent 协作.
- 初始使用内存存储, 与 SemanticIndexer 一致; Redis 持久化作为可选 (Phase 6).
- 语义检索复用 SemanticIndexer, 实例化独立 indexer.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from riskmonitor_multiagent.memory.persistence_backend import PersistenceBackend
from riskmonitor_multiagent.memory.semantic_indexer import SemanticIndexer
from riskmonitor_multiagent.skills.skill_contract import (
    new_skill_id,
    validate_skill,
)


class SkillStore:
    """Skill 存储.

    提供分层能力:
    1. 内存存储: dict[skill_id, skill_dict]
    2. 语义检索: 复用 SemanticIndexer (独立实例)
    3. Redis 持久化: 可选 (Phase 6 处理永久化)
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._indexer: SemanticIndexer = SemanticIndexer()
        self._redis_url = redis_url
        self._persistence: PersistenceBackend | None = None

    @property
    def persistence(self) -> PersistenceBackend:
        """获取持久化后端实例 (惰性初始化)."""
        if self._persistence is None:
            self._persistence = PersistenceBackend()
        return self._persistence

    def _set_persistence(self, backend: PersistenceBackend | None) -> None:
        """注入持久化后端 (测试用)."""
        self._persistence = backend

    # ==================== 内部工具 ====================

    def _build_skill_text(self, skill: dict[str, Any]) -> str:
        """构建 Skill 的语义文本, 用于向量化检索."""
        parts: list[str] = []
        name = skill.get("name")
        if isinstance(name, str) and name.strip():
            parts.append(name.strip())
        for tag in skill.get("tags") or []:
            if isinstance(tag, str) and tag.strip():
                parts.append(tag.strip())
        for cond in skill.get("applicable_conditions") or []:
            if isinstance(cond, str) and cond.strip():
                parts.append(cond.strip())
        for step in skill.get("steps") or []:
            if isinstance(step, dict):
                desc = step.get("description")
                if isinstance(desc, str) and desc.strip():
                    parts.append(desc.strip())
                outcome = step.get("expected_outcome")
                if isinstance(outcome, str) and outcome.strip():
                    parts.append(outcome.strip())
        fb = skill.get("failure_boundary")
        if isinstance(fb, str) and fb.strip():
            parts.append(fb.strip())
        return " ".join(parts)

    def _build_indexable(self, skill: dict[str, Any]) -> dict[str, Any]:
        """将 Skill 转换为 SemanticIndexer 可索引的条目."""
        return {
            "entry_id": str(skill.get("skill_id")),
            "kind": "semantic_case",
            "memory_type": "semantic",
            "scope": "shared",
            "content": {
                "snapshot_text": self._build_skill_text(skill),
            },
            "skill": dict(skill),
        }

    async def _index_skill(self, skill: dict[str, Any]) -> None:
        """索引 Skill 到语义索引器."""
        await self._indexer.index_entry(self._build_indexable(skill))

    async def _reindex(self, skill: dict[str, Any]) -> None:
        """重新索引 Skill (更新时调用)."""
        await self._index_skill(skill)

    # ==================== CRUD ====================

    async def create(self, skill: dict[str, Any]) -> dict[str, Any]:
        """创建 Skill.

        流程: 验证 -> 生成 skill_id -> 存储 -> 索引 -> 异步落盘 -> 返回.
        """
        validated = validate_skill(skill)
        skill_id = validated["skill_id"]
        self._store[skill_id] = validated
        await self._index_skill(validated)
        # 异步落盘到 MySQL (fire-and-forget)
        asyncio.ensure_future(self.persistence.persist_skill(validated))
        return dict(validated)

    async def get(self, skill_id: str) -> dict[str, Any] | None:
        """获取 Skill."""
        skill = self._store.get(skill_id)
        return dict(skill) if skill is not None else None

    async def update(self, skill_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """更新 Skill.

        合并 patch -> 保留 skill_id 和 created_at -> 刷新 updated_at -> 重新索引 -> 异步落盘.
        """
        existing = self._store.get(skill_id)
        if existing is None:
            raise KeyError(f"Skill not found: {skill_id}")
        merged = dict(existing)
        merged.update(patch)
        # 保留不可变字段
        merged["skill_id"] = skill_id
        merged["created_at"] = existing["created_at"]
        merged["updated_at"] = int(time.time() * 1000)
        validated = validate_skill(merged)
        self._store[skill_id] = validated
        await self._reindex(validated)
        # 异步落盘到 MySQL (fire-and-forget)
        asyncio.ensure_future(self.persistence.persist_skill(validated))
        return dict(validated)

    async def delete(self, skill_id: str) -> bool:
        """删除 Skill."""
        if skill_id not in self._store:
            return False
        del self._store[skill_id]
        self._indexer.index.pop(skill_id, None)
        return True

    async def list_all(
        self, *, status: str | None = None, tag: str | None = None
    ) -> list[dict[str, Any]]:
        """列出所有 Skill, 支持按 status 和 tag 过滤."""
        results: list[dict[str, Any]] = []
        for skill in self._store.values():
            if status is not None and skill.get("status") != status:
                continue
            if tag is not None and tag not in (skill.get("tags") or []):
                continue
            results.append(dict(skill))
        return results

    # ==================== 语义检索 ====================

    async def search(
        self, query: str, *, limit: int = 5, min_confidence: float = 0.0
    ) -> list[dict[str, Any]]:
        """语义检索 Skill.

        使用 SemanticIndexer 做向量化检索.
        过滤 confidence < min_confidence 的结果.
        过滤 status != "active" 的结果.
        """
        hits = await self._indexer.search(query, limit=limit)
        results: list[dict[str, Any]] = []
        for hit in hits:
            skill = hit.get("skill")
            if not isinstance(skill, dict):
                continue
            if skill.get("status") != "active":
                continue
            if float(skill.get("confidence", 0.0)) < min_confidence:
                continue
            result = dict(skill)
            result["semantic_score"] = float(hit.get("semantic_score", 0.0))
            results.append(result)
        return results

    async def find_similar(
        self, skill: dict[str, Any], threshold: float = 0.85
    ) -> list[dict[str, Any]]:
        """检查是否已存在语义相似的 Skill.

        用于 SkillProposer 决定创建还是更新.
        不排除任何 status 的 Skill (包括 deprecated/archived).
        """
        text = self._build_skill_text(skill)
        if not text.strip():
            return []
        hits = await self._indexer.search(text, limit=20)
        results: list[dict[str, Any]] = []
        for hit in hits:
            hit_skill = hit.get("skill")
            if not isinstance(hit_skill, dict):
                continue
            # 排除自身
            if hit_skill.get("skill_id") == skill.get("skill_id"):
                continue
            score = float(hit.get("semantic_score", 0.0))
            if score >= threshold:
                result = dict(hit_skill)
                result["semantic_score"] = score
                results.append(result)
        return results

    # ==================== 置信度更新 ====================

    async def update_confidence(
        self, skill_id: str, success: bool, *, delta: float = 0.05
    ) -> dict[str, Any]:
        """更新 Skill 置信度.

        成功: confidence = min(1.0, confidence + delta), usage_count += 1
        失败: confidence = max(0.0, confidence - delta), usage_count += 1
        重新计算 success_rate.
        如果 confidence < 0.3: status = "deprecated"
        如果 confidence < 0.15: status = "archived"
        """
        existing = self._store.get(skill_id)
        if existing is None:
            raise KeyError(f"Skill not found: {skill_id}")

        current_confidence = float(existing.get("confidence", 0.5))
        current_usage = int(existing.get("usage_count", 0))
        current_success_rate = float(existing.get("success_rate", 0.0))

        # 计算历史成功次数
        if current_usage > 0:
            historical_successes = round(current_success_rate * current_usage)
        else:
            historical_successes = 0

        new_usage = current_usage + 1
        new_successes = historical_successes + (1 if success else 0)
        new_success_rate = new_successes / new_usage

        if success:
            new_confidence = min(1.0, current_confidence + delta)
        else:
            new_confidence = max(0.0, current_confidence - delta)

        updated = dict(existing)
        updated["confidence"] = new_confidence
        updated["usage_count"] = new_usage
        updated["success_rate"] = new_success_rate
        updated["updated_at"] = int(time.time() * 1000)

        # 自动降级
        if new_confidence < 0.15:
            updated["status"] = "archived"
        elif new_confidence < 0.3:
            updated["status"] = "deprecated"

        self._store[skill_id] = updated
        await self._reindex(updated)
        return dict(updated)

    # ==================== 持久化 ====================

    async def flush_to_persistence(self) -> int:
        """批量落盘所有 Skill 到 MySQL.

        Returns:
            成功落盘的条目数
        """
        all_skills = list(self._store.values())
        if not all_skills:
            return 0
        count = 0
        for skill in all_skills:
            ok = await self.persistence.persist_skill(skill)
            if ok:
                count += 1
        return count

    async def restore_from_persistence(self) -> int:
        """从 MySQL 加载所有 Skill 到内存.

        Returns:
            恢复的 Skill 数量
        """
        skills = await self.persistence.load_skills()
        if not skills:
            return 0
        for skill in skills:
            skill_id = skill.get("skill_id")
            if skill_id:
                self._store[skill_id] = skill
                await self._index_skill(skill)
        return len(skills)

    # ==================== 健康检查 ====================

    async def health_check(self) -> bool:
        """健康检查."""
        return True
