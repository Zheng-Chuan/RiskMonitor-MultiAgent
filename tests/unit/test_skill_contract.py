"""Skill 契约单测."""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


# ==================== validate_skill ====================


def test_validate_skill_normal_input():
    """测试 validate_skill 正常输入."""
    from riskmonitor_multiagent.skills.skill_contract import (
        SKILL_SCHEMA_VERSION,
        validate_skill,
    )

    skill = validate_skill(
        {
            "name": "交易台风险排查",
            "tags": ["risk", "trading"],
            "applicable_conditions": ["延迟异常"],
            "steps": [
                {"description": "查持仓", "expected_outcome": "获取持仓数据"}
            ],
            "failure_boundary": "不要伪造数据",
        }
    )
    assert skill["schema_version"] == SKILL_SCHEMA_VERSION
    assert skill["name"] == "交易台风险排查"
    assert skill["tags"] == ["risk", "trading"]
    assert skill["applicable_conditions"] == ["延迟异常"]
    assert skill["status"] == "active"
    assert skill["write_origin"] == "auto"
    assert skill["confidence"] == 0.5
    assert skill["usage_count"] == 0
    assert skill["success_rate"] == 0.0
    assert skill["skill_id"].startswith("skill_")
    assert isinstance(skill["created_at"], int)
    assert isinstance(skill["updated_at"], int)
    assert skill["revision_history"] == []
    assert skill["source_run_id"] is None
    assert skill["source_agent_id"] is None


def test_validate_skill_missing_name():
    """测试 validate_skill 缺少 name 字段."""
    from riskmonitor_multiagent.skills.skill_contract import validate_skill

    with pytest.raises(ValueError, match="bad_name"):
        validate_skill({"tags": ["x"]})


def test_validate_skill_empty_name():
    """测试 validate_skill 空 name."""
    from riskmonitor_multiagent.skills.skill_contract import validate_skill

    with pytest.raises(ValueError, match="bad_name"):
        validate_skill({"name": ""})


def test_validate_skill_invalid_status():
    """测试 validate_skill 非法 status."""
    from riskmonitor_multiagent.skills.skill_contract import validate_skill

    with pytest.raises(ValueError, match="unsupported_status"):
        validate_skill({"name": "test", "status": "unknown"})


def test_validate_skill_invalid_write_origin():
    """测试 validate_skill 非法 write_origin."""
    from riskmonitor_multiagent.skills.skill_contract import validate_skill

    with pytest.raises(ValueError, match="unsupported_write_origin"):
        validate_skill({"name": "test", "write_origin": "unknown"})


def test_validate_skill_non_dict_raises():
    """测试 validate_skill 非 dict 输入."""
    from riskmonitor_multiagent.skills.skill_contract import validate_skill

    with pytest.raises(ValueError, match="must be a dict"):
        validate_skill("not a dict")  # type: ignore[arg-type]


def test_validate_skill_step_without_description():
    """测试 validate_skill 步骤缺少 description."""
    from riskmonitor_multiagent.skills.skill_contract import validate_skill

    with pytest.raises(ValueError, match="bad_step_0"):
        validate_skill(
            {"name": "test", "steps": [{"expected_outcome": "no desc"}]}
        )


# ==================== normalize_skill ====================


def test_normalize_skill_defaults():
    """测试 normalize_skill 默认值填充."""
    from riskmonitor_multiagent.skills.skill_contract import (
        SKILL_SCHEMA_VERSION,
        normalize_skill,
    )

    nd = normalize_skill({"name": "test"})
    assert nd["schema_version"] == SKILL_SCHEMA_VERSION
    assert nd["skill_id"].startswith("skill_")
    assert nd["name"] == "test"
    assert nd["tags"] == []
    assert nd["applicable_conditions"] == []
    assert nd["steps"] == []
    assert nd["failure_boundary"] == ""
    assert nd["confidence"] == 0.5
    assert nd["write_origin"] == "auto"
    assert nd["status"] == "active"
    assert isinstance(nd["created_at"], int)
    assert isinstance(nd["updated_at"], int)
    assert nd["usage_count"] == 0
    assert nd["success_rate"] == 0.0
    assert nd["revision_history"] == []
    assert nd["source_run_id"] is None
    assert nd["source_agent_id"] is None


def test_normalize_skill_type_conversion():
    """测试 normalize_skill 类型转换."""
    from riskmonitor_multiagent.skills.skill_contract import normalize_skill

    nd = normalize_skill(
        {
            "name": 123,
            "tags": "not_a_list",
            "confidence": "0.8",
            "usage_count": "5",
            "status": "",
        }
    )
    assert nd["name"] == "123"
    assert nd["tags"] == []
    assert nd["confidence"] == 0.8
    assert nd["usage_count"] == 5
    assert nd["status"] == "active"


def test_normalize_skill_confidence_clamp():
    """测试 normalize_skill confidence 钳制到 [0, 1]."""
    from riskmonitor_multiagent.skills.skill_contract import normalize_skill

    nd_high = normalize_skill({"name": "t", "confidence": 1.5})
    assert nd_high["confidence"] == 1.0

    nd_low = normalize_skill({"name": "t", "confidence": -0.5})
    assert nd_low["confidence"] == 0.0


# ==================== Skill.from_dict / to_dict 往返 ====================


def test_skill_from_dict_to_dict_roundtrip():
    """测试 Skill.from_dict / to_dict 往返."""
    from riskmonitor_multiagent.skills.skill_contract import Skill

    original = {
        "name": "风险排查技能",
        "tags": ["risk"],
        "applicable_conditions": ["告警触发"],
        "steps": [
            {"description": "step1", "expected_outcome": "outcome1"}
        ],
        "failure_boundary": "禁止伪造",
        "confidence": 0.8,
        "write_origin": "manual",
        "source_run_id": "run_123",
        "source_agent_id": "critic",
    }
    skill = Skill.from_dict(original)
    d = skill.to_dict()

    assert d["name"] == "风险排查技能"
    assert d["tags"] == ["risk"]
    assert d["applicable_conditions"] == ["告警触发"]
    assert d["steps"] == [{"description": "step1", "expected_outcome": "outcome1"}]
    assert d["failure_boundary"] == "禁止伪造"
    assert d["confidence"] == 0.8
    assert d["write_origin"] == "manual"
    assert d["source_run_id"] == "run_123"
    assert d["source_agent_id"] == "critic"
    assert d["status"] == "active"

    # 二次往返保持一致
    skill2 = Skill.from_dict(d)
    assert skill2.to_dict() == d


def test_skill_frozen():
    """测试 Skill 是 frozen dataclass."""
    from riskmonitor_multiagent.skills.skill_contract import Skill

    skill = Skill.from_dict({"name": "test"})
    with pytest.raises((AttributeError, Exception)):
        skill.name = "changed"  # type: ignore[misc]


# ==================== new_skill_id ====================


def test_new_skill_id_format():
    """测试 new_skill_id 格式."""
    from riskmonitor_multiagent.skills.skill_contract import new_skill_id

    sid = new_skill_id()
    assert sid.startswith("skill_")
    assert len(sid) == len("skill_") + 12

    # 唯一性
    sid2 = new_skill_id()
    assert sid != sid2
