import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from eval.gate import GateResult, evaluate_quality_gate, evaluate_with_custom_thresholds


def _build_summary() -> dict:
    return {
        "behavior_metrics": {
            "workflow_success": 1.0,
            "task_success_rate": 0.95,
            "tool_success_rate": 0.9,
            "tool_selection_accuracy": 1.0,
            "receipt_binding_rate": 1.0,
            "approval_correctness": 1.0,
            "replan_success_rate": 1.0,
            "replan_quality": 1.0,
            "memory_hit_rate": 0.2,
            "memory_usefulness": 0.2,
            "resume_success_rate": 1.0,
            "dangerous_action_block_rate": 1.0,
            "message_trace_completeness": 1.0,
            "factuality_score": 0.9,
            "evidence_coverage": 0.9,
            "tool_call_count": 5,
            "approval_count": 2,
            "replan_count": 1,
            "memory_hit_count": 1,
        },
        "metrics": {
            "efficiency": {"latency_ms": 1800, "token_count": 3500},
            "collaboration": {"information_diversity": 0.2, "role_specialization": 0.3},
        },
        "metric_definitions": {
            "task_success_rate": {"data_source": "run_trace.v2.final", "formula": "avg", "gate_rule": "blocking"},
        },
    }


class TestQualityGate:
    def test_passes_when_blocking_metrics_are_good(self) -> None:
        result = evaluate_quality_gate(_build_summary())
        assert result.passed is True
        assert result.reasons == []
        assert result.warnings
        assert result.metrics_summary["task_success_rate"] == 0.95
        assert any(item["severity"] == "warning" for item in result.decision_log)

    def test_blocks_on_real_behavior_failure(self) -> None:
        summary = _build_summary()
        summary["behavior_metrics"]["dangerous_action_block_rate"] = 0.4
        result = evaluate_quality_gate(summary)
        assert result.passed is False
        assert any("dangerous_action_block_rate" in reason for reason in result.reasons)

    def test_heuristic_warning_does_not_block(self) -> None:
        summary = _build_summary()
        summary["metrics"]["collaboration"]["information_diversity"] = 0.0
        result = evaluate_quality_gate(summary)
        assert result.passed is True
        assert any("information_diversity" in warning for warning in result.warnings)

    def test_custom_thresholds_override_defaults(self) -> None:
        summary = _build_summary()
        summary["behavior_metrics"]["factuality_score"] = 0.65
        result = evaluate_with_custom_thresholds(
            summary,
            {
                "blocking": {
                    "factuality_score": {"min": 0.6},
                },
                "warning": {},
            },
        )
        assert result.passed is True

    def test_empty_summary_returns_gate_result(self) -> None:
        result = evaluate_quality_gate({})
        assert isinstance(result, GateResult)
        assert isinstance(result.reasons, list)
        assert isinstance(result.decision_log, list)
