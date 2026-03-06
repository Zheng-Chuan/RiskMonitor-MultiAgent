from __future__ import annotations

from typing import Any

SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION = "system_engineer_output.v1"
RISK_ANALYST_OUTPUT_SCHEMA_VERSION = "risk_analyst_output.v1"
ORCHESTRATOR_OUTPUT_SCHEMA_VERSION = "orchestrator_output.v1"
CRITIC_REVIEW_SCHEMA_VERSION = "critic_review.v1"


def _is_non_empty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _has_evidence_refs(evidence: Any) -> bool:
    if not isinstance(evidence, dict):
        return False
    receipt_ids = evidence.get("receipt_command_ids")
    fields = evidence.get("fields")
    rag_hits = evidence.get("rag_hit_ids")
    has_receipts = isinstance(receipt_ids, list) and any(_is_non_empty_str(x) for x in receipt_ids)
    has_fields = isinstance(fields, list) and any(_is_non_empty_str(x) for x in fields)
    has_rag = isinstance(rag_hits, list) and any(_is_non_empty_str(x) for x in rag_hits)
    return bool(has_receipts or has_fields or has_rag)


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
    elif not _has_evidence_refs(evidence):
        errors.append("missing_key_system_engineer_evidence_refs")

    return len(errors) == 0, errors


def normalize_system_engineer_output(output: dict[str, Any]) -> dict[str, Any]:
    out = dict(output) if isinstance(output, dict) else {}
    out.setdefault("schema_version", SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION)
    out.setdefault("system_issue", True)
    out.setdefault("reason", "invalid_output")
    out.setdefault("evidence", {"fields": ["unknown"]})
    if not isinstance(out.get("evidence"), dict):
        out["evidence"] = {"fields": ["unknown"]}
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
    if not isinstance(evidence, dict):
        errors.append("bad_evidence")
    elif not _has_evidence_refs(evidence):
        errors.append("missing_key_risk_analyst_evidence_refs")

    return len(errors) == 0, errors


def normalize_risk_analyst_output(output: dict[str, Any]) -> dict[str, Any]:
    out = dict(output) if isinstance(output, dict) else {}
    out.setdefault("schema_version", RISK_ANALYST_OUTPUT_SCHEMA_VERSION)
    out.setdefault("report", "输出不符合契约 已回退到最小报告")
    out.setdefault("key_facts", {})
    out.setdefault("evidence", {"fields": ["unknown"]})
    if not isinstance(out.get("evidence"), dict):
        out["evidence"] = {"fields": ["unknown"]}
    if "confidence" in out and out["confidence"] is not None:
        try:
            out["confidence"] = float(out["confidence"])
        except Exception:
            out["confidence"] = None
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
    if isinstance(plan_steps, list):
        for s in plan_steps:
            if not isinstance(s, dict):
                errors.append("bad_plan_step")
                continue
            kind = s.get("kind")
            if not _is_non_empty_str(kind):
                errors.append("bad_plan_step_kind")
                continue
            if not _is_non_empty_str(s.get("step_id")):
                errors.append("bad_plan_step_id")
            if not _is_non_empty_str(s.get("reason")):
                errors.append("bad_plan_step_reason")
            if kind == "delegate":
                if not _is_non_empty_str(s.get("target_agent")):
                    errors.append("bad_delegate_target_agent")
                if not _is_non_empty_str(s.get("instruction")):
                    errors.append("bad_delegate_instruction")

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
        if not _has_evidence_refs(evidence):
            errors.append("missing_key_orchestrator_evidence_refs")
        command_ids: set[str] = set()
        if isinstance(commands, list):
            for c in commands:
                if not isinstance(c, dict):
                    continue
                cid = c.get("command_id")
                if _is_non_empty_str(cid):
                    command_ids.add(str(cid))
        receipt_ids = evidence.get("receipt_command_ids")
        if command_ids and isinstance(receipt_ids, list):
            missing = [rid for rid in receipt_ids if _is_non_empty_str(rid) and str(rid) not in command_ids]
            if missing:
                errors.append("receipt_binding_mismatch")

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
    if isinstance(out.get("plan_steps"), list):
        fixed_steps: list[dict[str, Any]] = []
        for i, s in enumerate(out.get("plan_steps")):
            if not isinstance(s, dict):
                continue
            step = dict(s)
            if not _is_non_empty_str(step.get("step_id")):
                step["step_id"] = f"s{i+1}"
            if not _is_non_empty_str(step.get("reason")):
                step["reason"] = "缺少原因说明 已自动回填"
            fixed_steps.append(step)
        out["plan_steps"] = fixed_steps
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
    elif isinstance(evidence, dict) and not _has_evidence_refs(evidence):
        errors.append("missing_key_critic_evidence_refs")
    run_summary = output.get("run_summary")
    if run_summary is not None and not isinstance(run_summary, dict):
        errors.append("bad_run_summary")
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
    out.setdefault("run_summary", {"text": "run_summary 未生成", "key_points": [], "receipt_command_ids": []})
    if not isinstance(out.get("issues"), list):
        out["issues"] = []
    if not isinstance(out.get("evidence"), dict):
        out["evidence"] = {"fields": ["unknown"]}
    if not isinstance(out.get("run_summary"), dict):
        out["run_summary"] = {"text": "run_summary 未生成", "key_points": [], "receipt_command_ids": []}
    return out
