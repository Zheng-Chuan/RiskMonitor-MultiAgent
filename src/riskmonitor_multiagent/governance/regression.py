from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from riskmonitor_multiagent.agents.base import AgentResult
from riskmonitor_multiagent.contracts.agent_outputs import MANAGER_OUTPUT_SCHEMA_VERSION, RISK_ANALYST_OUTPUT_SCHEMA_VERSION
from riskmonitor_multiagent.contracts.risk_event import build_breach_event, normalize_cdc_event
from riskmonitor_multiagent.observability.metrics import render_prometheus_metrics, reset_observability_metrics
from riskmonitor_multiagent.orchestration.state_machine import run_state_machine
from riskmonitor_multiagent.orchestration.tool_executor import execute_agent_command, new_agent_command


@dataclass(frozen=True)
class RegressionCase:
    name: str
    fn: Any


def _dummy_alert(alert_id: str) -> dict[str, Any]:
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


class _TempEnv:
    def __init__(self, overrides: dict[str, str]) -> None:
        self._overrides = overrides
        self._prev: dict[str, str | None] = {}

    def __enter__(self):
        for k, v in self._overrides.items():
            self._prev[k] = os.environ.get(k)
            os.environ[k] = v
        return self

    def __exit__(self, exc_type, exc, tb):
        for k, prev in self._prev.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev
        return False


def _case_rbac_deny() -> dict[str, Any]:
    cmd = new_agent_command(
        run_id="run-1",
        command_id="cmd-rbac-deny",
        target_agent="system_engineer",
        action="write_alert",
        params={"alert": _dummy_alert("a-rbac"), "approval": {"required": True, "approved": True}},
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)
    ok = bool(receipt.get("ok") is False and receipt.get("error") == "rbac_denied")
    return {"ok": ok, "receipt": receipt}


def _case_approval_required() -> dict[str, Any]:
    cmd = new_agent_command(
        run_id="run-1",
        command_id="cmd-approval-required",
        target_agent="manager",
        action="write_alert",
        params={"alert": _dummy_alert("a-approval")},
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)
    ok = bool(receipt.get("ok") is False and receipt.get("error") == "approval_required")
    return {"ok": ok, "receipt": receipt}


def _case_approval_reject() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        with _TempEnv(
            {
                "CONTEXT_STORE_DIR": str(base / "ctx"),
                "ENABLE_LANGGRAPH": "1",
                "HITL_AUTO_APPROVE": "0",
                "CHROMA_PERSIST_DIR": str(base / "chroma"),
                "TOKEN_BUDGET": "2000",
                "TOOL_BUDGET": "10",
                "TIME_BUDGET_MS": "15000",
            }
        ):
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

            async def _analyst_analyze(self, *, event, extra_instruction=None, max_tokens=512):
                return AgentResult(
                    ok=True,
                    output={
                        "schema_version": RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
                        "report": "ok",
                        "key_facts": {"event_id": event.get("event_id")},
                        "confidence": 0.8,
                        "evidence": {"event_id": event.get("event_id")},
                    },
                )

            now_ms = int(time.time() * 1000)
            source = normalize_cdc_event(
                raw_record={"desk": "Commodities", "delta": 60000.0},
                topic="risk.positions.cdc",
                partition=0,
                offset=999,
                message_ts_ms=now_ms,
            )
            event = build_breach_event(source_event=source, desk="Commodities", exposure=60000.0, threshold=50000.0, now_ms=now_ms)

            with patch("riskmonitor_multiagent.orchestration.state_machine.execute_agent_command", _ok_receipt), patch(
                "riskmonitor_multiagent.orchestration.state_machine.ManagerAgent.decide", _manager_decide
            ), patch("riskmonitor_multiagent.orchestration.state_machine.RiskAnalystAgent.analyze", _analyst_analyze):
                out = _run_state_machine_sync(event.to_dict())

            ok = bool(out.get("ok") is True and isinstance(out.get("result"), dict) and out["result"].get("blocked") is True)
            return {"ok": ok, "state_machine": out}


def _case_token_budget_exceeded() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        with _TempEnv(
            {
                "CONTEXT_STORE_DIR": str(base / "ctx"),
                "ENABLE_LANGGRAPH": "1",
                "HITL_AUTO_APPROVE": "1",
                "CHROMA_PERSIST_DIR": str(base / "chroma"),
                "TOKEN_BUDGET": "0",
                "TOOL_BUDGET": "10",
                "TIME_BUDGET_MS": "15000",
            }
        ):
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

            now_ms = int(time.time() * 1000)
            source = normalize_cdc_event(
                raw_record={"desk": "Commodities", "delta": 60000.0},
                topic="risk.positions.cdc",
                partition=0,
                offset=1000,
                message_ts_ms=now_ms,
            )
            event = build_breach_event(source_event=source, desk="Commodities", exposure=60000.0, threshold=50000.0, now_ms=now_ms)

            with patch("riskmonitor_multiagent.orchestration.state_machine.execute_agent_command", _ok_receipt):
                out = _run_state_machine_sync(event.to_dict())
            result = out.get("result") if isinstance(out.get("result"), dict) else {}
            budget = result.get("budget") if isinstance(result.get("budget"), dict) else {}
            ok = bool(out.get("ok") is True and budget.get("exceeded") is True and budget.get("exceeded_type") == "token")
            return {"ok": ok, "state_machine": out}


