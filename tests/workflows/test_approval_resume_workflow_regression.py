import sys
from pathlib import Path


project_root = Path(__file__).resolve().parents[2]
src_root = project_root / "src"
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))

from riskmonitor_multiagent.contracts.approval import validate_approval_request
from riskmonitor_multiagent.orchestration.tool_executor import (
    execute_agent_command,
    new_agent_command,
)


def _build_alert(alert_id: str, request_id: str) -> dict:
    return {
        "alert_id": alert_id,
        "request_id": request_id,
        "alert_type": "DESK_DELTA_BREACH",
        "severity": "WARNING",
        "desk": "EQ",
        "metric_name": "delta",
        "metric_value": 1.0,
        "threshold_value": 0.5,
        "breach_amount": 0.5,
        "message": "workflow approval regression",
        "created_at": "2026-01-01T00:00:00",
        "acknowledged": False,
        "acknowledged_at": None,
        "acknowledged_by": None,
    }


def test_approval_resume_workflow_blocks_then_resumes(monkeypatch) -> None:
    monkeypatch.setattr(
        "riskmonitor_multiagent.data_access.alerts_repository.save_alert",
        lambda alert: None,
        raising=True,
    )

    pending_command = new_agent_command(
        run_id="workflow-approval-run",
        command_id="workflow-approval-cmd",
        target_agent="manager",
        action="write_alert",
        params={
            "alert": _build_alert(
                alert_id="workflow-approval-alert",
                request_id="workflow-approval-req",
            ),
        },
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    pending_receipt = execute_agent_command(pending_command)

    assert pending_receipt["ok"] is False
    assert pending_receipt["status"] == "blocked"
    assert pending_receipt["error"] == "approval_required"
    assert pending_receipt["approval_state"] == "pending"
    assert pending_receipt["approval_trace"]["current_state"] == "pending"

    approval_request = pending_receipt.get("approval_request")
    assert isinstance(approval_request, dict)
    ok_request, request_errors = validate_approval_request(approval_request)
    assert ok_request is True, str(request_errors)
    assert approval_request["level"] == "command"
    assert approval_request["command_id"] == "workflow-approval-cmd"
    assert approval_request["tool_name"] == "write_alert"

    resumed_command = new_agent_command(
        run_id="workflow-approval-run",
        command_id="workflow-approval-cmd",
        target_agent="manager",
        action="write_alert",
        params={
            "alert": _build_alert(
                alert_id="workflow-approval-alert",
                request_id="workflow-approval-req",
            ),
            "approval": {
                "state": "approved",
                "approved": True,
                "actor": "ops",
                "note": "已核对影响范围",
                "reason": "风险可控",
                "risk_level": "HIGH",
                "impact_scope": ["desk:EQ"],
                "recommended_action": "approve command write_alert",
            },
        },
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    resumed_receipt = execute_agent_command(resumed_command)

    assert resumed_receipt["ok"] is True
    assert resumed_receipt["status"] == "completed"
    assert resumed_receipt["approval_state"] == "resumed"
    assert resumed_receipt["approval_trace"]["current_state"] == "resumed"
    states = [item.get("state") for item in resumed_receipt["approval_trace"]["history"]]
    assert states == ["pending", "approved", "resumed"]
    assert (resumed_receipt.get("approval_request") or {}).get("reason") == "风险可控"
    assert (resumed_receipt.get("approval_request") or {}).get("impact_scope") == ["desk:EQ"]
