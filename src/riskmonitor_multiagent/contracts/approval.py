from __future__ import annotations

from typing import Any

from riskmonitor_multiagent.utils import is_non_empty_str

APPROVAL_REQUEST_SCHEMA_VERSION = "approval_request.v1"
APPROVAL_RECORD_SCHEMA_VERSION = "approval_record.v1"

APPROVAL_LEVEL_VALUES = {"step", "command"}
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
APPROVAL_RISK_LEVEL_VALUES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

_APPROVAL_TRANSITIONS: dict[str, set[str]] = {
    "unknown": {"not_required", "pending", "approved", "rejected", "expired"},
    "not_required": set(),
    "pending": {"approved", "rejected", "expired"},
    "approved": {"resumed", "approved_but_failed"},
    "approved_but_failed": set(),
    "rejected": set(),
    "expired": set(),
    "resumed": set(),
}


def validate_approval_transition(current_state: str, next_state: str) -> tuple[bool, str | None]:
    current = _normalize_state(current_state)
    nxt = _normalize_state(next_state)
    if current is None:
        return False, "bad_current_approval_state"
    if nxt is None:
        return False, "bad_next_approval_state"
    if nxt == current:
        return True, None
    if nxt in _APPROVAL_TRANSITIONS.get(current, set()):
        return True, None
    return False, f"illegal_approval_transition:{current}->{nxt}"


def ensure_approval_transition(current_state: str, next_state: str) -> str:
    ok, error = validate_approval_transition(current_state, next_state)
    if not ok:
        raise ValueError(str(error))
    assert _normalize_state(next_state) is not None
    return str(_normalize_state(next_state))


def normalize_approval_request(request: dict[str, Any]) -> dict[str, Any]:
    req = dict(request) if isinstance(request, dict) else {}
    level = str(req.get("level") or "step").strip().lower()
    if level not in APPROVAL_LEVEL_VALUES:
        level = "step"

    impact_scope = _normalize_scope(req.get("impact_scope"))
    recommended_action = (
        str(req.get("recommended_action")).strip()
        if is_non_empty_str(req.get("recommended_action"))
        else "review_and_confirm"
    )
    reason = (
        str(req.get("reason")).strip()
        if is_non_empty_str(req.get("reason"))
        else "approval_required"
    )
    risk_level = _normalize_risk_level(req.get("risk_level"))
    if risk_level is None:
        risk_level = "HIGH"

    step_id = str(req.get("step_id")).strip() if is_non_empty_str(req.get("step_id")) else None
    command_id = str(req.get("command_id")).strip() if is_non_empty_str(req.get("command_id")) else None
    tool_name = str(req.get("tool_name")).strip() if is_non_empty_str(req.get("tool_name")) else None
    approval_id = (
        str(req.get("approval_id")).strip()
        if is_non_empty_str(req.get("approval_id"))
        else (
            f"command:{command_id}"
            if level == "command" and command_id
            else f"step:{step_id or 'unknown'}"
        )
    )

    return {
        "schema_version": APPROVAL_REQUEST_SCHEMA_VERSION,
        "approval_id": approval_id,
        "level": level,
        "step_id": step_id,
        "command_id": command_id,
        "tool_name": tool_name,
        "reason": reason,
        "risk_level": risk_level,
        "impact_scope": impact_scope,
        "recommended_action": recommended_action,
    }


def validate_approval_request(request: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(request, dict):
        return False, ["approval_request must be dict"]
    if request.get("schema_version") != APPROVAL_REQUEST_SCHEMA_VERSION:
        errors.append("bad_approval_request_schema_version")
    if not is_non_empty_str(request.get("approval_id")):
        errors.append("bad_approval_id")
    if request.get("level") not in APPROVAL_LEVEL_VALUES:
        errors.append("bad_approval_level")
    if not is_non_empty_str(request.get("reason")):
        errors.append("bad_approval_reason")
    if _normalize_risk_level(request.get("risk_level")) is None:
        errors.append("bad_approval_risk_level")
    if not isinstance(request.get("impact_scope"), list):
        errors.append("bad_approval_impact_scope")
    elif not all(is_non_empty_str(item) for item in request.get("impact_scope", [])):
        errors.append("bad_approval_impact_scope")
    if not is_non_empty_str(request.get("recommended_action")):
        errors.append("bad_approval_recommended_action")
    return len(errors) == 0, errors


def normalize_approval_record(record: dict[str, Any]) -> dict[str, Any]:
    payload = dict(record) if isinstance(record, dict) else {}
    request = normalize_approval_request(payload.get("request") if isinstance(payload.get("request"), dict) else payload)
    state = _normalize_state(payload.get("state")) or "pending"
    actor = str(payload.get("actor")).strip() if is_non_empty_str(payload.get("actor")) else None
    note = str(payload.get("note")).strip() if is_non_empty_str(payload.get("note")) else None
    error = str(payload.get("error")).strip() if is_non_empty_str(payload.get("error")) else None
    required = payload.get("required")
    if not isinstance(required, bool):
        required = state != "not_required"
    return {
        "schema_version": APPROVAL_RECORD_SCHEMA_VERSION,
        "approval_id": request["approval_id"],
        "level": request["level"],
        "step_id": request.get("step_id"),
        "command_id": request.get("command_id"),
        "tool_name": request.get("tool_name"),
        "state": state,
        "required": required,
        "reason": request["reason"],
        "risk_level": request["risk_level"],
        "impact_scope": list(request["impact_scope"]),
        "recommended_action": request["recommended_action"],
        "actor": actor,
        "note": note,
        "error": error,
        "request": request,
    }


def validate_approval_record(record: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return False, ["approval_record must be dict"]
    if record.get("schema_version") != APPROVAL_RECORD_SCHEMA_VERSION:
        errors.append("bad_approval_record_schema_version")
    request = record.get("request")
    ok_request, request_errors = validate_approval_request(request if isinstance(request, dict) else {})
    if not ok_request:
        errors.extend(request_errors)
    if record.get("state") not in APPROVAL_STATE_VALUES:
        errors.append("bad_approval_state")
    if not isinstance(record.get("required"), bool):
        errors.append("bad_approval_required")
    return len(errors) == 0, errors


def build_approval_summary_text(record: dict[str, Any]) -> str:
    level = str(record.get("level") or "step")
    state = str(record.get("state") or "pending")
    reason = str(record.get("reason") or "approval_required")
    risk_level = str(record.get("risk_level") or "HIGH")
    target = record.get("tool_name") or record.get("step_id") or record.get("command_id") or "unknown"
    return f"approval level={level} target={target} state={state} risk={risk_level} reason={reason}"


def _normalize_state(value: Any) -> str | None:
    if not is_non_empty_str(value):
        return None
    state = str(value).strip().lower()
    return state if state in APPROVAL_STATE_VALUES else None


def _normalize_risk_level(value: Any) -> str | None:
    if not is_non_empty_str(value):
        return None
    risk_level = str(value).strip().upper()
    return risk_level if risk_level in APPROVAL_RISK_LEVEL_VALUES else None


def _normalize_scope(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if is_non_empty_str(item)]
    if is_non_empty_str(value):
        return [str(value).strip()]
    return ["system"]

