from __future__ import annotations

from typing import Any

SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION = "system_engineer_output.v1"
RISK_ANALYST_OUTPUT_SCHEMA_VERSION = "risk_analyst_output.v1"
MANAGER_OUTPUT_SCHEMA_VERSION = "manager_output.v1"
ORCHESTRATOR_OUTPUT_SCHEMA_VERSION = "orchestrator_output.v1"
CRITIC_REVIEW_SCHEMA_VERSION = "critic_review.v1"


def _is_non_empty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def validate_system_engineer_output(output: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(output, dict):
        return False, ["output must be dict"]

    schema_version = output.get("schema_version")
    if schema_version is None:
        pass
    elif not _is_non_empty_str(schema_version):
        errors.append("bad_schema_version")
    elif schema_version != SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")

    if not isinstance(output.get("system_issue"), bool):
        errors.append("bad_system_issue")
    if not _is_non_empty_str(output.get("reason")):
        errors.append("bad_reason")

    latency_ms = output.get("latency_ms")
    if latency_ms is not None and not isinstance(latency_ms, int):
        errors.append("bad_latency_ms")

    evidence = output.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("bad_evidence")

    return len(errors) == 0, errors


def normalize_system_engineer_output(output: dict[str, Any]) -> dict[str, Any]:
    out = dict(output) if isinstance(output, dict) else {}
    out.setdefault("schema_version", SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION)
    out.setdefault("system_issue", True)
    out.setdefault("reason", "invalid_output")
    if "latency_ms" in out and out["latency_ms"] is not None and not isinstance(out["latency_ms"], int):
        out["latency_ms"] = None
    return out


def validate_risk_analyst_output(output: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(output, dict):
        return False, ["output must be dict"]

    schema_version = output.get("schema_version")
    if schema_version is None:
        pass
    elif not _is_non_empty_str(schema_version):
        errors.append("bad_schema_version")
    elif schema_version != RISK_ANALYST_OUTPUT_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")

    if not _is_non_empty_str(output.get("report")):
        errors.append("bad_report")
    if not isinstance(output.get("key_facts"), dict):
        errors.append("bad_key_facts")

    confidence = output.get("confidence")
    if confidence is not None and (
        not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0)
    ):
        errors.append("bad_confidence")

    evidence = output.get("evidence")
    if evidence is not None and not isinstance(evidence, dict):
        errors.append("bad_evidence")

    return len(errors) == 0, errors


def normalize_risk_analyst_output(output: dict[str, Any]) -> dict[str, Any]:
    out = dict(output) if isinstance(output, dict) else {}
    out.setdefault("schema_version", RISK_ANALYST_OUTPUT_SCHEMA_VERSION)
    out.setdefault("report", "输出不符合契约 已回退到最小报告")
    out.setdefault("key_facts", {})
    if "confidence" in out and out["confidence"] is not None:
        try:
            out["confidence"] = float(out["confidence"])
        except Exception:
            out["confidence"] = None
    return out


def validate_manager_output(output: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(output, dict):
        return False, ["output must be dict"]

    schema_version = output.get("schema_version")
    if schema_version is None:
        pass
    elif not _is_non_empty_str(schema_version):
        errors.append("bad_schema_version")
    elif schema_version != MANAGER_OUTPUT_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")

    decision = output.get("decision")
    if not _is_non_empty_str(decision) or decision not in {"WATCH", "CRITICAL"}:
        errors.append("bad_decision")
    if not _is_non_empty_str(output.get("action")):
        errors.append("bad_action")
    if not _is_non_empty_str(output.get("rationale")):
        errors.append("bad_rationale")

    commands = output.get("commands")
    if commands is not None and not isinstance(commands, list):
        errors.append("bad_commands")

    plan_steps = output.get("plan_steps")
    if plan_steps is not None and not isinstance(plan_steps, list):
        errors.append("bad_plan_steps")

    evidence = output.get("evidence")
    if evidence is not None and not isinstance(evidence, dict):
        errors.append("bad_evidence")

    degraded = output.get("degraded")
    if degraded is not None and not isinstance(degraded, bool):
        errors.append("bad_degraded")
    if isinstance(degraded, bool) and degraded:
        if not _is_non_empty_str(output.get("degraded_reason")):
            errors.append("bad_degraded_reason")
        degraded_scope = output.get("degraded_scope")
        if not isinstance(degraded_scope, list) or not degraded_scope or not all(_is_non_empty_str(x) for x in degraded_scope):
            errors.append("bad_degraded_scope")

    if isinstance(evidence, dict):
        has_receipts = isinstance(evidence.get("receipt_command_ids"), list) and any(_is_non_empty_str(x) for x in evidence.get("receipt_command_ids"))
        has_fields = isinstance(evidence.get("fields"), list) and any(_is_non_empty_str(x) for x in evidence.get("fields"))
        has_rag = isinstance(evidence.get("rag_hit_ids"), list) and any(_is_non_empty_str(x) for x in evidence.get("rag_hit_ids"))
        if not (has_receipts or has_fields or has_rag):
            errors.append("missing_key_decision_evidence_refs")

    return len(errors) == 0, errors


def normalize_manager_output(output: dict[str, Any]) -> dict[str, Any]:
    out = dict(output) if isinstance(output, dict) else {}
    out.setdefault("schema_version", MANAGER_OUTPUT_SCHEMA_VERSION)
    out.setdefault("decision", "WATCH")
    out.setdefault("action", "建议通知值班人员 并要求 desk 提供解释")
    out.setdefault("rationale", "输出不符合契约 已回退到最小决策")
    out.setdefault("evidence", {"fields": ["unknown"]})
    if not isinstance(out.get("evidence"), dict):
        out["evidence"] = {"fields": ["unknown"]}
    if isinstance(out["evidence"], dict) and "fields" not in out["evidence"]:
        out["evidence"]["fields"] = ["unknown"]
    out.setdefault("degraded", False)
    if not isinstance(out.get("degraded"), bool):
        out["degraded"] = False
    if out.get("degraded") is True:
        if not _is_non_empty_str(out.get("degraded_reason")):
            out["degraded_reason"] = "unknown"
        degraded_scope = out.get("degraded_scope")
        if not isinstance(degraded_scope, list) or not degraded_scope:
            out["degraded_scope"] = ["manager_decision"]
    if "plan_steps" in out and out["plan_steps"] is not None and not isinstance(out["plan_steps"], list):
        out["plan_steps"] = None
    if "commands" in out and out["commands"] is not None and not isinstance(out["commands"], list):
        out["commands"] = None
    return out


def validate_orchestrator_output(output: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(output, dict):
        return False, ["output must be dict"]

    schema_version = output.get("schema_version")
    if schema_version is None:
        pass
    elif not _is_non_empty_str(schema_version):
        errors.append("bad_schema_version")
    elif schema_version != ORCHESTRATOR_OUTPUT_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")

    intent = output.get("intent")
    if intent is not None and not isinstance(intent, dict):
        errors.append("bad_intent")

    plan_steps = output.get("plan_steps")
    if plan_steps is not None and not isinstance(plan_steps, list):
        errors.append("bad_plan_steps")

    commands = output.get("commands")
    if commands is not None and not isinstance(commands, list):
        errors.append("bad_commands")

    evidence = output.get("evidence")
    if evidence is not None and not isinstance(evidence, dict):
        errors.append("bad_evidence")

    degraded = output.get("degraded")
    if degraded is not None and not isinstance(degraded, bool):
        errors.append("bad_degraded")
    if isinstance(degraded, bool) and degraded:
        if not _is_non_empty_str(output.get("degraded_reason")):
            errors.append("bad_degraded_reason")
        degraded_scope = output.get("degraded_scope")
        if not isinstance(degraded_scope, list) or not degraded_scope or not all(_is_non_empty_str(x) for x in degraded_scope):
            errors.append("bad_degraded_scope")

    if isinstance(evidence, dict):
        has_receipts = isinstance(evidence.get("receipt_command_ids"), list) and any(_is_non_empty_str(x) for x in evidence.get("receipt_command_ids"))
        has_fields = isinstance(evidence.get("fields"), list) and any(_is_non_empty_str(x) for x in evidence.get("fields"))
        has_rag = isinstance(evidence.get("rag_hit_ids"), list) and any(_is_non_empty_str(x) for x in evidence.get("rag_hit_ids"))
        if not (has_receipts or has_fields or has_rag):
            errors.append("missing_key_orchestrator_evidence_refs")

    return len(errors) == 0, errors


def normalize_orchestrator_output(output: dict[str, Any]) -> dict[str, Any]:
    out = dict(output) if isinstance(output, dict) else {}
    out.setdefault("schema_version", ORCHESTRATOR_OUTPUT_SCHEMA_VERSION)
    out.setdefault("intent", {"type": "unknown", "confidence": 0.0, "slots": {}})
    if not isinstance(out.get("intent"), dict):
        out["intent"] = {"type": "unknown", "confidence": 0.0, "slots": {}}
    out.setdefault("plan_steps", [])
    if "plan_steps" in out and out["plan_steps"] is not None and not isinstance(out["plan_steps"], list):
        out["plan_steps"] = []
    if "commands" in out and out["commands"] is not None and not isinstance(out["commands"], list):
        out["commands"] = None
    out.setdefault("evidence", {"fields": ["unknown"]})
    if not isinstance(out.get("evidence"), dict):
        out["evidence"] = {"fields": ["unknown"]}
    if isinstance(out["evidence"], dict) and "fields" not in out["evidence"]:
        out["evidence"]["fields"] = ["unknown"]
    out.setdefault("degraded", False)
    if not isinstance(out.get("degraded"), bool):
        out["degraded"] = False
    if out.get("degraded") is True:
        if not _is_non_empty_str(out.get("degraded_reason")):
            out["degraded_reason"] = "unknown"
        degraded_scope = out.get("degraded_scope")
        if not isinstance(degraded_scope, list) or not degraded_scope:
            out["degraded_scope"] = ["orchestrator"]
    return out


def validate_critic_review(output: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(output, dict):
        return False, ["output must be dict"]

    schema_version = output.get("schema_version")
    if schema_version is None:
        pass
    elif not _is_non_empty_str(schema_version):
        errors.append("bad_schema_version")
    elif schema_version != CRITIC_REVIEW_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")

    if not isinstance(output.get("ok"), bool):
        errors.append("bad_ok")
    risk_level = output.get("risk_level")
    if not _is_non_empty_str(risk_level) or risk_level not in {"LOW", "MEDIUM", "HIGH"}:
        errors.append("bad_risk_level")
    issues = output.get("issues")
    if issues is not None and not isinstance(issues, list):
        errors.append("bad_issues")
    if not isinstance(output.get("require_human_approval"), bool):
        errors.append("bad_require_human_approval")
    evidence = output.get("evidence")
    if evidence is not None and not isinstance(evidence, dict):
        errors.append("bad_evidence")
    return len(errors) == 0, errors


def normalize_critic_review(output: dict[str, Any]) -> dict[str, Any]:
    out = dict(output) if isinstance(output, dict) else {}
    out.setdefault("schema_version", CRITIC_REVIEW_SCHEMA_VERSION)
    out.setdefault("ok", False)
    out.setdefault("risk_level", "HIGH")
    out.setdefault("issues", [{"code": "invalid_output", "message": "输出不符合契约 已触发保守策略", "severity": "HIGH"}])
    out.setdefault("require_human_approval", True)
    out.setdefault("suggested_fixes", ["补齐证据链", "降低副作用动作", "必要时要求人工确认"])
    out.setdefault("evidence", {"fields": ["unknown"]})
    if not isinstance(out.get("issues"), list):
        out["issues"] = []
    if not isinstance(out.get("evidence"), dict):
        out["evidence"] = {"fields": ["unknown"]}
    return out
