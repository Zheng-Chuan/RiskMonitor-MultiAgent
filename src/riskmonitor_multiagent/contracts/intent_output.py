"""
意图输出契约定义.

定义 IntentAgent 的输出格式,包括意图识别结果、风险等级、权限要求等.
"""

from __future__ import annotations

from typing import Any

from riskmonitor_multiagent.utils import is_non_empty_str

# 契约版本
INTENT_OUTPUT_SCHEMA_VERSION = "intent_output.v2"


def validate_intent_output(output: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    验证意图 Agent 输出.

    检查项:
    - schema_version 有效性
    - primary_intent_type 为非空字符串
    - intents 列表格式与内容
    - risk_level 为 LOW/MEDIUM/HIGH
    - permission_requirements 结构
    - disambiguation 一致性
    - evidence 引用
    """
    if not isinstance(output, dict):
        return False, ["output must be dict"]

    errors: list[str] = []

    # 检查 schema_version
    version = output.get("schema_version")
    if version is not None:
        if not is_non_empty_str(version):
            errors.append("bad_schema_version")
        elif version != INTENT_OUTPUT_SCHEMA_VERSION:
            errors.append("unsupported_schema_version")

    # 检查主意图类型
    if not is_non_empty_str(output.get("primary_intent_type")):
        errors.append("bad_primary_intent_type")

    # 检查 intents 列表
    intents = output.get("intents")
    if not isinstance(intents, list) or not intents:
        errors.append("bad_intents")
    else:
        for i, it in enumerate(intents):
            if not isinstance(it, dict):
                errors.append(f"intent_{i}_not_dict")
                continue
            if not is_non_empty_str(it.get("intent_type")):
                errors.append(f"intent_{i}_missing_type")
            # 检查 confidence
            conf = it.get("confidence")
            if conf is None:
                errors.append(f"intent_{i}_missing_confidence")
            else:
                try:
                    f = float(conf)
                    if not (0.0 <= f <= 1.0):
                        errors.append(f"intent_{i}_bad_confidence")
                except (TypeError, ValueError):
                    errors.append(f"intent_{i}_bad_confidence")
            # 检查 slots
            slots = it.get("slots")
            if slots is not None and not isinstance(slots, dict):
                errors.append(f"intent_{i}_bad_slots")

    # 检查风险等级
    risk_level = output.get("risk_level")
    if risk_level not in {"LOW", "MEDIUM", "HIGH"}:
        errors.append("bad_risk_level")

    # 检查权限要求
    pr = output.get("permission_requirements")
    if isinstance(pr, dict):
        if not isinstance(pr.get("side_effects"), bool):
            errors.append("bad_side_effects")
        if not isinstance(pr.get("requires_human_approval"), bool):
            errors.append("bad_requires_human_approval")
        allowed = pr.get("allowed_tools")
        if allowed is not None and not isinstance(allowed, list):
            errors.append("bad_allowed_tools")
    elif pr is not None:
        errors.append("bad_permission_requirements")

    # 检查消歧说明
    dis = output.get("disambiguation")
    if isinstance(dis, dict):
        if not isinstance(dis.get("has_multiple"), bool):
            errors.append("bad_disambiguation_has_multiple")
        if dis.get("has_multiple") and not is_non_empty_str(dis.get("explanation")):
            errors.append("bad_disambiguation_explanation")
    elif dis is not None:
        errors.append("bad_disambiguation")

    # 检查证据
    evidence = output.get("evidence")
    if evidence is not None and not isinstance(evidence, dict):
        errors.append("bad_evidence")

    return len(errors) == 0, errors


def normalize_intent_output(output: dict[str, Any]) -> dict[str, Any]:
    """
    归一化意图输出,补充缺失字段并处理多意图排序.

    主要处理:
    - 补充缺失的基础字段
    - 按 confidence 降序排序 intents
    - 更新 primary_intent_type 为最高置信度意图
    - 多意图时设置 disambiguation 标志
    """
    out = dict(output) if isinstance(output, dict) else {}

    # 基础默认值
    out.setdefault("schema_version", INTENT_OUTPUT_SCHEMA_VERSION)
    out.setdefault("risk_level", "MEDIUM")
    out.setdefault("permission_requirements", {
        "side_effects": False,
        "requires_human_approval": True,  # 保守策略
        "allowed_tools": None,
    })
    out.setdefault("evidence", {"fields": ["task.payload.content"]})
    out.setdefault("degraded", True)
    out.setdefault("degraded_reason", "llm_output_incomplete")
    out.setdefault("degraded_scope", ["intent"])

    # 处理 intents 列表
    intents = out.get("intents")
    if not isinstance(intents, list) or not intents:
        intents = [{"intent_type": "unknown", "slots": {}, "confidence": 0.0}]

    # 确保每个 intent 都有必需的字段
    valid_intents = []
    for it in intents:
        if isinstance(it, dict):
            it.setdefault("intent_type", "unknown")
            it.setdefault("slots", {})
            it.setdefault("confidence", 0.0)
            valid_intents.append(it)

    if not valid_intents:
        valid_intents = [{"intent_type": "unknown", "slots": {}, "confidence": 0.0}]

    # 按 confidence 降序排序
    valid_intents.sort(key=lambda x: float(x.get("confidence") or 0.0), reverse=True)
    out["intents"] = valid_intents

    # 更新 primary_intent_type 为最高置信度意图
    primary = out.get("primary_intent_type")
    if not is_non_empty_str(primary):
        out["primary_intent_type"] = valid_intents[0].get("intent_type", "unknown")

    # 处理 disambiguation
    dis = out.get("disambiguation")
    if not isinstance(dis, dict):
        dis = {}
    # 多意图检测
    if len(valid_intents) > 1:
        dis["has_multiple"] = True
        if not is_non_empty_str(dis.get("explanation")):
            # 自动生成解释
            intent_types = [it.get("intent_type", "unknown") for it in valid_intents[:3]]
            dis["explanation"] = f"检测到多意图: {', '.join(intent_types)}"
    else:
        dis.setdefault("has_multiple", False)
        dis.setdefault("explanation", "")
    dis.setdefault("notes", [])
    out["disambiguation"] = dis

    return out
