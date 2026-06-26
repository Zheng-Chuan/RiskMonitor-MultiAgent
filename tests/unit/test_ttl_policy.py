"""TTLPolicyEngine 单元测试.

Phase 6 Checkpoint 14.4.2: 记忆分级 TTL 策略.

测试覆盖:
1. kind 到 tier 映射正确
2. TTL 秒数正确
3. should_persist 逻辑
4. is_expired 逻辑
5. get_cleanup_candidates: 只返回过期的
6. custom_overrides 覆盖
7. 兜底逻辑: 未知 kind → 根据 memory_type 推断
8. 已有 ttl_tier 字段直接使用
9. cleanup 不影响运行中任务
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


# ==================== 测试 1: kind 到 tier 映射正确 ====================


def test_kind_to_tier_mapping_ephemeral():
    """测试工作态 kind 映射到 EPHEMERAL."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    ephemeral_kinds = ["working", "plan", "step", "command", "receipt", "approval", "message"]
    for kind in ephemeral_kinds:
        entry = {"kind": kind, "memory_type": "episodic", "ts_ms": 1000}
        assert engine.classify(entry) == TTLTier.EPHEMERAL, f"kind={kind} should be EPHEMERAL"


def test_kind_to_tier_mapping_short_term():
    """测试任务记忆 kind 映射到 SHORT_TERM."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    short_term_kinds = ["final", "analysis", "task", "experience_rejection"]
    for kind in short_term_kinds:
        entry = {"kind": kind, "memory_type": "episodic", "ts_ms": 1000}
        assert engine.classify(entry) == TTLTier.SHORT_TERM, f"kind={kind} should be SHORT_TERM"


def test_kind_to_tier_mapping_long_term():
    """测试经验 kind 映射到 LONG_TERM."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    long_term_kinds = ["lesson", "semantic_case", "few_shot"]
    for kind in long_term_kinds:
        entry = {"kind": kind, "ts_ms": 1000}
        assert engine.classify(entry) == TTLTier.LONG_TERM, f"kind={kind} should be LONG_TERM"


def test_kind_to_tier_mapping_permanent():
    """测试 Skill 和配置 kind 映射到 PERMANENT."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    permanent_kinds = ["skill", "policy", "config"]
    for kind in permanent_kinds:
        entry = {"kind": kind, "ts_ms": 1000}
        assert engine.classify(entry) == TTLTier.PERMANENT, f"kind={kind} should be PERMANENT"


# ==================== 测试 2: TTL 秒数正确 ====================


def test_ttl_seconds_values():
    """测试各层级的 TTL 秒数."""
    from riskmonitor_multiagent.memory.ttl_policy import TTL_SECONDS, TTLTier

    assert TTL_SECONDS[TTLTier.EPHEMERAL] == 86400       # 24h
    assert TTL_SECONDS[TTLTier.SHORT_TERM] == 604800     # 7d
    assert TTL_SECONDS[TTLTier.LONG_TERM] is None        # 永不过期
    assert TTL_SECONDS[TTLTier.PERMANENT] is None       # 永不过期


def test_get_ttl_seconds_for_ephemeral():
    """测试 ephemeral entry 返回 86400."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "working", "memory_type": "episodic", "ts_ms": 1000}
    assert engine.get_ttl_seconds(entry) == 86400


def test_get_ttl_seconds_for_short_term():
    """测试 short_term entry 返回 604800."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "final", "memory_type": "episodic", "ts_ms": 1000}
    assert engine.get_ttl_seconds(entry) == 604800


def test_get_ttl_seconds_for_long_term():
    """测试 long_term entry 返回 None (永不过期)."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "lesson", "memory_type": "procedural", "ts_ms": 1000}
    assert engine.get_ttl_seconds(entry) is None


def test_get_ttl_seconds_for_permanent():
    """测试 permanent entry 返回 None (永不过期)."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "skill", "ts_ms": 1000}
    assert engine.get_ttl_seconds(entry) is None


# ==================== 测试 3: should_persist 逻辑 ====================


def test_should_persist_ephemeral_false():
    """测试 ephemeral 不落盘."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "working", "memory_type": "episodic", "ts_ms": 1000}
    assert engine.should_persist(entry) is False


