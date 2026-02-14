import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.orchestration.tool_executor import execute_agent_command, new_agent_command
from riskmonitor_multiagent.orchestration.tool_registry import SideEffectPolicy, ToolMeta


def _dummy_alert(alert_id: str) -> dict:
    return {
        "alert_id": alert_id,
        "request_id": "req-1",
        "alert_type": "DESK_DELTA_BREACH",
        "severity": "INFO",
        "desk": "Test Desk",
        "trader_id": None,
        "metric_name": "delta",
        "metric_value": 1.0,
        "threshold_value": 0.5,
        "breach_amount": 0.5,
        "message": "test",
        "created_at": "2026-01-01T00:00:00",
        "acknowledged": False,
        "acknowledged_at": None,
        "acknowledged_by": None,
    }


def test_side_effect_require_reason_enforced_when_approved(monkeypatch):
    cmd = new_agent_command(
        run_id="run-1",
        command_id="cmd-need-reason",
        target_agent="manager",
        action="write_alert",
        params={
            "alert": _dummy_alert("a-1"),
            "approval": {"required": True, "approved": True},
            "_event": {"severity": "INFO"},
        },
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)
    assert receipt.get("ok") is False
    assert receipt.get("error") == "approval_reason_required"


def test_side_effect_min_severity_enforced(monkeypatch):
    import riskmonitor_multiagent.orchestration.tool_executor as te

    def _patched_meta(action: str) -> ToolMeta | None:
        if action == "write_alert":
            return ToolMeta(
                action="write_alert",
                capability="side_effect",
                owner="manager",
                description="test",
                risk_level="high",
                default_timeout_ms=1000,
                side_effect_policy=SideEffectPolicy(require_approval=False, require_reason=False, min_severity="CRITICAL"),
            )
        return te.get_tool_meta(action)

    monkeypatch.setattr(te, "get_tool_meta", _patched_meta, raising=True)
    cmd = new_agent_command(
        run_id="run-1",
        command_id="cmd-min-sev",
        target_agent="manager",
        action="write_alert",
        params={"alert": _dummy_alert("a-2"), "approval": {"required": False, "approved": True}, "_event": {"severity": "INFO"}},
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)
    assert receipt.get("ok") is False
    assert receipt.get("error") == "policy_denied"
    evidence = receipt.get("evidence")
    assert isinstance(evidence, dict)
    assert evidence.get("reason") == "min_severity_not_met"

