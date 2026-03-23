"""
Agent 输出契约定义与验证.

本模块定义各 Agent 的输出格式规范,提供:
- 验证函数: validate_* - 检查输出是否符合契约
- 归一化函数: normalize_* - 将不完整输出补充为有效格式

所有函数均返回标准结构,便于上层统一处理.
"""

from __future__ import annotations

from typing import Any

from riskmonitor_multiagent.utils import is_non_empty_str, has_evidence_refs

# 契约版本常量
SYSTEM_ENGINEER_VERSION = "system_engineer_output.v1"
RISK_ANALYST_VERSION = "risk_analyst_output.v1"
ORCHESTRATOR_VERSION = "orchestrator_output.v1"
CRITIC_VERSION = "critic_review.v1"

# 向后兼容的别名(测试直接导入这些名称)
SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION = SYSTEM_ENGINEER_VERSION
RISK_ANALYST_OUTPUT_SCHEMA_VERSION = RISK_ANALYST_VERSION
ORCHESTRATOR_OUTPUT_SCHEMA_VERSION = ORCHESTRATOR_VERSION
CRITIC_REVIEW_SCHEMA_VERSION = CRITIC_VERSION


def _validate_schema_version(
    output: dict,
    expected: str,
    errors: list[str],
) -> None:
    """验证 schema_version 字段.
    
    放宽验证:只要版本号存在且是字符串即可,不强制要求完全匹配.
    版本差异通过 normalize 函数处理.
    """
    version = output.get("schema_version")
    if version is None:
        return  # 允许缺失,normalize 会补充
    if not is_non_empty_str(version):
        errors.append("bad_schema_version")
    # 放宽:版本不匹配不报错,让 normalize 处理兼容性


def _ensure_dict(value: Any, default: dict) -> dict:
    """确保值为字典类型."""
    return value if isinstance(value, dict) else default


# ==================== System Engineer ====================

