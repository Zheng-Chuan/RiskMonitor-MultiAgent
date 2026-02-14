import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.agents.base import AgentResult
from riskmonitor_multiagent.contracts.agent_outputs import MANAGER_OUTPUT_SCHEMA_VERSION, RISK_ANALYST_OUTPUT_SCHEMA_VERSION
from riskmonitor_multiagent.contracts.risk_event import build_breach_event, normalize_cdc_event
from riskmonitor_multiagent.governance.replay_compare import ReplayVariant, run_replay_compare


def _ok_receipt(cmd):
    return {
        "schema_version": "agent_receipt.v1",
        "run_id": cmd.get("run_id"),
        "command_id": cmd.get("command_id"),
        "target_agent": cmd.get("target_agent"),
        "ok": True,
        "latency_ms": 1.0,
        "evidence": {"action": cmd.get("action")},
        "artifacts": [],
        "error": None,
        "output": {"action": cmd.get("action"), "result": {"ok": True}},
    }


async def _analyst_analyze(self, *, event, extra_instruction=None, max_tokens=512):
    return AgentResult(
        ok=True,
        output={
            "schema_version": RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
            "report": "ok",
            "key_facts": {"event_id": event.get("event_id")},
            "confidence": 0.9,
            "evidence": {"event_id": event.get("event_id")},
        },
    )


async def _manager_decide(self, *, event, analyst_report, max_tokens=512):
    pv = os.getenv("POLICY_VERSION", "")
    decision = "CRITICAL" if pv.endswith("b") else "WATCH"
    return AgentResult(
        ok=True,
        output={
            "schema_version": MANAGER_OUTPUT_SCHEMA_VERSION,
            "decision": decision,
            "action": "act",
            "rationale": pv,
            "plan_steps": None,
            "commands": None,
            "evidence": {"policy_version": pv},
        },
    )


def test_replay_compare_detects_policy_differences(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_LANGGRAPH", "1")
    monkeypatch.setenv("HITL_AUTO_APPROVE", "1")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))

    now_ms = int(time.time() * 1000)
    source = normalize_cdc_event(
        raw_record={"desk": "Commodities", "delta": 60000.0},
        topic="risk.positions.cdc",
        partition=0,
        offset=2000,
        message_ts_ms=now_ms,
    )
    event = build_breach_event(source_event=source, desk="Commodities", exposure=60000.0, threshold=50000.0, now_ms=now_ms).to_dict()

    with patch("riskmonitor_multiagent.orchestration.state_machine.execute_agent_command", _ok_receipt), patch(
        "riskmonitor_multiagent.orchestration.state_machine.RiskAnalystAgent.analyze", _analyst_analyze
    ), patch("riskmonitor_multiagent.orchestration.state_machine.ManagerAgent.decide", _manager_decide):
        report = run_replay_compare(
            event=event,
            a=ReplayVariant(name="a", policy_version="policy.a"),
            b=ReplayVariant(name="b", policy_version="policy.b"),
            output_file=str(tmp_path / "report.json"),
        )
    assert report.get("schema_version") == "replay_compare.v1"
    diffs = report.get("diffs")
    assert isinstance(diffs, list)
    assert any(d.get("path") == "manager.decision" for d in diffs)

