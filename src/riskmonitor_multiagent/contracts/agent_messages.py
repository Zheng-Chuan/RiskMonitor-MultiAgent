from __future__ import annotations

from typing import Any, Optional

AGENT_COMMAND_SCHEMA_VERSION = "agent_command.v1"
AGENT_RECEIPT_SCHEMA_VERSION = "agent_receipt.v1"
RECEIPT_STATUS_VALUES = {"completed", "failed", "blocked"}
APPROVAL_STATE_VALUES = {
    "not_required",
    "pending",
    "approved",
    "approved_but_failed",
    "rejected",
    "expired",
    "resumed",
    "unknown",
}
FAILURE_CLASSIFICATION_VALUES = {
    "permission",
    "validation",
    "runtime",
    "dependency",
    "timeout",
}


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
    if timeout_ms is not None and (not isinstance(timeout_ms, int) or timeout_ms < 0):
        errors.append("bad_timeout_ms")
    retry_budget = cmd.get("retry_budget")
    if retry_budget is not None and (not isinstance(retry_budget, int) or retry_budget < 0):
        errors.append("bad_retry_budget")
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
    if not isinstance(rcp.get("tool_name"), str) or not rcp["tool_name"].strip():
        errors.append("bad_tool_name")
    if not isinstance(rcp.get("ok"), bool):
        errors.append("bad_ok")
    if rcp.get("target_agent") not in {"system_engineer", "risk_analyst", "manager"}:
        errors.append("bad_target_agent")
    inputs = rcp.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("bad_inputs")
    status = rcp.get("status")
    if not isinstance(status, str) or status not in RECEIPT_STATUS_VALUES:
        errors.append("bad_status")
    latency_ms = rcp.get("latency_ms")
    if not isinstance(latency_ms, (int, float)) or float(latency_ms) < 0:
        errors.append("bad_latency_ms")
    if not isinstance(rcp.get("side_effect"), bool):
        errors.append("bad_side_effect")
    approval_state = rcp.get("approval_state")
    if not isinstance(approval_state, str) or approval_state not in APPROVAL_STATE_VALUES:
        errors.append("bad_approval_state")
    evidence = rcp.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("bad_evidence")
    artifacts = rcp.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("bad_artifacts")
    if "outputs" not in rcp:
        errors.append("bad_outputs")
    outputs = rcp.get("outputs")
    if "outputs" in rcp and outputs is not None and not isinstance(outputs, dict):
        errors.append("bad_outputs")
    if "error" not in rcp:
        errors.append("bad_error")
    error = rcp.get("error")
    if "error" in rcp and error is not None and not isinstance(error, str):
        errors.append("bad_error")
    output = rcp.get("output")
    if "output" not in rcp:
        errors.append("bad_output")
    if "output" in rcp and output is not None and not isinstance(output, dict):
        errors.append("bad_output")
    failure_classification = rcp.get("failure_classification")
    if failure_classification is not None and failure_classification not in FAILURE_CLASSIFICATION_VALUES:
        errors.append("bad_failure_classification")
    retry_count = rcp.get("retry_count")
    if not isinstance(retry_count, int) or retry_count < 0:
        errors.append("bad_retry_count")
    retry_budget = rcp.get("retry_budget")
    if not isinstance(retry_budget, int) or retry_budget < 0:
        errors.append("bad_retry_budget")
    timeout_ms = rcp.get("timeout_ms")
    if not isinstance(timeout_ms, int) or timeout_ms < 0:
        errors.append("bad_timeout_ms")
    approval_trace = rcp.get("approval_trace")
    if not isinstance(approval_trace, dict):
        errors.append("bad_approval_trace")
    return len(errors) == 0, errors
