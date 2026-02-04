from __future__ import annotations

from typing import Any

SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION = "system_engineer_output.v1"
RISK_ANALYST_OUTPUT_SCHEMA_VERSION = "risk_analyst_output.v1"
MANAGER_OUTPUT_SCHEMA_VERSION = "manager_output.v1"


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
    if evidence is not None and not isinstance(evidence, dict):
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

    return len(errors) == 0, errors


def normalize_manager_output(output: dict[str, Any]) -> dict[str, Any]:
    out = dict(output) if isinstance(output, dict) else {}
    out.setdefault("schema_version", MANAGER_OUTPUT_SCHEMA_VERSION)
    out.setdefault("decision", "WATCH")
    out.setdefault("action", "建议通知值班人员 并要求 desk 提供解释")
    out.setdefault("rationale", "输出不符合契约 已回退到最小决策")
    if "plan_steps" in out and out["plan_steps"] is not None and not isinstance(out["plan_steps"], list):
        out["plan_steps"] = None
    if "commands" in out and out["commands"] is not None and not isinstance(out["commands"], list):
        out["commands"] = None
    return out