def test_should_persist_short_term_false():
    """测试 short_term 不落盘."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "final", "memory_type": "episodic", "ts_ms": 1000}
    assert engine.should_persist(entry) is False


def test_should_persist_long_term_true():
    """测试 long_term 需要落盘."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "lesson", "memory_type": "procedural", "ts_ms": 1000}
    assert engine.should_persist(entry) is True


def test_should_persist_permanent_true():
    """测试 permanent 需要落盘."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "skill", "ts_ms": 1000}
    assert engine.should_persist(entry) is True


# ==================== 测试 4: is_expired 逻辑 ====================


def test_is_expired_permanent_never_expires():
    """测试永久级别永不过期."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    # lesson 是 LONG_TERM
    entry = {"kind": "lesson", "memory_type": "procedural", "ts_ms": 1000}
    # 即使过了很久
    far_future_ms = int(time.time() * 1000) + 365 * 24 * 3600 * 1000
    assert engine.is_expired(entry, now_ms=far_future_ms) is False

    # skill 是 PERMANENT
    entry_skill = {"kind": "skill", "ts_ms": 1000}
    assert engine.is_expired(entry_skill, now_ms=far_future_ms) is False


def test_is_expired_ephemeral_after_25h():
    """测试 ephemeral 25h 后过期."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    ts_ms = 1_000_000_000_000  # 某个时间点
    entry = {"kind": "working", "memory_type": "episodic", "ts_ms": ts_ms}

    # 25h 后 = ts_ms + 25 * 3600 * 1000
    now_25h = ts_ms + 25 * 3600 * 1000
    assert engine.is_expired(entry, now_ms=now_25h) is True

    # 23h 后未过期
    now_23h = ts_ms + 23 * 3600 * 1000
    assert engine.is_expired(entry, now_ms=now_23h) is False


def test_is_expired_short_term_after_8d():
    """测试 short_term 8d 后过期."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    ts_ms = 1_000_000_000_000
    entry = {"kind": "final", "memory_type": "episodic", "ts_ms": ts_ms}

    # 8d 后 = ts_ms + 8 * 24 * 3600 * 1000
    now_8d = ts_ms + 8 * 24 * 3600 * 1000
    assert engine.is_expired(entry, now_ms=now_8d) is True

    # 6d 后未过期
    now_6d = ts_ms + 6 * 24 * 3600 * 1000
    assert engine.is_expired(entry, now_ms=now_6d) is False


def test_is_expired_no_ts_ms():
    """测试无 ts_ms 时返回 False (不报错)."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "working", "memory_type": "episodic"}
    assert engine.is_expired(entry, now_ms=9999999999999) is False


# ==================== 测试 5: get_cleanup_candidates ====================


def test_get_cleanup_candidates_only_returns_expired():
    """测试 get_cleanup_candidates 只返回已过期的 entry."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    base_ts = 1_000_000_000_000

    entries = [
        # ephemeral, 已过期 (25h 前)
        {"kind": "working", "memory_type": "episodic", "ts_ms": base_ts - 25 * 3600 * 1000},
        # ephemeral, 未过期 (1h 前)
        {"kind": "working", "memory_type": "episodic", "ts_ms": base_ts - 1 * 3600 * 1000},
        # short_term, 未过期 (1d 前)
        {"kind": "final", "memory_type": "episodic", "ts_ms": base_ts - 24 * 3600 * 1000},
        # short_term, 已过期 (8d 前)
        {"kind": "final", "memory_type": "episodic", "ts_ms": base_ts - 8 * 24 * 3600 * 1000},
        # long_term, 永不过期
        {"kind": "lesson", "memory_type": "procedural", "ts_ms": base_ts - 365 * 24 * 3600 * 1000},
        # permanent, 永不过期
        {"kind": "skill", "ts_ms": base_ts - 365 * 24 * 3600 * 1000},
    ]

    candidates = engine.get_cleanup_candidates(entries, now_ms=base_ts)
    assert len(candidates) == 2
    # 确认返回的是过期条目
    kinds = [c.get("kind") for c in candidates]
    assert "working" in kinds
    assert "final" in kinds
    # 永久条目不在清理列表中
    assert "lesson" not in kinds
    assert "skill" not in kinds


