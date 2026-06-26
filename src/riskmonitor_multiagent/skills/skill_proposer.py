"""
SkillProposer - 从高质量完成的 run 中提取可复用模式, 生成 Skill 提案.

在 CriticAgent 评审之后触发, 自动从 run_trace 提取可复用模式.

设计约束:
- 多Agent架构不变量: SkillProposer 在 CriticAgent 评审之后触发, 不旁路 CriticAgent 的审查权.
- 异常隔离: SkillProposer 的失败不应影响主流程.
- 语义去重: 使用 SkillStore.find_similar() 做去重.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from riskmonitor_multiagent.skills.skill_store import SkillStore

logger = logging.getLogger(__name__)


class SkillProposer:
    """从高质量完成的 run 中提取可复用模式, 生成 Skill 提案."""

    def __init__(self, skill_store: SkillStore, *, confidence_threshold: float = 0.85) -> None:
        self._store = skill_store
        self._confidence_threshold = confidence_threshold

    async def propose(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        critic_final: dict[str, Any],
        orchestrator_output: dict[str, Any],
        receipts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """从 run 结果中提取模式, 生成 Skill 提案.

        流程:
        1. 检查 critic_final 的 confidence/ok, 低于阈值则不提议
        2. 从 task + orchestrator_output + receipts 提取可复用模式
        3. 调用 skill_store.find_similar() 做语义去重
        4. 如果相似度 >= 0.85: 更新已有 Skill (usage_count 不变, 更新内容)
        5. 如果无相似: 创建新 Skill
        6. 返回提案结果: {action, skill_id, similarity_score, reason}
        """
        # 1. 检查 confidence 和 ok
        ok = bool(critic_final.get("ok", False))
        confidence = critic_final.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 0.9 if ok else 0.4
        confidence = min(1.0, max(0.0, float(confidence)))

        if not ok or confidence < self._confidence_threshold:
            return {
                "action": "skipped",
                "skill_id": None,
                "similarity_score": 0.0,
                "reason": (
                    f"confidence={confidence:.2f} below "
                    f"threshold={self._confidence_threshold} or ok={ok}"
                ),
            }

        # 2. 提取可复用模式
        skill_data = self._extract_skill_pattern(
            run_id=run_id,
            task=task,
            critic_final=critic_final,
            orchestrator_output=orchestrator_output,
        )

        # 3. 语义去重
        try:
            similar = await self._store.find_similar(
                skill_data, threshold=self._confidence_threshold
            )
        except Exception as exc:
            logger.warning("find_similar failed: %s", exc)
            similar = []

        if similar:
            existing = similar[0]
            similarity_score = float(
                existing.get("semantic_score", self._confidence_threshold)
            )
            # 4. 更新已有 Skill
            try:
                skill_id = str(existing.get("skill_id") or "")
                if not skill_id:
                    return {
                        "action": "skipped",
                        "skill_id": None,
                        "similarity_score": similarity_score,
                        "reason": "similar_skill_has_no_id",
                    }
                # 构建 patch: 更新内容但保留 usage_count / created_at
                patch: dict[str, Any] = {
                    "name": skill_data["name"],
                    "tags": skill_data["tags"],
                    "applicable_conditions": skill_data["applicable_conditions"],
                    "steps": skill_data["steps"],
                    "failure_boundary": skill_data["failure_boundary"],
                    "confidence": skill_data["confidence"],
                    "source_run_id": run_id,
                }
                # 添加 revision history
                existing_revisions = existing.get("revision_history", [])
                if not isinstance(existing_revisions, list):
                    existing_revisions = []
                revision_entry: dict[str, Any] = {
                    "action": "updated",
                    "run_id": run_id,
                    "reason": "similar_skill_found",
                }
                patch["revision_history"] = list(existing_revisions) + [revision_entry]
                updated = await self._store.update(skill_id, patch)
                return {
                    "action": "updated",
                    "skill_id": skill_id,
                    "similarity_score": similarity_score,
                    "reason": "similar_skill_found_and_updated",
                    "skill": updated,
                }
            except Exception as exc:
                logger.warning("update existing skill failed: %s", exc)
                return {
                    "action": "skipped",
                    "skill_id": existing.get("skill_id"),
                    "similarity_score": similarity_score,
                    "reason": f"update_failed: {exc}",
                }

        # 5. 创建新 Skill
        try:
            created = await self._store.create(skill_data)
            return {
                "action": "created",
                "skill_id": created["skill_id"],
                "similarity_score": 0.0,
                "reason": "no_similar_skill_found",
                "skill": created,
            }
        except Exception as exc:
            logger.warning("create skill failed: %s", exc)
            return {
                "action": "skipped",
                "skill_id": None,
                "similarity_score": 0.0,
                "reason": f"create_failed: {exc}",
            }

    # ==================== 模式提取 ====================

    def _extract_skill_pattern(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        critic_final: dict[str, Any],
        orchestrator_output: dict[str, Any],
    ) -> dict[str, Any]:
        """从 task + orchestrator_output + critic_final 提取可复用模式."""
        intent = self._extract_intent(task)
        content = self._extract_content(task)

        name = self._build_name(intent)
        tags = self._build_tags(content, task)
        applicable_conditions = self._build_applicable_conditions(content, task, intent)
        steps = self._build_steps(orchestrator_output)
        failure_boundary = self._build_failure_boundary(critic_final)

        ok = bool(critic_final.get("ok", False))
        confidence = critic_final.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 0.9 if ok else 0.4

        return {
            "name": name,
            "tags": tags,
            "applicable_conditions": applicable_conditions,
            "steps": steps,
            "failure_boundary": failure_boundary,
            "confidence": float(confidence),
            "write_origin": "auto",
            "status": "active",
            "source_run_id": run_id,
            "source_agent_id": "skill_proposer",
        }

    def _extract_intent(self, task: dict[str, Any]) -> str:
        """提取 intent 字符串.

        兼容多种 task 结构:
        - task["intent"]: 字符串
        - task["intent"]: dict (含 type)
        - task["payload"]["content"]: 字符串
        - task["description"]: 字符串
        """
        intent = task.get("intent")
        if isinstance(intent, str) and intent.strip():
            return intent.strip()
        if isinstance(intent, dict):
            intent_type = intent.get("type")
            if isinstance(intent_type, str) and intent_type.strip():
                return intent_type.strip()
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        content = payload.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        desc = task.get("description")
        if isinstance(desc, str) and desc.strip():
            return desc.strip()
        return str(task.get("task_id") or "unknown_task")

    def _extract_content(self, task: dict[str, Any]) -> dict[str, Any]:
        """提取 content dict."""
        content = task.get("content")
        if isinstance(content, dict):
            return content
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        return payload if isinstance(payload, dict) else {}

    def _build_name(self, intent: str) -> str:
        """从 intent 生成简洁名称 (前 50 字符, 去掉特殊字符)."""
        name = intent[:50].strip()
        name = re.sub(r"[^\w\u4e00-\u9fff\s\-]", "", name)
        name = name.strip()
        return name if name else "unnamed_skill"

    def _build_tags(
        self, content: dict[str, Any], task: dict[str, Any]
    ) -> list[str]:
        """从 content category 或 task tags 提取."""
        category = content.get("category")
        if isinstance(category, str) and category.strip():
            return [category.strip()]
        tags = content.get("tags")
        if isinstance(tags, list):
            result = [str(t).strip() for t in tags if str(t).strip()]
            if result:
                return result
        task_tags = task.get("tags")
        if isinstance(task_tags, list):
            result = [str(t).strip() for t in task_tags if str(t).strip()]
            if result:
                return result
        return ["general"]

    def _build_applicable_conditions(
        self, content: dict[str, Any], task: dict[str, Any], intent: str
    ) -> list[str]:
        """从 content 提取关键条件."""
        conds = content.get("applicable_conditions")
        if isinstance(conds, list):
            result = [str(c).strip() for c in conds if str(c).strip()]
            if result:
                return result
        conds2 = content.get("conditions")
        if isinstance(conds2, list):
            result = [str(c).strip() for c in conds2 if str(c).strip()]
            if result:
                return result
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        payload_content = payload.get("content")
        if isinstance(payload_content, str) and payload_content.strip():
            return [payload_content.strip()[:120]]
        if intent and intent != "unknown_task":
            return [intent[:120]]
        return ["general"]

    def _build_steps(
        self, orchestrator_output: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """从 orchestrator_output plan_steps 提取步骤列表.

        每步含 description 和 expected_outcome.
        """
        plan_steps = orchestrator_output.get("plan_steps")
        if not isinstance(plan_steps, list):
            return [
                {"description": "execute_task", "expected_outcome": "task_completed"}
            ]

        steps: list[dict[str, Any]] = []
        for step in plan_steps:
            if not isinstance(step, dict):
                continue
            description = (
                step.get("instruction")
                or step.get("reason")
                or step.get("description")
                or step.get("step_id")
                or "unknown_step"
            )
            expected_outcome = (
                step.get("expected_outcome")
                or step.get("target_agent")
                or "step_completed"
            )
            steps.append(
                {
                    "description": str(description),
                    "expected_outcome": str(expected_outcome),
                }
            )

        return steps if steps else [
            {"description": "execute_task", "expected_outcome": "task_completed"}
        ]

    def _build_failure_boundary(self, critic_final: dict[str, Any]) -> str:
        """从 critic_final issues 或 risk_level 推导 failure_boundary."""
        issues = critic_final.get("issues")
        if isinstance(issues, list) and issues:
            parts: list[str] = []
            for issue in issues[:3]:
                if isinstance(issue, dict):
                    msg = issue.get("message") or issue.get("code")
                    if msg:
                        parts.append(str(msg))
                elif isinstance(issue, str):
                    parts.append(issue)
            if parts:
                return "; ".join(parts)

        risk_level = critic_final.get("risk_level")
        if isinstance(risk_level, str) and risk_level.strip():
            return f"risk_level={risk_level.strip()}"

        return "no_known_failure_boundary"
