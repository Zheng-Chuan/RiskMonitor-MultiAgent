from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from riskmonitor_multiagent.contracts.agent_outputs import (
    validate_manager_output,
    validate_risk_analyst_output,
    validate_system_engineer_output,
)
from riskmonitor_multiagent.contracts.risk_event import validate_risk_event
from riskmonitor_multiagent.orchestration.state_machine import run_state_machine


@dataclass(frozen=True)
class QualityGateConfig:
    cases_file: str
    baseline_file: str
    write_baseline: bool = False
    disable_llm: bool = True


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


def _run_state_machine_sync(event: dict[str, Any]) -> dict[str, Any]:
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


def _load_cases(path: str) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError("bad_cases_file")
    out: list[dict[str, Any]] = []
    for c in data["cases"]:
        if not isinstance(c, dict):
            continue
        if not isinstance(c.get("case_id"), str) or not c["case_id"].strip():
            continue
        if not isinstance(c.get("event"), dict):
            continue
        out.append(c)
    return out


def _now_iso_utc() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _snapshot(final_output: dict[str, Any]) -> dict[str, Any]:
    manager = final_output.get("manager") if isinstance(final_output.get("manager"), dict) else {}
    evidence = manager.get("evidence") if isinstance(manager.get("evidence"), dict) else {}
    commands = manager.get("commands") if isinstance(manager.get("commands"), list) else []
    receipts = final_output.get("receipts") if isinstance(final_output.get("receipts"), list) else []

    engineer = final_output.get("engineer") if isinstance(final_output.get("engineer"), dict) else {}
    analyst = final_output.get("analyst") if isinstance(final_output.get("analyst"), dict) else {}
    approval = final_output.get("approval") if isinstance(final_output.get("approval"), dict) else {}

    return {
        "schema_version": "week15_snapshot.v1",
        "event_id": final_output.get("event_id"),
        "blocked": final_output.get("blocked"),
        "engineer": {
            "system_issue": engineer.get("system_issue"),
            "reason": engineer.get("reason"),
        },
        "analyst": {
            "key_facts": analyst.get("key_facts"),
            "confidence": analyst.get("confidence"),
        },
        "manager": {
            "decision": manager.get("decision"),
            "degraded": manager.get("degraded"),
            "degraded_reason": manager.get("degraded_reason"),
            "degraded_scope": manager.get("degraded_scope"),
            "command_actions": [c.get("action") for c in commands if isinstance(c, dict)],
            "evidence_has_fields": isinstance(evidence.get("fields"), list) and len(evidence.get("fields") or []) > 0,
            "evidence_has_receipts": isinstance(evidence.get("receipt_command_ids"), list) and len(evidence.get("receipt_command_ids") or []) > 0,
            "evidence_has_rag": isinstance(evidence.get("rag_hit_ids"), list) and len(evidence.get("rag_hit_ids") or []) > 0,
        },
        "approval": {
            "required": approval.get("required"),
            "approved": approval.get("approved"),
            "reason": approval.get("reason"),
        },
        "receipts": {
            "count": len([r for r in receipts if isinstance(r, dict)]),
            "ok_count": len([r for r in receipts if isinstance(r, dict) and r.get("ok") is True]),
        },
    }


def _diff(a: Any, b: Any, path: str = "") -> List[Dict[str, Any]]:
    if type(a) != type(b):
        return [{"path": path or "", "a": a, "b": b}]
    if isinstance(a, dict):
        diffs: List[Dict[str, Any]] = []
        keys = set(a.keys()) | set(b.keys())
        for k in sorted(keys):
            p = f"{path}.{k}" if path else str(k)
            diffs.extend(_diff(a.get(k), b.get(k), p))
        return diffs
    if isinstance(a, list):
        if len(a) != len(b):
            return [{"path": path, "a": f"len={len(a)}", "b": f"len={len(b)}"}]
        diffs: List[Dict[str, Any]] = []
        for i, (ai, bi) in enumerate(zip(a, b)):
            diffs.extend(_diff(ai, bi, f"{path}[{i}]"))
        return diffs
    if a != b:
        return [{"path": path, "a": a, "b": b}]
    return []


