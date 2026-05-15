"""统一 run trace v2 聚合与 replay."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from riskmonitor_multiagent import config
from riskmonitor_multiagent.contracts.run_trace import RUN_TRACE_SCHEMA_VERSION, normalize_run_trace
from riskmonitor_multiagent.governance.versions import (
    PROMPT_VERSION_CRITIC,
    PROMPT_VERSION_INTENT,
    PROMPT_VERSION_MANAGER,
    PROMPT_VERSION_ORCHESTRATOR,
    PROMPT_VERSION_RISK_ANALYST,
    PROMPT_VERSION_SYSTEM_ENGINEER,
    get_policy_version,
)
from riskmonitor_multiagent.orchestration.tool_registry import TOOL_REGISTRY_VERSION
from riskmonitor_multiagent.utils.time import now_ms


@dataclass
class RunTraceSnapshot:
    """单次运行的统一 trace 快照."""

    run_id: str
    entry_type: str
    status: str
    task_id: str | None = None
    entries: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    version_snapshot: dict[str, Any] = field(default_factory=dict)
    failure_summary: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RUN_TRACE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return normalize_run_trace(
            {
                "schema_version": self.schema_version,
                "run_id": self.run_id,
                "entry_type": self.entry_type,
                "status": self.status,
                "task_id": self.task_id,
                "entries": self.entries,
                "summary": self.summary,
                "version_snapshot": self.version_snapshot,
                "failure_summary": self.failure_summary,
            }
        )


class RunTraceStore:
    """带磁盘持久化的 run trace 存储."""

    def __init__(self, *, base_dir: str | Path | None = None) -> None:
        self._traces: dict[str, RunTraceSnapshot] = {}
        self._base_dir = Path(base_dir or os.getenv("RUN_TRACE_DIR", "results/run_traces")).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, snapshot: RunTraceSnapshot) -> None:
        self._traces[snapshot.run_id] = snapshot
        self._write_snapshot(snapshot)

    def get_snapshot(self, run_id: str) -> RunTraceSnapshot | None:
        snapshot = self._traces.get(run_id)
        if snapshot is not None:
            return snapshot
        return self._read_snapshot(run_id)

    def render_replay(self, run_id: str) -> str:
        snapshot = self.get_snapshot(run_id)
        if snapshot is None:
            raise ValueError(f"unknown_run_trace:{run_id}")
        return render_trace_replay(snapshot)

    def render_replay_json(self, run_id: str) -> str:
        snapshot = self.get_snapshot(run_id)
        if snapshot is None:
            raise ValueError(f"unknown_run_trace:{run_id}")
        return json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def get_snapshot_path(self, run_id: str) -> Path:
        return self._base_dir / f"{run_id}.json"

    def _write_snapshot(self, snapshot: RunTraceSnapshot) -> None:
        path = self.get_snapshot_path(snapshot.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _read_snapshot(self, run_id: str) -> RunTraceSnapshot | None:
        path = self.get_snapshot_path(run_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshot = RunTraceSnapshot(
            run_id=str(payload.get("run_id") or run_id),
            entry_type=str(payload.get("entry_type") or ""),
            status=str(payload.get("status") or "unknown"),
            task_id=str(payload.get("task_id") or "") or None,
            entries=[dict(item) for item in payload.get("entries", []) if isinstance(item, dict)],
            summary=dict(payload.get("summary") or {}),
            version_snapshot=dict(payload.get("version_snapshot") or {}),
            failure_summary=dict(payload.get("failure_summary") or {}),
            schema_version=str(payload.get("schema_version") or RUN_TRACE_SCHEMA_VERSION),
        )
        self._traces[run_id] = snapshot
        return snapshot


def build_run_trace_snapshot(
    *,
    result: dict[str, Any],
    source_event: dict[str, Any] | None = None,
    related_events: list[dict[str, Any]] | None = None,
    related_event_trace: list[dict[str, Any]] | None = None,
) -> RunTraceSnapshot:
    """从 workflow 结果构建统一 run trace."""
    run_id = str(result.get("run_id") or "")
    entries: list[dict[str, Any]] = []
    run_context = result.get("run_context") if isinstance(result.get("run_context"), dict) else {}
    task_graph = result.get("task_graph") if isinstance(result.get("task_graph"), dict) else {}
    execution = result.get("task_graph_execution") if isinstance(result.get("task_graph_execution"), dict) else {}
    receipts = [dict(receipt) for receipt in result.get("receipts", []) or [] if isinstance(receipt, dict)]
    approval_trace = [dict(item) for item in result.get("approval_trace", []) or [] if isinstance(item, dict)]
    version_snapshot = _build_version_snapshot(result=result)
    dependency_index = _build_step_dependency_index(task_graph=task_graph)
    memory_entries = _build_memory_entries(result=result)
    failure_summary = _build_failure_summary(
        result=result,
        execution=execution,
        receipts=receipts,
        memory_entries=memory_entries,
    )

    entries.append(
        _entry(
            category="task",
            trace_type="task",
            timestamp_ms=now_ms(),
            summary={
                "entry_type": result.get("entry_type"),
                "task_id": result.get("task_id"),
                "trigger_event_id": run_context.get("trigger_event_id"),
            },
            payload={
                **run_context,
                "task_id": result.get("task_id"),
                "task_graph_schema_version": task_graph.get("schema_version"),
            },
        )
    )
    entries.append(
        _entry(
            category="version_snapshot",
            trace_type="version_snapshot",
            timestamp_ms=now_ms(),
            summary={
                "model": version_snapshot.get("model"),
                "policy_version": version_snapshot.get("policy_version"),
                "toolset_version": version_snapshot.get("toolset_version"),
            },
            payload=version_snapshot,
        )
    )

    if isinstance(source_event, dict) and source_event:
        entries.append(
            _entry(
                category="message",
                trace_type="source_event",
                timestamp_ms=int(source_event.get("timestamp_ms") or now_ms()),
                summary={
                    "event_id": source_event.get("event_id"),
                    "event_type": source_event.get("event_type"),
                    "source_agent": source_event.get("source_agent"),
                },
                payload=source_event,
            )
        )

    route_decision = result.get("route_decision") if isinstance(result.get("route_decision"), dict) else {}
    if route_decision:
        entries.append(
            _entry(
                category="message",
                trace_type="moderator_decision",
                timestamp_ms=int(route_decision.get("timestamp_ms") or now_ms()),
                summary={
                    "selected_agent": route_decision.get("selected_agent"),
                    "rule_name": route_decision.get("rule_name"),
                    "decision_source": route_decision.get("decision_source"),
                },
                payload=route_decision,
            )
        )

    intent = result.get("intent") if isinstance(result.get("intent"), dict) else {}
    if intent:
        entries.append(
            _entry(
                category="plan",
                trace_type="intent",
                timestamp_ms=now_ms(),
                summary={
                    "primary_intent_type": intent.get("primary_intent_type"),
                },
                payload=intent,
            )
        )

    orchestrator_plan = result.get("orchestrator_plan") if isinstance(result.get("orchestrator_plan"), dict) else {}
    if orchestrator_plan:
        entries.append(
            _entry(
                category="plan",
                trace_type="orchestrator_plan",
                timestamp_ms=now_ms(),
                summary={
                    "plan_steps": len(orchestrator_plan.get("plan_steps", []) or []),
                    "nodes": len(task_graph.get("nodes", []) or []),
                },
                payload=orchestrator_plan,
            )
        )

    critic_plan = result.get("critic_plan") if isinstance(result.get("critic_plan"), dict) else {}
    if critic_plan:
        entries.append(
            _entry(
                category="plan",
                trace_type="critic_plan",
                timestamp_ms=now_ms(),
                summary={
                    "ok": critic_plan.get("ok"),
                    "issues": len(critic_plan.get("issues", []) or []),
                },
                payload=critic_plan,
            )
        )

    replan_payload = result.get("replan") if isinstance(result.get("replan"), dict) else {}
    if replan_payload:
        phase = str(replan_payload.get("phase") or "")
        replan_trace_type = "runtime_replan" if "runtime" in phase else "replan"
        entries.append(
            _entry(
                category="plan",
                trace_type=replan_trace_type,
                timestamp_ms=now_ms(),
                status="recorded",
                summary={
                    "phase": phase or replan_trace_type,
                    "reason": replan_payload.get("reason"),
                    "has_task_graph": isinstance(replan_payload.get("task_graph"), dict),
                },
                payload=replan_payload,
            )
        )

    for item in execution.get("trace", []) or []:
        if not isinstance(item, dict):
            continue
        step_id = str(item.get("step_id") or "")
        related_receipts = _find_related_receipts(step_id=step_id, receipts=receipts)
        related_memories = _find_related_memories(step_id=step_id, memory_entries=memory_entries)
        entries.append(
            _entry(
                category="step",
                trace_type="task_graph_step",
                timestamp_ms=int(item.get("started_at_ms") or item.get("finished_at_ms") or now_ms()),
                status=str(item.get("status") or "recorded"),
                summary={
                    "step_id": step_id,
                    "kind": item.get("kind"),
                    "status": item.get("status"),
                    "failure_classification": item.get("failure_classification"),
                },
                payload={
                    **item,
                    "predecessors": dependency_index.get(step_id, {}).get("predecessors", []),
                    "successors": dependency_index.get(step_id, {}).get("successors", []),
                    "related_receipt_command_ids": [receipt.get("command_id") for receipt in related_receipts if receipt.get("command_id")],
                    "related_memory_ids": [memory.get("memory_id") for memory in related_memories if memory.get("memory_id")],
                },
            )
        )

    for receipt in receipts:
        command_summary = {
            "command_id": receipt.get("command_id"),
            "target_agent": receipt.get("target_agent"),
            "tool_name": receipt.get("tool_name"),
            "step_id": receipt.get("step_id"),
        }
        entries.append(
            _entry(
                category="command",
                trace_type="command",
                timestamp_ms=now_ms(),
                status=str(receipt.get("status") or "recorded"),
                summary=command_summary,
                payload={
                    "command_id": receipt.get("command_id"),
                    "target_agent": receipt.get("target_agent"),
                    "tool_name": receipt.get("tool_name"),
                    "step_id": receipt.get("step_id"),
                    "inputs": receipt.get("inputs"),
                    "expected_output_schema": receipt.get("output_schema"),
                },
            )
        )
        entries.append(
            _entry(
                category="receipt",
                trace_type="receipt",
                timestamp_ms=now_ms(),
                status=str(receipt.get("status") or "recorded"),
                summary={
                    "command_id": receipt.get("command_id"),
                    "tool_name": receipt.get("tool_name"),
                    "approval_state": receipt.get("approval_state"),
                },
                payload=receipt,
            )
        )

    for approval in approval_trace:
        entries.append(
            _entry(
                category="approval",
                trace_type="approval",
                timestamp_ms=now_ms(),
                status=str(approval.get("approval_state") or "recorded"),
                summary={
                    "approval_id": approval.get("approval_id"),
                    "level": approval.get("level"),
                    "step_id": approval.get("step_id"),
                    "command_id": approval.get("command_id"),
                    "approval_state": approval.get("approval_state"),
                },
                payload=approval,
            )
        )

    for memory_entry in memory_entries:
        entries.append(
            _entry(
                category="memory",
                trace_type=str(memory_entry.get("trace_type") or "memory"),
                timestamp_ms=int(memory_entry.get("timestamp_ms") or now_ms()),
                status="recorded",
                summary=dict(memory_entry.get("summary") or {}),
                payload=dict(memory_entry.get("payload") or {}),
            )
        )

    for event in related_events or []:
        if not isinstance(event, dict):
            continue
        entries.append(
            _entry(
                category="message",
                trace_type="event_history",
                timestamp_ms=int(event.get("timestamp_ms") or now_ms()),
                summary={
                    "event_id": event.get("event_id"),
                    "event_type": event.get("event_type"),
                },
                payload=event,
            )
        )

    for trace_item in related_event_trace or []:
        if not isinstance(trace_item, dict):
            continue
        entries.append(
            _entry(
                category="message",
                trace_type="event_trace",
                timestamp_ms=int(trace_item.get("timestamp_ms") or now_ms()),
                status=str(trace_item.get("status") or "recorded"),
                summary={
                    "event_id": trace_item.get("event_id"),
                    "event_type": trace_item.get("event_type"),
                    "subscriber_count": trace_item.get("subscriber_count"),
                },
                payload=trace_item,
            )
        )

    entries.append(
        _entry(
            category="final",
            trace_type="run_finished",
            timestamp_ms=now_ms(),
            status=str(result.get("status") or "completed"),
            summary={
                "status": result.get("status"),
                "latency_ms": result.get("latency_ms"),
                "tokens_total": result.get("tokens_total"),
            },
            payload={
                "final_output": result.get("final_output", {}),
                "errors": result.get("errors", []),
                "task_graph_execution": execution,
            },
        )
    )

    return RunTraceSnapshot(
        run_id=run_id,
        entry_type=str(result.get("entry_type") or ""),
        status=str(result.get("status") or "unknown"),
        task_id=str(result.get("task_id") or "") or None,
        entries=sorted(entries, key=lambda item: int(item.get("timestamp_ms") or 0)),
        summary={
            "entry_count": len(entries),
            "receipt_count": len(receipts),
            "approval_count": len(approval_trace),
            "memory_entry_count": len(memory_entries),
            "event_count": len(related_events or []),
            "trace_counts": _count_trace_categories(entries),
        },
        version_snapshot=version_snapshot,
        failure_summary=failure_summary,
    )


def get_run_trace_store() -> RunTraceStore:
    global _RUN_TRACE_STORE
    if _RUN_TRACE_STORE is None:
        _RUN_TRACE_STORE = RunTraceStore()
    return _RUN_TRACE_STORE


def reset_run_trace_store() -> None:
    global _RUN_TRACE_STORE
    _RUN_TRACE_STORE = None


def _entry(
    *,
    category: str,
    trace_type: str,
    timestamp_ms: int,
    summary: dict[str, Any],
    payload: dict[str, Any],
    status: str = "recorded",
) -> dict[str, Any]:
    return {
        "category": category,
        "trace_type": trace_type,
        "timestamp_ms": int(timestamp_ms),
        "status": status,
        "summary": dict(summary),
        "payload": dict(payload),
    }


def render_trace_replay(snapshot: RunTraceSnapshot) -> str:
    lines = [
        f"schema_version={snapshot.schema_version}",
        f"run_id={snapshot.run_id}",
        f"entry_type={snapshot.entry_type}",
        f"status={snapshot.status}",
        f"task_id={snapshot.task_id or ''}",
    ]
    if snapshot.version_snapshot:
        lines.append("version_snapshot:")
        lines.append(f"  model={snapshot.version_snapshot.get('model')}")
        lines.append(f"  policy_version={snapshot.version_snapshot.get('policy_version')}")
        lines.append(f"  toolset_version={snapshot.version_snapshot.get('toolset_version')}")
    if snapshot.failure_summary:
        lines.append("failure_summary:")
        lines.append(
            "  "
            + _compact_summary(
                {
                    "step_id": snapshot.failure_summary.get("step_id"),
                    "status": snapshot.failure_summary.get("status"),
                    "error": snapshot.failure_summary.get("error"),
                    "failure_classification": snapshot.failure_summary.get("failure_classification"),
                }
            )
        )
    lines.append("timeline:")
    for entry in sorted(snapshot.entries, key=lambda item: int(item.get("timestamp_ms") or 0)):
        lines.append(
            "  - "
            + f"{entry.get('category')}:{entry.get('trace_type')} "
            + f"ts={entry.get('timestamp_ms')} "
            + f"status={entry.get('status', 'recorded')} "
            + f"summary={_compact_summary(entry.get('summary', {}))}"
        )
    final_entry = next((entry for entry in reversed(snapshot.entries) if entry.get("category") == "final"), None)
    if isinstance(final_entry, dict):
        lines.append("final:")
        lines.append(f"  summary={_compact_summary(final_entry.get('summary', {}))}")
    return "\n".join(lines)


def _build_version_snapshot(*, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt_versions": {
            "intent": PROMPT_VERSION_INTENT,
            "orchestrator": PROMPT_VERSION_ORCHESTRATOR,
            "critic": PROMPT_VERSION_CRITIC,
            "system_engineer": PROMPT_VERSION_SYSTEM_ENGINEER,
            "risk_analyst": PROMPT_VERSION_RISK_ANALYST,
            "manager": PROMPT_VERSION_MANAGER,
        },
        "policy_version": get_policy_version(),
        "model": config.get_llm_model(),
        "toolset_version": TOOL_REGISTRY_VERSION,
        "benchmark_config": dict(result.get("benchmark_config") or {}),
    }


def _build_step_dependency_index(*, task_graph: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    nodes = task_graph.get("nodes", []) if isinstance(task_graph.get("nodes"), list) else []
    edges = task_graph.get("edges", []) if isinstance(task_graph.get("edges"), list) else []
    step_ids = [str(node.get("step_id") or "") for node in nodes if isinstance(node, dict) and node.get("step_id")]
    predecessors: dict[str, list[str]] = {step_id: [] for step_id in step_ids}
    successors: dict[str, list[str]] = {step_id: [] for step_id in step_ids}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        step_id = str(node.get("step_id") or "")
        parent_id = str(node.get("parent_id") or "")
        if step_id and parent_id and parent_id in predecessors:
            predecessors.setdefault(step_id, [])
            if parent_id not in predecessors[step_id]:
                predecessors[step_id].append(parent_id)
            successors.setdefault(parent_id, [])
            if step_id not in successors[parent_id]:
                successors[parent_id].append(step_id)
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        from_step_id = str(edge.get("from_step_id") or "")
        to_step_id = str(edge.get("to_step_id") or "")
        if from_step_id and to_step_id:
            predecessors.setdefault(to_step_id, [])
            if from_step_id not in predecessors[to_step_id]:
                predecessors[to_step_id].append(from_step_id)
            successors.setdefault(from_step_id, [])
            if to_step_id not in successors[from_step_id]:
                successors[from_step_id].append(to_step_id)
    return {
        step_id: {
            "predecessors": sorted(predecessors.get(step_id, [])),
            "successors": sorted(successors.get(step_id, [])),
        }
        for step_id in sorted(set(step_ids) | set(predecessors.keys()) | set(successors.keys()))
    }


def _build_memory_entries(*, result: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    planning_memory = result.get("planning_memory") if isinstance(result.get("planning_memory"), dict) else {}
    if planning_memory:
        entries.append(
            {
                "memory_id": "planning_memory",
                "trace_type": "planning_memory",
                "timestamp_ms": now_ms(),
                "summary": {"keys": sorted(planning_memory.keys())[:5]},
                "payload": planning_memory,
            }
        )
    for idx, hit in enumerate(result.get("memory_hits", []) or [], start=1):
        if not isinstance(hit, dict):
            continue
        entries.append(
            {
                "memory_id": str(hit.get("entry_id") or f"memory_hit_{idx}"),
                "trace_type": "memory_hit",
                "timestamp_ms": now_ms(),
                "summary": {
                    "kind": hit.get("kind"),
                    "memory_type": hit.get("memory_type"),
                    "run_id": hit.get("run_id"),
                },
                "payload": hit,
            }
        )
    for idx, hit in enumerate(result.get("resume_memory_state", []) or [], start=1):
        if not isinstance(hit, dict):
            continue
        entries.append(
            {
                "memory_id": str(hit.get("entry_id") or f"resume_memory_{idx}"),
                "trace_type": "resume_memory",
                "timestamp_ms": now_ms(),
                "summary": {
                    "kind": hit.get("kind"),
                    "memory_type": hit.get("memory_type"),
                    "run_id": hit.get("run_id"),
                },
                "payload": hit,
            }
        )
    shared_memory_board = result.get("shared_memory_board") if isinstance(result.get("shared_memory_board"), list) else []
    if shared_memory_board:
        entries.append(
            {
                "memory_id": "shared_memory_board",
                "trace_type": "shared_memory_board",
                "timestamp_ms": now_ms(),
                "summary": {"item_count": len(shared_memory_board)},
                "payload": {"items": shared_memory_board},
            }
        )
    private_memory_state = result.get("private_memory_state") if isinstance(result.get("private_memory_state"), dict) else {}
    for agent_id, items in private_memory_state.items():
        if not isinstance(items, list) or not items:
            continue
        entries.append(
            {
                "memory_id": f"private_memory:{agent_id}",
                "trace_type": "private_memory_state",
                "timestamp_ms": now_ms(),
                "summary": {"agent_id": agent_id, "item_count": len(items)},
                "payload": {
                    "agent_id": agent_id,
                    "items": items,
                },
            }
        )
    run_summary = result.get("run_summary") if isinstance(result.get("run_summary"), dict) else {}
    if run_summary:
        entries.append(
            {
                "memory_id": "run_summary",
                "trace_type": "run_summary",
                "timestamp_ms": now_ms(),
                "summary": {"keys": sorted(run_summary.keys())[:5]},
                "payload": run_summary,
            }
        )
    lesson = result.get("procedural_lesson") if isinstance(result.get("procedural_lesson"), dict) else {}
    if lesson:
        entries.append(
            {
                "memory_id": str(lesson.get("entry_id") or "procedural_lesson"),
                "trace_type": "procedural_lesson",
                "timestamp_ms": now_ms(),
                "summary": {"kind": lesson.get("kind"), "memory_type": lesson.get("memory_type")},
                "payload": lesson,
            }
        )
    long_term_experience = result.get("long_term_experience") if isinstance(result.get("long_term_experience"), dict) else {}
    if long_term_experience:
        entries.append(
            {
                "memory_id": str(long_term_experience.get("entry_id") or "long_term_experience"),
                "trace_type": "long_term_experience",
                "timestamp_ms": now_ms(),
                "summary": {"kind": long_term_experience.get("kind"), "memory_type": long_term_experience.get("memory_type")},
                "payload": long_term_experience,
            }
        )
    rejected_experience = result.get("rejected_experience") if isinstance(result.get("rejected_experience"), dict) else {}
    if rejected_experience:
        entries.append(
            {
                "memory_id": str(rejected_experience.get("entry_id") or "rejected_experience"),
                "trace_type": "rejected_experience",
                "timestamp_ms": now_ms(),
                "summary": {"kind": rejected_experience.get("kind"), "memory_type": rejected_experience.get("memory_type")},
                "payload": rejected_experience,
            }
        )
    memory_policy = result.get("memory_policy") if isinstance(result.get("memory_policy"), dict) else {}
    if memory_policy:
        entries.append(
            {
                "memory_id": "memory_policy",
                "trace_type": "memory_policy",
                "timestamp_ms": now_ms(),
                "summary": {"accepted": memory_policy.get("accepted"), "confidence": memory_policy.get("confidence")},
                "payload": memory_policy,
            }
        )
    for idx, item in enumerate(result.get("approval_memory", []) or [], start=1):
        if not isinstance(item, dict):
            continue
        entries.append(
            {
                "memory_id": str(item.get("entry_id") or f"approval_memory_{idx}"),
                "trace_type": "approval_memory",
                "timestamp_ms": now_ms(),
                "summary": {"entry_id": item.get("entry_id")},
                "payload": item,
            }
        )
    return entries


def _find_related_receipts(*, step_id: str, receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [receipt for receipt in receipts if str(receipt.get("step_id") or "") == step_id]


def _find_related_memories(*, step_id: str, memory_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    related: list[dict[str, Any]] = []
    for entry in memory_entries:
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        trace_ref = payload.get("trace_ref") if isinstance(payload.get("trace_ref"), dict) else {}
        approval_record = payload.get("approval_record") if isinstance(payload.get("approval_record"), dict) else {}
        if trace_ref.get("step_id") == step_id or approval_record.get("step_id") == step_id:
            related.append(entry)
    return related


def _build_failure_summary(
    *,
    result: dict[str, Any],
    execution: dict[str, Any],
    receipts: list[dict[str, Any]],
    memory_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    failed_step_id = execution.get("failed_step_id") or execution.get("blocked_step_id")
    trace_items = execution.get("trace", []) if isinstance(execution.get("trace"), list) else []
    failed_item = None
    for item in trace_items:
        if not isinstance(item, dict):
            continue
        if failed_step_id and item.get("step_id") == failed_step_id:
            failed_item = item
            break
        if item.get("status") in {"failed", "blocked"}:
            failed_item = item
            break
    if not isinstance(failed_item, dict):
        return {}
    step_id = str(failed_item.get("step_id") or "")
    related_receipts = _find_related_receipts(step_id=step_id, receipts=receipts)
    related_memories = _find_related_memories(step_id=step_id, memory_entries=memory_entries)
    return {
        "step_id": step_id,
        "status": failed_item.get("status"),
        "error": failed_item.get("error"),
        "failure_classification": failed_item.get("failure_classification"),
        "command_id": failed_item.get("command_id"),
        "related_receipt_command_ids": [receipt.get("command_id") for receipt in related_receipts if receipt.get("command_id")],
        "related_memory_ids": [memory.get("memory_id") for memory in related_memories if memory.get("memory_id")],
        "run_status": result.get("status"),
    }


def _count_trace_categories(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category") or "unknown")
        counts[category] = counts.get(category, 0) + 1
    return counts


def _compact_summary(summary: dict[str, Any]) -> str:
    parts = []
    for key, value in summary.items():
        if value is None:
            continue
        if value == "":
            continue
        if value == []:
            continue
        if value == {}:
            continue
        parts.append(f"{key}={value}")
    return ",".join(parts)


_RUN_TRACE_STORE: RunTraceStore | None = None


__all__ = [
    "RunTraceSnapshot",
    "RunTraceStore",
    "build_run_trace_snapshot",
    "get_run_trace_store",
    "render_trace_replay",
    "reset_run_trace_store",
]