def test_get_cleanup_candidates_empty_list():
    """测试空列表返回空."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    candidates = engine.get_cleanup_candidates([], now_ms=1000)
    assert candidates == []


def test_get_cleanup_candidates_all_permanent():
    """测试全是永久条目时返回空."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    entries = [
        {"kind": "lesson", "memory_type": "procedural", "ts_ms": 1},
        {"kind": "skill", "ts_ms": 1},
    ]
    candidates = engine.get_cleanup_candidates(entries, now_ms=9999999999999)
    assert candidates == []


# ==================== 测试 6: custom_overrides 覆盖 ====================


def test_custom_overrides_override_default_mapping():
    """测试 custom_overrides 覆盖默认 kind 映射."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    # 默认 "working" → EPHEMERAL, 覆盖为 PERMANENT
    engine = TTLPolicyEngine(custom_overrides={"working": TTLTier.PERMANENT})
    entry = {"kind": "working", "memory_type": "episodic", "ts_ms": 1000}
    assert engine.classify(entry) == TTLTier.PERMANENT
    assert engine.should_persist(entry) is True
    assert engine.get_ttl_seconds(entry) is None


def test_custom_overrides_do_not_affect_other_kinds():
    """测试 custom_overrides 不影响其他 kind 的映射."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine(custom_overrides={"working": TTLTier.PERMANENT})
    # "lesson" 仍然映射到 LONG_TERM
    entry = {"kind": "lesson", "memory_type": "procedural", "ts_ms": 1000}
    assert engine.classify(entry) == TTLTier.LONG_TERM


def test_custom_overrides_empty_dict():
    """测试空 overrides 使用默认映射."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine(custom_overrides={})
    entry = {"kind": "working", "memory_type": "episodic", "ts_ms": 1000}
    assert engine.classify(entry) == TTLTier.EPHEMERAL


# ==================== 测试 7: 兜底逻辑 ====================


def test_fallback_by_memory_type_procedural():
    """测试未知 kind 根据 memory_type=procedural 推断为 LONG_TERM."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "unknown_kind", "memory_type": "procedural", "ts_ms": 1000}
    assert engine.classify(entry) == TTLTier.LONG_TERM


def test_fallback_by_memory_type_semantic():
    """测试未知 kind 根据 memory_type=semantic 推断为 LONG_TERM."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "unknown_kind", "memory_type": "semantic", "ts_ms": 1000}
    assert engine.classify(entry) == TTLTier.LONG_TERM


def test_fallback_by_memory_type_episodic():
    """测试未知 kind 根据 memory_type=episodic 推断为 SHORT_TERM."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "unknown_kind", "memory_type": "episodic", "ts_ms": 1000}
    assert engine.classify(entry) == TTLTier.SHORT_TERM


def test_fallback_final_ephemeral():
    """测试完全未知的 kind 和 memory_type 兜底为 EPHEMERAL."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "totally_unknown", "memory_type": "unknown_type", "ts_ms": 1000}
    assert engine.classify(entry) == TTLTier.EPHEMERAL


def test_fallback_no_kind_no_memory_type():
    """测试无 kind 和 memory_type 兜底为 EPHEMERAL."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry: dict[str, Any] = {}
    assert engine.classify(entry) == TTLTier.EPHEMERAL


# ==================== 测试 8: 已有 ttl_tier 字段直接使用 ====================


def test_existing_ttl_tier_field_used_directly():
    """测试 entry 含 ttl_tier 字段时直接使用."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    # kind=working 默认是 EPHEMERAL, 但 ttl_tier 字段指定为 PERMANENT
    entry = {"kind": "working", "memory_type": "episodic", "ts_ms": 1000, "ttl_tier": "permanent"}
    assert engine.classify(entry) == TTLTier.PERMANENT
    assert engine.should_persist(entry) is True


def test_existing_ttl_tier_long_term():
    """测试 ttl_tier=long_term 直接使用."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "plan", "memory_type": "episodic", "ts_ms": 1000, "ttl_tier": "long_term"}
    assert engine.classify(entry) == TTLTier.LONG_TERM
    assert engine.should_persist(entry) is True


