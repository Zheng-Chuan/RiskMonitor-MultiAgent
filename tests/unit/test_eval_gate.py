import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
for p in (_PROJECT_ROOT, _SRC_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from eval.gate import evaluate_quality_gate


def test_quality_gate_passes_when_metrics_meet_thresholds():
    summary = {
        "aggregates": {
            # 传统指标
            "step_reason_coverage": 1.0,
            "evidence_missing_rate": 0.0,
            "receipt_binding_rate": 1.0,
            "contract_fail_rate": 0.0,
            "latency_ms_p95": 1000.0,
            "tokens_total": 1000,
            "stability_ok_rate": 1.0,
            # 协作/过程指标 (Collaboration & Process Metrics)
            "ids_avg": 0.5,  # > min_ids_avg (0.3)
            "upr_avg": 0.3,  # < max_upr_avg (0.5)
            "milestone_achieved_rate_avg": 0.8,  # > min_milestone (0.75)
            # 新增 Agent System Metrics
            "task_completion_score_avg": 0.8,  # > min (0.7)
            "hallucination_score_avg": 0.9,  # > min (0.8)
            "tool_call_success_rate_avg": 0.95,  # > min (0.9)
            "tool_efficiency_score_avg": 0.8,  # > min (0.7)
            "error_recovery_rate_avg": 0.9,  # > min (0.8)
            "plan_revision_count_avg": 0.5,  # < max (1.0)
            "memory_efficiency_score_avg": 0.7,  # > min (0.6)
        }
    }
    out = evaluate_quality_gate(summary)
    assert out.get("passed") is True
    assert out.get("reasons") == []


def test_quality_gate_blocks_on_evidence_missing():
    summary = {
        "aggregates": {
            "step_reason_coverage": 1.0,
            "evidence_missing_rate": 0.3,
            "receipt_binding_rate": 1.0,
            "contract_fail_rate": 0.0,
            "latency_ms_p95": 1000.0,
            "tokens_total": 1000,
            "stability_ok_rate": 1.0,
            # 新增指标也需满足阈值
            "task_completion_score_avg": 0.8,
            "hallucination_score_avg": 0.9,
            "tool_call_success_rate_avg": 0.95,
            "tool_efficiency_score_avg": 0.8,
            "error_recovery_rate_avg": 0.9,
            "plan_revision_count_avg": 0.5,
            "memory_efficiency_score_avg": 0.7,
        }
    }
    out = evaluate_quality_gate(summary)
    assert out.get("passed") is False
    assert "evidence_missing_rate_above_threshold" in (out.get("reasons") or [])


def test_quality_gate_blocks_on_new_agent_metrics():
    """测试新增 Agent System Metrics 的门禁检查."""
    summary = {
        "aggregates": {
            "step_reason_coverage": 1.0,
            "evidence_missing_rate": 0.0,
            "receipt_binding_rate": 1.0,
            "contract_fail_rate": 0.0,
            "latency_ms_p95": 1000.0,
            "tokens_total": 1000,
            "stability_ok_rate": 1.0,
            "ids_avg": 0.5,
            "upr_avg": 0.3,
            "milestone_achieved_rate_avg": 0.8,
            # 新增指标未达标
            "task_completion_score_avg": 0.5,  # < min (0.7)
            "hallucination_score_avg": 0.5,  # < min (0.8)
            "tool_call_success_rate_avg": 0.5,  # < min (0.9)
            "error_recovery_rate_avg": 0.5,  # < min (0.8)
            "plan_revision_count_avg": 2.0,  # > max (1.0)
            "memory_efficiency_score_avg": 0.5,  # < min (0.6)
        }
    }
    out = evaluate_quality_gate(summary)
    assert out.get("passed") is False
    reasons = out.get("reasons") or []
    assert "task_completion_score_avg_below_threshold" in reasons
    assert "hallucination_score_avg_below_threshold" in reasons
    assert "tool_call_success_rate_avg_below_threshold" in reasons
    assert "error_recovery_rate_avg_below_threshold" in reasons
    assert "plan_revision_count_avg_above_threshold" in reasons
    assert "memory_efficiency_score_avg_below_threshold" in reasons
