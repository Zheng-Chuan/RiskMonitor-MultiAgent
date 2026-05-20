import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.orchestration.tool_executor import execute_agent_command, new_agent_command


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


def test_engineer_cannot_call_side_effect_tool(monkeypatch):
    monkeypatch.setattr(
        "riskmonitor_multiagent.data_access.alerts_repository.save_alert",
        lambda alert: None,
        raising=True,
    )
    cmd = new_agent_command(
        run_id="run-1",
        command_id="cmd-1",
        target_agent="system_engineer",
        action="write_alert",
        params={"alert": _dummy_alert("a-1"), "approval": {"required": True, "approved": True}},
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)
    assert receipt["ok"] is False
    assert receipt["error"] == "rbac_denied"
    assert receipt["evidence"]["reason"] == "rbac_denied"


def test_manager_requires_approval_for_side_effect_tool(monkeypatch):
    monkeypatch.setattr(
        "riskmonitor_multiagent.data_access.alerts_repository.save_alert",
        lambda alert: None,
        raising=True,
    )
    cmd = new_agent_command(
        run_id="run-1",
        command_id="cmd-2",
        target_agent="manager",
        action="write_alert",
        params={"alert": _dummy_alert("a-2")},
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)
    assert receipt["ok"] is False
    assert receipt["error"] == "approval_required"
    assert receipt["evidence"]["reason"] == "approval_required"
    assert receipt["approval_state"] == "pending"
    assert isinstance(receipt["approval_trace"], dict)
    assert receipt["approval_trace"]["current_state"] == "pending"


def test_manager_can_execute_side_effect_tool_after_approval(monkeypatch):
    calls = {"n": 0}

    def _save(alert):
        calls["n"] += 1

    monkeypatch.setattr("riskmonitor_multiagent.data_access.alerts_repository.save_alert", _save, raising=True)
    cmd = new_agent_command(
        run_id="run-1",
        command_id="cmd-3",
        target_agent="manager",
        action="write_alert",
        params={"alert": _dummy_alert("a-3"), "approval": {"required": True, "approved": True, "note": "approved"}},
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)
    assert receipt["ok"] is True
    assert calls["n"] == 1
    assert receipt["approval_state"] == "resumed"
    history = receipt["approval_trace"]["history"]
    states = [item.get("state") for item in history]
    assert "pending" in states
    assert "approved" in states
    assert "resumed" in states


def test_rbac_denies_cross_role_read_only_tool():
    cmd = new_agent_command(
        run_id="run-1",
        command_id="cmd-4",
        target_agent="risk_analyst",
        action="collect_metrics",
        params={},
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)
    assert receipt["ok"] is False
    assert receipt["error"] == "rbac_denied"
    assert receipt["evidence"]["reason"] == "role_not_allowed"


def test_rbac_denies_manager_calling_analyst_tool():
    cmd = new_agent_command(
        run_id="run-1",
        command_id="cmd-5",
        target_agent="manager",
        action="search_similar_alerts",
        params={"query": "desk=Equity Derivatives", "top_k": 1},
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)
    assert receipt["ok"] is False
    assert receipt["error"] == "rbac_denied"
    assert receipt["evidence"]["reason"] == "role_not_allowed"
