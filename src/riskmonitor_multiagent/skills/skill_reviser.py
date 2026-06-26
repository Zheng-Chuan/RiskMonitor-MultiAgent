"""
SkillReviser - Skill 改进闭环.

当 Skill 被使用但产生次优结果时, 提议 Skill 修订.

设计约束:
- 多Agent架构不变量: SkillReviser 在 CriticAgent 评审之后触发, 不旁路 CriticAgent 的审查权.
- 异常隔离: SkillReviser 的失败不应影响主流程.
- 修订是可选的: 不强制每次失败都修订.
- revision_history 可回滚: 每次修订追加历史记录.
- 遵循现有代码风格: async/await, 类型标注.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from riskmonitor_multiagent.skills.skill_store import SkillStore

logger = logging.getLogger(__name__)


@dataclass
class RevisionProposal:
    """Skill 修订提案."""

    skill_id: str
    revision_id: str  # "rev_" + uuid
    reason: str  # 修订原因
    original_steps: list[dict[str, Any]]
    revised_steps: list[dict[str, Any]]
    original_failure_boundary: str
    revised_failure_boundary: str
    proposed_at: int  # 毫秒时间戳
    proposed_by: str  # "critic" | "auto"
    ab_test_result: dict[str, Any] | None = None  # A/B 对比结果


class SkillReviser:
    """当 Skill 被使用但产生次优结果时, 提议 Skill 修订."""

    def __init__(self, skill_store: SkillStore) -> None:
        self._store = skill_store

    async def check_and_propose_revision(
        self,
        *,
        skill_id: str,
        run_id: str,
        execution_result: dict[str, Any],
        critic_final: dict[str, Any],
    ) -> RevisionProposal | None:
        """检查是否需要修订 Skill.

        触发条件:
        1. Skill 被使用 (在 skill_usage_tracker 中有记录)
        2. 执行结果不理想 (critic ok=False 或有 issues)

        修订内容:
        1. 从 critic issues 提取失败原因
        2. 从 execution_result 提取实际步骤和结果
        3. 与 Skill 的 steps 对比, 找出差异
        4. 生成修订后的 steps 和 failure_boundary
        """
        skill = await self._store.get(skill_id)
        if skill is None:
            logger.warning("Skill not found for revision: %s", skill_id)
            return None

        # 触发条件: critic ok=True 且无 issues → 不修订
        ok = bool(critic_final.get("ok", False))
        issues = critic_final.get("issues")
        has_issues = isinstance(issues, list) and len(issues) > 0

        if ok and not has_issues:
            return None

        # 提取失败原因
        failure_reason = self._extract_failure_reason(critic_final)

        # 获取原始 steps 和 failure_boundary
        original_steps = skill.get("steps")
        if not isinstance(original_steps, list):
            original_steps = []
        original_steps = [dict(s) if isinstance(s, dict) else {} for s in original_steps]

        original_failure_boundary = str(skill.get("failure_boundary") or "")

        # 生成修订后的 steps
        revised_steps = self._generate_revised_steps(
            original_steps=original_steps,
            failure_reason=failure_reason,
            execution_result=execution_result,
        )

        # 生成修订后的 failure_boundary
        revised_failure_boundary = self._generate_revised_failure_boundary(
            original_failure_boundary=original_failure_boundary,
            failure_reason=failure_reason,
        )

        proposed_by = "critic" if not ok and has_issues else "auto"

        proposal = RevisionProposal(
            skill_id=skill_id,
            revision_id=f"rev_{uuid.uuid4().hex[:12]}",
            reason=failure_reason,
            original_steps=original_steps,
            revised_steps=revised_steps,
            original_failure_boundary=original_failure_boundary,
            revised_failure_boundary=revised_failure_boundary,
            proposed_at=int(time.time() * 1000),
            proposed_by=proposed_by,
        )

        logger.info(
            "Revision proposed for skill %s: reason=%s, revised_steps=%d",
            skill_id,
            failure_reason[:80],
            len(revised_steps),
        )
        return proposal

    async def apply_revision(
        self,
        *,
        skill_id: str,
        proposal: RevisionProposal,
    ) -> dict[str, Any]:
        """应用修订到 Skill.

        1. 将 proposal 追加到 Skill 的 revision_history
        2. 更新 Skill 的 steps 和 failure_boundary
        3. 更新 updated_at
        4. 返回更新后的 Skill
        """
        skill = await self._store.get(skill_id)
        if skill is None:
            raise KeyError(f"Skill not found: {skill_id}")

        # 构建 revision_history 条目
        revision_entry: dict[str, Any] = {
            "revision_id": proposal.revision_id,
            "reason": proposal.reason,
            "proposed_at": proposal.proposed_at,
            "proposed_by": proposal.proposed_by,
            "original_steps": [dict(s) for s in proposal.original_steps],
            "revised_steps": [dict(s) for s in proposal.revised_steps],
            "original_failure_boundary": proposal.original_failure_boundary,
            "revised_failure_boundary": proposal.revised_failure_boundary,
        }
        if proposal.ab_test_result is not None:
            revision_entry["ab_test_result"] = dict(proposal.ab_test_result)

        existing_revisions = skill.get("revision_history")
        if not isinstance(existing_revisions, list):
            existing_revisions = []

        patch: dict[str, Any] = {
            "steps": [dict(s) for s in proposal.revised_steps],
            "failure_boundary": proposal.revised_failure_boundary,
            "revision_history": list(existing_revisions) + [revision_entry],
            "write_origin": "revision",
        }

        updated = await self._store.update(skill_id, patch)
        logger.info(
            "Revision applied to skill %s: revision_id=%s, total_revisions=%d",
            skill_id,
            proposal.revision_id,
            len(updated.get("revision_history", [])),
        )
        return updated

    async def ab_compare(
        self,
        *,
        skill_id: str,
        original_steps: list[dict[str, Any]],
        revised_steps: list[dict[str, Any]],
        test_cases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """A/B 对比修订前后的效果.

        模拟运行:
        1. 用 original_steps 对每个 test_case 生成预期结果
        2. 用 revised_steps 对每个 test_case 生成预期结果
        3. 对比: revised 不劣于 original 则通过

        返回:
        {
            "original_score": float,
            "revised_score": float,
            "passed": bool,  # revised_score >= original_score
            "case_results": [...]
        }
        """
        case_results: list[dict[str, Any]] = []

        for case in test_cases:
            orig_score = self._simulate_step_execution(original_steps, case)
            rev_score = self._simulate_step_execution(revised_steps, case)
            case_results.append(
                {
                    "case": case,
                    "original_score": orig_score,
                    "revised_score": rev_score,
                }
            )

        if case_results:
            original_score = sum(c["original_score"] for c in case_results) / len(case_results)
            revised_score = sum(c["revised_score"] for c in case_results) / len(case_results)
        else:
            original_score = 0.0
            revised_score = 0.0

        return {
            "original_score": original_score,
            "revised_score": revised_score,
            "passed": revised_score >= original_score,
            "case_results": case_results,
        }

    # ==================== 内部工具 ====================

    def _extract_failure_reason(self, critic_final: dict[str, Any]) -> str:
        """从 critic 评审结果提取失败原因."""
        issues = critic_final.get("issues")
        if isinstance(issues, list) and issues:
            parts: list[str] = []
            for issue in issues[:3]:
                if isinstance(issue, dict):
                    msg = issue.get("message") or issue.get("code") or issue.get("description")
                    if msg:
                        parts.append(str(msg))
                elif isinstance(issue, str):
                    parts.append(issue)
            if parts:
                return "; ".join(parts)

        risk_level = critic_final.get("risk_level")
        if isinstance(risk_level, str) and risk_level.strip():
            return f"risk_level={risk_level.strip()}"

        summary = critic_final.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary[:200]

        return "execution_suboptimal"

    def _generate_revised_steps(
        self,
        original_steps: list[dict[str, Any]],
        failure_reason: str,
        execution_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """生成修订后的步骤.

        策略:
        1. 保留成功的步骤
        2. 对失败步骤添加 failure_note
        3. 添加新的 recovery 步骤
        """
        # 从 execution_result 中提取失败的步骤描述
        failed_step_descs = self._extract_failed_step_descs(execution_result)

        revised: list[dict[str, Any]] = []
        for step in original_steps:
            if not isinstance(step, dict):
                continue
            revised_step = dict(step)
            desc = step.get("description")
            desc_str = str(desc) if desc is not None else ""
            if desc_str in failed_step_descs:
                revised_step["failure_note"] = failure_reason
            revised.append(revised_step)

        # 添加 recovery 步骤
        recovery_step: dict[str, Any] = {
            "description": "recovery: review failure and retry with adjusted approach",
            "expected_outcome": "issue_resolved",
            "recovery_for": failure_reason[:100] if failure_reason else "previous_failure",
        }
        revised.append(recovery_step)

        return revised

    def _generate_revised_failure_boundary(
        self,
        original_failure_boundary: str,
        failure_reason: str,
    ) -> str:
        """生成修订后的 failure_boundary."""
        if not original_failure_boundary.strip():
            return failure_reason if failure_reason else "no_known_failure_boundary"

        if failure_reason and failure_reason not in original_failure_boundary:
            return f"{original_failure_boundary}; {failure_reason}"

        return original_failure_boundary

    def _extract_failed_step_descs(self, execution_result: dict[str, Any]) -> set[str]:
        """从 execution_result 中提取失败步骤的描述集合."""
        failed_descs: set[str] = set()

        failed_steps = execution_result.get("failed_steps")
        if isinstance(failed_steps, list):
            for fs in failed_steps:
                if isinstance(fs, dict):
                    desc = fs.get("description") or fs.get("step_id")
                    if desc:
                        failed_descs.add(str(desc))
                elif isinstance(fs, str):
                    failed_descs.add(fs)

        # 兼容 receipts 中的失败标记
        receipts = execution_result.get("receipts")
        if isinstance(receipts, list):
            for receipt in receipts:
                if not isinstance(receipt, dict):
                    continue
                if receipt.get("status") == "failed":
                    desc = receipt.get("step_id") or receipt.get("description")
                    if desc:
                        failed_descs.add(str(desc))

        return failed_descs

    def _simulate_step_execution(
        self,
        steps: list[dict[str, Any]],
        test_case: dict[str, Any],
    ) -> float:
        """模拟步骤执行, 返回得分 [0, 1].

        评分逻辑:
        1. 每个有 description 的步骤: 基础分 0.3
        2. expected_outcome 匹配 test_case 期望: +0.3
        3. 有 failure_note (处理失败): +0.2, 若 test_case 期望失败再 +0.2
        4. recovery 步骤: +0.2, 若 test_case 期望失败再 +0.2
        """
        if not steps:
            return 0.0

        expected_outcomes = test_case.get("expected_outcomes")
        if not isinstance(expected_outcomes, list):
            expected_outcomes = []

        expect_failure = bool(test_case.get("expect_failure", False))

        total = 0.0
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_score = 0.0

            desc = step.get("description")
            if isinstance(desc, str) and desc.strip():
                step_score += 0.3

            outcome = step.get("expected_outcome")
            if isinstance(outcome, str) and outcome in expected_outcomes:
                step_score += 0.3

            if step.get("failure_note"):
                step_score += 0.2
                if expect_failure:
                    step_score += 0.2

            if isinstance(desc, str) and "recovery" in desc.lower():
                step_score += 0.2
                if expect_failure:
                    step_score += 0.2

            total += min(1.0, step_score)

        return total / len(steps) if steps else 0.0