def test_existing_ttl_tier_ephemeral():
    """测试 ttl_tier=ephemeral 直接使用."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "lesson", "memory_type": "procedural", "ts_ms": 1000, "ttl_tier": "ephemeral"}
    assert engine.classify(entry) == TTLTier.EPHEMERAL
    assert engine.should_persist(entry) is False


def test_existing_ttl_tier_enum_object():
    """测试 ttl_tier 为 TTLTier 枚举对象时也能正确解析."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "plan", "memory_type": "episodic", "ts_ms": 1000, "ttl_tier": TTLTier.PERMANENT}
    assert engine.classify(entry) == TTLTier.PERMANENT


def test_existing_ttl_tier_invalid_falls_back():
    """测试无效的 ttl_tier 字段值回退到默认映射."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "working", "memory_type": "episodic", "ts_ms": 1000, "ttl_tier": "invalid_value"}
    # 无效的 ttl_tier 应回退到 kind 映射 → EPHEMERAL
    assert engine.classify(entry) == TTLTier.EPHEMERAL


# ==================== 测试 9: cleanup 不影响运行中任务 ====================


def test_cleanup_does_not_affect_non_expired():
    """测试过期条目不影响未过期条目."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLPolicyEngine

    engine = TTLPolicyEngine()
    base_ts = 1_000_000_000_000

    entries = [
        # 已过期 ephemeral
        {"kind": "working", "memory_type": "episodic", "ts_ms": base_ts - 48 * 3600 * 1000, "entry_id": "expired_1"},
        # 未过期 ephemeral
        {"kind": "working", "memory_type": "episodic", "ts_ms": base_ts - 1 * 3600 * 1000, "entry_id": "active_1"},
        # 已过期 short_term
        {"kind": "final", "memory_type": "episodic", "ts_ms": base_ts - 10 * 24 * 3600 * 1000, "entry_id": "expired_2"},
        # 未过期 short_term
        {"kind": "final", "memory_type": "episodic", "ts_ms": base_ts - 1 * 24 * 3600 * 1000, "entry_id": "active_2"},
        # 永久 lesson
        {"kind": "lesson", "memory_type": "procedural", "ts_ms": base_ts - 365 * 24 * 3600 * 1000, "entry_id": "permanent_1"},
        # 永久 skill
        {"kind": "skill", "ts_ms": base_ts - 365 * 24 * 3600 * 1000, "entry_id": "permanent_2"},
    ]

    candidates = engine.get_cleanup_candidates(entries, now_ms=base_ts)

    # 只有 2 个过期
    assert len(candidates) == 2
    candidate_ids = {c.get("entry_id") for c in candidates}
    assert candidate_ids == {"expired_1", "expired_2"}

    # 确认未过期的不在清理列表中
    remaining_ids = {e.get("entry_id") for e in entries} - candidate_ids
    assert "active_1" in remaining_ids
    assert "active_2" in remaining_ids
    assert "permanent_1" in remaining_ids
    assert "permanent_2" in remaining_ids


# ==================== 测试: working_memory 和 private_task_state 映射 ====================


def test_working_memory_kind_maps_to_ephemeral():
    """测试 working_memory kind 映射到 EPHEMERAL."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "working_memory", "memory_type": "episodic", "ts_ms": 1000}
    assert engine.classify(entry) == TTLTier.EPHEMERAL


def test_private_task_state_kind_maps_to_ephemeral():
    """测试 private_task_state kind 映射到 EPHEMERAL."""
    from riskmonitor_multiagent.memory.ttl_policy import TTLTier, TTLPolicyEngine

    engine = TTLPolicyEngine()
    entry = {"kind": "private_task_state", "memory_type": "episodic", "ts_ms": 1000}
    assert engine.classify(entry) == TTLTier.EPHEMERAL
