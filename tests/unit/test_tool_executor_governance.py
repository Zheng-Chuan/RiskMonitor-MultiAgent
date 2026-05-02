import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.orchestration.tool_executor import ToolResult, execute_agent_command, new_agent_command


def test_tool_executor_retries_timeout_and_classifies_failure(monkeypatch):
    import riskmonitor_multiagent.orchestration.tool_executor as te

    calls = {"n": 0}

    def _slow_handler(params):
        del params
        calls["n"] += 1
        time.sleep(0.03)
        return ToolResult(
            ok=True,
            output={"action": "collect_metrics", "result": {"cpu": 0.7}},
            evidence={"action": "collect_metrics"},
            artifacts=[{"kind": "tool_result", "action": "collect_metrics"}],
            error=None,
            latency_ms=30.0,
        )

    monkeypatch.setitem(te._ENGINEER_ALLOWLIST, "collect_metrics", _slow_handler)
    cmd = new_agent_command(
        run_id="run-timeout",
        command_id="cmd-timeout",
        target_agent="system_engineer",
        action="collect_metrics",
        params={},
        timeout_ms=5,
        expected_output_schema="tool_result.v1",
        retry_budget=1,
    )

    receipt = execute_agent_command(cmd)
    assert receipt["ok"] is False
    assert receipt["error"] == "tool_timeout"
    assert receipt["failure_classification"] == "timeout"
    assert receipt["retry_count"] == 1
    assert calls["n"] == 2
    retry_records = receipt["evidence"]["retry_records"]
    assert len(retry_records) == 2


def test_tool_executor_enforces_run_budget(monkeypatch):
    import riskmonitor_multiagent.orchestration.tool_executor as te

    te._RUN_BUDGET_STATE.clear()

    def _fast_handler(params):
        del params
        return ToolResult(
            ok=True,
            output={"action": "collect_metrics", "result": {"cpu": 0.4}},
            evidence={"action": "collect_metrics"},
            artifacts=[{"kind": "tool_result", "action": "collect_metrics"}],
            error=None,
            latency_ms=1.0,
        )

    monkeypatch.setitem(te._ENGINEER_ALLOWLIST, "collect_metrics", _fast_handler)

    cmd1 = new_agent_command(
        run_id="run-budget",
        command_id="cmd-budget-1",
        target_agent="system_engineer",
        action="collect_metrics",
        params={"_budget": {"tool_call_limit": 1}},
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    cmd2 = new_agent_command(
        run_id="run-budget",
        command_id="cmd-budget-2",
        target_agent="system_engineer",
        action="collect_metrics",
        params={"_budget": {"tool_call_limit": 1}},
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )

    receipt1 = execute_agent_command(cmd1)
    receipt2 = execute_agent_command(cmd2)
    assert receipt1["ok"] is True
    assert receipt2["ok"] is False
    assert receipt2["error"] == "tool_budget_exceeded"
    assert receipt2["evidence"]["budget"]["tool_call_limit"] == 1


def test_tool_executor_returns_rejected_approval_trace(monkeypatch):
    monkeypatch.setattr(
        "riskmonitor_multiagent.data_access.alerts_repository.save_alert",
        lambda alert: None,
        raising=True,
    )
    cmd = new_agent_command(
        run_id="run-rejected",
        command_id="cmd-rejected",
        target_agent="manager",
        action="write_alert",
        params={
            "alert": {
                "alert_id": "a-rejected",
                "request_id": "req-1",
                "alert_type": "DESK_DELTA_BREACH",
                "severity": "INFO",
                "desk": "Test Desk",
                "metric_name": "delta",
                "metric_value": 1.0,
                "threshold_value": 0.5,
                "breach_amount": 0.5,
                "message": "test",
                "created_at": "2026-01-01T00:00:00",
                "acknowledged": False,
                "acknowledged_at": None,
                "acknowledged_by": None,
            },
            "approval": {"state": "rejected", "approved": False},
        },
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)
    assert receipt["ok"] is False
    assert receipt["status"] == "blocked"
    assert receipt["approval_state"] == "rejected"
    assert receipt["approval_trace"]["current_state"] == "rejected"


def test_tool_executor_returns_resumed_approval_trace_and_request(monkeypatch):
    monkeypatch.setattr(
        "riskmonitor_multiagent.data_access.alerts_repository.save_alert",
        lambda alert: None,
        raising=True,
    )
    cmd = new_agent_command(
        run_id="run-approved",
        command_id="cmd-approved",
        target_agent="manager",
        action="write_alert",
        params={
            "alert": {
                "alert_id": "a-approved",
                "request_id": "req-2",
                "alert_type": "DESK_DELTA_BREACH",
                "severity": "WARNING",
                "desk": "EQ",
                "metric_name": "delta",
                "metric_value": 1.0,
                "threshold_value": 0.5,
                "breach_amount": 0.5,
                "message": "test",
                "created_at": "2026-01-01T00:00:00",
                "acknowledged": False,
                "acknowledged_at": None,
                "acknowledged_by": None,
            },
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
    receipt = execute_agent_command(cmd)

    assert receipt["ok"] is True
    assert receipt["status"] == "completed"
    assert receipt["approval_state"] == "resumed"
    assert receipt["approval_trace"]["current_state"] == "resumed"
    assert receipt["approval_trace"]["history"][-1]["state"] == "resumed"
    assert (receipt.get("approval_request") or {}).get("reason") == "风险可控"
    assert (receipt.get("approval_request") or {}).get("impact_scope") == ["desk:EQ"]


def test_tool_executor_returns_expired_approval_trace(monkeypatch):
    monkeypatch.setattr(
        "riskmonitor_multiagent.data_access.alerts_repository.save_alert",
        lambda alert: None,
        raising=True,
    )
    cmd = new_agent_command(
        run_id="run-expired",
        command_id="cmd-expired",
        target_agent="manager",
        action="write_alert",
        params={
            "alert": {
                "alert_id": "a-expired",
                "request_id": "req-3",
                "alert_type": "DESK_DELTA_BREACH",
                "severity": "INFO",
                "desk": "Rates",
                "metric_name": "delta",
                "metric_value": 1.0,
                "threshold_value": 0.5,
                "breach_amount": 0.5,
                "message": "test",
                "created_at": "2026-01-01T00:00:00",
                "acknowledged": False,
                "acknowledged_at": None,
                "acknowledged_by": None,
            },
            "approval": {"state": "expired", "approved": False},
        },
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)

    assert receipt["ok"] is False
    assert receipt["status"] == "blocked"
    assert receipt["approval_state"] == "expired"
    assert receipt["approval_trace"]["current_state"] == "expired"
