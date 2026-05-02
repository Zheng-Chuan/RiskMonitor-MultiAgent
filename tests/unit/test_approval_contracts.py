from __future__ import annotations

import pytest

from riskmonitor_multiagent.contracts.approval import (
    APPROVAL_RECORD_SCHEMA_VERSION,
    APPROVAL_REQUEST_SCHEMA_VERSION,
    ensure_approval_transition,
    normalize_approval_record,
    normalize_approval_request,
    validate_approval_record,
    validate_approval_request,
    validate_approval_transition,
)


def test_approval_state_machine_accepts_happy_path() -> None:
    ok_pending, error_pending = validate_approval_transition("pending", "approved")
    ok_resumed, error_resumed = validate_approval_transition("approved", "resumed")

    assert ok_pending is True
    assert error_pending is None
    assert ok_resumed is True
    assert error_resumed is None
    assert ensure_approval_transition("approved", "resumed") == "resumed"


def test_approval_state_machine_rejects_illegal_transition() -> None:
    ok, error = validate_approval_transition("resumed", "pending")

    assert ok is False
    assert error == "illegal_approval_transition:resumed->pending"
    with pytest.raises(ValueError, match="illegal_approval_transition:resumed->pending"):
        ensure_approval_transition("resumed", "pending")


def test_approval_request_and_record_validate() -> None:
    request = normalize_approval_request(
        {
            "level": "step",
            "step_id": "s2",
            "reason": "需要人工确认影响范围",
            "risk_level": "HIGH",
            "impact_scope": ["desk:eq", "system"],
            "recommended_action": "review_and_resume_step",
        }
    )
    record = normalize_approval_record(
        {
            "request": request,
            "state": "pending",
            "error": "approval_required",
        }
    )

    ok_request, request_errors = validate_approval_request(request)
    ok_record, record_errors = validate_approval_record(record)

    assert request["schema_version"] == APPROVAL_REQUEST_SCHEMA_VERSION
    assert record["schema_version"] == APPROVAL_RECORD_SCHEMA_VERSION
    assert ok_request is True, request_errors
    assert ok_record is True, record_errors