def _case_tool_budget_exceeded() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        with _TempEnv(
            {
                "CONTEXT_STORE_DIR": str(base / "ctx"),
                "ENABLE_LANGGRAPH": "1",
                "HITL_AUTO_APPROVE": "1",
                "CHROMA_PERSIST_DIR": str(base / "chroma"),
                "TOKEN_BUDGET": "2000",
                "TOOL_BUDGET": "0",
                "TIME_BUDGET_MS": "15000",
            }
        ):
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

            now_ms = int(time.time() * 1000)
            source = normalize_cdc_event(
                raw_record={"desk": "Commodities", "delta": 60000.0},
                topic="risk.positions.cdc",
                partition=0,
                offset=1001,
                message_ts_ms=now_ms,
            )
            event = build_breach_event(source_event=source, desk="Commodities", exposure=60000.0, threshold=50000.0, now_ms=now_ms)
            with patch("riskmonitor_multiagent.orchestration.state_machine.execute_agent_command", _ok_receipt):
                out = _run_state_machine_sync(event.to_dict())
            result = out.get("result") if isinstance(out.get("result"), dict) else {}
            budget = result.get("budget") if isinstance(result.get("budget"), dict) else {}
            ok = bool(out.get("ok") is True and budget.get("exceeded") is True and budget.get("exceeded_type") == "tool")
            return {"ok": ok, "state_machine": out}


def _case_timeout_budget_exceeded() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        with _TempEnv(
            {
                "CONTEXT_STORE_DIR": str(base / "ctx"),
                "ENABLE_LANGGRAPH": "1",
                "HITL_AUTO_APPROVE": "1",
                "CHROMA_PERSIST_DIR": str(base / "chroma"),
                "TOKEN_BUDGET": "2000",
                "TOOL_BUDGET": "10",
                "TIME_BUDGET_MS": "0",
            }
        ):
            now_ms = int(time.time() * 1000)
            source = normalize_cdc_event(
                raw_record={"desk": "Commodities", "delta": 60000.0},
                topic="risk.positions.cdc",
                partition=0,
                offset=1002,
                message_ts_ms=now_ms,
            )
            event = build_breach_event(source_event=source, desk="Commodities", exposure=60000.0, threshold=50000.0, now_ms=now_ms)
            out = _run_state_machine_sync(event.to_dict())
            result = out.get("result") if isinstance(out.get("result"), dict) else {}
            budget = result.get("budget") if isinstance(result.get("budget"), dict) else {}
            ok = bool(out.get("ok") is True and budget.get("exceeded") is True and budget.get("exceeded_type") == "time")
            return {"ok": ok, "state_machine": out}

def _run_state_machine_sync(event: dict[str, Any]) -> dict[str, Any]:
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import threading

        out: dict[str, Any] = {}
        err: list[BaseException] = []

        def _runner():
            try:
                nonlocal out
                out = asyncio.run(run_state_machine(event=event))
            except BaseException as e:
                err.append(e)

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()
        if err:
            raise err[0]
        return out
    return asyncio.run(run_state_machine(event=event))


def _cases() -> list[RegressionCase]:
    return [
        RegressionCase(name="rbac_deny", fn=_case_rbac_deny),
        RegressionCase(name="approval_required", fn=_case_approval_required),
        RegressionCase(name="approval_reject", fn=_case_approval_reject),
        RegressionCase(name="token_budget_exceeded", fn=_case_token_budget_exceeded),
        RegressionCase(name="tool_budget_exceeded", fn=_case_tool_budget_exceeded),
        RegressionCase(name="timeout_budget_exceeded", fn=_case_timeout_budget_exceeded),
    ]


def run_governance_regression(*, output_file: str | None = None) -> dict[str, Any]:
    reset_observability_metrics()
    started_ms = int(time.time() * 1000)
    results: list[dict[str, Any]] = []
    for c in _cases():
        case_started = time.monotonic()
        try:
            out = c.fn()
            ok = bool(out.get("ok") is True)
            results.append(
                {
                    "name": c.name,
                    "ok": ok,
                    "latency_ms": float((time.monotonic() - case_started) * 1000.0),
                    "output": out,
                }
            )
        except Exception as e:
            results.append(
                {
                    "name": c.name,
                    "ok": False,
                    "latency_ms": float((time.monotonic() - case_started) * 1000.0),
                    "error": str(e),
                }
            )
    summary = {
        "schema_version": "governance_regression.v1",
        "started_ms": started_ms,
        "finished_ms": int(time.time() * 1000),
        "ok": all(r.get("ok") is True for r in results),
        "results": results,
        "metrics": render_prometheus_metrics(),
    }
    if output_file:
        path = Path(output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return summary
