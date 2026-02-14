import os
import sys
import time
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.contracts.risk_event import build_breach_event, normalize_cdc_event
from riskmonitor_multiagent.agents.base import AgentResult
from riskmonitor_multiagent.contracts.agent_outputs import (
    MANAGER_OUTPUT_SCHEMA_VERSION,
    RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
)
from riskmonitor_multiagent.orchestration.state_machine import run_state_machine


@pytest.mark.asyncio
async def test_state_machine_runs_and_persists_context(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_LANGGRAPH", "1")
    monkeypatch.setenv("HITL_AUTO_APPROVE", "1")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("DISABLE_LLM", "1")

    now_ms = int(time.time() * 1000)
    source = normalize_cdc_event(
        raw_record={"desk": "Commodities", "delta": 60000.0},
        topic="risk.positions.cdc",
        partition=0,
        offset=1,
        message_ts_ms=now_ms,
    )
    event = build_breach_event(source_event=source, desk="Commodities", exposure=60000.0, threshold=50000.0, now_ms=now_ms)

    out = await run_state_machine(event=event.to_dict())
    assert out["ok"] is True

    result = out["result"]
    assert isinstance(result, dict)
    assert result["event_id"].endswith(":breach")
    assert isinstance(result.get("run_id"), str) and result["run_id"]

    receipts = result.get("receipts")
    assert isinstance(receipts, list)
    assert len(receipts) >= 1
    run_meta = result.get("run_meta")
    assert isinstance(run_meta, dict)
    assert isinstance(run_meta.get("policy_version"), str)
    assert isinstance(run_meta.get("tool_registry_version"), str)
    assert isinstance(run_meta.get("rbac_policy_version"), str)
    prompt_versions = run_meta.get("prompt_versions")
    assert isinstance(prompt_versions, dict)
    assert set(prompt_versions.keys()) >= {"system_engineer", "risk_analyst", "manager"}

    manager = result.get("manager")
    assert isinstance(manager, dict)
    evidence = manager.get("evidence")
    assert isinstance(evidence, dict)
    assert isinstance(evidence.get("receipt_command_ids"), list)
    assert len(evidence.get("receipt_command_ids")) >= 1

    stored = list(tmp_path.glob("run_*.json"))
    assert stored

    source2 = normalize_cdc_event(
        raw_record={"desk": "Commodities", "delta": 60000.0},
        topic="risk.positions.cdc",
        partition=0,
        offset=2,
        message_ts_ms=now_ms,
    )
    event2 = build_breach_event(source_event=source2, desk="Commodities", exposure=60000.0, threshold=50000.0, now_ms=now_ms)
    out2 = await run_state_machine(event=event2.to_dict())
    assert out2["ok"] is True
    result2 = out2["result"]
    rag2 = result2.get("rag")
    assert isinstance(rag2, dict)
    memory_hits = rag2.get("memory_hits")
    assert isinstance(memory_hits, list)
    assert len(memory_hits) >= 1

    memory = result2.get("memory")
    assert isinstance(memory, dict)
    assert memory.get("write_ok") is True


@pytest.mark.asyncio
async def test_state_machine_replay_returns_same_final_output(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_LANGGRAPH", "1")
    monkeypatch.setenv("HITL_AUTO_APPROVE", "1")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("DISABLE_LLM", "1")

    now_ms = int(time.time() * 1000)
    source = normalize_cdc_event(
        raw_record={"desk": "Commodities", "delta": 60000.0},
        topic="risk.positions.cdc",
        partition=0,
        offset=10,
        message_ts_ms=now_ms,
    )
    event = build_breach_event(source_event=source, desk="Commodities", exposure=60000.0, threshold=50000.0, now_ms=now_ms)

    out1 = await run_state_machine(event=event.to_dict())
    out2 = await run_state_machine(event=event.to_dict())
    assert out1["ok"] is True
    assert out2["ok"] is True
    assert out1["result"] == out2["result"]


@pytest.mark.asyncio
async def test_state_machine_rewrite_loop_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_LANGGRAPH", "1")
    monkeypatch.setenv("HITL_AUTO_APPROVE", "1")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("DISABLE_LLM", "1")

    import riskmonitor_multiagent.orchestration.state_machine as sm

    calls = {"n": 0}

    async def _fake_analyze(self, *, event, extra_instruction=None):
        calls["n"] += 1
        if extra_instruction is None:
            return AgentResult(
                ok=False,
                output={
                    "schema_version": RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
                    "report": "",
                    "key_facts": {},
                    "confidence": 0.1,
                    "evidence": {},
                },
            )
        return AgentResult(
            ok=True,
            output={
                "schema_version": RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
                "report": "ok",
                "key_facts": {"desk": "Commodities"},
                "confidence": 0.8,
                "evidence": {"fixed": True},
            },
        )

    monkeypatch.setattr(sm.RiskAnalystAgent, "analyze", _fake_analyze, raising=True)

    now_ms = int(time.time() * 1000)
    source = normalize_cdc_event(
        raw_record={"desk": "Commodities", "delta": 60000.0},
        topic="risk.positions.cdc",
        partition=0,
        offset=11,
        message_ts_ms=now_ms,
    )
    event = build_breach_event(source_event=source, desk="Commodities", exposure=60000.0, threshold=50000.0, now_ms=now_ms)
    out = await run_state_machine(event=event.to_dict())
    assert out["ok"] is True
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_state_machine_requires_human_approval_when_auto_off(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_LANGGRAPH", "1")
    monkeypatch.setenv("HITL_AUTO_APPROVE", "0")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("DISABLE_LLM", "1")

    import riskmonitor_multiagent.orchestration.state_machine as sm

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

    monkeypatch.setattr(sm, "execute_agent_command", _ok_receipt, raising=True)

    async def _manager_decide(self, *, event, analyst_report):
        return AgentResult(
            ok=True,
            output={
                "schema_version": MANAGER_OUTPUT_SCHEMA_VERSION,
                "decision": "CRITICAL",
                "action": "do",
                "rationale": "why",
                "plan_steps": None,
                "commands": None,
                "evidence": {"event_id": event.get("event_id")},
            },
        )

    monkeypatch.setattr(sm.ManagerAgent, "decide", _manager_decide, raising=True)

    now_ms = int(time.time() * 1000)
    source = normalize_cdc_event(
        raw_record={"desk": "Commodities", "delta": 120000.0},
        topic="risk.positions.cdc",
        partition=0,
        offset=12,
        message_ts_ms=now_ms,
    )
    event = build_breach_event(source_event=source, desk="Commodities", exposure=120000.0, threshold=50000.0, now_ms=now_ms)
    out = await run_state_machine(event=event.to_dict())
    assert out["ok"] is True
    result = out["result"]
    assert isinstance(result, dict)
    assert result.get("blocked") is True
    approval = result.get("approval")
    assert isinstance(approval, dict)
    assert approval.get("required") is True
    assert approval.get("approved") is False


@pytest.mark.asyncio
async def test_state_machine_requires_human_approval_for_side_effect_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_LANGGRAPH", "1")
    monkeypatch.setenv("HITL_AUTO_APPROVE", "0")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("DISABLE_LLM", "1")

    import riskmonitor_multiagent.orchestration.state_machine as sm

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

    monkeypatch.setattr(sm, "execute_agent_command", _ok_receipt, raising=True)

    async def _manager_decide(self, *, event, analyst_report):
        return AgentResult(
            ok=True,
            output={
                "schema_version": MANAGER_OUTPUT_SCHEMA_VERSION,
                "decision": "WATCH",
                "action": "write",
                "rationale": "why",
                "plan_steps": None,
                "commands": [
                    {
                        "schema_version": "agent_command.v1",
                        "run_id": event.get("payload", {}).get("_run_id") if isinstance(event.get("payload"), dict) else "run-1",
                        "command_id": "cmd_side_effect_write_alert",
                        "target_agent": "manager",
                        "action": "write_alert",
                        "params": {"alert": {"alert_id": "a-side-effect"}},
                        "timeout_ms": 1000,
                        "expected_output_schema": "tool_result.v1",
                    }
                ],
                "evidence": {"event_id": event.get("event_id")},
            },
        )

    monkeypatch.setattr(sm.ManagerAgent, "decide", _manager_decide, raising=True)

    now_ms = int(time.time() * 1000)
    source = normalize_cdc_event(
        raw_record={"desk": "Commodities", "delta": 60000.0},
        topic="risk.positions.cdc",
        partition=0,
        offset=99,
        message_ts_ms=now_ms,
    )
    event = build_breach_event(source_event=source, desk="Commodities", exposure=60000.0, threshold=50000.0, now_ms=now_ms)
    out = await run_state_machine(event=event.to_dict())
    assert out["ok"] is True
    result = out["result"]
    assert isinstance(result, dict)
    assert result.get("blocked") is True
    approval = result.get("approval")
    assert isinstance(approval, dict)
    assert approval.get("required") is True
    assert approval.get("approved") is False
    assert approval.get("reason") == "side_effect_required"


@pytest.mark.asyncio
async def test_state_machine_records_audit_for_side_effect_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXT_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_LANGGRAPH", "1")
    monkeypatch.setenv("HITL_AUTO_APPROVE", "1")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("DISABLE_LLM", "1")

    import riskmonitor_multiagent.orchestration.state_machine as sm

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

    monkeypatch.setattr(sm, "execute_agent_command", _ok_receipt, raising=True)

    async def _manager_decide(self, *, event, analyst_report):
        return AgentResult(
            ok=True,
            output={
                "schema_version": MANAGER_OUTPUT_SCHEMA_VERSION,
                "decision": "WATCH",
                "action": "write",
                "rationale": "why",
                "plan_steps": None,
                "commands": [
                    {
                        "schema_version": "agent_command.v1",
                        "run_id": "run-1",
                        "command_id": "cmd_side_effect_write_alert",
                        "target_agent": "manager",
                        "action": "write_alert",
                        "params": {"alert": {"alert_id": "a-side-effect"}},
                        "timeout_ms": 1000,
                        "expected_output_schema": "tool_result.v1",
                    }
                ],
                "evidence": {"event_id": event.get("event_id")},
            },
        )

    monkeypatch.setattr(sm.ManagerAgent, "decide", _manager_decide, raising=True)

    now_ms = int(time.time() * 1000)
    source = normalize_cdc_event(
        raw_record={"desk": "Commodities", "delta": 60000.0},
        topic="risk.positions.cdc",
        partition=0,
        offset=100,
        message_ts_ms=now_ms,
    )
    event = build_breach_event(source_event=source, desk="Commodities", exposure=60000.0, threshold=50000.0, now_ms=now_ms)
    out = await run_state_machine(event=event.to_dict())
    assert out["ok"] is True
    result = out["result"]
    assert isinstance(result, dict)
    assert result.get("blocked") is not True
    approval = result.get("approval")
    assert isinstance(approval, dict)
    assert approval.get("required") is True
    assert approval.get("approved") is True
    assert approval.get("reason") == "side_effect_required"
    audit_records = result.get("audit_records")
    assert isinstance(audit_records, list)
    assert len(audit_records) == 1
    ar = audit_records[0]
    assert ar.get("action") == "write_alert"
    assert ar.get("target_agent") == "manager"
    assert ar.get("approved") is True
    assert ar.get("ok") is True