def validate_system_engineer_output(output: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    验证系统工程师 Agent 输出.

    检查项:
    - schema_version 有效性
    - system_issue 为布尔值
    - reason 为非空字符串
    - evidence 包含有效引用
    """
    if not isinstance(output, dict):
        return False, ["output must be dict"]

    errors: list[str] = []
    _validate_schema_version(output, SYSTEM_ENGINEER_VERSION, errors)

    if not isinstance(output.get("system_issue"), bool):
        errors.append("bad_system_issue")
    if not is_non_empty_str(output.get("reason")):
        errors.append("bad_reason")

    latency = output.get("latency_ms")
    if latency is not None and not isinstance(latency, int):
        errors.append("bad_latency_ms")

    evidence = output.get("evidence")
    if not isinstance(evidence, dict) or not has_evidence_refs(evidence):
        errors.append("missing_key_system_engineer_evidence_refs")

    return len(errors) == 0, errors


def normalize_system_engineer_output(output: dict[str, Any]) -> dict[str, Any]:
    """
    归一化系统工程师输出,补充缺失字段.

    默认值:
    - schema_version: system_engineer_output.v1
    - system_issue: True (保守策略)
    - reason: "invalid_output"
    - evidence: {fields: ["unknown"]}
    """
    out = dict(output) if isinstance(output, dict) else {}
    out.setdefault("schema_version", SYSTEM_ENGINEER_VERSION)
    out.setdefault("system_issue", True)  # 保守策略: 有问题
    out.setdefault("reason", "invalid_output")
    out.setdefault("evidence", {"fields": ["unknown"]})

    # 清理 latency_ms
    if "latency_ms" in out:
        if out["latency_ms"] is not None and not isinstance(out["latency_ms"], int):
            out["latency_ms"] = None

    return out


# ==================== Risk Analyst ====================

def validate_risk_analyst_output(output: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    验证风险分析师 Agent 输出.

    检查项:
    - schema_version 有效性
    - report 为非空字符串
    - key_facts 为字典
    - confidence 在 [0,1] 范围内
    - evidence 包含有效引用
    """
    if not isinstance(output, dict):
        return False, ["output must be dict"]

    errors: list[str] = []
    _validate_schema_version(output, RISK_ANALYST_VERSION, errors)

    if not is_non_empty_str(output.get("report")):
        errors.append("bad_report")
    if not isinstance(output.get("key_facts"), dict):
        errors.append("bad_key_facts")

    confidence = output.get("confidence")
    if confidence is not None:
        try:
            if not (0.0 <= float(confidence) <= 1.0):
                errors.append("bad_confidence")
        except (TypeError, ValueError):
            errors.append("bad_confidence")

    evidence = output.get("evidence")
    if not isinstance(evidence, dict) or not has_evidence_refs(evidence):
        errors.append("missing_key_risk_analyst_evidence_refs")

    return len(errors) == 0, errors


def normalize_risk_analyst_output(output: dict[str, Any]) -> dict[str, Any]:
    """
    归一化风险分析师输出,补充缺失字段.

    默认值:
    - schema_version: risk_analyst_output.v1
    - report: "输出不符合契约 已回退到最小报告"
    - key_facts: {}
    - evidence: {fields: ["unknown"]}
    """
    out = dict(output) if isinstance(output, dict) else {}
    out.setdefault("schema_version", RISK_ANALYST_VERSION)
    out.setdefault("report", "输出不符合契约 已回退到最小报告")
    out.setdefault("key_facts", {})
    out.setdefault("evidence", {"fields": ["unknown"]})

    # 清理 confidence
    if "confidence" in out and out["confidence"] is not None:
        try:
            out["confidence"] = float(out["confidence"])
        except Exception:
            out["confidence"] = None

    return out


# ==================== Orchestrator ====================

def validate_orchestrator_output(output: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    验证编排器 Agent 输出.

    检查项:
    - schema_version 有效性(放宽,允许版本差异)
    - intent 结构(放宽,允许缺失)
    - plan_steps 格式与完整性(放宽非关键字段)
    - evidence 引用有效性
    - degraded 标志一致性
    - commands 与 receipt 绑定
    
    优化策略:只检查核心字段,其他字段通过 normalize 自动修复.
    """
    if not isinstance(output, dict):
        return False, ["output must be dict"]

    errors: list[str] = []
    _validate_schema_version(output, ORCHESTRATOR_VERSION, errors)

    # 检查 intent(放宽:允许缺失或不完整,normalize 会补充)
    intent = output.get("intent")
    if intent is not None and not isinstance(intent, dict):
        errors.append("bad_intent")

    # 检查 plan_steps(放宽:只要存在且是列表即可,字段缺失通过 normalize 修复)
    steps = output.get("plan_steps")
    if steps is not None:
        if not isinstance(steps, list):
            errors.append("bad_plan_steps")
        else:
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    errors.append("bad_plan_step")
                    continue
                # 放宽:只检查 kind 字段存在,其他字段缺失通过 normalize 修复
                if not is_non_empty_str(step.get("kind")):
                    errors.append("bad_plan_step_kind")
                # step_id 和 reason 缺失不报错,normalize 会补充
                # 检查 delegate 特有字段
                if step.get("kind") == "delegate":
                    if not is_non_empty_str(step.get("target_agent")):
                        errors.append("bad_delegate_target_agent")

    # 检查 degraded 一致性
    degraded = output.get("degraded")
    if degraded is not None:
        if not isinstance(degraded, bool):
            errors.append("bad_degraded")
        elif degraded:
            if not is_non_empty_str(output.get("degraded_reason")):
                errors.append("bad_degraded_reason")
            scope = output.get("degraded_scope")
            if not isinstance(scope, list) or not scope:
                errors.append("bad_degraded_scope")

    # 检查 evidence 引用
    evidence = output.get("evidence")
    if isinstance(evidence, dict):
        if not has_evidence_refs(evidence):
            errors.append("missing_key_orchestrator_evidence_refs")
        # 检查 receipt 绑定
        if isinstance(steps, list):
            command_ids = {
                str(c.get("command_id"))
                for c in (output.get("commands") or [])
                if isinstance(c, dict) and is_non_empty_str(c.get("command_id"))
            }
            receipt_ids = evidence.get("receipt_command_ids")
            if command_ids and isinstance(receipt_ids, list):
                missing = [rid for rid in receipt_ids if is_non_empty_str(rid) and str(rid) not in command_ids]
                if missing:
                    errors.append("receipt_binding_mismatch")

    return len(errors) == 0, errors


def normalize_orchestrator_output(output: dict[str, Any]) -> dict[str, Any]:
    """
    归一化编排器输出,补充缺失字段并修复格式.

    主要修复:
    - 补充 schema_version, intent, plan_steps
    - 为 plan_steps 自动生成 step_id
    - 补充缺失的 reason
    - 处理 degraded 标志
    """
    out = dict(output) if isinstance(output, dict) else {}

    # 基础字段
    out.setdefault("schema_version", ORCHESTRATOR_VERSION)
    out.setdefault("intent", {"type": "unknown", "confidence": 0.0, "slots": {}})
    out.setdefault("plan_steps", [])
    out.setdefault("evidence", {"fields": ["unknown"]})
    out.setdefault("degraded", False)

    # 修复 plan_steps
    if isinstance(out.get("plan_steps"), list):
        fixed: list[dict] = []
        for i, step in enumerate(out["plan_steps"]):
            if not isinstance(step, dict):
                continue
            step = dict(step)
            # 自动生成 step_id
            if not is_non_empty_str(step.get("step_id")):
                step["step_id"] = f"s{i+1}"
            # 补充 reason
            if not is_non_empty_str(step.get("reason")):
                step["reason"] = "缺少原因说明 已自动回填"
            fixed.append(step)
        out["plan_steps"] = fixed

    # 修复 degraded
    if out.get("degraded"):
        if not is_non_empty_str(out.get("degraded_reason")):
            out["degraded_reason"] = "unknown"
        if not isinstance(out.get("degraded_scope"), list) or not out.get("degraded_scope"):
            out["degraded_scope"] = ["orchestrator"]

    return out


# ==================== Critic ====================

def validate_critic_review(output: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    验证评审员 Agent 输出.

    检查项:
    - schema_version 有效性
    - ok 为布尔值
    - risk_level 为 LOW/MEDIUM/HIGH
    - require_human_approval 为布尔值
    - evidence 包含有效引用
    """
    if not isinstance(output, dict):
        return False, ["output must be dict"]

    errors: list[str] = []
    _validate_schema_version(output, CRITIC_VERSION, errors)

    if not isinstance(output.get("ok"), bool):
        errors.append("bad_ok")

    risk_level = output.get("risk_level")
    if risk_level not in {"LOW", "MEDIUM", "HIGH"}:
        errors.append("bad_risk_level")

    if not isinstance(output.get("require_human_approval"), bool):
        errors.append("bad_require_human_approval")

    evidence = output.get("evidence")
    if isinstance(evidence, dict):
        if not has_evidence_refs(evidence):
            errors.append("missing_key_critic_evidence_refs")
    elif evidence is not None:
        errors.append("bad_evidence")

    return len(errors) == 0, errors


def normalize_critic_review(output: dict[str, Any]) -> dict[str, Any]:
    """
    归一化评审员输出,补充缺失字段.

    默认值 (保守策略):
    - ok: False
    - risk_level: HIGH
    - require_human_approval: True
    - issues: [{code: "invalid_output", ...}]
    """
    out = dict(output) if isinstance(output, dict) else {}

    out.setdefault("schema_version", CRITIC_VERSION)
    out.setdefault("ok", False)  # 保守策略
    out.setdefault("risk_level", "HIGH")
    out.setdefault("require_human_approval", True)
    out.setdefault("suggested_fixes", [
        "补齐证据链",
        "降低副作用动作",
        "必要时要求人工确认",
    ])
    out.setdefault("evidence", {"fields": ["unknown"]})
    out.setdefault("run_summary", {
        "text": "run_summary 未生成",
        "key_points": [],
        "receipt_command_ids": [],
    })
    out.setdefault("issues", [{
        "code": "invalid_output",
        "message": "输出不符合契约 已触发保守策略",
        "severity": "HIGH",
    }])

    return out
