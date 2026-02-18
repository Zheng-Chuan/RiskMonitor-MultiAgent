from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from riskmonitor_multiagent.orchestration.state_machine import run_state_machine


@dataclass(frozen=True)
class ReplayVariant:
    name: str
    policy_version: str


_IGNORE_PATH_PREFIXES = (
    "run_id",
    "budget.started_ms",
    "budget.elapsed_ms",
    "receipts",
    "audit_records",
    "audit_db",
    "analyst.report",
    "engineer.reason",
    "manager.action",
    "manager.rationale",
)

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


def _should_ignore(path: str) -> bool:
    for p in _IGNORE_PATH_PREFIXES:
        if path == p or path.startswith(p + "."):
            return True
    return False


def _diff(a: Any, b: Any, path: str = "") -> List[Dict[str, Any]]:
    if _should_ignore(path):
        return []
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


def run_replay_compare(
    *,
    event: Dict[str, Any],
    a: ReplayVariant,
    b: ReplayVariant,
    output_file: Optional[str] = None,
) -> Dict[str, Any]:
    started_ms = int(time.time() * 1000)
    runs: List[Dict[str, Any]] = []
    for v in (a, b):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with _TempEnv(
                {
                    "CONTEXT_STORE_DIR": str(base / "ctx"),
                    "CHROMA_PERSIST_DIR": str(base / "chroma"),
                    "ENABLE_LANGGRAPH": "1",
                    "HITL_AUTO_APPROVE": "1",
                    "POLICY_VERSION": v.policy_version,
                    "TOKEN_BUDGET": os.getenv("TOKEN_BUDGET", "2000"),
                    "TOOL_BUDGET": os.getenv("TOOL_BUDGET", "10"),
                    "TIME_BUDGET_MS": os.getenv("TIME_BUDGET_MS", "15000"),
                }
            ):
                out = _run_state_machine_sync(dict(event))
                runs.append({"variant": v.name, "policy_version": v.policy_version, "output": out})
    a_out = runs[0]["output"].get("result") if isinstance(runs[0]["output"], dict) else None
    b_out = runs[1]["output"].get("result") if isinstance(runs[1]["output"], dict) else None
    diffs = _diff(a_out, b_out, "")
    report = {
        "schema_version": "replay_compare.v1",
        "started_ms": started_ms,
        "finished_ms": int(time.time() * 1000),
        "ok": True,
        "variants": [{"name": a.name, "policy_version": a.policy_version}, {"name": b.name, "policy_version": b.policy_version}],
        "diffs": diffs,
        "runs": runs,
    }
    if output_file:
        path = Path(output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report
