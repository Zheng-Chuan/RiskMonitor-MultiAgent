from __future__ import annotations

import json
from pathlib import Path

from riskmonitor_multiagent.cli.replay import main as replay_main
from riskmonitor_multiagent.cli.replay import replay_run
from riskmonitor_multiagent.observability.run_trace import (
    RunTraceSnapshot,
    build_run_trace_snapshot,
    get_run_trace_store,
    reset_run_trace_store,
)


def test_build_run_trace_snapshot_collects_unified_timeline() -> None:
    reset_run_trace_store()
    snapshot = build_run_trace_snapshot(
        result={
            "status": "completed",
            "run_id": "run_001",
            "entry_type": "system_event",
            "task_id": "task_001",
            "run_context": {"entry_type": "system_event", "trigger_event_id": "evt_001"},
            "benchmark_config": {"suite": "smoke"},
            "route_decision": {"selected_agent": "orchestrator", "rule_name": "task_created_priority"},
            "intent": {"primary_intent_type": "investigate"},
            "task_graph": {
                "schema_version": "task_graph.v1",
                "nodes": [{"step_id": "s1"}, {"step_id": "s2", "parent_id": "s1"}],
                "edges": [{"from_step_id": "s1", "to_step_id": "s2", "condition": "always"}],
            },
            "orchestrator_plan": {"plan_steps": [{"step_id": "s1"}]},
            "critic_plan": {"ok": True, "issues": []},
            "task_graph_execution": {
                "failed_step_id": "s2",
                "trace": [
                    {"step_id": "s1", "kind": "delegate", "status": "completed", "started_at_ms": 10, "finished_at_ms": 12},
                    {
                        "step_id": "s2",
                        "kind": "tool_call",
                        "status": "failed",
                        "started_at_ms": 20,
                        "finished_at_ms": 22,
                        "error": "tool_timeout",
                        "failure_classification": "timeout",
                        "command_id": "cmd_001",
                    },
                ]
            },
            "receipts": [{"command_id": "cmd_001", "tool_name": "query_alerts", "step_id": "s2", "status": "failed", "approval_state": "approved"}],
            "approval_trace": [
                {
                    "approval_id": "step:s2",
                    "level": "step",
                    "step_id": "s2",
                    "approval_state": "pending",
                    "required": True,
                    "reason": "需要人工确认",
                }
            ],
            "memory_hits": [{"entry_id": "mem-1", "kind": "analysis", "memory_type": "episodic"}],
            "planning_memory": {"summary": "memory"},
            "resume_memory_state": [{"entry_id": "mem-r1", "kind": "approval", "memory_type": "episodic"}],
            "shared_memory_board": [{"entry_id": "board-1", "agent_role": "risk_analyst"}],
            "private_memory_state": {"risk_analyst": [{"entry_id": "pm-1", "kind": "private_task_state"}]},
            "run_summary": {"summary": "done"},
            "procedural_lesson": {"memory_type": "procedural", "kind": "lesson"},
            "long_term_experience": {"entry_id": "exp-1", "memory_type": "semantic", "kind": "semantic_case"},
            "memory_policy": {"accepted": True, "confidence": 0.95},
            "approval_memory": [{"entry_id": "approval-1"}],
            "final_output": {"summary": "ok"},
            "errors": ["tool_timeout"],
            "latency_ms": 12.3,
            "tokens_total": 42,
        },
        source_event={"event_id": "evt_001", "event_type": "task_created", "source_agent": "monitor", "timestamp_ms": 1},
        related_events=[
            {"event_id": "evt_001", "event_type": "task_created", "timestamp_ms": 1},
            {"event_id": "evt_002", "event_type": "moderator_decision", "timestamp_ms": 2},
        ],
        related_event_trace=[
            {"event_id": "evt_001", "event_type": "task_created", "status": "accepted", "timestamp_ms": 1},
        ],
    )

    assert snapshot.run_id == "run_001"
    assert snapshot.entry_type == "system_event"
    assert snapshot.schema_version == "run_trace.v2"
    assert snapshot.version_snapshot.get("benchmark_config") == {"suite": "smoke"}
    assert snapshot.failure_summary.get("step_id") == "s2"
    assert snapshot.failure_summary.get("failure_classification") == "timeout"
    trace_types = [entry["trace_type"] for entry in snapshot.entries]
    categories = [entry["category"] for entry in snapshot.entries]
    assert "version_snapshot" in trace_types
    assert "source_event" in trace_types
    assert "moderator_decision" in trace_types
    assert "task_graph_step" in trace_types
    assert "command" in trace_types
    assert "receipt" in trace_types
    assert "approval" in trace_types
    assert "planning_memory" in trace_types
    assert "shared_memory_board" in trace_types
    assert "private_memory_state" in trace_types
    assert "long_term_experience" in trace_types
    assert "memory_policy" in trace_types
    assert "run_finished" in trace_types
    assert "step" in categories
    step_entry = next(entry for entry in snapshot.entries if entry["trace_type"] == "task_graph_step" and entry["payload"].get("step_id") == "s2")
    assert step_entry["payload"]["predecessors"] == ["s1"]
    assert step_entry["payload"]["related_receipt_command_ids"] == ["cmd_001"]