def _validate_contracts(final_output: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    engineer = final_output.get("engineer") if isinstance(final_output.get("engineer"), dict) else None
    if engineer is None:
        errors.append("missing_engineer")
    else:
        ok, e = validate_system_engineer_output(engineer)
        if not ok:
            errors.extend([f"engineer:{x}" for x in e])

    analyst = final_output.get("analyst") if isinstance(final_output.get("analyst"), dict) else None
    if analyst is None:
        errors.append("missing_analyst")
    else:
        ok, e = validate_risk_analyst_output(analyst)
        if not ok:
            errors.extend([f"analyst:{x}" for x in e])

    manager = final_output.get("manager") if isinstance(final_output.get("manager"), dict) else None
    if manager is None:
        errors.append("missing_manager")
    else:
        ok, e = validate_manager_output(manager)
        if not ok:
            errors.extend([f"manager:{x}" for x in e])

    return errors


def run_week15_quality_gate(*, config: QualityGateConfig) -> dict[str, Any]:
    started_ms = int(time.time() * 1000)
    cases = _load_cases(config.cases_file)
    baseline_path = Path(config.baseline_file)
    baseline: dict[str, Any] = {}
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    results: list[dict[str, Any]] = []
    ok_all = True

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        env_overrides = {
            "CONTEXT_STORE_DIR": str(base / "ctx"),
            "CHROMA_PERSIST_DIR": str(base / "chroma"),
            "ENABLE_LANGGRAPH": "1",
            "HITL_AUTO_APPROVE": "1",
        }
        if config.disable_llm:
            env_overrides["DISABLE_LLM"] = "1"

        with _TempEnv(env_overrides):
            for c in cases:
                case_id = str(c.get("case_id"))
                event = c.get("event") if isinstance(c.get("event"), dict) else {}
                event = dict(event)
                event["occurred_at"] = _now_iso_utc()
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else None
                if payload is not None and isinstance(payload.get("source_occurred_at"), str):
                    payload = dict(payload)
                    payload["source_occurred_at"] = event["occurred_at"]
                    event["payload"] = payload
                case_errors: list[str] = []
                ok_event, event_errors = validate_risk_event(event)
                if not ok_event:
                    case_errors.extend([f"event:{x}" for x in event_errors])
                out = _run_state_machine_sync(event)
                final_output = out.get("result") if isinstance(out, dict) else None
                if not isinstance(final_output, dict):
                    case_errors.append("missing_final_output")
                    final_output = {}
                case_errors.extend(_validate_contracts(final_output))
                snap = _snapshot(final_output)

                diffs: list[dict[str, Any]] = []
                expected = baseline.get(case_id) if isinstance(baseline, dict) else None
                if config.write_baseline:
                    pass
                else:
                    if not isinstance(expected, dict):
                        case_errors.append("missing_baseline")
                    else:
                        diffs = _diff(expected, snap)
                        if diffs:
                            case_errors.append("baseline_diff")

                case_ok = len(case_errors) == 0
                ok_all = ok_all and case_ok
                results.append({"case_id": case_id, "ok": case_ok, "errors": case_errors, "diffs": diffs, "snapshot": snap})

    report = {
        "schema_version": "week15_quality_gate_report.v1",
        "started_ms": started_ms,
        "finished_ms": int(time.time() * 1000),
        "ok": bool(ok_all),
        "cases_file": str(config.cases_file),
        "baseline_file": str(config.baseline_file),
        "write_baseline": bool(config.write_baseline),
        "disable_llm": bool(config.disable_llm),
        "results": results,
    }

    if config.write_baseline:
        baseline_out: dict[str, Any] = {}
        for r in results:
            baseline_out[r["case_id"]] = r["snapshot"]
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(baseline_out, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    return report
