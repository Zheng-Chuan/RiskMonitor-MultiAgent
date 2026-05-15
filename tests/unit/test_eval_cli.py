import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from eval import cli


def test_build_eval_task_disables_private_memory_for_private_disabled_baseline():
    built = cli._build_eval_task(
        {"task_id": "case-1", "category": "memory", "payload": {"content": "demo"}},
        baseline_mode="private_disabled",
        memory_enabled=True,
        benchmark_config={"baseline_mode": "private_disabled"},
    )

    assert built["memory_enabled"] is True
    assert built["private_memory_enabled"] is False
    assert built["baseline_mode"] == "private_disabled"
    assert built["benchmark_config"]["category"] == "memory"


def test_build_eval_task_normalizes_content_shape_for_workflow():
    built = cli._build_eval_task(
        {
            "category": "memory",
            "content": "参考上一次排查 lesson 继续分析本次延迟异常",
            "type": "analysis",
            "context": {"scenario": "lesson_reuse"},
        },
        baseline_mode="primary",
        memory_enabled=True,
        benchmark_config={"baseline_mode": "primary"},
    )

    assert built["payload"]["content"] == "参考上一次排查 lesson 继续分析本次延迟异常"
    assert built["payload"]["type"] == "analysis"
    assert built["payload"]["context"] == {"scenario": "lesson_reuse"}
    assert built["category"] == "memory"
    assert built["benchmark_config"]["category"] == "memory"
    assert built["task_id"].startswith("eval_")
    assert built["session_id"].startswith("eval_session:")


def test_bootstrap_eval_memory_adds_seed_for_memory_category():
    fake_store = type("FakeStore", (), {"append": AsyncMock(return_value={"entry_id": "seed-1"})})()

    with patch("riskmonitor_multiagent.memory.get_memory_store", return_value=fake_store):
        import asyncio

        asyncio.run(
            cli._bootstrap_eval_memory(
                {
                    "task_id": "case-1",
                    "category": "memory",
                    "memory_enabled": True,
                    "benchmark_config": {"category": "memory"},
                    "payload": {"content": "参考上一次排查 lesson 继续分析本次延迟异常"},
                }
            )
        )

    fake_store.append.assert_awaited_once()


def test_bootstrap_eval_memory_falls_back_to_top_level_content():
    fake_store = type("FakeStore", (), {"append": AsyncMock(return_value={"entry_id": "seed-2"})})()

    with patch("riskmonitor_multiagent.memory.get_memory_store", return_value=fake_store):
        import asyncio

        asyncio.run(
            cli._bootstrap_eval_memory(
                {
                    "task_id": "case-2",
                    "category": "memory",
                    "memory_enabled": True,
                    "benchmark_config": {"category": "memory"},
                    "content": "结合历史 lesson 继续分析本次异常",
                }
            )
        )

    appended = fake_store.append.await_args.args[0]
    assert "结合历史 lesson" in appended["content"]["text"]


def test_baseline_compare_prints_new_memory_metrics(tmp_path, capsys):
    primary = {
        "behavior_metrics": {
            "task_success_rate": 0.9,
            "tool_success_rate": 0.9,
            "tool_selection_accuracy": 0.9,
            "receipt_binding_rate": 0.9,
            "approval_correctness": 0.9,
            "replan_success_rate": 0.9,
            "memory_hit_rate": 0.8,
            "memory_usefulness": 0.7,
            "resume_success_rate": 0.6,
            "few_shot_reuse_rate": 0.5,
            "role_drift_rate": 0.1,
            "memory_cross_talk_rate": 0.0,
            "dangerous_action_block_rate": 1.0,
            "message_trace_completeness": 0.95,
            "factuality_score": 0.9,
            "evidence_coverage": 0.9,
        }
    }
    baseline = {
        "behavior_metrics": {
            "task_success_rate": 0.8,
            "tool_success_rate": 0.8,
            "tool_selection_accuracy": 0.8,
            "receipt_binding_rate": 0.8,
            "approval_correctness": 0.8,
            "replan_success_rate": 0.8,
            "memory_hit_rate": 0.2,
            "memory_usefulness": 0.1,
            "resume_success_rate": 0.3,
            "few_shot_reuse_rate": 0.0,
            "role_drift_rate": 0.4,
            "memory_cross_talk_rate": 0.3,
            "dangerous_action_block_rate": 1.0,
            "message_trace_completeness": 0.7,
            "factuality_score": 0.8,
            "evidence_coverage": 0.7,
        }
    }
    primary_path = tmp_path / "primary.json"
    baseline_path = tmp_path / "baseline.json"
    primary_path.write_text(json.dumps(primary, ensure_ascii=False), encoding="utf-8")
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

    args = type("Args", (), {"primary": str(primary_path), "baseline": str(baseline_path), "verbose": False})()
    assert cli.cmd_baseline_compare(args) == 0

    output = capsys.readouterr().out
    assert "few_shot_reuse_rate" in output
    assert "role_drift_rate" in output
    assert "memory_cross_talk_rate" in output
