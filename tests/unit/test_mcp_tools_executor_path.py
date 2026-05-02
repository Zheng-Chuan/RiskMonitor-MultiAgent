from __future__ import annotations

from unittest.mock import patch

from riskmonitor_multiagent.tools import mcp_tools


def test_query_positions_by_trader_uses_tool_executor_path():
    fake_receipt = {
        "schema_version": "agent_receipt.v1",
        "run_id": "mcp:test",
        "command_id": "cmd-mcp-1",
        "target_agent": "risk_analyst",
        "tool_name": "query_positions_by_trader",
        "inputs": {"trader_id": "TRADER-001"},
        "outputs": {
            "action": "query_positions_by_trader",
            "result": {
                "trader_id": "TRADER-001",
                "position_count": 1,
                "total_delta": 12.5,
                "positions": [],
            },
        },
        "status": "completed",
        "ok": True,
        "latency_ms": 4.2,
        "evidence": {"action": "query_positions_by_trader"},
        "artifacts": [],
        "error": None,
        "output": {
            "action": "query_positions_by_trader",
            "result": {
                "trader_id": "TRADER-001",
                "position_count": 1,
                "total_delta": 12.5,
                "positions": [],
            },
        },
        "side_effect": False,
        "approval_state": "not_required",
    }

    with patch(
        "riskmonitor_multiagent.tools.mcp_tools.execute_agent_command",
        return_value=fake_receipt,
    ) as mocked_execute:
        result = mcp_tools.query_positions_by_trader("TRADER-001")

    mocked_execute.assert_called_once()
    called_command = mocked_execute.call_args.args[0]
    assert called_command["action"] == "query_positions_by_trader"
    assert called_command["target_agent"] == "risk_analyst"
    assert result["trader_id"] == "TRADER-001"
    assert result["position_count"] == 1


def test_submit_alerts_uses_tool_executor_path():
    fake_receipt = {
        "schema_version": "agent_receipt.v1",
        "run_id": "mcp:test",
        "command_id": "cmd-mcp-2",
        "target_agent": "manager",
        "tool_name": "submit_alerts",
        "inputs": {"alerts": [{"alert_id": "a1"}]},
        "outputs": {
            "action": "submit_alerts",
            "result": {"saved": 1},
        },
        "status": "completed",
        "ok": True,
        "latency_ms": 5.0,
        "evidence": {"action": "submit_alerts"},
        "artifacts": [],
        "error": None,
        "output": {
            "action": "submit_alerts",
            "result": {"saved": 1},
        },
        "side_effect": True,
        "approval_state": "approved",
    }

    with patch(
        "riskmonitor_multiagent.tools.mcp_tools.execute_agent_command",
        return_value=fake_receipt,
    ) as mocked_execute:
        result = mcp_tools.submit_alerts(
            alerts=[{"alert_id": "a1"}],
            approval={"approved": True, "note": "approved for test"},
        )

    mocked_execute.assert_called_once()
    called_command = mocked_execute.call_args.args[0]
    assert called_command["action"] == "submit_alerts"
    assert called_command["target_agent"] == "manager"
    assert result["saved"] == 1
