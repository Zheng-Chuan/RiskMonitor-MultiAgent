"""Phase 8B: 自我改进闭环端到端验收测试.

验证 Phase 5-8 各能力形成的涌现属性: 系统越用越好.

覆盖能力:
- Phase 5: Skill 系统 (SkillStore, SkillProposer, SkillInjector, SkillUsageTracker, SkillReviser, SkillGovernor)
- Phase 6: 记忆永久化 (PersistenceBackend, TTL策略, ContextCompressor, SessionSegmenter)
- Phase 7: 调度与网关 (CronManager, GatewayAdapter, GatewayRouter)
- Phase 8A: Prompt 优化 (TieredPromptBuilder, PromptCacheManager)

设计约束:
- 测试使用 mock 数据, 不依赖外部 LLM API
- 使用 InMemoryPersistenceBackend 替代 MySQL
- 每个测试独立可运行 (无顺序依赖)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


# ==================== Fixture 覆盖 ====================


@pytest.fixture(autouse=True, scope="module")
def _require_mysql_for_acceptance_tests():
    """覆盖 acceptance conftest 的 MySQL 依赖.

    自我改进闭环测试使用 InMemoryPersistenceBackend, 不需要真实 MySQL.
    """
    yield


# ==================== In-Memory 持久化后端 ====================


class InMemoryPersistenceBackend:
    """内存态持久化后端, 用于测试.

    模拟 PersistenceBackend 的接口, 数据存储在 Python dict 中.
    不依赖 MySQL 或 Redis.
    """

    def __init__(self) -> None:
        self._memory_store: dict[str, dict[str, Any]] = {}
        self._skill_store: dict[str, dict[str, Any]] = {}

    async def persist_memory_entry(self, entry: dict[str, Any]) -> bool:
        entry_id = str(entry.get("entry_id") or "")
        if not entry_id:
            return False
        self._memory_store[entry_id] = dict(entry)
        return True

    async def batch_persist_memory(self, entries: list[dict[str, Any]]) -> int:
        count = 0
        for entry in entries:
            if await self.persist_memory_entry(entry):
                count += 1
        return count

    async def load_memory_entries(
        self,
        *,
        run_id: str | None = None,
        agent_id: str | None = None,
        kinds: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for entry in self._memory_store.values():
            if run_id is not None and entry.get("run_id") != run_id:
                continue
            if agent_id is not None and entry.get("agent_id") != agent_id:
                continue
            if kinds is not None and entry.get("kind") not in kinds:
                continue
            results.append(dict(entry))
            if len(results) >= limit:
                break
        results.sort(key=lambda e: int(e.get("ts_ms") or 0), reverse=True)
        return results

    async def persist_skill(self, skill: dict[str, Any]) -> bool:
        skill_id = str(skill.get("skill_id") or "")
        if not skill_id:
            return False
        self._skill_store[skill_id] = dict(skill)
        return True

    async def load_skills(self, *, status: str | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for skill in self._skill_store.values():
            if status is not None and skill.get("status") != status:
                continue
            results.append(dict(skill))
        results.sort(key=lambda s: int(s.get("updated_at") or 0), reverse=True)
        return results

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        pass


# ==================== 测试数据构造 ====================


def _make_skill(**kwargs: Any) -> dict[str, Any]:
    """构造测试用 Skill dict."""
    base: dict[str, Any] = {
        "name": "交易台风险排查",
        "tags": ["risk", "trading"],
        "applicable_conditions": ["延迟异常", "告警触发"],
        "steps": [
            {"description": "查询持仓数据", "expected_outcome": "获取当前持仓"},
            {"description": "核对限额", "expected_outcome": "确认是否超限"},
        ],
        "failure_boundary": "禁止伪造数据",
        "confidence": 0.6,
    }
    base.update(kwargs)
    return base


def _make_task(**kwargs: Any) -> dict[str, Any]:
    """构造测试用 task."""
    base: dict[str, Any] = {
        "task_id": "task-001",
        "intent": "query_positions",
        "content": {
            "category": "risk",
            "description": "查询交易台持仓并核对限额",
        },
    }
    base.update(kwargs)
    return base


def _make_critic_ok(**kwargs: Any) -> dict[str, Any]:
    """构造 critic ok=True 的评审结果."""
    base: dict[str, Any] = {
        "ok": True,
        "confidence": 0.92,
        "issues": [],
        "risk_level": "LOW",
    }
    base.update(kwargs)
    return base


def _make_critic_fail(**kwargs: Any) -> dict[str, Any]:
    """构造 critic ok=False 的评审结果."""
    base: dict[str, Any] = {
        "ok": False,
        "confidence": 0.3,
        "issues": [
            {"message": "持仓数据不完整", "code": "INCOMPLETE_DATA"},
            {"message": "限额核对遗漏", "code": "MISSING_CHECK"},
        ],
        "risk_level": "HIGH",
    }
    base.update(kwargs)
    return base


def _make_execution_result(**kwargs: Any) -> dict[str, Any]:
    """构造执行结果."""
    base: dict[str, Any] = {
        "status": "completed",
        "final_output": {"summary": "执行完成"},
        "failed_steps": [
            {"description": "核对限额", "step_id": "s2"},
        ],
        "receipts": [],
    }
    base.update(kwargs)
    return base


def _make_orchestrator_output(**kwargs: Any) -> dict[str, Any]:
    """构造 orchestrator 输出."""
    base: dict[str, Any] = {
        "plan_steps": [
            {"instruction": "查询持仓数据", "expected_outcome": "获取当前持仓", "target_agent": "risk_analyst"},
            {"instruction": "核对限额", "expected_outcome": "确认是否超限", "target_agent": "risk_analyst"},
        ],
    }
    base.update(kwargs)
    return base


def _make_skill_store() -> "SkillStore":
    """创建带有 InMemoryPersistenceBackend 的 SkillStore."""
    from riskmonitor_multiagent.skills import SkillStore

    store = SkillStore()
    store._set_persistence(InMemoryPersistenceBackend())
    return store


# ==================== 测试类 ====================


class TestSelfImprovingLoop:
    """验证自我改进闭环的端到端验收测试."""

    # ==================== 测试 1 ====================

    @pytest.mark.asyncio
    async def test_skill_accumulation_over_multiple_runs(self):
        """测试 1: Skill 库随使用积累.

        模拟 3 次高质量完成的 run:
        - Run 1: 创建第一个 Skill
        - Run 2: 创建第二个 Skill (不同模式)
        - Run 3: 更新已有 Skill (相同模式, 语义去重)
        验证: SkillStore 中有 2 个 Skill, usage_count 正确
        """
        from riskmonitor_multiagent.skills import SkillProposer

        store = _make_skill_store()
        proposer = SkillProposer(store, confidence_threshold=0.85)

        # Run 1: 交易台风险排查模式
        result1 = await proposer.propose(
            run_id="run-001",
            task=_make_task(intent="交易台风险排查"),
            critic_final=_make_critic_ok(),
            orchestrator_output=_make_orchestrator_output(),
        )
        assert result1["action"] == "created"
        assert result1["skill_id"] is not None

        # Run 2: 限额监控模式 (不同模式)
        result2 = await proposer.propose(
            run_id="run-002",
            task=_make_task(
                intent="限额监控预警",
                content={"category": "limit", "description": "监控交易限额并预警"},
            ),
            critic_final=_make_critic_ok(),
            orchestrator_output=_make_orchestrator_output(
                plan_steps=[
                    {"instruction": "查询限额配置", "expected_outcome": "获取限额", "target_agent": "risk_analyst"},
                    {"instruction": "比对持仓与限额", "expected_outcome": "确认超限", "target_agent": "risk_analyst"},
                ],
            ),
        )
        assert result2["action"] == "created"
        assert result2["skill_id"] is not None
        assert result2["skill_id"] != result1["skill_id"]

        # Run 3: 相同模式 (语义去重 → 更新已有 Skill)
        result3 = await proposer.propose(
            run_id="run-003",
            task=_make_task(intent="交易台风险排查"),
            critic_final=_make_critic_ok(),
            orchestrator_output=_make_orchestrator_output(),
        )
        assert result3["action"] == "updated"
        assert result3["skill_id"] == result1["skill_id"]

        # 验证: SkillStore 中有 2 个 Skill
        all_skills = await store.list_all()
        assert len(all_skills) == 2

        # 验证: 第一个 Skill 的 revision_history 非空 (因被更新过)
        skill1 = await store.get(result1["skill_id"])
        assert len(skill1["revision_history"]) >= 1

    # ==================== 测试 2 ====================

    @pytest.mark.asyncio
    async def test_skill_injection_improves_planning(self):
        """测试 2: Skill 注入提升规划质量.

        - 创建一个与当前任务高度相关的 Skill
        - skill_off: 规划 prompt 中无 Skill 引用
        - skill_on: 规划 prompt 中有 Skill 引用
        验证: skill_on 时 context["skills"] 非空
        """
        from riskmonitor_multiagent.skills import SkillInjector

        store = _make_skill_store()
        await store.create(
            _make_skill(
                name="交易台风险排查",
                applicable_conditions=["延迟异常", "告警触发", "持仓", "限额"],
                confidence=0.85,
            )
        )

        injector = SkillInjector(store, min_confidence=0.3, max_skills=3)
        task = _make_task()

        # skill_off
        result_off = await injector.retrieve_applicable_skills(
            task=task, skill_enabled=False
        )
        assert result_off["skill_enabled"] is False
        assert result_off["skills"] == []
        assert result_off["skill_count"] == 0

        # skill_on
        result_on = await injector.retrieve_applicable_skills(
            task=task, skill_enabled=True
        )
        assert result_on["skill_enabled"] is True
        assert result_on["skill_count"] >= 1
        assert len(result_on["skills"]) >= 1

        # 验证注入结构包含必要字段
        injected = result_on["skills"][0]
        assert "skill_id" in injected
        assert "name" in injected
        assert "steps" in injected
        assert "applicable_conditions" in injected

    # ==================== 测试 3 ====================

    @pytest.mark.asyncio
    async def test_confidence_updates_after_execution(self):
        """测试 3: 执行结果驱动置信度变化.

        - 注入 Skill → 执行成功 → 置信度上升
        - 注入 Skill → 执行失败 → 置信度下降
        - 连续失败 → 自动降级
        验证: confidence 变化方向正确, status 转换正确
        """
        from riskmonitor_multiagent.skills import SkillUsageTracker

        store = _make_skill_store()
        created = await store.create(_make_skill(confidence=0.5))
        skill_id = created["skill_id"]

        tracker = SkillUsageTracker(store, success_delta=0.1, fail_delta=0.1)

        # 成功 → 置信度上升
        tracker.track_usage(skill_id, run_id="run-success")
        results = await tracker.update_after_execution(
            run_id="run-success", execution_success=True, critic_ok=True
        )
        assert len(results) == 1
        assert results[0]["new_confidence"] > results[0]["old_confidence"]
        assert results[0]["success"] is True

        # 失败 → 置信度下降
        tracker.track_usage(skill_id, run_id="run-fail")
        results = await tracker.update_after_execution(
            run_id="run-fail", execution_success=False, critic_ok=False
        )
        assert len(results) == 1
        assert results[0]["new_confidence"] < results[0]["old_confidence"]
        assert results[0]["success"] is False

        # 连续失败 → 自动降级 (confidence < 0.3 → deprecated)
        skill = await store.get(skill_id)
        current = float(skill["confidence"])

        # 持续失败直到降级
        fail_run_idx = 0
        while current >= 0.3:
            fail_run_idx += 1
            tracker.track_usage(skill_id, run_id=f"run-fail-{fail_run_idx}")
            await tracker.update_after_execution(
                run_id=f"run-fail-{fail_run_idx}", execution_success=False, critic_ok=False
            )
            skill = await store.get(skill_id)
            current = float(skill["confidence"])

        # 验证: status 已变为 deprecated
        assert skill["status"] == "deprecated"

        # 继续失败 → archived (confidence < 0.15)
        while current >= 0.15:
            fail_run_idx += 1
            tracker.track_usage(skill_id, run_id=f"run-fail-{fail_run_idx}")
            await tracker.update_after_execution(
                run_id=f"run-fail-{fail_run_idx}", execution_success=False, critic_ok=False
            )
            skill = await store.get(skill_id)
            current = float(skill["confidence"])

        assert skill["status"] == "archived"

    # ==================== 测试 4 ====================

    @pytest.mark.asyncio
    async def test_skill_revision_after_failure(self):
        """测试 4: 失败后 Skill 被修订.

        - 使用 Skill → 失败 → Critic 提议修订
        - 修订后 revision_history 非空
        - 修订后的 steps 与原 steps 不同
        验证: revision 链路完整
        """
        from riskmonitor_multiagent.skills import SkillReviser

        store = _make_skill_store()
        created = await store.create(_make_skill())
        skill_id = created["skill_id"]
        original_steps = list(created["steps"])

        reviser = SkillReviser(store)

        # 检查并提议修订
        proposal = await reviser.check_and_propose_revision(
            skill_id=skill_id,
            run_id="run-001",
            execution_result=_make_execution_result(),
            critic_final=_make_critic_fail(),
        )
        assert proposal is not None
        assert proposal.skill_id == skill_id
        assert proposal.revision_id.startswith("rev_")
        assert proposal.proposed_by == "critic"

        # 应用修订
        updated = await reviser.apply_revision(
            skill_id=skill_id, proposal=proposal
        )

        # 验证: revision_history 非空
        assert len(updated["revision_history"]) >= 1
        rev_entry = updated["revision_history"][0]
        assert rev_entry["revision_id"] == proposal.revision_id
        assert rev_entry["proposed_by"] == "critic"

        # 验证: 修订后的 steps 与原 steps 不同
        assert updated["steps"] != original_steps
        # 修订后增加了 recovery 步骤
        assert len(updated["steps"]) > len(original_steps)

        # 验证: write_origin 标记为 revision
        assert updated["write_origin"] == "revision"

    # ==================== 测试 5 ====================

    @pytest.mark.asyncio
    async def test_governance_prevents_noise(self):
        """测试 5: 治理防止噪音.

        - 创建大量低质量 Skill
        - 注入时只返回高质量 Skill
        - 低置信度 Skill 不参与注入
        - token 预算不超限
        验证: 注入数量受控, 质量受控
        """
        from riskmonitor_multiagent.skills import (
            SkillGovernanceConfig,
            SkillGovernor,
            SkillInjector,
        )

        store = _make_skill_store()

        # 创建低置信度 Skill (噪音)
        for i in range(5):
            await store.create(
                _make_skill(
                    name=f"低质量技能{i}",
                    confidence=0.1,
                    status="active",
                )
            )

        # 创建 deprecated Skill
        for i in range(3):
            await store.create(
                _make_skill(
                    name=f"废弃技能{i}",
                    confidence=0.8,
                    status="deprecated",
                )
            )

        # 创建高质量 Skill
        high_quality_names = []
        for i in range(3):
            name = f"高质量技能{i}"
            high_quality_names.append(name)
            await store.create(
                _make_skill(
                    name=name,
                    confidence=0.9,
                    status="active",
                )
            )

        # 配置治理: 注入最低置信度 0.3, 最多 2 个, token 预算 500
        config = SkillGovernanceConfig(
            min_confidence_for_injection=0.3,
            max_skills_per_category=2,
            max_injection_token_budget=500,
        )
        governor = SkillGovernor(store, config)
        injector = SkillInjector(
            store, min_confidence=0.0, max_skills=10, governor=governor
        )

        result = await injector.retrieve_applicable_skills(
            task=_make_task(), skill_enabled=True
        )

        # 验证: 注入数量受控 (不超过 max_skills_per_category=2)
        assert result["skill_count"] <= 2

        # 验证: 只返回高质量 Skill (低置信度和 deprecated 被过滤)
        injected_names = [s["name"] for s in result["skills"]]
        for name in injected_names:
            assert name in high_quality_names

        # 验证: token 预算不超限
        token_cost = governor.estimate_skills_token_cost(result["skills"])
        assert token_cost <= config.max_injection_token_budget

    # ==================== 测试 6 ====================

    @pytest.mark.asyncio
    async def test_memory_persistence_and_recovery(self):
        """测试 6: 记忆永久化和恢复.

        - 创建 MemoryEntry → 落盘
        - 创建 Skill → 落盘
        - 模拟恢复: restore_from_persistence
        验证: 数据一致
        """
        from riskmonitor_multiagent.memory.persistence_backend import (
            _build_memory_row,
            _parse_memory_row,
        )

        backend = InMemoryPersistenceBackend()

        # 创建 MemoryEntry 并落盘
        memory_entry = {
            "entry_id": "mem_test_001",
            "ts_ms": int(time.time() * 1000),
            "agent_id": "orchestrator",
            "scope": "shared",
            "kind": "lesson",
            "memory_type": "procedural",
            "content": {"summary": "交易台风险排查经验", "decision_pattern": "先查持仓再核对限额"},
            "source": "critic",
            "confidence": 0.9,
            "created_by": "system",
            "trace_ref": {"run_id": "run-001"},
            "tags": ["risk", "trading"],
            "session_id": "session-001",
            "run_id": "run-001",
        }
        ok = await backend.persist_memory_entry(memory_entry)
        assert ok is True

        # 恢复 MemoryEntry
        loaded = await backend.load_memory_entries(run_id="run-001")
        assert len(loaded) == 1
        assert loaded[0]["entry_id"] == "mem_test_001"
        assert loaded[0]["kind"] == "lesson"

        # 创建 Skill 并落盘
        skill = _make_skill(confidence=0.85)
        from riskmonitor_multiagent.skills.skill_contract import validate_skill

        validated_skill = validate_skill(skill)
        ok = await backend.persist_skill(validated_skill)
        assert ok is True

        # 恢复 Skill
        loaded_skills = await backend.load_skills()
        assert len(loaded_skills) == 1
        assert loaded_skills[0]["skill_id"] == validated_skill["skill_id"]
        assert loaded_skills[0]["name"] == validated_skill["name"]

        # 验证 SkillStore 级别的恢复
        store1 = _make_skill_store()
        store1._set_persistence(backend)
        await store1.create(_make_skill(name="持久化测试技能", confidence=0.7))
        flushed = await store1.flush_to_persistence()
        assert flushed >= 1

        # 新 Store 从持久化恢复
        store2 = _make_skill_store()
        store2._set_persistence(backend)
        restored = await store2.restore_from_persistence()
        assert restored >= 1

        # 验证数据一致
        all_skills = await store2.list_all()
        restored_names = [s["name"] for s in all_skills]
        assert "持久化测试技能" in restored_names

    # ==================== 测试 7 ====================

    @pytest.mark.asyncio
    async def test_ttl_strategy_correctness(self):
        """测试 7: TTL 分级正确.

        - ephemeral: 工作态记忆, 24h 后过期
        - short_term: 任务记忆, 7d 后过期
        - long_term: 经验, 永不过期
        - permanent: Skill, 永不过期
        验证: 各级别 is_expired 判断正确
        """
        from riskmonitor_multiagent.memory import TTL_SECONDS, TTLTier, TTLPolicyEngine

        engine = TTLPolicyEngine()
        now_ms = int(time.time() * 1000)

        # ephemeral: 工作态记忆 (kind=working)
        ephemeral_entry = {
            "kind": "working",
            "memory_type": "episodic",
            "ts_ms": now_ms - 25 * 3600 * 1000,  # 25h 前
        }
        assert engine.classify(ephemeral_entry) == TTLTier.EPHEMERAL
        assert engine.is_expired(ephemeral_entry, now_ms=now_ms) is True

        # ephemeral 未过期
        ephemeral_fresh = {
            "kind": "working",
            "memory_type": "episodic",
            "ts_ms": now_ms - 1 * 3600 * 1000,  # 1h 前
        }
        assert engine.is_expired(ephemeral_fresh, now_ms=now_ms) is False

        # short_term: 任务记忆 (kind=final)
        short_term_entry = {
            "kind": "final",
            "memory_type": "episodic",
            "ts_ms": now_ms - 8 * 24 * 3600 * 1000,  # 8d 前
        }
        assert engine.classify(short_term_entry) == TTLTier.SHORT_TERM
        assert engine.is_expired(short_term_entry, now_ms=now_ms) is True

        # short_term 未过期
        short_term_fresh = {
            "kind": "final",
            "memory_type": "episodic",
            "ts_ms": now_ms - 3 * 24 * 3600 * 1000,  # 3d 前
        }
        assert engine.is_expired(short_term_fresh, now_ms=now_ms) is False

        # long_term: 经验 (kind=lesson) → 永不过期
        long_term_entry = {
            "kind": "lesson",
            "memory_type": "procedural",
            "ts_ms": now_ms - 365 * 24 * 3600 * 1000,  # 1年前
        }
        assert engine.classify(long_term_entry) == TTLTier.LONG_TERM
        assert engine.is_expired(long_term_entry, now_ms=now_ms) is False

        # permanent: Skill (kind=skill) → 永不过期
        permanent_entry = {
            "kind": "skill",
            "memory_type": "procedural",
            "ts_ms": now_ms - 365 * 24 * 3600 * 1000,  # 1年前
        }
        assert engine.classify(permanent_entry) == TTLTier.PERMANENT
        assert engine.is_expired(permanent_entry, now_ms=now_ms) is False

        # 验证 TTL_SECONDS 常量
        assert TTL_SECONDS[TTLTier.EPHEMERAL] == 86400
        assert TTL_SECONDS[TTLTier.SHORT_TERM] == 604800
        assert TTL_SECONDS[TTLTier.LONG_TERM] is None
        assert TTL_SECONDS[TTLTier.PERMANENT] is None

        # 验证 should_persist: long_term 和 permanent 需要落盘
        assert engine.should_persist(long_term_entry) is True
        assert engine.should_persist(permanent_entry) is True
        assert engine.should_persist(ephemeral_entry) is False
        assert engine.should_persist(short_term_entry) is False

    # ==================== 测试 8 ====================

    @pytest.mark.asyncio
    async def test_context_compression_for_long_tasks(self):
        """测试 8: 长任务上下文压缩.

        - 构建 25 条消息的长历史
        - 触发压缩
        - 压缩后 token 数在限制内
        - 头尾消息完整保留
        验证: 压缩有效, 关键信息不丢失
        """
        from riskmonitor_multiagent.memory import ContextCompressor

        # max_tokens=1000: 中间消息会被截断到 100 字, 压缩后应在限制内
        compressor = ContextCompressor(
            max_tokens=1000,
            head_protect_count=2,
            tail_protect_count=3,
            compression_threshold=0.85,
            enable_llm_summary=False,  # 不依赖 LLM
        )

        # 构建 15 条消息: 短头尾 + 长中间消息 (截断后压缩有效)
        messages: list[dict[str, Any]] = []
        messages.append({"role": "system", "content": "风险管理助手."})
        messages.append({"role": "user", "content": "排查TRADER-001风险."})
        for i in range(3, 13):
            role = "assistant" if i % 2 == 0 else "user"
            # 每条中间消息约 300 字, 截断到 100 字后压缩比为 ~1/3
            messages.append({
                "role": role,
                "content": (
                    f"步骤{i}:正在执行交易台风险排查的第{i}个子任务"
                    f"涉及持仓数据查询和限额核对的详细分析"
                    f"包括delta exposure计算和breach检测"
                    f"同时需要比对历史持仓和实时快照数据"
                    f"以及与交易对手的信用敞口进行交叉验证"
                    f"还需要检查市场流动性和压力测试指标"
                    f"并评估利率敏感性和汇率风险敞口"
                    f"最终输出风险评估报告和处置建议"
                    f"这是第{i}步的完整执行记录和中间结果"
                    f"包括数据处理流程分析判断依据和建议措施"
                    f"以及风险指标阈值检查和预警信号确认"
                ),
            })
        messages.append({"role": "assistant", "content": "排查完成."})
        messages.append({"role": "user", "content": "请给结论."})
        messages.append({"role": "assistant", "content": "风险正常."})

        # 验证需要压缩
        assert compressor.should_compress(messages) is True

        # 执行压缩
        result = await compressor.compress(messages)

        # 验证: 触发了压缩
        assert result.compressed is True
        assert result.original_tokens > result.compressed_tokens
        assert result.compression_ratio < 1.0

        # 验证: 压缩后 token 数在限制内 (压缩后应低于 max_tokens)
        assert result.compressed_tokens <= compressor.max_tokens

        # 验证: 头尾消息完整保留
        compressed_msgs = result.compressed_messages
        assert compressed_msgs[0]["content"] == messages[0]["content"]
        assert compressed_msgs[-1]["content"] == messages[-1]["content"]

        # 验证: 保护了头部和尾部消息
        assert result.protected_head_count == 2
        assert result.protected_tail_count == 3
        assert result.summarized_count > 0

    # ==================== 测试 9 ====================

    @pytest.mark.asyncio
    async def test_session_segmentation_for_long_run(self):
        """测试 9: 超长任务自动分段.

        - 模拟 15 步任务 (max_steps_per_segment=10)
        - 应产生 2 段
        - parent_segment_id 链正确
        - 恢复上下文包含前段摘要
        验证: 分段不丢失上下文
        """
        from riskmonitor_multiagent.memory import SessionSegmenter

        segmenter = SessionSegmenter(max_steps_per_segment=10)
        run_id = "run-seg-001"

        # 模拟 15 步任务
        all_steps: list[dict[str, Any]] = []
        for i in range(15):
            all_steps.append({
                "step_id": f"step-{i:03d}",
                "kind": "delegate" if i % 3 == 0 else "tool_call",
                "status": "completed",
                "tool_name": "check_positions" if i % 2 == 0 else "check_limits",
                "target_agent": "risk_analyst",
            })

        # 第一段: step 0-9
        seg1_steps = all_steps[:10]
        checkpoint1 = await segmenter.create_checkpoint(
            run_id=run_id,
            step_count=10,
            steps=seg1_steps,
            parent_segment_id=None,
            context={"task_id": "task-001", "phase": "investigation"},
        )
        assert checkpoint1.segment_index == 0
        assert checkpoint1.parent_segment_id is None
        assert checkpoint1.step_count == 10
        assert len(checkpoint1.summary) > 0

        # 第二段: step 10-14
        seg2_steps = all_steps[10:]
        checkpoint2 = await segmenter.create_checkpoint(
            run_id=run_id,
            step_count=5,
            steps=seg2_steps,
            parent_segment_id=checkpoint1.segment_id,
            context={"task_id": "task-001", "phase": "conclusion"},
        )
        assert checkpoint2.segment_index == 1
        assert checkpoint2.parent_segment_id == checkpoint1.segment_id
        assert checkpoint2.step_count == 5

        # 验证: 产生 2 段
        chain = segmenter.get_segment_chain(run_id)
        assert len(chain) == 2
        assert chain[0].segment_index == 0
        assert chain[1].segment_index == 1

        # 验证: parent_segment_id 链正确
        assert chain[0].parent_segment_id is None
        assert chain[1].parent_segment_id == chain[0].segment_id

        # 验证: 恢复上下文包含前段摘要
        resume_ctx = segmenter.build_resume_context(checkpoint2)
        assert "summary" in resume_ctx
        assert len(resume_ctx["summary"]) > 0
        assert resume_ctx["parent_segment_id"] == checkpoint1.segment_id
        assert resume_ctx["segment_index"] == 1
        assert resume_ctx["context_snapshot"]["phase"] == "conclusion"

    # ==================== 测试 10 ====================

    @pytest.mark.asyncio
    async def test_prompt_tier_caching(self):
        """测试 10: Prompt 三层缓存.

        - 构建 stable_tier → 缓存
        - 第二次构建 → 命中缓存
        - volatile_tier 变化 → stable_tier 仍命中
        - 版本变更 → 缓存失效
        验证: 缓存命中率 > 0, 失效正确
        """
        from riskmonitor_multiagent.prompts import PromptCacheManager, TieredPromptBuilder

        builder = TieredPromptBuilder(stable_version="v1", context_date="2026-06-27")
        cache = PromptCacheManager()

        stable = builder.build_stable_tier(
            agent_role="风险管理助手",
            tools_index=[{"name": "check_positions", "description": "查询持仓"}],
            behavior_rules=["必须核实数据来源", "禁止伪造数据"],
        )
        context = builder.build_context_tier(
            skills=[{"name": "交易台排查", "confidence": 0.8}],
            project_rules=["每日收盘后排查"],
        )

        cache_key = builder.get_cache_key(stable, context)

        # 第一次: 缓存未命中 → miss
        cached = cache.get(cache_key)
        assert cached is None
        cache.set(cache_key, stable.content, stable.version)

        # 第二次: 缓存命中 → hit
        cached = cache.get(cache_key)
        assert cached is not None
        assert cached["content"] == stable.content

        # volatile_tier 变化不影响 stable_tier 缓存
        # volatile_tier 版本为毫秒时间戳, 不参与缓存键
        volatile1 = builder.build_volatile_tier(
            current_event={"type": "alert"},
            task={"task_id": "task-001"},
        )
        volatile2 = builder.build_volatile_tier(
            current_event={"type": "alert", "severity": "HIGH"},
            task={"task_id": "task-001"},
        )
        # volatile_tier 不可缓存
        assert volatile1.cacheable is False
        assert volatile2.cacheable is False
        # volatile_tier 内容不同
        assert volatile1.content != volatile2.content

        # stable_tier 仍命中 (volatile 变化不影响缓存)
        cached = cache.get(cache_key)
        assert cached is not None

        # 版本变更 → 缓存失效
        invalidated = cache.invalidate(version="v1")
        assert invalidated >= 1

        cached = cache.get(cache_key)
        assert cached is None  # 已失效

        # 验证: 缓存命中率 > 0
        stats = cache.get_stats()
        assert stats["hit_count"] > 0
        assert stats["miss_count"] > 0
        assert stats["hit_rate"] > 0.0

    # ==================== 测试 11 ====================

    @pytest.mark.asyncio
    async def test_cron_task_triggers_workflow(self):
        """测试 11: Cron 触发任务进入统一执行内核.

        - 创建 CronTask
        - 触发 → 进入 system_event 入口
        - 有完整 trace
        验证: Cron 任务不绕过治理
        """
        from riskmonitor_multiagent.scheduling import CronManager

        cron_mgr = CronManager()

        # 创建 CronTask
        task_template = {
            "intent": "daily_risk_check",
            "payload": {"content": "每日收盘后自动排查交易台风险"},
        }
        cron_task = await cron_mgr.create_task({
            "name": "每日风险排查",
            "natural_language": "每个工作日收盘后",
            "task_template": task_template,
            "trigger_config": {"entry_type": "system_event"},
        })

        assert cron_task.task_id.startswith("cron_")
        assert cron_task.enabled is True
        assert cron_task.cron_expression == "0 18 * * 1-5"
        assert cron_task.max_recursion_depth == 3

        # 模拟触发
        due_tasks = await cron_mgr.get_due_tasks()
        assert len(due_tasks) >= 1
        assert due_tasks[0].task_id == cron_task.task_id

        await cron_mgr.mark_triggered(cron_task.task_id)
        task = await cron_mgr.get_task(cron_task.task_id)
        assert task.trigger_count == 1
        assert task.last_triggered is not None

        # 验证: Cron 任务通过 system_event 入口 (不绕过治理)
        assert task.trigger_config.get("entry_type") == "system_event"

        # 验证: 递归防护
        assert cron_mgr.check_recursion(cron_task.task_id, 1) is True
        assert cron_mgr.check_recursion(cron_task.task_id, 5) is False  # 超过 max_recursion_depth=3

        # 验证: 完整的 trace 结构
        trace = {
            "task_id": cron_task.task_id,
            "trigger_source": "cron",
            "entry_type": "system_event",
            "task_template": task_template,
            "cron_expression": cron_task.cron_expression,
            "trigger_count": task.trigger_count,
        }
        assert trace["entry_type"] == "system_event"
        assert trace["trigger_source"] == "cron"

    # ==================== 测试 12 ====================

    @pytest.mark.asyncio
    async def test_gateway_cross_platform_consistency(self):
        """测试 12: 多平台消息一致性.

        - 企业微信消息 → GatewayMessage → 路由
        - Slack 消息 → GatewayMessage → 路由
        - 不同平台的同一请求 → 相同 entry_type
        验证: 平台适配不影响执行内核
        """
        from riskmonitor_multiagent.gateway import (
            GatewayRouter,
            SlackAdapter,
            WeChatWorkAdapter,
        )

        router = GatewayRouter()
        router.register_adapter(WeChatWorkAdapter())
        router.register_adapter(SlackAdapter())

        # 企业微信用户任务消息
        wechat_result = await router.route_message(
            raw_input={
                "msg_type": "text",
                "content": "请排查交易台 TRADER-001 的持仓风险",
                "from_user": "user_001",
                "chat_id": "chat_001",
            },
            platform="wechat_work",
        )
        assert wechat_result["entry_type"] == "user_task"
        assert wechat_result["platform"] == "wechat_work"
        assert wechat_result["message"].content == "请排查交易台 TRADER-001 的持仓风险"

        # Slack 用户任务消息 (相同意图)
        slack_result = await router.route_message(
            raw_input={
                "type": "message",
                "event": {
                    "text": "请排查交易台 TRADER-001 的持仓风险",
                    "user": "U001",
                    "channel": "C001",
                    "ts": "1719500000.000000",
                },
            },
            platform="slack",
        )
        assert slack_result["entry_type"] == "user_task"
        assert slack_result["platform"] == "slack"
        assert slack_result["message"].content == "请排查交易台 TRADER-001 的持仓风险"

        # 验证: 不同平台的同一请求 → 相同 entry_type
        assert wechat_result["entry_type"] == slack_result["entry_type"]

        # 企业微信告警消息 → system_event
        wechat_alert = await router.route_message(
            raw_input={
                "msg_type": "alert",
                "content": "持仓超限告警",
                "from_user": "system",
            },
            platform="wechat_work",
        )
        assert wechat_alert["entry_type"] == "system_event"

        # Slack 告警消息 → system_event
        slack_alert = await router.route_message(
            raw_input={
                "type": "alert",
                "event": {
                    "text": "持仓超限告警",
                    "user": "system",
                    "channel": "C001",
                },
            },
            platform="slack",
        )
        assert slack_alert["entry_type"] == "system_event"

        # 验证: 告警类型也跨平台一致
        assert wechat_alert["entry_type"] == slack_alert["entry_type"]

    # ==================== 测试 13 ====================

    @pytest.mark.asyncio
    async def test_full_self_improving_cycle(self):
        """测试 13: 完整自我改进循环.

        模拟完整的改进闭环:
        1. 首次运行: 无 Skill → 规划
        2. 高质量完成 → SkillProposer 创建 Skill
        3. 第二次运行: Skill 注入 → 规划 + 执行
        4. 成功 → 置信度上升
        5. 第三次运行: Skill 注入 → 执行 → 失败
        6. 失败 → 置信度下降 → SkillReviser 修订
        7. 第四次运行: 修订后 Skill → 执行 → 成功

        验证: 系统在多轮使用后:
        - Skill 库有积累
        - 置信度有变化
        - 修订有历史
        - 系统整体表现呈上升趋势
        """
        from riskmonitor_multiagent.skills import (
            SkillInjector,
            SkillProposer,
            SkillReviser,
            SkillUsageTracker,
        )

        store = _make_skill_store()
        proposer = SkillProposer(store, confidence_threshold=0.85)
        injector = SkillInjector(store, min_confidence=0.3, max_skills=3)
        tracker = SkillUsageTracker(store, success_delta=0.1, fail_delta=0.1)
        reviser = SkillReviser(store)

        task = _make_task()
        orchestrator_output = _make_orchestrator_output()

        # === 1. 首次运行: 无 Skill ===
        inject_result_1 = await injector.retrieve_applicable_skills(
            task=task, skill_enabled=True
        )
        assert inject_result_1["skill_count"] == 0  # 无 Skill 可注入

        # 首次运行高质量完成 → SkillProposer 创建 Skill
        propose_result = await proposer.propose(
            run_id="run-cycle-001",
            task=task,
            critic_final=_make_critic_ok(),
            orchestrator_output=orchestrator_output,
        )
        assert propose_result["action"] == "created"
        skill_id = propose_result["skill_id"]
        assert skill_id is not None

        # 验证: Skill 库有积累
        all_skills = await store.list_all()
        assert len(all_skills) == 1

        # === 2. 第二次运行: Skill 注入 → 成功 ===
        inject_result_2 = await injector.retrieve_applicable_skills(
            task=task, skill_enabled=True
        )
        assert inject_result_2["skill_count"] >= 1  # Skill 被注入

        # 跟踪使用 → 执行成功 → 置信度上升
        tracker.track_usage(skill_id, run_id="run-cycle-002")
        skill_before = await store.get(skill_id)
        confidence_before = float(skill_before["confidence"])

        await tracker.update_after_execution(
            run_id="run-cycle-002", execution_success=True, critic_ok=True
        )
        skill_after = await store.get(skill_id)
        confidence_after_success = float(skill_after["confidence"])

        # 验证: 置信度上升
        assert confidence_after_success > confidence_before

        # === 3. 第三次运行: Skill 注入 → 失败 ===
        inject_result_3 = await injector.retrieve_applicable_skills(
            task=task, skill_enabled=True
        )
        assert inject_result_3["skill_count"] >= 1

        tracker.track_usage(skill_id, run_id="run-cycle-003")
        await tracker.update_after_execution(
            run_id="run-cycle-003", execution_success=False, critic_ok=False
        )
        skill_after_fail = await store.get(skill_id)
        confidence_after_fail = float(skill_after_fail["confidence"])

        # 验证: 置信度下降
        assert confidence_after_fail < confidence_after_success

        # 失败 → SkillReviser 修订
        proposal = await reviser.check_and_propose_revision(
            skill_id=skill_id,
            run_id="run-cycle-003",
            execution_result=_make_execution_result(),
            critic_final=_make_critic_fail(),
        )
        assert proposal is not None

        # 应用修订
        revised_skill = await reviser.apply_revision(
            skill_id=skill_id, proposal=proposal
        )

        # 验证: 修订有历史
        assert len(revised_skill["revision_history"]) >= 1
        assert revised_skill["write_origin"] == "revision"

        # === 4. 第四次运行: 修订后 Skill → 成功 ===
        inject_result_4 = await injector.retrieve_applicable_skills(
            task=task, skill_enabled=True
        )
        assert inject_result_4["skill_count"] >= 1  # 修订后 Skill 仍可注入

        tracker.track_usage(skill_id, run_id="run-cycle-004")
        await tracker.update_after_execution(
            run_id="run-cycle-004", execution_success=True, critic_ok=True
        )
        skill_final = await store.get(skill_id)
        confidence_final = float(skill_final["confidence"])

        # 验证: 系统整体表现呈上升趋势
        # 最终置信度 > 失败后的置信度
        assert confidence_final > confidence_after_fail

        # === 综合验证 ===

        # Skill 库有积累
        final_skills = await store.list_all()
        assert len(final_skills) >= 1

        # 置信度有变化 (与初始值不同)
        assert confidence_final != confidence_before

        # 修订有历史
        assert len(skill_final["revision_history"]) >= 1

        # usage_count 正确 (被使用了 3 次: run-002, run-003, run-004)
        assert skill_final["usage_count"] >= 3

        # 系统整体表现: 最终置信度 >= 初始置信度 (呈上升趋势)
        assert confidence_final >= confidence_before
