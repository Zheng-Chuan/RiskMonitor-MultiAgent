"""
Skill 治理与噪音控制.

在 Skill 注入阶段执行治理策略, 控制噪音和 prompt 膨胀:
- 注入限制: 置信度过滤、状态过滤、数量限制、token 预算截断
- 过期清理: 超期 Skill 自动归档, 低置信度 Skill 自动归档
- 去重合并: 高相似度 Skill 合并
- 治理报告: 全局统计

设计约束:
- 多Agent架构不变量: 治理是增强 SkillInjector 的能力, 不替代多 Agent 协作.
- 异常隔离: 治理失败不影响主流程.
- 遵循现有代码风格: async/await, 类型标注.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from riskmonitor_multiagent.skills.skill_store import SkillStore

logger = logging.getLogger(__name__)


@dataclass
class SkillGovernanceConfig:
    """Skill 治理配置."""

    max_skills_per_category: int = 10  # 每个分类最多 Skill 数
    min_confidence_for_injection: float = 0.3  # 注入最低置信度
    max_skill_age_days: int = 90  # Skill 最大年龄（天），超期自动归档
    max_injection_token_budget: int = 2000  # Skill 注入的 token 预算
    auto_archive_threshold: float = 0.15  # 低于此置信度自动归档
    auto_deprecate_threshold: float = 0.3  # 低于此置信度自动降级


class SkillGovernor:
    """Skill 治理与噪音控制."""

    def __init__(
        self, skill_store: SkillStore, config: SkillGovernanceConfig | None = None
    ) -> None:
        self._store = skill_store
        self._config = config or SkillGovernanceConfig()

    @property
    def config(self) -> SkillGovernanceConfig:
        """治理配置 (只读)."""
        return self._config

    # ==================== 注入限制 ====================

    async def enforce_injection_limits(
        self,
        skills: list[dict[str, Any]],
        *,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """执行注入限制.

        1. 过滤 confidence < min_confidence_for_injection
        2. 过滤 status != "active"
        3. 按 confidence 降序排序
        4. 限制数量不超过 max_skills_per_category
        5. 估算总 token 数, 超过 max_injection_token_budget 则截断
        """
        cfg = self._config

        # 1 & 2: 过滤低置信度和非 active
        filtered: list[dict[str, Any]] = []
        for skill in skills:
            confidence = float(skill.get("confidence", 0.0))
            status = skill.get("status", "active")
            if confidence < cfg.min_confidence_for_injection:
                continue
            if status != "active":
                continue
            filtered.append(skill)

        # 3: 按 confidence 降序排序
        filtered.sort(key=lambda s: float(s.get("confidence", 0.0)), reverse=True)

        # 4: 限制数量
        max_count = cfg.max_skills_per_category
        if max_count > 0 and len(filtered) > max_count:
            filtered = filtered[:max_count]

        # 5: token 预算截断
        budget = cfg.max_injection_token_budget
        if budget <= 0:
            return filtered

        result: list[dict[str, Any]] = []
        cumulative_tokens = 0
        for skill in filtered:
            skill_tokens = self.estimate_skills_token_cost([skill])
            if cumulative_tokens + skill_tokens > budget:
                break
            result.append(skill)
            cumulative_tokens += skill_tokens

        return result

    # ==================== 过期清理 ====================

    async def cleanup_stale_skills(self) -> dict[str, Any]:
        """清理过期和低质量 Skill.

        1. 检查所有 Skill 的 created_at
        2. 超过 max_skill_age_days 且 confidence < auto_deprecate_threshold → archived
        3. confidence < auto_archive_threshold → archived
        4. 超期但 confidence >= auto_deprecate_threshold 且 status=active → deprecated
        5. 返回清理统计: {archived_count, deprecated_count, total_scanned}
        """
        cfg = self._config
        now_ms = int(time.time() * 1000)
        max_age_ms = cfg.max_skill_age_days * 24 * 60 * 60 * 1000

        all_skills = await self._store.list_all()

        archived_count = 0
        deprecated_count = 0

        for skill in all_skills:
            skill_id = skill.get("skill_id")
            if not skill_id:
                continue

            confidence = float(skill.get("confidence", 0.0))
            status = skill.get("status", "active")
            created_at = int(skill.get("created_at", now_ms))
            age_ms = now_ms - created_at
            is_expired = age_ms > max_age_ms

            # 3: confidence < auto_archive_threshold → archived (无论是否超期)
            if confidence < cfg.auto_archive_threshold:
                if status != "archived":
                    try:
                        await self._store.update(skill_id, {"status": "archived"})
                        archived_count += 1
                    except Exception as exc:
                        logger.warning(
                            "cleanup_stale: archive skill %s failed: %s",
                            skill_id,
                            exc,
                        )
                continue

            # 2: 超期且 confidence < auto_deprecate_threshold → archived
            if is_expired and confidence < cfg.auto_deprecate_threshold:
                if status != "archived":
                    try:
                        await self._store.update(skill_id, {"status": "archived"})
                        archived_count += 1
                    except Exception as exc:
                        logger.warning(
                            "cleanup_stale: archive expired skill %s failed: %s",
                            skill_id,
                            exc,
                        )
                continue

            # 4: 超期但 confidence 足够高 → 降级
            if is_expired and status == "active":
                try:
                    await self._store.update(skill_id, {"status": "deprecated"})
                    deprecated_count += 1
                except Exception as exc:
                    logger.warning(
                        "cleanup_stale: deprecate expired skill %s failed: %s",
                        skill_id,
                        exc,
                    )

        return {
            "archived_count": archived_count,
            "deprecated_count": deprecated_count,
            "total_scanned": len(all_skills),
        }

    # ==================== 去重合并 ====================

    async def merge_duplicate_skills(
        self, *, similarity_threshold: float = 0.9
    ) -> dict[str, Any]:
        """合并高度相似的 Skill.

        1. 遍历所有 active Skill
        2. 对每对 Skill 做 find_similar 检查
        3. 相似度 >= threshold → 合并（保留置信度更高的, 将另一个 archived）
        4. 返回合并统计: {merged_count, total_pairs_checked}
        """
        active_skills = await self._store.list_all(status="active")

        merged_count = 0
        total_pairs_checked = 0
        archived_ids: set[str] = set()

        for skill in active_skills:
            skill_id = skill.get("skill_id")
            if not skill_id or skill_id in archived_ids:
                continue

            try:
                similar = await self._store.find_similar(
                    skill, threshold=similarity_threshold
                )
            except Exception as exc:
                logger.warning(
                    "merge_duplicate: find_similar for %s failed: %s",
                    skill_id,
                    exc,
                )
                continue

            skill_confidence = float(skill.get("confidence", 0.0))

            for dup in similar:
                dup_id = dup.get("skill_id")
                if not dup_id or dup_id == skill_id or dup_id in archived_ids:
                    continue

                total_pairs_checked += 1
                dup_confidence = float(dup.get("confidence", 0.0))

                # 保留置信度更高的, 归档另一个
                if dup_confidence >= skill_confidence:
                    # 当前 skill 置信度更低, 归档当前
                    keep_id = dup_id
                    archive_id = skill_id
                else:
                    keep_id = skill_id
                    archive_id = dup_id

                try:
                    await self._store.update(archive_id, {"status": "archived"})
                    archived_ids.add(archive_id)
                    merged_count += 1
                    logger.info(
                        "merge_duplicate: archived %s, kept %s (threshold=%.2f)",
                        archive_id,
                        keep_id,
                        similarity_threshold,
                    )
                except Exception as exc:
                    logger.warning(
                        "merge_duplicate: archive %s failed: %s",
                        archive_id,
                        exc,
                    )

        return {
            "merged_count": merged_count,
            "total_pairs_checked": total_pairs_checked,
        }

    # ==================== Token 估算 ====================

    def estimate_skills_token_cost(self, skills: list[dict[str, Any]]) -> int:
        """估算 Skill 列表的 token 开销.

        中文 1.5 字/token, 英文 4 字符/token.
        """
        total_tokens = 0
        for skill in skills:
            text = self._build_skill_text(skill)
            total_tokens += self._estimate_text_tokens(text)
        return total_tokens

    # ==================== 治理报告 ====================

    async def get_governance_report(self) -> dict[str, Any]:
        """生成治理报告."""
        all_skills = await self._store.list_all()

        total_skills = len(all_skills)
        active_skills = sum(
            1 for s in all_skills if s.get("status") == "active"
        )
        deprecated_skills = sum(
            1 for s in all_skills if s.get("status") == "deprecated"
        )
        archived_skills = sum(
            1 for s in all_skills if s.get("status") == "archived"
        )

        confidences = [
            float(s.get("confidence", 0.0)) for s in all_skills
        ]
        avg_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

        total_usage_count = sum(
            int(s.get("usage_count", 0)) for s in all_skills
        )

        success_rates = [
            float(s.get("success_rate", 0.0))
            for s in all_skills
            if int(s.get("usage_count", 0)) > 0
        ]
        avg_success_rate = (
            sum(success_rates) / len(success_rates) if success_rates else 0.0
        )

        # 按分类统计
        by_category: dict[str, int] = {}
        for skill in all_skills:
            tags = skill.get("tags") or []
            if isinstance(tags, list) and tags:
                for tag in tags:
                    tag_str = str(tag)
                    by_category[tag_str] = by_category.get(tag_str, 0) + 1
            else:
                by_category["uncategorized"] = (
                    by_category.get("uncategorized", 0) + 1
                )

        # 最老 Skill 年龄
        now_ms = int(time.time() * 1000)
        oldest_age_days = 0
        for skill in all_skills:
            created_at = int(skill.get("created_at", now_ms))
            age_days = (now_ms - created_at) // (24 * 60 * 60 * 1000)
            if age_days > oldest_age_days:
                oldest_age_days = age_days

        # 是否需要清理 (仅检查未归档的 Skill)
        cleanup_needed = False
        cfg = self._config
        for skill in all_skills:
            status = skill.get("status", "active")
            if status == "archived":
                continue
            confidence = float(skill.get("confidence", 0.0))
            if confidence < cfg.auto_archive_threshold:
                cleanup_needed = True
                break
            created_at = int(skill.get("created_at", now_ms))
            age_ms = now_ms - created_at
            max_age_ms = cfg.max_skill_age_days * 24 * 60 * 60 * 1000
            if age_ms > max_age_ms and confidence < cfg.auto_deprecate_threshold:
                cleanup_needed = True
                break

        return {
            "total_skills": total_skills,
            "active_skills": active_skills,
            "deprecated_skills": deprecated_skills,
            "archived_skills": archived_skills,
            "avg_confidence": round(avg_confidence, 4),
            "total_usage_count": total_usage_count,
            "avg_success_rate": round(avg_success_rate, 4),
            "by_category": by_category,
            "oldest_skill_age_days": oldest_age_days,
            "cleanup_needed": cleanup_needed,
        }

    # ==================== 内部工具 ====================

    def _build_skill_text(self, skill: dict[str, Any]) -> str:
        """构建 Skill 的文本表示, 用于 token 估算."""
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

    @staticmethod
    def _estimate_text_tokens(text: str) -> int:
        """估算文本的 token 数.

        中文 1.5 字/token, 英文 4 字符/token.
        """
        if not text:
            return 0

        chinese_chars = 0
        other_chars = 0

        for char in text:
            code = ord(char)
            # CJK 统一汉字范围 + 扩展
            if (
                0x4E00 <= code <= 0x9FFF
                or 0x3400 <= code <= 0x4DBF
                or 0xF900 <= code <= 0xFAFF
                or 0x20000 <= code <= 0x2A6DF
            ):
                chinese_chars += 1
            else:
                other_chars += 1

        chinese_tokens = chinese_chars / 1.5 if chinese_chars > 0 else 0
        english_tokens = other_chars / 4.0 if other_chars > 0 else 0

        return int(chinese_tokens + english_tokens) + 1  # +1 向上取整保护
