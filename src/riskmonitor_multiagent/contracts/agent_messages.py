from __future__ import annotations

from typing import Any, Optional

AGENT_COMMAND_SCHEMA_VERSION = "agent_command.v1"
AGENT_RECEIPT_SCHEMA_VERSION = "agent_receipt.v1"


def validate_agent_command(cmd: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(cmd, dict):
        return False, ["command must be dict"]
    if cmd.get("schema_version") != AGENT_COMMAND_SCHEMA_VERSION:
        errors.append("bad_schema_version")
    if not isinstance(cmd.get("run_id"), str) or not cmd["run_id"].strip():
        errors.append("bad_run_id")
    if not isinstance(cmd.get("command_id"), str) or not cmd["command_id"].strip():
        errors.append("bad_command_id")
    if cmd.get("target_agent") not in {"system_engineer", "risk_analyst", "manager"}:
        errors.append("bad_target_agent")
    if not isinstance(cmd.get("action"), str) or not cmd["action"].strip():
        errors.append("bad_action")
    params = cmd.get("params")
    if params is not None and not isinstance(params, dict):
        errors.append("bad_params")
    timeout_ms = cmd.get("timeout_ms")
    if timeout_ms is not None and not isinstance(timeout_ms, int):
        errors.append("bad_timeout_ms")
    expected_output_schema = cmd.get("expected_output_schema")
    if expected_output_schema is not None and not isinstance(expected_output_schema, str):
        errors.append("bad_expected_output_schema")
    return len(errors) == 0, errors


def validate_agent_receipt(rcp: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(rcp, dict):
        return False, ["receipt must be dict"]
    if rcp.get("schema_version") != AGENT_RECEIPT_SCHEMA_VERSION:
        errors.append("bad_schema_version")
    if not isinstance(rcp.get("run_id"), str) or not rcp["run_id"].strip():
        errors.append("bad_run_id")
    if not isinstance(rcp.get("command_id"), str) or not rcp["command_id"].strip():
        errors.append("bad_command_id")
    if not isinstance(rcp.get("ok"), bool):
        errors.append("bad_ok")
    if rcp.get("target_agent") not in {"system_engineer", "risk_analyst", "manager"}:
        errors.append("bad_target_agent")
    if not isinstance(rcp.get("latency_ms"), (int, float)):
        errors.append("bad_latency_ms")
    evidence = rcp.get("evidence")
    if evidence is not None and not isinstance(evidence, dict):
        errors.append("bad_evidence")
    artifacts = rcp.get("artifacts")
    if artifacts is not None and not isinstance(artifacts, list):
        errors.append("bad_artifacts")
    error = rcp.get("error")
    if error is not None and not isinstance(error, str):
        errors.append("bad_error")
    output = rcp.get("output")
    if output is not None and not isinstance(output, dict):
        errors.append("bad_output")
    return len(errors) == 0, errors