def test_replay_run_renders_timeline(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_TRACE_DIR", str(tmp_path / "run_traces"))
    reset_run_trace_store()
    store = get_run_trace_store()
    store.save_snapshot(
        RunTraceSnapshot(
            run_id="run_002",
            entry_type="user_task",
            status="completed",
            task_id="task_002",
            version_snapshot={"model": "demo-model", "policy_version": "policy.v1", "toolset_version": "tool_registry.v1"},
            failure_summary={},
            entries=[
                {"category": "plan", "trace_type": "intent", "timestamp_ms": 1, "status": "recorded", "summary": {"primary_intent_type": "analyze"}, "payload": {}},
                {"category": "final", "trace_type": "run_finished", "timestamp_ms": 2, "status": "completed", "summary": {"status": "completed"}, "payload": {}},
            ],
        )
    )

    output = replay_run("run_002")

    assert "run_id=run_002" in output
    assert "schema_version=run_trace.v2" in output
    assert "entry_type=user_task" in output
    assert "version_snapshot:" in output
    assert "timeline:" in output
    assert "intent" in output
    assert "run_finished" in output


def test_replay_run_supports_json_output(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_TRACE_DIR", str(tmp_path / "run_traces"))
    reset_run_trace_store()
    store = get_run_trace_store()
    store.save_snapshot(
        RunTraceSnapshot(
            run_id="run_003",
            entry_type="user_task",
            status="completed",
            task_id="task_003",
            version_snapshot={"model": "demo-model"},
            failure_summary={"step_id": "s2"},
            entries=[
                {"category": "task", "trace_type": "task", "timestamp_ms": 1, "status": "recorded", "summary": {}, "payload": {}},
                {"category": "final", "trace_type": "run_finished", "timestamp_ms": 2, "status": "completed", "summary": {"status": "completed"}, "payload": {}},
            ],
        )
    )

    output = replay_run("run_003", output_format="json")
    payload = json.loads(output)

    assert payload["schema_version"] == "run_trace.v2"
    assert payload["run_id"] == "run_003"
    assert payload["failure_summary"]["step_id"] == "s2"


def test_replay_run_can_reload_snapshot_from_disk(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_TRACE_DIR", str(tmp_path / "run_traces"))
    reset_run_trace_store()
    store = get_run_trace_store()
    store.save_snapshot(
        RunTraceSnapshot(
            run_id="run_disk_001",
            entry_type="user_task",
            status="completed",
            task_id="task_disk_001",
            entries=[
                {"category": "final", "trace_type": "run_finished", "timestamp_ms": 2, "status": "completed", "summary": {"status": "completed"}, "payload": {}},
            ],
        )
    )
    snapshot_path = store.get_snapshot_path("run_disk_001")
    assert Path(snapshot_path).exists()

    reset_run_trace_store()
    output = replay_run("run_disk_001", output_format="json")
    payload = json.loads(output)

    assert payload["run_id"] == "run_disk_001"
    assert payload["entries"][0]["trace_type"] == "run_finished"


def test_replay_cli_main_prints_output(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("RUN_TRACE_DIR", str(tmp_path / "run_traces"))
    reset_run_trace_store()
    store = get_run_trace_store()
    store.save_snapshot(
        RunTraceSnapshot(
            run_id="run_cli_001",
            entry_type="user_task",
            status="completed",
            task_id="task_cli_001",
            entries=[
                {"category": "final", "trace_type": "run_finished", "timestamp_ms": 2, "status": "completed", "summary": {"status": "completed"}, "payload": {}},
            ],
        )
    )

    exit_code = replay_main(["run_cli_001", "--format", "json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["run_id"] == "run_cli_001"
